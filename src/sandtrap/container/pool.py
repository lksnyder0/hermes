"""
Container pool manager for SandTrap.

This module manages a pool of pre-warmed Docker containers for fast SSH session
allocation. Containers are created on startup, allocated to sessions on demand,
and stopped (preserved) after session ends for forensics.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import docker
from docker.models.containers import Container

from sandtrap.config import ContainerPoolConfig
from sandtrap.container.security import build_container_config

logger = logging.getLogger(__name__)


class ContainerPool:
    """
    Manages a pool of pre-warmed Docker containers for SSH sessions.

    The pool maintains a set of ready containers, allocates them to sessions
    on demand, and spawns replacements in the background to keep the pool
    at target size.

    Lifecycle:
    1. Initialize pool with N ready containers at startup
    2. Allocate container to session on request (pop from ready pool)
    3. Spawn replacement container in background (non-blocking)
    4. Stop and track container when session ends
    5. Cleanup old stopped containers (future Phase 7)
    """

    def __init__(self, docker_client: docker.DockerClient, config: ContainerPoolConfig):
        """
        Initialize the container pool.

        Args:
            docker_client: Docker client instance
            config: Container pool configuration
        """
        self.docker_client = docker_client
        self.config = config

        # Pool state
        self.ready_pool: List[Container] = []
        self.active_sessions: Dict[str, Container] = {}
        self.stopped_containers: List[Tuple[Container, datetime]] = []

        # Synchronization and control
        self._lock = asyncio.Lock()
        self._shutdown = False

        logger.info(
            f"Container pool initialized (target size: {config.size}, image: {config.image})"
        )

    async def initialize(self) -> None:
        """
        Initialize the container pool by creating all ready containers.

        This creates pool_size containers in parallel and starts them.
        All containers must be created successfully or initialization fails.

        Raises:
            RuntimeError: If any container fails to create
        """
        logger.info(f"Initializing container pool with {self.config.size} containers...")
        start_time = datetime.utcnow()

        try:
            # Create containers in parallel for faster startup
            tasks = [self._create_container_sync() for _ in range(self.config.size)]
            containers = await asyncio.gather(*tasks)

            # Add all to ready pool
            async with self._lock:
                self.ready_pool.extend(containers)

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Container pool initialized successfully in {elapsed:.2f}s "
                f"({self.config.size} containers ready)"
            )

        except Exception as e:
            logger.error(f"Failed to initialize container pool: {e}", exc_info=True)
            # Cleanup any partially created containers
            await self._cleanup_ready_containers()
            raise RuntimeError(f"Container pool initialization failed: {e}") from e

    async def allocate(self, session_id: str) -> Container:
        """
        Allocate a container to a session.

        Pops a container from the ready pool and assigns it to the session.
        If pool is empty, creates a container on-demand. Spawns a replacement
        container in the background to maintain pool size.

        Args:
            session_id: Unique identifier for the session

        Returns:
            Docker container allocated to the session

        Raises:
            RuntimeError: If container allocation fails
        """
        async with self._lock:
            # Try to get container from ready pool
            if self.ready_pool:
                container = self.ready_pool.pop()
                logger.debug(f"Allocated container from pool: {container.id[:12]}")
            else:
                # Pool empty - create on demand (should be rare)
                logger.warning(f"Container pool empty! Creating on-demand for session {session_id}")
                try:
                    container = await self._create_container_sync()
                except Exception as e:
                    logger.error(f"Failed to create on-demand container: {e}", exc_info=True)
                    raise RuntimeError(f"Container allocation failed: {e}") from e

            # Update container labels with session ID
            try:
                container.reload()  # Refresh container info
                # Note: Can't modify labels on running container, just track in our state
            except Exception as e:
                logger.warning(f"Failed to reload container info: {e}")

            # Track in active sessions
            self.active_sessions[session_id] = container

        # Spawn replacement in background (non-blocking)
        asyncio.create_task(self._spawn_replacement())

        logger.info(
            f"Container {container.id[:12]} allocated to session {session_id} "
            f"(pool size: {len(self.ready_pool)}, active: {len(self.active_sessions)})"
        )

        return container

    async def release(self, session_id: str) -> None:
        """
        Release a container from a session.

        Stops the container (preserving disk state for forensics) and removes
        it from active sessions. The stopped container is tracked with a
        timestamp for future cleanup.

        Args:
            session_id: Session identifier to release

        Raises:
            KeyError: If session_id is not in active sessions
        """
        async with self._lock:
            if session_id not in self.active_sessions:
                logger.warning(f"Attempted to release unknown session: {session_id}")
                return

            container = self.active_sessions.pop(session_id)

        # Stop container (outside lock to prevent blocking)
        try:
            logger.debug(f"Stopping container {container.id[:12]} for session {session_id}")
            await asyncio.get_event_loop().run_in_executor(None, container.stop)

            # Track stopped container with timestamp
            async with self._lock:
                self.stopped_containers.append((container, datetime.utcnow()))

            logger.info(
                f"Container {container.id[:12]} released from session {session_id} "
                f"(stopped containers: {len(self.stopped_containers)})"
            )

        except Exception as e:
            logger.error(f"Failed to stop container {container.id[:12]}: {e}", exc_info=True)
            # Still remove from active sessions even if stop failed
            # Container will be in inconsistent state but won't block pool

    async def shutdown(self) -> None:
        """
        Shutdown the container pool.

        Stops all active and ready containers. Does not remove stopped
        containers (preserved for forensics).
        """
        logger.info("Shutting down container pool...")
        self._shutdown = True

        async with self._lock:
            # Stop all active containers
            for session_id, container in list(self.active_sessions.items()):
                try:
                    logger.debug(f"Stopping active container {container.id[:12]}")
                    await asyncio.get_event_loop().run_in_executor(None, container.stop)
                    self.stopped_containers.append((container, datetime.utcnow()))
                except Exception as e:
                    logger.error(f"Failed to stop container {container.id[:12]}: {e}")

            self.active_sessions.clear()

            # Stop all ready containers
            await self._cleanup_ready_containers()

        logger.info(
            f"Container pool shutdown complete "
            f"(stopped containers preserved: {len(self.stopped_containers)})"
        )

    async def _create_container_sync(self) -> Container:
        """
        Create and start a new container synchronously (for asyncio.gather).

        This is a wrapper around _create_container that runs the synchronous
        Docker operations in an executor.

        Returns:
            Started container

        Raises:
            RuntimeError: If container creation fails after retry
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_container)

    def _create_container(self) -> Container:
        """
        Create and start a new container (synchronous Docker operations).

        Builds container config, creates container via Docker API, and starts it.
        Implements retry logic with single retry on failure.

        Returns:
            Started container

        Raises:
            RuntimeError: If container creation fails after retry
        """
        name = self._generate_container_name()

        try:
            # Build container config with security constraints
            container_config = build_container_config(
                config=self.config.security,
                image=self.config.image,
                name=name,
            )

            logger.debug(f"Creating container: {name}")

            # Create container (doesn't start it yet)
            container = self.docker_client.containers.create(**container_config)

            # Start container
            container.start()

            logger.debug(f"Container created and started: {container.id[:12]} ({name})")
            return container

        except docker.errors.DockerException as e:
            logger.warning(f"Container creation failed, retrying: {e}")

            # Single retry with delay
            import time

            time.sleep(2)

            try:
                container = self.docker_client.containers.create(**container_config)
                container.start()
                logger.info(f"Container created successfully on retry: {container.id[:12]}")
                return container
            except docker.errors.DockerException as retry_error:
                logger.error(
                    f"Container creation failed after retry: {retry_error}",
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Failed to create container after retry: {retry_error}"
                ) from retry_error

    async def _spawn_replacement(self) -> None:
        """
        Spawn a replacement container in the background.

        This is a non-blocking task that adds a container to the ready pool
        to maintain target pool size. Errors are logged but not raised.
        """
        if self._shutdown:
            return

        try:
            container = await self._create_container_sync()

            async with self._lock:
                if not self._shutdown:
                    self.ready_pool.append(container)
                    logger.debug(
                        f"Replacement container spawned: {container.id[:12]} "
                        f"(pool size: {len(self.ready_pool)})"
                    )
                else:
                    # Shutdown during spawn - stop the container
                    await asyncio.get_event_loop().run_in_executor(None, container.stop, 10)

        except Exception as e:
            logger.error(f"Failed to spawn replacement container: {e}", exc_info=True)
            # Don't raise - this is a background task

    def _generate_container_name(self, session_id: Optional[str] = None) -> str:
        """
        Generate a unique container name.

        Format: sandtrap-target-{id}-{timestamp}
        Where id is first 8 chars of session_id or random UUID

        Args:
            session_id: Optional session ID to include in name

        Returns:
            Unique container name
        """
        if session_id:
            id_part = session_id[:8]
        else:
            id_part = str(uuid.uuid4())[:8]

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"sandtrap-target-{id_part}-{timestamp}"

    async def _cleanup_ready_containers(self) -> None:
        """
        Cleanup all containers in the ready pool.

        Stops all ready containers and moves them to stopped_containers list.
        Called during shutdown.
        """
        for container in self.ready_pool:
            try:
                logger.debug(f"Stopping ready container {container.id[:12]}")
                await asyncio.get_event_loop().run_in_executor(None, container.stop)
                self.stopped_containers.append((container, datetime.utcnow()))
            except Exception as e:
                logger.error(f"Failed to stop container {container.id[:12]}: {e}")

        self.ready_pool.clear()

    def get_stats(self) -> Dict[str, int]:
        """
        Get current pool statistics.

        Returns:
            Dictionary with pool stats (ready, active, stopped counts)
        """
        return {
            "ready": len(self.ready_pool),
            "active": len(self.active_sessions),
            "stopped": len(self.stopped_containers),
            "total": len(self.ready_pool)
            + len(self.active_sessions)
            + len(self.stopped_containers),
        }

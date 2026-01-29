"""
SandTrap entry point.

This module provides the main() function that starts the SSH honeypot server.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import docker

from sandtrap import __version__
from sandtrap.config import Config
from sandtrap.container.pool import ContainerPool
from sandtrap.server.asyncssh_backend import AsyncSSHBackend
from sandtrap.server.backend import PTYRequest, SessionInfo
from sandtrap.session.proxy import ContainerProxy
from sandtrap.session.recorder import SessionRecorder


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="SandTrap - SSH Honeypot with Docker Container Sandboxing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"SandTrap {__version__}",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config/config.yaml"),
        help="Path to configuration file (default: config/config.yaml)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    parser.add_argument(
        "--generate-keys",
        action="store_true",
        help="Generate SSH host keys and exit",
    )

    return parser.parse_args()


async def container_session_handler(
    session_info: SessionInfo,
    pty_request: PTYRequest,
    process: object,
    container_pool: ContainerPool,
    recording_config=None,
) -> None:
    """
    Handle SSH session by proxying to Docker container.

    Lifecycle:
    1. Allocate container from pool
    2. Create SessionRecorder (if enabled)
    3. Create ContainerProxy with recorder
    4. Start proxy (creates exec and I/O tasks)
    5. Wait for proxy to complete
    6. Release container back to pool

    Args:
        session_info: Session metadata
        pty_request: PTY configuration
        process: asyncssh.SSHServerProcess with stdin/stdout/stderr
        container_pool: Container pool manager
        recording_config: Optional RecordingConfig for session recording
    """
    logger = logging.getLogger(__name__)
    logger.info(f"container_session_handler called for session {session_info.session_id}")
    container = None
    proxy = None
    recorder = None

    try:
        # Step 1: Allocate container
        logger.info(f"Allocating container for session {session_info.session_id}")
        container = await container_pool.allocate(session_info.session_id)

        # Step 2: Create recorder
        if recording_config:
            recorder = SessionRecorder(
                config=recording_config,
                session_id=session_info.session_id,
                width=pty_request.width,
                height=pty_request.height,
                metadata={
                    "username": session_info.username,
                    "source_ip": session_info.source_ip,
                    "source_port": session_info.source_port,
                    "container_id": container.id[:12],
                },
            )
            recorder.start()

        # Step 3: Create proxy
        proxy = ContainerProxy(
            container=container,
            pty_request=pty_request,
            process=process,
            session_id=session_info.session_id,
            recorder=recorder,
        )

        # Step 4: Start proxy
        await proxy.start()

        # Step 5: Wait for completion
        await proxy.wait_completion()

    except RuntimeError as e:
        # Container allocation or exec creation failed
        logger.error(f"Session setup failed for {session_info.session_id}: {e}")
        try:
            error_msg = b"\r\nContainer allocation failed. Please try again later.\r\n"
            process.stdout.write(error_msg)
        except Exception:
            pass  # Session may already be closed

    except Exception as e:
        # Unexpected error
        logger.exception(f"Session error for {session_info.session_id}: {e}")

    finally:
        # Step 6: Clean up
        if proxy:
            await proxy.stop()

        if recorder:
            recorder.stop()
            recorder.write_metadata()

        if container:
            logger.info(f"Releasing container for session {session_info.session_id}")
            await container_pool.release(session_info.session_id)


async def async_main(config_path: Path) -> int:
    """
    Asynchronous main function.

    Args:
        config_path: Path to configuration file

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)
    ssh_backend = None
    container_pool = None
    docker_client = None

    try:
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        config = Config.from_file(config_path)

        logger.info("SandTrap starting...")
        logger.info(f"SSH Server: {config.server.host}:{config.server.port}")
        logger.info(f"Host Key: {config.server.host_key_path}")
        logger.info(f"Container pool size: {config.container_pool.size}")
        logger.info(f"Max concurrent sessions: {config.server.max_concurrent_sessions}")

        # Initialize Docker client
        logger.info("Connecting to Docker...")
        if config.docker.base_url:
            docker_client = docker.DockerClient(base_url=config.docker.base_url)
        else:
            docker_client = docker.from_env()

        # Verify Docker connection
        docker_version = docker_client.version()
        logger.info(f"Connected to Docker {docker_version.get('Version', 'unknown')}")

        # Initialize container pool
        logger.info("Initializing container pool...")
        container_pool = ContainerPool(docker_client, config.container_pool)
        await container_pool.initialize()
        logger.info(f"Container pool ready with {config.container_pool.size} containers")

        # Initialize SSH backend
        logger.info("Initializing SSH backend...")
        ssh_backend = AsyncSSHBackend(config)

        # Register container pool with SSH backend
        ssh_backend.set_container_pool(container_pool)

        # Set session handler with container pool closure
        async def session_handler_with_pool(
            session_info: SessionInfo,
            pty_request: PTYRequest,
            process: object,
        ) -> None:
            await container_session_handler(
                session_info, pty_request, process, container_pool, config.recording
            )

        ssh_backend.set_session_handler(session_handler_with_pool)

        # Start SSH server
        logger.info("Starting SSH server...")
        await ssh_backend.start()

        logger.info("SandTrap is running! Press Ctrl+C to stop.")

        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1
    except docker.errors.DockerException as e:
        logger.error(f"Docker error: {e}")
        logger.error("Make sure Docker is running and accessible")
        return 1
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        # Clean shutdown
        if ssh_backend:
            logger.info("Shutting down SSH server...")
            await ssh_backend.stop()

        if container_pool:
            logger.info("Shutting down container pool...")
            await container_pool.shutdown()

        if docker_client:
            logger.info("Closing Docker connection...")
            docker_client.close()

        logger.info("Shutdown complete")


def main() -> int:
    """
    Main entry point for SandTrap.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info(f"SandTrap v{__version__}")

    # Handle special commands
    if args.generate_keys:
        logger.info("Generating SSH host keys...")
        # TODO: Implement key generation
        logger.error("Key generation not yet implemented")
        return 1

    # Run async main
    try:
        return asyncio.run(async_main(args.config))
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Container I/O proxy for Hermes sessions.

Manages bidirectional streaming between SSH sessions and Docker exec.
"""

import asyncio
import logging
from typing import Optional

from docker.models.containers import Container

from hermes.server.backend import PTYRequest

logger = logging.getLogger(__name__)


class ContainerProxy:
    """
    Proxies I/O between SSH session and Docker container exec.

    Manages the lifecycle of a Docker exec instance and coordinates
    bidirectional streaming of stdin/stdout between the SSH client
    and the container.

    Architecture:
    - Creates Docker exec with PTY in target container
    - Spawns two concurrent tasks for bidirectional streaming
    - Handles graceful shutdown on either side disconnecting
    """

    def __init__(
        self,
        container: Container,
        pty_request: PTYRequest,
        process: object,  # asyncssh.SSHServerProcess (avoiding circular import)
        session_id: str,
        recorder: object = None,  # Optional SessionRecorder
    ):
        """
        Initialize the container proxy.

        Args:
            container: Docker container (already allocated from pool)
            pty_request: PTY configuration from SSH client
            process: SSHServerProcess with stdin/stdout/stderr streams
            session_id: Unique session identifier for logging
            recorder: Optional SessionRecorder for asciicast v2 recording
        """
        self.container = container
        self.pty_request = pty_request
        self.process = process
        self.session_id = session_id
        self.recorder = recorder

        self.exec_socket: Optional[object] = None
        self.ssh_to_container_task: Optional[asyncio.Task] = None
        self.container_to_ssh_task: Optional[asyncio.Task] = None

        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """
        Start the container exec and I/O proxy.

        Creates a Docker exec instance with PTY and spawns two tasks
        for bidirectional streaming:
        1. SSH stdin → Container exec socket
        2. Container exec socket → SSH stdout

        Raises:
            RuntimeError: If exec creation fails
        """
        logger.info(
            f"Starting container proxy for session {self.session_id} "
            f"(container: {self.container.id[:12]})"
        )

        try:
            # Create Docker exec with PTY
            exec_result = self.container.exec_run(
                cmd="/bin/bash",
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
                socket=True,  # Returns raw socket for streaming
                user="root",
                workdir="/root",
                environment={
                    "TERM": self.pty_request.term_type,
                    "COLUMNS": str(self.pty_request.width),
                    "LINES": str(self.pty_request.height),
                },
            )

            # exec_result.output is a SocketIO wrapper when socket=True;
            # extract the underlying raw socket for asyncio compatibility.
            sock_io = exec_result.output
            self.exec_socket = sock_io._sock if hasattr(sock_io, '_sock') else sock_io

            # Set socket to non-blocking mode for asyncio
            self.exec_socket.setblocking(False)

            logger.debug(
                f"Docker exec created for session {self.session_id} "
                f"(term: {self.pty_request.term_type}, "
                f"size: {self.pty_request.width}x{self.pty_request.height})"
            )

        except Exception as e:
            logger.error(
                f"Failed to create Docker exec for session {self.session_id}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Docker exec creation failed: {e}") from e

        # Start bidirectional streaming tasks
        self._running = True
        self.ssh_to_container_task = asyncio.create_task(self._ssh_to_container())
        self.container_to_ssh_task = asyncio.create_task(self._container_to_ssh())

        logger.info(f"Container proxy started for session {self.session_id}")

    async def _ssh_to_container(self) -> None:
        """
        Forward data from SSH stdin to container exec socket.

        Runs until:
        - SSH connection closes (stdin returns empty)
        - Error occurs
        - Shutdown event is set
        """
        logger.debug(f"SSH→Container task started (session: {self.session_id})")
        loop = asyncio.get_event_loop()

        try:
            while self._running:
                # Read from SSH stdin
                data = await self.process.stdin.read(4096)

                if not data:
                    # SSH client disconnected
                    logger.info(f"SSH client disconnected (session: {self.session_id})")
                    break

                if self.recorder:
                    self.recorder.record_input(data)

                # Write to container exec socket
                try:
                    await loop.sock_sendall(self.exec_socket, data)
                except BlockingIOError:
                    # Retry after small delay
                    await asyncio.sleep(0.01)
                    await loop.sock_sendall(self.exec_socket, data)

        except ConnectionResetError:
            logger.info(f"SSH connection reset (session: {self.session_id})")
        except BrokenPipeError:
            logger.info(f"Container exec closed (session: {self.session_id})")
        except Exception as e:
            logger.error(
                f"Error in SSH→Container forwarding (session: {self.session_id}): {e}",
                exc_info=True,
            )
        finally:
            self._shutdown_event.set()
            logger.debug(f"SSH→Container task ended (session: {self.session_id})")

    async def _container_to_ssh(self) -> None:
        """
        Forward data from container exec socket to SSH stdout.

        Runs until:
        - Container exec ends (socket returns empty)
        - Error occurs
        - Shutdown event is set
        """
        logger.debug(f"Container→SSH task started (session: {self.session_id})")
        loop = asyncio.get_event_loop()

        try:
            while self._running:
                # Read from container exec socket
                try:
                    data = await loop.sock_recv(self.exec_socket, 4096)
                except BlockingIOError:
                    # No data available, retry after small delay
                    await asyncio.sleep(0.01)
                    continue

                if not data:
                    # Container exec ended
                    logger.info(f"Container exec ended (session: {self.session_id})")
                    break

                if self.recorder:
                    self.recorder.record_output(data)

                # Write to SSH stdout
                self.process.stdout.write(data)
                await self.process.stdout.drain()

        except ConnectionResetError:
            logger.info(f"Container connection reset (session: {self.session_id})")
        except BrokenPipeError:
            logger.info(f"SSH client disconnected (session: {self.session_id})")
        except Exception as e:
            logger.error(
                f"Error in Container→SSH forwarding (session: {self.session_id}): {e}",
                exc_info=True,
            )
        finally:
            self._shutdown_event.set()
            logger.debug(f"Container→SSH task ended (session: {self.session_id})")

    async def handle_resize(self, width: int, height: int) -> None:
        """
        Handle terminal resize event.

        Args:
            width: New terminal width in characters
            height: New terminal height in characters

        Note:
            Phase 4 implementation: Log only. Docker exec doesn't support
            dynamic resize without complex workarounds (SIGWINCH forwarding).
            Most use cases work fine with initial terminal size.
        """
        logger.debug(
            f"Terminal resize to {width}x{height} (session: {self.session_id}) - "
            f"not forwarded to container (known limitation)"
        )
        if self.recorder:
            self.recorder.record_resize(width, height)

    async def wait_completion(self) -> None:
        """
        Wait for proxy to complete.

        Returns when either I/O task exits or shutdown event is set.
        """
        # Wait for shutdown event
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """
        Stop the proxy and clean up resources.

        Cancels I/O tasks and closes the exec socket.
        """
        if not self._running:
            return

        logger.info(f"Stopping container proxy (session: {self.session_id})")
        self._running = False

        # Cancel tasks if still running
        if self.ssh_to_container_task and not self.ssh_to_container_task.done():
            self.ssh_to_container_task.cancel()
            try:
                await self.ssh_to_container_task
            except asyncio.CancelledError:
                pass

        if self.container_to_ssh_task and not self.container_to_ssh_task.done():
            self.container_to_ssh_task.cancel()
            try:
                await self.container_to_ssh_task
            except asyncio.CancelledError:
                pass

        # Close exec socket
        if self.exec_socket:
            try:
                self.exec_socket.close()
            except Exception as e:
                logger.warning(f"Error closing exec socket (session: {self.session_id}): {e}")

        logger.info(f"Container proxy stopped (session: {self.session_id})")

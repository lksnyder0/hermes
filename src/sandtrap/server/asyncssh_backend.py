"""
AsyncSSH backend implementation for SandTrap.

This module implements the SSH server using the asyncssh library.
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import asyncssh

from sandtrap.config import Config
from sandtrap.server.auth import AuthenticationManager
from sandtrap.server.backend import PTYRequest, SSHBackend, SessionInfo

logger = logging.getLogger(__name__)


class SandTrapSSHServer(asyncssh.SSHServer):
    """
    AsyncSSH server implementation for SandTrap.

    Handles connection establishment, authentication, and session setup.
    """

    def __init__(
        self,
        auth_manager: AuthenticationManager,
        session_handler: Optional[Callable] = None,
        backend=None,
    ):
        """
        Initialize the SSH server.

        Args:
            auth_manager: Authentication manager instance
            session_handler: Callback for handling sessions
            backend: Reference to the backend for session info storage
        """
        self.auth_manager = auth_manager
        self.session_handler = session_handler
        self._backend = backend
        self.connection_id: Optional[str] = None
        self.session_info: Optional[SessionInfo] = None
        self.conn: Optional[asyncssh.SSHServerConnection] = None

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        """
        Called when a new connection is established.

        Args:
            conn: SSH server connection
        """
        self.connection_id = str(uuid.uuid4())
        self.conn = conn  # Store connection reference
        peername = conn.get_extra_info("peername")
        source_ip = peername[0] if peername else "unknown"
        source_port = peername[1] if peername else 0

        self.session_info = SessionInfo(
            session_id=self.connection_id,
            username="",
            source_ip=source_ip,
            source_port=source_port,
            authenticated=False,
            failed_attempts=0,
        )

        # Store session info in backend for session factory access
        if self._backend:
            self._backend._session_info_map[self.connection_id] = self.session_info

        logger.info(
            f"New SSH connection from {source_ip}:{source_port} "
            f"(connection_id: {self.connection_id})"
        )

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """
        Called when connection is closed.

        Args:
            exc: Exception that caused disconnection, if any
        """
        if self.connection_id:
            logger.info(
                f"Connection closed: {self.connection_id} "
                f"({'error: ' + str(exc) if exc else 'normal'})"
            )
            self.auth_manager.cleanup_connection(self.connection_id)

    def password_auth_supported(self) -> bool:
        """Indicate that password authentication is supported."""
        return True

    def begin_auth(self, username: str) -> bool:
        """
        Begin authentication for a user.

        Args:
            username: Username attempting to authenticate

        Returns:
            True to continue with authentication
        """
        if self.session_info:
            self.session_info.username = username
        logger.debug(f"Begin auth for user: {username} (connection: {self.connection_id})")
        return True

    def validate_password(self, username: str, password: str) -> bool:
        """
        Validate password for a user.

        Args:
            username: Username attempting to authenticate
            password: Password provided

        Returns:
            True if authentication successful, False otherwise
        """
        if not self.connection_id:
            logger.error("validate_password called without connection_id")
            return False

        result = self.auth_manager.validate(self.connection_id, username, password)

        if self.session_info:
            if result:
                self.session_info.authenticated = True
            else:
                self.session_info.failed_attempts += 1

        return result


class AsyncSSHBackend(SSHBackend):
    """
    AsyncSSH-based SSH backend implementation.

    Uses the asyncssh library to provide SSH server functionality.
    """

    def __init__(self, config: Config):
        """
        Initialize the AsyncSSH backend.

        Args:
            config: SandTrap configuration
        """
        super().__init__(config)
        self.auth_manager = AuthenticationManager(config.authentication)
        self.session_handler: Optional[Callable] = None
        self.container_pool = None  # Will be set by set_container_pool()
        self._server: Optional[asyncssh.SSHListener] = None
        self._session_info_map: Dict[str, SessionInfo] = {}  # Store session info by connection

        logger.info("AsyncSSH backend initialized")

    async def start(self) -> None:
        """
        Start the SSH server.

        Raises:
            RuntimeError: If server fails to start
        """
        host = self.config.server.host
        port = self.config.server.port
        host_key_path = self.config.server.host_key_path

        # Check if host key exists
        if not host_key_path.exists():
            raise RuntimeError(
                f"SSH host key not found: {host_key_path}\n"
                f"Generate one with: ssh-keygen -t rsa -f {host_key_path} -N ''"
            )

        logger.info(f"Starting SSH server on {host}:{port}")
        logger.info(f"Using host key: {host_key_path}")

        try:
            self._server = await asyncssh.listen(
                host=host,
                port=port,
                server_host_keys=[str(host_key_path)],
                server_factory=lambda: SandTrapSSHServer(
                    self.auth_manager, self.session_handler, self
                ),
                process_factory=self._process_factory,
                encoding=None,  # Handle binary data
            )

            logger.info(f"SSH server started successfully on {host}:{port}")

        except Exception as e:
            logger.error(f"Failed to start SSH server: {e}", exc_info=True)
            raise RuntimeError(f"Failed to start SSH server: {e}") from e

    async def stop(self) -> None:
        """Stop the SSH server."""
        if self._server:
            logger.info("Stopping SSH server")
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("SSH server stopped")

    def set_session_handler(self, handler: Callable[[SessionInfo, PTYRequest, Any], Any]) -> None:
        """
        Set the callback function for handling SSH sessions.

        Args:
            handler: Async function to handle new sessions
        """
        self.session_handler = handler
        logger.info("Session handler registered")

    def set_container_pool(self, pool) -> None:
        """
        Set the container pool for session handling.

        Args:
            pool: ContainerPool instance
        """
        self.container_pool = pool
        logger.info("Container pool registered with SSH backend")

    async def authenticate(self, session_info: SessionInfo, username: str, password: str) -> bool:
        """
        Authenticate a user (not used directly in this implementation).

        Authentication happens in the SandTrapSSHServer.validate_password method.

        Args:
            session_info: Current session information
            username: Username attempting to authenticate
            password: Password provided

        Returns:
            True if authentication successful, False otherwise
        """
        return self.auth_manager.validate(session_info.session_id, username, password)

    async def _process_factory(self, process: asyncssh.SSHServerProcess) -> None:
        """
        Factory function invoked for each new SSH session.

        Extracts PTY info and session metadata from the process object,
        then delegates to the registered session handler.

        Args:
            process: SSHServerProcess with stdin/stdout/stderr streams
        """
        # Look up session info via the connection
        conn = process.channel.get_connection()
        if not conn:
            logger.error("No connection available in process factory")
            process.exit(1)
            return

        # Find session info from our map
        if not self._session_info_map:
            logger.error("No session info available in map")
            process.exit(1)
            return

        # Match by connection - use the most recent entry
        # (session_factory/process_factory is called right after connection_made)
        session_info = list(self._session_info_map.values())[-1]

        # Extract PTY info from the process
        term_type = process.get_terminal_type() or "xterm"
        term_size = process.get_terminal_size()
        width = term_size[0] if term_size else 80
        height = term_size[1] if term_size else 24
        pixel_width = term_size[2] if term_size and len(term_size) > 2 else 0
        pixel_height = term_size[3] if term_size and len(term_size) > 3 else 0

        pty_request = PTYRequest(
            term_type=term_type,
            width=width,
            height=height,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
        )

        logger.info(
            f"Process factory: session {session_info.session_id}, "
            f"term={term_type}, size={width}x{height}"
        )

        if not self.session_handler:
            logger.error("No session handler registered")
            process.exit(1)
            return

        try:
            await self.session_handler(session_info, pty_request, process)
        except Exception as e:
            logger.error(
                f"Session handler error (session: {session_info.session_id}): {e}",
                exc_info=True,
            )
        finally:
            process.exit(0)

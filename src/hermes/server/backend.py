"""
Abstract SSH backend interface for Hermes.

This module defines the interface that all SSH backend implementations must follow,
allowing easy swapping of SSH libraries (e.g., asyncssh, paramiko) if needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from hermes.config import Config


@dataclass
class SessionInfo:
    """Information about an SSH session."""

    session_id: str
    username: str
    source_ip: str
    source_port: int
    authenticated: bool = False
    failed_attempts: int = 0


@dataclass
class PTYRequest:
    """Pseudo-terminal request details."""

    term_type: str
    width: int
    height: int
    pixel_width: int = 0
    pixel_height: int = 0


class SSHBackend(ABC):
    """
    Abstract base class for SSH server backends.

    This interface allows Hermes to use different SSH libraries
    while maintaining a consistent internal API.
    """

    def __init__(self, config: Config):
        """
        Initialize the SSH backend.

        Args:
            config: Hermes configuration
        """
        self.config = config

    @abstractmethod
    async def start(self) -> None:
        """
        Start the SSH server.

        Raises:
            RuntimeError: If server fails to start
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the SSH server.
        """
        pass

    @abstractmethod
    def set_session_handler(self, handler: Callable[[SessionInfo, PTYRequest, Any], Any]) -> None:
        """
        Set the callback function for handling SSH sessions.

        Args:
            handler: Async function to handle new sessions
                     Receives: (session_info, pty_request, session_object)
        """
        pass

    @abstractmethod
    async def authenticate(self, session_info: SessionInfo, username: str, password: str) -> bool:
        """
        Authenticate a user.

        Args:
            session_info: Current session information
            username: Username attempting to authenticate
            password: Password provided

        Returns:
            True if authentication successful, False otherwise
        """
        pass

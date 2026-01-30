"""
Authentication manager for Hermes.

Handles validation of credentials against configured static credentials
and implements accept-all mode after N failed attempts.
"""

import logging
from typing import Dict

from hermes.config import AuthenticationConfig

logger = logging.getLogger(__name__)


class AuthenticationManager:
    """
    Manages authentication logic for SSH connections.

    Tracks failed attempts per connection and implements accept-all mode.
    """

    def __init__(self, config: AuthenticationConfig):
        """
        Initialize the authentication manager.

        Args:
            config: Authentication configuration
        """
        self.config = config
        self._failed_attempts: Dict[str, int] = {}

        # Build credential lookup for performance
        self._credentials: Dict[str, str] = {
            cred.username: cred.password for cred in config.static_credentials
        }

        logger.info(f"Loaded {len(self._credentials)} static credentials")
        logger.info(
            f"Accept-all mode after {config.accept_all_after_failures} failures "
            f"({'disabled' if config.accept_all_after_failures == 0 else 'enabled'})"
        )

    def validate(self, connection_id: str, username: str, password: str) -> bool:
        """
        Validate credentials for a connection.

        Args:
            connection_id: Unique identifier for the connection
            username: Username attempting to authenticate
            password: Password provided

        Returns:
            True if authentication successful, False otherwise
        """
        # Check if accept-all mode is active for this connection
        if self._should_accept_all(connection_id):
            logger.info(f"Accept-all mode active for {connection_id} (username: {username})")
            self._reset_failures(connection_id)
            return True

        # Check static credentials
        if username in self._credentials:
            if self._credentials[username] == password:
                logger.info(f"Valid credentials for {username} from {connection_id}")
                self._reset_failures(connection_id)
                return True

        # Authentication failed
        self._increment_failures(connection_id)
        logger.warning(
            f"Invalid credentials for {username} from {connection_id} "
            f"(attempt {self._failed_attempts.get(connection_id, 0)})"
        )
        return False

    def _should_accept_all(self, connection_id: str) -> bool:
        """
        Check if accept-all mode should be activated.

        Args:
            connection_id: Unique identifier for the connection

        Returns:
            True if accept-all mode should be used
        """
        if self.config.accept_all_after_failures == 0:
            return False

        failures = self._failed_attempts.get(connection_id, 0)
        return failures >= self.config.accept_all_after_failures

    def _increment_failures(self, connection_id: str) -> None:
        """Increment failed attempt counter for a connection."""
        self._failed_attempts[connection_id] = self._failed_attempts.get(connection_id, 0) + 1

    def _reset_failures(self, connection_id: str) -> None:
        """Reset failed attempt counter for a connection."""
        if connection_id in self._failed_attempts:
            del self._failed_attempts[connection_id]

    def cleanup_connection(self, connection_id: str) -> None:
        """
        Cleanup tracking data for a disconnected connection.

        Args:
            connection_id: Unique identifier for the connection
        """
        self._reset_failures(connection_id)

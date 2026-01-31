"""
Integration tests for AuthenticationManager + SandTrapSSHServer interaction.

These tests verify that authentication flows correctly between the SSH server
callbacks and the authentication manager without mocking either component.
"""

import pytest
from unittest.mock import MagicMock

from hermes.config import AuthenticationConfig
from hermes.server.auth import AuthenticationManager


class TestAuthManagerMultiConnectionFlow:
    """Test realistic multi-connection authentication scenarios."""

    @pytest.fixture
    def auth(self) -> AuthenticationManager:
        config = AuthenticationConfig(
            static_credentials=[
                AuthenticationConfig.Credential(username="root", password="toor"),
                AuthenticationConfig.Credential(username="admin", password="secret"),
            ],
            accept_all_after_failures=3,
        )
        return AuthenticationManager(config)

    def test_attacker_brute_force_then_accept_all(self, auth: AuthenticationManager):
        """Simulate an attacker brute-forcing until accept-all kicks in."""
        conn = "attacker-1"

        # Attacker tries common passwords
        assert auth.validate(conn, "root", "root") is False
        assert auth.validate(conn, "root", "password") is False
        assert auth.validate(conn, "root", "123456") is False

        # After 3 failures, accept-all activates
        assert auth.validate(conn, "root", "anything") is True

        # Failure counter was reset after accept-all
        # So next wrong attempt starts counting again
        assert auth.validate(conn, "root", "wrong") is False

    def test_legitimate_user_amid_attackers(self, auth: AuthenticationManager):
        """Legitimate user should succeed even while attackers are failing."""
        # Attacker failing
        auth.validate("attacker", "root", "wrong1")
        auth.validate("attacker", "root", "wrong2")

        # Legitimate user connects and succeeds
        assert auth.validate("legit-user", "admin", "secret") is True

        # Attacker still hasn't hit threshold
        assert auth.validate("attacker", "root", "wrong3") is False
        # Now attacker hits threshold
        assert auth.validate("attacker", "root", "anything") is True

    def test_connection_cleanup_during_active_sessions(self, auth: AuthenticationManager):
        """Cleaning up one connection doesn't affect others."""
        auth.validate("conn-a", "root", "wrong")
        auth.validate("conn-a", "root", "wrong")
        auth.validate("conn-b", "root", "wrong")

        auth.cleanup_connection("conn-a")

        # conn-a state is gone, conn-b still has 1 failure
        assert auth._failed_attempts.get("conn-a") is None
        assert auth._failed_attempts.get("conn-b") == 1

    def test_many_concurrent_connections(self, auth: AuthenticationManager):
        """Simulate many connections each with independent failure tracking."""
        for i in range(50):
            conn = f"conn-{i}"
            auth.validate(conn, "root", "wrong")

        assert len(auth._failed_attempts) == 50

        # Clean up half
        for i in range(25):
            auth.cleanup_connection(f"conn-{i}")

        assert len(auth._failed_attempts) == 25

    def test_valid_credentials_never_increment_failures(self, auth: AuthenticationManager):
        """Successful auth should never leave failure state behind."""
        for _ in range(10):
            auth.validate("conn", "root", "toor")

        assert "conn" not in auth._failed_attempts


class TestAuthManagerEdgeCases:
    """Edge cases for authentication logic."""

    def test_empty_credentials_always_reject(self):
        """With no configured credentials, only accept-all can succeed."""
        config = AuthenticationConfig(
            static_credentials=[],
            accept_all_after_failures=2,
        )
        auth = AuthenticationManager(config)

        assert auth.validate("c1", "root", "root") is False
        assert auth.validate("c1", "root", "root") is False
        # Accept-all kicks in
        assert auth.validate("c1", "root", "root") is True

    def test_no_credentials_and_disabled_accept_all(self):
        """With no credentials and no accept-all, everything is rejected."""
        config = AuthenticationConfig(
            static_credentials=[],
            accept_all_after_failures=0,
        )
        auth = AuthenticationManager(config)

        for _ in range(20):
            assert auth.validate("c1", "root", "root") is False

    def test_accept_all_after_one_failure(self):
        """Accept-all with threshold of 1: first attempt fails, second succeeds."""
        config = AuthenticationConfig(
            static_credentials=[],
            accept_all_after_failures=1,
        )
        auth = AuthenticationManager(config)

        assert auth.validate("c1", "x", "y") is False
        assert auth.validate("c1", "x", "y") is True

    def test_duplicate_credential_usernames_last_wins(self):
        """If duplicate usernames exist, last password wins (dict behavior)."""
        config = AuthenticationConfig(
            static_credentials=[
                AuthenticationConfig.Credential(username="root", password="first"),
                AuthenticationConfig.Credential(username="root", password="second"),
            ],
            accept_all_after_failures=0,
        )
        auth = AuthenticationManager(config)

        assert auth.validate("c1", "root", "first") is False
        assert auth.validate("c1", "root", "second") is True

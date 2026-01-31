"""
Unit tests for AuthenticationManager.
"""

import pytest

from hermes.config import AuthenticationConfig
from hermes.server.auth import AuthenticationManager


@pytest.fixture
def auth_config() -> AuthenticationConfig:
    return AuthenticationConfig(
        static_credentials=[
            AuthenticationConfig.Credential(username="root", password="toor"),
            AuthenticationConfig.Credential(username="admin", password="admin123"),
        ],
        accept_all_after_failures=3,
    )


@pytest.fixture
def auth_config_no_accept_all() -> AuthenticationConfig:
    return AuthenticationConfig(
        static_credentials=[
            AuthenticationConfig.Credential(username="root", password="toor"),
        ],
        accept_all_after_failures=0,
    )


@pytest.fixture
def auth(auth_config: AuthenticationConfig) -> AuthenticationManager:
    return AuthenticationManager(auth_config)


@pytest.fixture
def auth_no_accept(auth_config_no_accept_all: AuthenticationConfig) -> AuthenticationManager:
    return AuthenticationManager(auth_config_no_accept_all)


class TestAuthenticationManagerInit:
    def test_credentials_loaded(self, auth: AuthenticationManager):
        assert len(auth._credentials) == 2
        assert auth._credentials["root"] == "toor"
        assert auth._credentials["admin"] == "admin123"

    def test_empty_credentials(self):
        config = AuthenticationConfig(static_credentials=[], accept_all_after_failures=0)
        mgr = AuthenticationManager(config)
        assert len(mgr._credentials) == 0

    def test_failed_attempts_starts_empty(self, auth: AuthenticationManager):
        assert auth._failed_attempts == {}


class TestAuthenticationManagerValidate:
    def test_valid_credentials_accepted(self, auth: AuthenticationManager):
        assert auth.validate("conn1", "root", "toor") is True

    def test_valid_credentials_second_user(self, auth: AuthenticationManager):
        assert auth.validate("conn1", "admin", "admin123") is True

    def test_wrong_password_rejected(self, auth: AuthenticationManager):
        assert auth.validate("conn1", "root", "wrong") is False

    def test_unknown_user_rejected(self, auth: AuthenticationManager):
        assert auth.validate("conn1", "nobody", "pass") is False

    def test_failed_attempt_tracked(self, auth: AuthenticationManager):
        auth.validate("conn1", "root", "wrong")
        assert auth._failed_attempts["conn1"] == 1

    def test_multiple_failures_tracked(self, auth: AuthenticationManager):
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn1", "root", "wrong")
        assert auth._failed_attempts["conn1"] == 2

    def test_successful_auth_resets_failures(self, auth: AuthenticationManager):
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn1", "root", "toor")
        assert "conn1" not in auth._failed_attempts

    def test_separate_connections_tracked_independently(self, auth: AuthenticationManager):
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn2", "root", "wrong")
        assert auth._failed_attempts["conn1"] == 1
        assert auth._failed_attempts["conn2"] == 1


class TestAcceptAllMode:
    def test_accept_all_after_n_failures(self, auth: AuthenticationManager):
        # 3 failures needed to trigger accept-all
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn1", "root", "wrong")
        auth.validate("conn1", "root", "wrong")
        # Now any credentials should be accepted
        assert auth.validate("conn1", "anything", "anything") is True

    def test_accept_all_resets_failures(self, auth: AuthenticationManager):
        auth.validate("conn1", "x", "x")
        auth.validate("conn1", "x", "x")
        auth.validate("conn1", "x", "x")
        auth.validate("conn1", "any", "any")  # accepted via accept-all
        assert "conn1" not in auth._failed_attempts

    def test_accept_all_disabled_when_zero(self, auth_no_accept: AuthenticationManager):
        for _ in range(10):
            auth_no_accept.validate("conn1", "x", "x")
        # Should still reject even after many failures
        assert auth_no_accept.validate("conn1", "x", "x") is False

    def test_accept_all_not_triggered_before_threshold(self, auth: AuthenticationManager):
        auth.validate("conn1", "x", "x")
        auth.validate("conn1", "x", "x")
        # Only 2 failures, threshold is 3
        assert auth.validate("conn1", "x", "x") is False

    def test_accept_all_does_not_affect_other_connections(self, auth: AuthenticationManager):
        # Trigger accept-all on conn1
        for _ in range(3):
            auth.validate("conn1", "x", "x")
        # conn2 should still reject
        assert auth.validate("conn2", "x", "x") is False


class TestCleanupConnection:
    def test_cleanup_removes_tracking(self, auth: AuthenticationManager):
        auth.validate("conn1", "x", "x")
        auth.cleanup_connection("conn1")
        assert "conn1" not in auth._failed_attempts

    def test_cleanup_unknown_connection_no_error(self, auth: AuthenticationManager):
        auth.cleanup_connection("nonexistent")  # should not raise

    def test_cleanup_resets_accept_all_state(self, auth: AuthenticationManager):
        for _ in range(3):
            auth.validate("conn1", "x", "x")
        auth.cleanup_connection("conn1")
        # After cleanup, accept-all should no longer be active
        assert auth.validate("conn1", "x", "x") is False

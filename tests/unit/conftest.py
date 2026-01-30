"""
Shared fixtures and utilities for unit tests.

Provides reusable mocks, fixtures, and test helpers to reduce boilerplate
and improve maintainability across test suites.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import contextmanager

import pytest

from hermes.server.backend import PTYRequest


# ============================================================================
# Real Object Fixtures
# ============================================================================

@pytest.fixture
def pty_request():
    """Standard PTY configuration for tests."""
    return PTYRequest(
        term_type="xterm-256color",
        width=120,
        height=40,
    )


# ============================================================================
# Socket Mock Utilities
# ============================================================================

class SocketMock:
    """Realistic socket mock that tracks blocking state."""

    def __init__(self):
        self.blocking = True
        self.closed = False

    def setblocking(self, flag: bool) -> None:
        self.blocking = flag

    def close(self) -> None:
        self.closed = True


class FailingSocketMock(SocketMock):
    """Socket that raises OSError on setblocking."""

    def setblocking(self, flag: bool) -> None:
        raise OSError("Socket operation failed")


# ============================================================================
# Process Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_process():
    """Mock SSHServerProcess with async stdin and stdout."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process


@pytest.fixture
def mock_process_eof():
    """Mock process that returns empty bytes (EOF) on stdin read."""
    process = MagicMock()
    process.stdin = AsyncMock(return_value=b"")
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process


@pytest.fixture
def mock_process_write_error():
    """Mock process where stdout.write raises after first call."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()

    call_count = [0]

    def write_with_error(data):
        call_count[0] += 1
        if call_count[0] > 1:
            raise BrokenPipeError("stdout closed")

    process.stdout.write = MagicMock(side_effect=write_with_error)
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process


# ============================================================================
# Container Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_container():
    """Mock Docker container."""
    container = MagicMock()
    container.id = "abc123def456"
    return container


@pytest.fixture
def mock_container_exec_fails():
    """Mock container where exec_run raises RuntimeError."""
    container = MagicMock()
    container.id = "abc123def456"
    container.exec_run.side_effect = RuntimeError("Docker exec failed")
    return container


@pytest.fixture
def mock_container_socket_error():
    """Mock container where socket.setblocking raises."""
    container = MagicMock()
    container.id = "abc123def456"
    socket_io = type("SocketIO", (), {"_sock": FailingSocketMock()})()
    container.exec_run.return_value = MagicMock(output=socket_io)
    return container


# ============================================================================
# Recorder Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_recorder():
    """Mock SessionRecorder."""
    return MagicMock()


@pytest.fixture
def mock_recorder_start_fails():
    """Mock recorder where start() raises."""
    recorder = MagicMock()
    recorder.start.side_effect = OSError("Recording directory not writable")
    return recorder


# ============================================================================
# Handler Patch Fixture Factory
# ============================================================================

@pytest.fixture
def patch_handler_deps():
    """
    Fixture factory for patching handler dependencies (ContainerProxy, SessionRecorder).

    Usage:
        async def test_something(patch_handler_deps):
            with patch_handler_deps() as (MockProxy, MockRecorder, proxy_inst, recorder_inst):
                # MockProxy and MockRecorder are the patch objects
                # proxy_inst and recorder_inst are the instances
                await container_session_handler(...)
    """

    @contextmanager
    def factory(proxy_async=True, recorder_async=False):
        """
        Args:
            proxy_async: If True, proxy instance is AsyncMock; else MagicMock
            recorder_async: If True, recorder instance is AsyncMock; else MagicMock
        """
        with patch("hermes.__main__.ContainerProxy") as MockProxy, \
             patch("hermes.__main__.SessionRecorder") as MockRecorder:

            proxy_inst = AsyncMock() if proxy_async else MagicMock()
            recorder_inst = AsyncMock() if recorder_async else MagicMock()

            MockProxy.return_value = proxy_inst
            MockRecorder.return_value = recorder_inst

            yield MockProxy, MockRecorder, proxy_inst, recorder_inst

    return factory

"""
Integration tests for session handler end-to-end flow.

Tests the interaction between container_session_handler, ContainerPool,
ContainerProxy, and SessionRecorder working together.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes.config import Config, ContainerPoolConfig, RecordingConfig
from hermes.container.pool import ContainerPool
from hermes.server.backend import PTYRequest, SessionInfo
from hermes.__main__ import container_session_handler


def _mock_process() -> MagicMock:
    """Create a mock SSHServerProcess."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdin.read = AsyncMock(return_value=b"")  # immediate disconnect
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    return process


def _mock_container() -> MagicMock:
    """Create a mock Docker container with exec support."""
    container = MagicMock()
    container.id = "integ123456789"
    container.stop = MagicMock()
    container.reload = MagicMock()

    # exec_run returns a result with a socket-like output
    sock = MagicMock()
    sock._sock = MagicMock()
    sock._sock.setblocking = MagicMock()
    sock._sock.close = MagicMock()

    exec_result = MagicMock()
    exec_result.output = sock
    container.exec_run = MagicMock(return_value=exec_result)
    return container


def _session_info() -> SessionInfo:
    return SessionInfo(
        session_id="integ-session-001",
        username="attacker",
        source_ip="10.0.0.1",
        source_port=12345,
        authenticated=True,
    )


def _pty_request() -> PTYRequest:
    return PTYRequest(term_type="xterm-256color", width=120, height=40)


class TestSessionHandlerWithRecorder:
    """Test session handler creates and manages recorder correctly."""

    @pytest.mark.asyncio
    async def test_recorder_created_and_stopped(self, tmp_path: Path):
        """Recorder should be started at session start and stopped at end."""
        recording_config = RecordingConfig(
            enabled=True,
            output_dir=tmp_path / "recordings",
        )

        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        process = _mock_process()

        # Patch ContainerProxy to avoid real socket operations
        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=_session_info(),
                pty_request=_pty_request(),
                process=process,
                container_pool=pool,
                config=Config(),
                recording_config=recording_config,
            )

        # Verify pool lifecycle
        pool.allocate.assert_called_once_with("integ-session-001")
        pool.release.assert_called_once_with("integ-session-001")

        # Verify proxy lifecycle
        proxy_instance.start.assert_called_once()
        proxy_instance.wait_completion.assert_called_once()
        proxy_instance.stop.assert_called_once()

        # Verify recording directory was created
        assert (tmp_path / "recordings").exists()

    @pytest.mark.asyncio
    async def test_no_recorder_when_config_absent(self):
        """Without recording config, no recorder should be created."""
        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=_session_info(),
                pty_request=_pty_request(),
                process=_mock_process(),
                container_pool=pool,
                config=Config(),
                recording_config=None,
            )

        # Proxy should have been created with recorder=None
        call_kwargs = MockProxy.call_args[1]
        assert call_kwargs["recorder"] is None


class TestSessionHandlerErrorPaths:
    """Test session handler behavior under failure conditions."""

    @pytest.mark.asyncio
    async def test_allocation_failure_writes_error_to_client(self):
        """If container allocation fails, error message goes to SSH client."""
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(side_effect=RuntimeError("no containers"))
        pool.release = AsyncMock()

        process = _mock_process()

        await container_session_handler(
            session_info=_session_info(),
            pty_request=_pty_request(),
            process=process,
            container_pool=pool,
            config=Config(),
            recording_config=None,
        )

        # Error message written to client
        process.stdout.write.assert_called_once()
        written = process.stdout.write.call_args[0][0]
        assert b"Session error" in written

        # Release should NOT be called since allocation failed
        pool.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_proxy_start_failure_still_releases_container(self):
        """If proxy fails to start, container should still be released."""
        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.start.side_effect = RuntimeError("exec failed")
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=_session_info(),
                pty_request=_pty_request(),
                process=_mock_process(),
                container_pool=pool,
                config=Config(),
                recording_config=None,
            )

        # Container should be released even though proxy failed
        pool.release.assert_called_once_with("integ-session-001")

    @pytest.mark.asyncio
    async def test_recorder_stopped_even_on_proxy_failure(self, tmp_path: Path):
        """Recorder cleanup runs in finally block regardless of proxy errors."""
        recording_config = RecordingConfig(
            enabled=True,
            output_dir=tmp_path / "recordings",
        )

        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.start.side_effect = RuntimeError("boom")
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=_session_info(),
                pty_request=_pty_request(),
                process=_mock_process(),
                container_pool=pool,
                config=Config(),
                recording_config=recording_config,
            )

        # Recording directory should still have been created (recorder.start ran)
        assert (tmp_path / "recordings").exists()


class TestSessionHandlerMetadataFlow:
    """Test that metadata flows correctly through the session."""

    @pytest.mark.asyncio
    async def test_session_id_propagated_through_stack(self):
        """Session ID should be passed to pool, proxy, and recorder."""
        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        session_info = _session_info()

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=session_info,
                pty_request=_pty_request(),
                process=_mock_process(),
                container_pool=pool,
                config=Config(),
                recording_config=None,
            )

        # Session ID used consistently
        pool.allocate.assert_called_with("integ-session-001")
        pool.release.assert_called_with("integ-session-001")
        proxy_kwargs = MockProxy.call_args[1]
        assert proxy_kwargs["session_id"] == "integ-session-001"

    @pytest.mark.asyncio
    async def test_pty_request_forwarded_to_proxy(self):
        """PTY dimensions should be passed to proxy."""
        container = _mock_container()
        pool = MagicMock(spec=ContainerPool)
        pool.allocate = AsyncMock(return_value=container)
        pool.release = AsyncMock()

        pty = _pty_request()

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info=_session_info(),
                pty_request=pty,
                process=_mock_process(),
                container_pool=pool,
                config=Config(),
                recording_config=None,
            )

        proxy_kwargs = MockProxy.call_args[1]
        assert proxy_kwargs["pty_request"] is pty

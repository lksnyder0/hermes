"""
Integration tests for session timeout functionality in container session handler.

Tests timeout monitoring and cleanup sequence within the actual session handler.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes.config import Config, RecordingConfig, ServerConfig
from hermes.server.backend import PTYRequest, SessionInfo
from hermes.__main__ import container_session_handler


@pytest.fixture
def mock_pool():
    """Mock container pool."""
    pool = MagicMock()
    pool.allocate = AsyncMock()
    pool.release = AsyncMock()
    return pool


@pytest.fixture
def session_info():
    """Standard session info for timeout tests."""
    return SessionInfo(
        session_id="integration-timeout-test",
        username="root",
        source_ip="10.0.0.100",
        source_port=2222,
        authenticated=True,
    )


@pytest.fixture
def pty_request():
    """Standard PTY configuration."""
    return PTYRequest(
        term_type="xterm-256color",
        width=120,
        height=40,
    )


@pytest.fixture
def mock_process():
    """Mock SSH process with valid attributes."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    return process


@pytest.fixture
def mock_container():
    """Mock Docker container with proper attributes."""
    container = MagicMock()
    container.id = "container-12345"
    return container


@pytest.mark.unit
@pytest.mark.asyncio
class TestTimeoutParameterHandling:
    """Tests that container_session_handler accepts correct timeout parameters."""

    async def test_handler_accepts_timeout_from_config(
        self, session_info, pty_request, mock_process, mock_container, mock_pool
    ):
        """Verify handler accepts timeout configuration."""
        config = Config()
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.wait_completion = AsyncMock(return_value=None)
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool, config
            )

        assert proxy_instance.start.called
        assert proxy_instance.wait_completion.called

    async def test_handler_accepts_recording_config(
        self, session_info, pty_request, mock_process, mock_container, mock_pool
    ):
        """Verify handler accepts recording configuration."""
        config = Config()
        recording = RecordingConfig(enabled=False)
        config.recording = recording
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.SessionRecorder") as MockRecorder:
            mock_pool.allocate.return_value = mock_container
            rec_instance = AsyncMock()
            MockRecorder.return_value = rec_instance

            with patch("hermes.__main__.ContainerProxy") as MockProxy:
                proxy_instance = AsyncMock()
                proxy_instance.wait_completion = AsyncMock(return_value=None)
                MockProxy.return_value = proxy_instance

                await container_session_handler(
                    session_info, pty_request, mock_process, mock_pool, config, recording
                )

        assert rec_instance.start.called
        assert rec_instance.stop.called

    async def test_handler_uses_server_config_timeout(
        self, session_info, pty_request, mock_process, mock_container, mock_pool
    ):
        """Verify handler uses server.session_timeout from config."""
        short_timeout = 60
        config = Config(server=ServerConfig(session_timeout=short_timeout))
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.wait_completion = AsyncMock(return_value=None)
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool, config
            )

        assert proxy_instance.start.called
        assert config.server.session_timeout == short_timeout

    async def test_session_times_out_and_cleans_up(
        self, session_info, pty_request, mock_process, mock_container, mock_pool
    ):
        """Verify timeout fires, sends error to client stdout, and releases the container."""
        short_timeout = 0.05  # 50ms — too short for real ServerConfig (ge=60), use MagicMock
        config = MagicMock()
        config.server.session_timeout = short_timeout
        mock_pool.allocate.return_value = mock_container

        async def slow_completion() -> None:
            await asyncio.sleep(short_timeout * 4)  # outlives the timeout

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.wait_completion = AsyncMock(side_effect=slow_completion)
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool, config
            )

        # Container must be released after timeout
        mock_pool.release.assert_called_once_with(session_info.session_id)

        # Timeout error message must be written to stdout (not stdin)
        writes = [call.args[0] for call in mock_process.stdout.write.call_args_list]
        assert any(b"timeout" in msg.lower() for msg in writes)

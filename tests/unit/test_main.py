"""
Tests for hermes/__main__.py entry point.

Tests cover:
- parse_args(): command-line argument parsing
- main(): entry point with error handling
- async_main(): async initialization and server startup
- container_session_handler(): session proxy orchestration
"""

import argparse
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import docker

from hermes import __version__
from hermes.__main__ import (
    parse_args,
    main,
    async_main,
    container_session_handler,
    setup_logging,
)
from hermes.config import Config
from hermes.server.backend import SessionInfo, PTYRequest


@pytest.fixture
def test_config() -> Config:
    """Create a basic test configuration."""
    config = Config()
    config.server.session_timeout = 30
    return config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_config():
    """Mock Config object with all required attributes."""
    config = MagicMock()
    config.server.host = "0.0.0.0"
    config.server.port = 2222
    config.server.max_concurrent_sessions = 10
    config.server.host_key_path = Path("/tmp/host_key")
    config.container_pool.size = 3
    config.docker.base_url = None
    config.recording = None
    return config


@pytest.fixture
def mock_docker_client():
    """Mock Docker client."""
    client = MagicMock()
    client.version.return_value = {"Version": "20.10.0"}
    client.close = MagicMock()
    return client


@pytest.fixture
def mock_pool():
    """Mock ContainerPool."""
    pool = AsyncMock()
    pool.initialize = AsyncMock()
    pool.shutdown = AsyncMock()
    pool.allocate = AsyncMock()
    pool.release = AsyncMock()
    return pool


@pytest.fixture
def mock_ssh_backend():
    """Mock AsyncSSHBackend."""
    backend = AsyncMock()
    backend.set_container_pool = MagicMock()
    backend.set_session_handler = MagicMock()
    backend.start = AsyncMock()
    backend.stop = AsyncMock()
    return backend


@pytest.fixture
def mock_container():
    """Mock Docker container."""
    container = MagicMock()
    container.id = "abc123def456"
    return container


@pytest.fixture
def session_info():
    """Create a SessionInfo for testing."""
    return SessionInfo(
        session_id="test-session-1",
        username="root",
        source_ip="192.168.1.100",
        source_port=12345,
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
    """Mock SSH process."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process


# ============================================================================
# Tests for parse_args()
# ============================================================================


class TestParseArgs:
    """Tests for command-line argument parsing."""

    def test_default_values(self):
        """Should parse arguments with defaults when none provided."""
        with patch.object(sys, "argv", ["hermes"]):
            args = parse_args()

        assert args.config == Path("config/config.yaml")
        assert args.log_level == "INFO"
        assert args.generate_keys is False

    def test_config_short_flag(self):
        """Should accept -c for config path."""
        with patch.object(sys, "argv", ["hermes", "-c", "/etc/hermes.yaml"]):
            args = parse_args()

        assert args.config == Path("/etc/hermes.yaml")

    def test_config_long_flag(self):
        """Should accept --config for config path."""
        with patch.object(sys, "argv", ["hermes", "--config", "/tmp/config.yaml"]):
            args = parse_args()

        assert args.config == Path("/tmp/config.yaml")

    def test_log_level_debug(self):
        """Should parse DEBUG log level."""
        with patch.object(sys, "argv", ["hermes", "--log-level", "DEBUG"]):
            args = parse_args()

        assert args.log_level == "DEBUG"

    def test_log_level_warning(self):
        """Should parse WARNING log level."""
        with patch.object(sys, "argv", ["hermes", "--log-level", "WARNING"]):
            args = parse_args()

        assert args.log_level == "WARNING"

    def test_log_level_error(self):
        """Should parse ERROR log level."""
        with patch.object(sys, "argv", ["hermes", "--log-level", "ERROR"]):
            args = parse_args()

        assert args.log_level == "ERROR"

    def test_log_level_critical(self):
        """Should parse CRITICAL log level."""
        with patch.object(sys, "argv", ["hermes", "--log-level", "CRITICAL"]):
            args = parse_args()

        assert args.log_level == "CRITICAL"

    def test_generate_keys_flag(self):
        """Should parse --generate-keys flag."""
        with patch.object(sys, "argv", ["hermes", "--generate-keys"]):
            args = parse_args()

        assert args.generate_keys is True

    def test_version_flag_raises_exit(self):
        """Should exit when --version is passed."""
        with patch.object(sys, "argv", ["hermes", "--version"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_invalid_log_level_raises(self):
        """Should reject invalid log level."""
        with patch.object(sys, "argv", ["hermes", "--log-level", "INVALID"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_multiple_flags_combined(self):
        """Should parse multiple flags together."""
        with patch.object(
            sys,
            "argv",
            ["hermes", "--config", "/tmp/test.yaml", "--log-level", "DEBUG"],
        ):
            args = parse_args()

        assert args.config == Path("/tmp/test.yaml")
        assert args.log_level == "DEBUG"


# ============================================================================
# Tests for setup_logging()
# ============================================================================


class TestSetupLogging:
    """Tests for logging configuration."""

    def test_setup_logging_info(self):
        """Should configure INFO level logging."""
        with patch("hermes.__main__.logging.basicConfig") as mock_config:
            setup_logging("INFO")

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == 20  # logging.INFO

    def test_setup_logging_debug(self):
        """Should configure DEBUG level logging."""
        with patch("hermes.__main__.logging.basicConfig") as mock_config:
            setup_logging("DEBUG")

            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == 10  # logging.DEBUG

    def test_setup_logging_error(self):
        """Should configure ERROR level logging."""
        with patch("hermes.__main__.logging.basicConfig") as mock_config:
            setup_logging("ERROR")

            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == 40  # logging.ERROR


# ============================================================================
# Tests for main()
# ============================================================================


class TestMain:
    """Tests for the main entry point."""

    def test_main_runs_async_main(self):
        """Should call asyncio.run(async_main)."""
        with patch("hermes.__main__.parse_args") as mock_parse:
            with patch("hermes.__main__.setup_logging"):
                with patch("hermes.__main__.asyncio.run") as mock_run:
                    mock_parse.return_value = argparse.Namespace(
                        config=Path("config.yaml"),
                        log_level="INFO",
                        generate_keys=False,
                    )
                    mock_run.return_value = 0

                    result = main()

                    assert result == 0
                    mock_run.assert_called_once()

    def test_main_keyboard_interrupt_returns_0(self):
        """Should handle KeyboardInterrupt gracefully."""
        with patch("hermes.__main__.parse_args") as mock_parse:
            with patch("hermes.__main__.setup_logging"):
                with patch(
                    "hermes.__main__.asyncio.run",
                    side_effect=KeyboardInterrupt,
                ):
                    mock_parse.return_value = argparse.Namespace(
                        config=Path("config.yaml"),
                        log_level="INFO",
                        generate_keys=False,
                    )

                    result = main()

                    assert result == 0

    def test_main_skips_generate_keys(self):
        """Should not implement --generate-keys (raises NotImplementedError)."""
        with patch("hermes.__main__.parse_args") as mock_parse:
            with patch("hermes.__main__.setup_logging"):
                mock_parse.return_value = argparse.Namespace(
                    config=Path("config.yaml"),
                    log_level="INFO",
                    generate_keys=True,
                )

                # The generate-keys feature is not yet implemented and returns 1
                result = main()

                assert result == 1

    def test_main_calls_setup_logging(self):
        """Should configure logging before running."""
        with patch("hermes.__main__.parse_args") as mock_parse:
            with patch("hermes.__main__.setup_logging") as mock_setup:
                with patch("hermes.__main__.asyncio.run", return_value=0):
                    mock_parse.return_value = argparse.Namespace(
                        config=Path("config.yaml"),
                        log_level="DEBUG",
                        generate_keys=False,
                    )

                    main()

                    mock_setup.assert_called_once_with("DEBUG")

    def test_main_passes_config_path(self):
        """Should pass config path to async_main."""
        with patch("hermes.__main__.parse_args") as mock_parse:
            with patch("hermes.__main__.setup_logging"):
                with patch("hermes.__main__.async_main", new_callable=AsyncMock) as mock_async_main:
                    config_path = Path("/custom/config.yaml")
                    mock_parse.return_value = argparse.Namespace(
                        config=config_path,
                        log_level="INFO",
                        generate_keys=False,
                    )
                    mock_async_main.return_value = 0

                    result = main()

                    # Verify async_main was called with the correct config path
                    mock_async_main.assert_called_once_with(config_path)
                    assert result == 0


# ============================================================================
# Tests for async_main()
# ============================================================================


class TestAsyncMain:
    """Tests for asynchronous main initialization and startup."""

    @pytest.mark.asyncio
    async def test_async_main_successful_startup(self, mock_config):
        """Should successfully start SSH server and initialize pool."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch("hermes.__main__.docker.from_env") as mock_docker_from_env:
                with patch("hermes.__main__.ContainerPool") as MockPool:
                    with patch("hermes.__main__.AsyncSSHBackend") as MockBackend:
                        # Setup mocks
                        client = MagicMock()
                        client.version.return_value = {"Version": "20.10.0"}
                        client.close = MagicMock()
                        mock_docker_from_env.return_value = client

                        pool = AsyncMock()
                        pool.initialize = AsyncMock()
                        pool.shutdown = AsyncMock()
                        MockPool.return_value = pool

                        backend = AsyncMock()
                        backend.set_container_pool = MagicMock()
                        backend.set_session_handler = MagicMock()
                        backend.start = AsyncMock()
                        backend.stop = AsyncMock()
                        MockBackend.return_value = backend

                        # Mock the event wait to return immediately
                        with patch("hermes.__main__.asyncio.Event") as MockEvent:
                            event = MagicMock()
                            event.wait = AsyncMock()
                            MockEvent.return_value = event

                            result = await asyncio.wait_for(
                                asyncio.shield(async_main(config_path)),
                                timeout=0.5,
                            )

                            assert result == 0

    @pytest.mark.asyncio
    async def test_async_main_config_file_not_found(self):
        """Should return error code when config file missing."""
        config_path = Path("nonexistent.yaml")

        with patch(
            "hermes.__main__.Config.from_file",
            side_effect=FileNotFoundError("not found"),
        ):
            result = await async_main(config_path)

            assert result == 1

    @pytest.mark.asyncio
    async def test_async_main_docker_not_running(self, mock_config):
        """Should return error code when Docker not accessible."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch(
                "hermes.__main__.docker.from_env",
                side_effect=docker.errors.DockerException("Cannot connect to Docker"),
            ):
                result = await async_main(config_path)

                assert result == 1

    @pytest.mark.asyncio
    async def test_async_main_pool_initialization_failure(self, mock_config):
        """Should cleanup and return error code if pool init fails."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch("hermes.__main__.docker.from_env") as mock_docker_from_env:
                with patch("hermes.__main__.ContainerPool") as MockPool:
                    client = MagicMock()
                    client.version.return_value = {"Version": "20.10.0"}
                    client.close = MagicMock()
                    mock_docker_from_env.return_value = client

                    pool = AsyncMock()
                    pool.initialize.side_effect = RuntimeError("Container creation failed")
                    pool.shutdown = AsyncMock()
                    MockPool.return_value = pool

                    result = await async_main(config_path)

                    assert result == 1
                    pool.shutdown.assert_called_once()
                    client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_graceful_shutdown(self, mock_config):
        """Should properly cleanup resources on shutdown."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch("hermes.__main__.docker.from_env") as mock_docker_from_env:
                with patch("hermes.__main__.ContainerPool") as MockPool:
                    with patch("hermes.__main__.AsyncSSHBackend") as MockBackend:
                        client = MagicMock()
                        client.version.return_value = {"Version": "20.10.0"}
                        client.close = MagicMock()
                        mock_docker_from_env.return_value = client

                        pool = AsyncMock()
                        pool.initialize = AsyncMock()
                        pool.shutdown = AsyncMock()
                        MockPool.return_value = pool

                        backend = AsyncMock()
                        backend.set_container_pool = MagicMock()
                        backend.set_session_handler = MagicMock()
                        backend.start = AsyncMock()
                        backend.stop = AsyncMock()
                        MockBackend.return_value = backend

                        with patch("hermes.__main__.asyncio.Event") as MockEvent:
                            event = MagicMock()
                            event.wait = AsyncMock()
                            MockEvent.return_value = event

                            await asyncio.wait_for(
                                asyncio.shield(async_main(config_path)),
                                timeout=0.5,
                            )

                            # Verify cleanup was called
                            backend.stop.assert_called_once()
                            pool.shutdown.assert_called_once()
                            client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_uses_custom_docker_base_url(self, mock_config):
        """Should use custom Docker base_url if configured."""
        config_path = Path("config.yaml")
        mock_config.docker.base_url = "unix:///var/run/docker.sock"

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch("hermes.__main__.docker.DockerClient") as MockDockerClient:
                with patch("hermes.__main__.ContainerPool") as MockPool:
                    with patch("hermes.__main__.AsyncSSHBackend") as MockBackend:
                        client = MagicMock()
                        client.version.return_value = {"Version": "20.10.0"}
                        client.close = MagicMock()
                        MockDockerClient.return_value = client

                        pool = AsyncMock()
                        pool.initialize = AsyncMock()
                        pool.shutdown = AsyncMock()
                        MockPool.return_value = pool

                        backend = AsyncMock()
                        backend.set_container_pool = MagicMock()
                        backend.set_session_handler = MagicMock()
                        backend.start = AsyncMock()
                        backend.stop = AsyncMock()
                        MockBackend.return_value = backend

                        with patch("hermes.__main__.asyncio.Event") as MockEvent:
                            event = MagicMock()
                            event.wait = AsyncMock()
                            MockEvent.return_value = event

                            await asyncio.wait_for(
                                asyncio.shield(async_main(config_path)),
                                timeout=0.5,
                            )

                            MockDockerClient.assert_called_once_with(
                                base_url="unix:///var/run/docker.sock"
                            )

    @pytest.mark.asyncio
    async def test_async_main_registers_session_handler(self, mock_config):
        """Should register session handler with SSH backend."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch("hermes.__main__.docker.from_env") as mock_docker_from_env:
                with patch("hermes.__main__.ContainerPool") as MockPool:
                    with patch("hermes.__main__.AsyncSSHBackend") as MockBackend:
                        client = MagicMock()
                        client.version.return_value = {"Version": "20.10.0"}
                        client.close = MagicMock()
                        mock_docker_from_env.return_value = client

                        pool = AsyncMock()
                        pool.initialize = AsyncMock()
                        pool.shutdown = AsyncMock()
                        MockPool.return_value = pool

                        backend = AsyncMock()
                        backend.set_container_pool = MagicMock()
                        backend.set_session_handler = MagicMock()
                        backend.start = AsyncMock()
                        backend.stop = AsyncMock()
                        MockBackend.return_value = backend

                        with patch("hermes.__main__.asyncio.Event") as MockEvent:
                            event = MagicMock()
                            event.wait = AsyncMock()
                            MockEvent.return_value = event

                            await asyncio.wait_for(
                                asyncio.shield(async_main(config_path)),
                                timeout=0.5,
                            )

                            backend.set_container_pool.assert_called_once_with(pool)
                            backend.set_session_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_main_catches_generic_exception(self, mock_config):
        """Should catch and handle unexpected exceptions."""
        config_path = Path("config.yaml")

        with patch("hermes.__main__.Config.from_file", return_value=mock_config):
            with patch(
                "hermes.__main__.docker.from_env",
                side_effect=RuntimeError("Unexpected error"),
            ):
                result = await async_main(config_path)

                assert result == 1


# ============================================================================
# Tests for container_session_handler()
# ============================================================================


class TestContainerSessionHandler:
    """Tests for session proxy orchestration."""

    @pytest.mark.asyncio
    async def test_allocates_and_releases_container(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should allocate container and release after completion."""
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance
            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool, test_config
            )


            mock_pool.allocate.assert_called_once_with("test-session-1")
            mock_pool.release.assert_called_once_with("test-session-1")

    @pytest.mark.asyncio
    async def test_creates_proxy_with_recorder(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should create ContainerProxy with recorder if recording enabled."""
        mock_pool.allocate.return_value = mock_container
        recording_config = MagicMock()
        recording_config.enabled = True
        recording_config.output_dir = Path("/tmp/recordings")

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            with patch("hermes.__main__.SessionRecorder") as MockRecorder:
                proxy_instance = AsyncMock()
                MockProxy.return_value = proxy_instance

                recorder_instance = MagicMock()
                recorder_instance.start = MagicMock()
                recorder_instance.stop = MagicMock()
                recorder_instance.write_metadata = MagicMock()
                MockRecorder.return_value = recorder_instance

                await container_session_handler(
                    session_info,
                    pty_request,
                    mock_process,
                    mock_pool,
                    test_config,
                    recording_config,
                )

                MockRecorder.assert_called_once()
                recorder_instance.start.assert_called_once()
                recorder_instance.stop.assert_called_once()
                recorder_instance.write_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_and_waits_proxy(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should start proxy and wait for completion."""
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info,
                pty_request,
                mock_process,
                mock_pool,
                test_config,
            )

        proxy_instance.start.assert_called_once()
        proxy_instance.wait_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_allocation_failure_writes_error(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should write error to stdout if allocation fails."""
        mock_pool.allocate.side_effect = RuntimeError("pool exhausted")

        # Should handle allocation failure gracefully
        try:
            await container_session_handler(
                session_info,
                pty_request,
                mock_process,
                mock_pool,
                test_config,
            )
        except RuntimeError as e:
            assert "pool exhausted" in str(e)

        mock_process.stdout.write.assert_called()

    @pytest.mark.asyncio
    async def test_allocation_failure_does_not_release(
        self, session_info, pty_request, mock_process, mock_pool
    ):
        """Should not release container if allocation never succeeded."""
        mock_pool.allocate.side_effect = RuntimeError("pool exhausted")

        # Should handle allocation failure gracefully and not release
        try:
            await container_session_handler(session_info, pty_request, mock_process, mock_pool, test_config)
        except RuntimeError:
            # Allocation failed, should not release
            mock_pool.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_proxy_failure_releases_container(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should release container even if proxy.start() fails."""
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.start.side_effect = RuntimeError("exec failed")
            proxy_instance.stop = AsyncMock()
            MockProxy.return_value = proxy_instance

            try:
                await container_session_handler(session_info, pty_request, mock_process, mock_pool, test_config)
            except RuntimeError:
                pass

            mock_pool.release.assert_called_once()

    @pytest.mark.asyncio
    async def test_stops_proxy_in_finally(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should always stop proxy even on error."""
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info,
                pty_request,
                mock_process,
                mock_pool,
                test_config,
            )

        proxy_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_recording_config_to_proxy(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should pass recorder to ContainerProxy if recording enabled."""
        mock_pool.allocate.return_value = mock_container
        recording_config = MagicMock()
        recording_config.enabled = True
        recording_config.output_dir = Path("/tmp/recordings")

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            with patch("hermes.__main__.SessionRecorder") as MockRecorder:
                proxy_instance = AsyncMock()
                MockProxy.return_value = proxy_instance

                recorder_instance = MagicMock()
                recorder_instance.start = MagicMock()
                recorder_instance.stop = MagicMock()
                recorder_instance.write_metadata = MagicMock()
                MockRecorder.return_value = recorder_instance

                await container_session_handler(
                    session_info,
                    pty_request,
                    mock_process,
                    mock_pool,
                    test_config,
                    recording_config,
                )

                # Verify proxy was created with the recorder
                call_args = MockProxy.call_args
                assert call_args[1]["recorder"] is recorder_instance

    @pytest.mark.asyncio
    async def test_no_recorder_when_recording_disabled(
        self, session_info, pty_request, mock_process, mock_pool, mock_container, test_config
    ):
        """Should not create recorder when recording is None."""
        mock_pool.allocate.return_value = mock_container

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            with patch("hermes.__main__.SessionRecorder") as MockRecorder:
                proxy_instance = AsyncMock()
                MockProxy.return_value = proxy_instance

                await container_session_handler(
                    session_info, pty_request, mock_process, mock_pool, test_config, None
                )

                MockRecorder.assert_not_called()
                # Verify proxy was created without recorder
                call_args = MockProxy.call_args
                assert call_args[1]["recorder"] is None

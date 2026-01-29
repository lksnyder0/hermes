"""
Unit tests for AsyncSSH backend process factory and server components.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sandtrap.server.asyncssh_backend import AsyncSSHBackend, SandTrapSSHServer
from sandtrap.server.backend import PTYRequest, SessionInfo


@pytest.fixture
def mock_config():
    """Create a minimal mock Config for backend instantiation."""
    config = MagicMock()
    config.server.host = "127.0.0.1"
    config.server.port = 2222
    config.server.host_key_path = MagicMock()
    config.server.host_key_path.exists.return_value = True
    config.authentication = MagicMock()
    return config


@pytest.fixture
def backend(mock_config):
    """Create an AsyncSSHBackend instance."""
    return AsyncSSHBackend(mock_config)


@pytest.fixture
def session_info():
    """Create a sample SessionInfo."""
    return SessionInfo(
        session_id="test-session-1",
        username="testuser",
        source_ip="192.168.1.100",
        source_port=54321,
        authenticated=True,
    )


@pytest.fixture
def mock_process():
    """Create a mock SSHServerProcess with standard attributes."""
    process = MagicMock()
    process.get_terminal_type.return_value = "xterm-256color"
    process.get_terminal_size.return_value = (120, 40, 0, 0)
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.exit = MagicMock()

    # Channel/connection chain for session info lookup
    conn = MagicMock()
    process.channel.get_connection.return_value = conn

    return process


class TestAsyncSSHBackendInit:
    """Tests for AsyncSSHBackend initialization."""

    def test_init_sets_config(self, backend, mock_config):
        assert backend.config is mock_config

    def test_init_creates_empty_session_info_map(self, backend):
        assert backend._session_info_map == {}

    def test_init_no_server(self, backend):
        assert backend._server is None

    def test_init_no_session_handler(self, backend):
        assert backend.session_handler is None


class TestAsyncSSHBackendSetters:
    """Tests for set_session_handler and set_container_pool."""

    def test_set_session_handler(self, backend):
        handler = AsyncMock()
        backend.set_session_handler(handler)
        assert backend.session_handler is handler

    def test_set_container_pool(self, backend):
        pool = MagicMock()
        backend.set_container_pool(pool)
        assert backend.container_pool is pool


class TestProcessFactory:
    """Tests for the _process_factory method."""

    @pytest.mark.asyncio
    async def test_extracts_pty_info(self, backend, session_info, mock_process):
        """Process factory should extract terminal type and size from process."""
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        handler.assert_called_once()
        call_args = handler.call_args
        pty_req = call_args[0][1]
        assert isinstance(pty_req, PTYRequest)
        assert pty_req.term_type == "xterm-256color"
        assert pty_req.width == 120
        assert pty_req.height == 40

    @pytest.mark.asyncio
    async def test_passes_session_info(self, backend, session_info, mock_process):
        """Process factory should pass the correct SessionInfo to the handler."""
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        call_args = handler.call_args[0]
        assert call_args[0] is session_info

    @pytest.mark.asyncio
    async def test_passes_process_to_handler(self, backend, session_info, mock_process):
        """Process factory should pass the SSHServerProcess to the handler."""
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        call_args = handler.call_args[0]
        assert call_args[2] is mock_process

    @pytest.mark.asyncio
    async def test_defaults_term_type_to_xterm(self, backend, session_info, mock_process):
        """Should default to 'xterm' when terminal type is None."""
        mock_process.get_terminal_type.return_value = None
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        pty_req = handler.call_args[0][1]
        assert pty_req.term_type == "xterm"

    @pytest.mark.asyncio
    async def test_defaults_term_size_when_none(self, backend, session_info, mock_process):
        """Should default to 80x24 when terminal size is None."""
        mock_process.get_terminal_size.return_value = None
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        pty_req = handler.call_args[0][1]
        assert pty_req.width == 80
        assert pty_req.height == 24

    @pytest.mark.asyncio
    async def test_exits_with_1_when_no_connection(self, backend, mock_process):
        """Should exit(1) when channel has no connection."""
        mock_process.channel.get_connection.return_value = None

        await backend._process_factory(mock_process)

        mock_process.exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_exits_with_1_when_no_session_info(self, backend, mock_process):
        """Should exit(1) when session info map is empty."""
        await backend._process_factory(mock_process)

        mock_process.exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_exits_with_1_when_no_handler(self, backend, session_info, mock_process):
        """Should exit(1) when no session handler is registered."""
        backend._session_info_map["test-session-1"] = session_info
        backend.session_handler = None

        await backend._process_factory(mock_process)

        mock_process.exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_exits_with_0_after_handler_completes(
        self, backend, session_info, mock_process
    ):
        """Should exit(0) after session handler completes normally."""
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        mock_process.exit.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_exits_with_0_after_handler_raises(
        self, backend, session_info, mock_process
    ):
        """Should exit(0) even when session handler raises an exception."""
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        mock_process.exit.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_pixel_dimensions_extracted(self, backend, session_info, mock_process):
        """Should extract pixel dimensions when available in term_size tuple."""
        mock_process.get_terminal_size.return_value = (132, 50, 1056, 800)
        backend._session_info_map["test-session-1"] = session_info
        handler = AsyncMock()
        backend.session_handler = handler

        await backend._process_factory(mock_process)

        pty_req = handler.call_args[0][1]
        assert pty_req.pixel_width == 1056
        assert pty_req.pixel_height == 800


class TestSandTrapSSHServer:
    """Tests for the SandTrapSSHServer connection and auth callbacks."""

    @pytest.fixture
    def auth_manager(self):
        return MagicMock()

    @pytest.fixture
    def server(self, auth_manager, backend):
        return SandTrapSSHServer(auth_manager, session_handler=None, backend=backend)

    def test_connection_made_stores_session_info(self, server, backend):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("10.0.0.1", 12345)

        server.connection_made(conn)

        assert server.session_info is not None
        assert server.session_info.source_ip == "10.0.0.1"
        assert server.session_info.source_port == 12345
        assert server.session_info.authenticated is False
        # Also stored in backend map
        assert len(backend._session_info_map) == 1

    def test_connection_made_unknown_peername(self, server):
        conn = MagicMock()
        conn.get_extra_info.return_value = None

        server.connection_made(conn)

        assert server.session_info.source_ip == "unknown"
        assert server.session_info.source_port == 0

    def test_password_auth_supported(self, server):
        assert server.password_auth_supported() is True

    def test_begin_auth_sets_username(self, server):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("1.2.3.4", 100)
        server.connection_made(conn)

        result = server.begin_auth("attacker")

        assert result is True
        assert server.session_info.username == "attacker"

    def test_validate_password_success(self, server, auth_manager):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("1.2.3.4", 100)
        server.connection_made(conn)
        auth_manager.validate.return_value = True

        result = server.validate_password("root", "toor")

        assert result is True
        assert server.session_info.authenticated is True
        assert server.session_info.failed_attempts == 0

    def test_validate_password_failure_increments_attempts(self, server, auth_manager):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("1.2.3.4", 100)
        server.connection_made(conn)
        auth_manager.validate.return_value = False

        server.validate_password("root", "wrong")
        server.validate_password("root", "wrong2")

        assert server.session_info.authenticated is False
        assert server.session_info.failed_attempts == 2

    def test_validate_password_no_connection_id(self, server):
        """Should return False if called before connection_made."""
        result = server.validate_password("root", "pass")
        assert result is False

    def test_connection_lost_cleans_up(self, server, auth_manager):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("1.2.3.4", 100)
        server.connection_made(conn)
        cid = server.connection_id

        server.connection_lost(None)

        auth_manager.cleanup_connection.assert_called_once_with(cid)

    def test_connection_lost_with_exception(self, server, auth_manager):
        conn = MagicMock()
        conn.get_extra_info.return_value = ("1.2.3.4", 100)
        server.connection_made(conn)

        server.connection_lost(ConnectionError("reset"))

        auth_manager.cleanup_connection.assert_called_once()


class TestAsyncSSHBackendStart:
    """Tests for backend start/stop and listen configuration."""

    @pytest.mark.asyncio
    async def test_start_raises_if_no_host_key(self, mock_config):
        mock_config.server.host_key_path.exists.return_value = False
        backend = AsyncSSHBackend(mock_config)

        with pytest.raises(RuntimeError, match="SSH host key not found"):
            await backend.start()

    @pytest.mark.asyncio
    async def test_start_uses_process_factory(self, backend):
        """Verify asyncssh.listen is called with process_factory, not session_factory."""
        with patch("sandtrap.server.asyncssh_backend.asyncssh.listen", new_callable=AsyncMock) as mock_listen:
            mock_listen.return_value = MagicMock()
            await backend.start()

            mock_listen.assert_called_once()
            call_kwargs = mock_listen.call_args[1]
            assert "process_factory" in call_kwargs
            assert "session_factory" not in call_kwargs
            assert call_kwargs["process_factory"].__func__ is AsyncSSHBackend._process_factory
            assert call_kwargs["encoding"] is None

    @pytest.mark.asyncio
    async def test_stop_closes_server(self, backend):
        mock_server = MagicMock()
        mock_server.wait_closed = AsyncMock()
        backend._server = mock_server

        await backend.stop()

        mock_server.close.assert_called_once()
        mock_server.wait_closed.assert_called_once()
        assert backend._server is None

    @pytest.mark.asyncio
    async def test_stop_noop_when_no_server(self, backend):
        """Stop should be safe to call when server is not running."""
        await backend.stop()  # Should not raise

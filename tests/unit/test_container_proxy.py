"""
Unit tests for ContainerProxy I/O proxying.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes.server.backend import PTYRequest
from hermes.session.proxy import ContainerProxy





@pytest.fixture
def proxy(mock_container, pty_request, mock_process):
    return ContainerProxy(
        container=mock_container,
        pty_request=pty_request,
        process=mock_process,
        session_id="test-proxy-session",
    )


class TestContainerProxyInit:
    """Tests for ContainerProxy initialization."""

    def test_stores_container(self, proxy, mock_container):
        assert proxy.container is mock_container

    def test_stores_pty_request(self, proxy, pty_request):
        assert proxy.pty_request is pty_request

    def test_stores_process(self, proxy, mock_process):
        assert proxy.process is mock_process

    def test_stores_session_id(self, proxy):
        assert proxy.session_id == "test-proxy-session"

    def test_initial_state(self, proxy):
        assert proxy._running is False
        assert proxy.exec_socket is None
        assert proxy.ssh_to_container_task is None
        assert proxy.container_to_ssh_task is None


class TestContainerProxyStart:
    """Tests for starting the proxy and creating Docker exec."""

    @pytest.mark.asyncio
    async def test_start_creates_exec_with_pty(self, proxy, mock_container):
        """Start should create Docker exec with correct PTY environment."""
        mock_socket = MagicMock()
        mock_container.exec_run.return_value = MagicMock(output=mock_socket)

        # Patch the streaming tasks to complete immediately
        with patch.object(proxy, "_ssh_to_container", new_callable=AsyncMock):
            with patch.object(proxy, "_container_to_ssh", new_callable=AsyncMock):
                await proxy.start()

        mock_container.exec_run.assert_called_once_with(
            cmd="/bin/bash",
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
            socket=True,
            user="root",
            workdir="/root",
            environment={
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "40",
            },
        )

    @pytest.mark.asyncio
    async def test_start_sets_socket_nonblocking(self, proxy, mock_container):
        # Create a real socket mock that tracks setblocking calls
        class SocketMock:
            def __init__(self):
                self.blocking = True

            def setblocking(self, flag):
                self.blocking = flag

        # exec_run().output is a SocketIO wrapper with ._sock attribute
        raw_sock = SocketMock()
        socket_io = type('SocketIO', (), {'_sock': raw_sock})()
        mock_container.exec_run.return_value = MagicMock(output=socket_io)

        with patch.object(proxy, "_ssh_to_container", new_callable=AsyncMock):
            with patch.object(proxy, "_container_to_ssh", new_callable=AsyncMock):
                await proxy.start()

        # Verify socket was extracted and marked non-blocking
        assert proxy.exec_socket is raw_sock
        assert proxy.exec_socket.blocking is False

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, proxy, mock_container):
        mock_container.exec_run.return_value = MagicMock(output=MagicMock())

        with patch.object(proxy, "_ssh_to_container", new_callable=AsyncMock):
            with patch.object(proxy, "_container_to_ssh", new_callable=AsyncMock):
                await proxy.start()

        assert proxy._running is True

    @pytest.mark.asyncio
    async def test_start_raises_on_exec_failure(self, proxy, mock_container):
        mock_container.exec_run.side_effect = Exception("container not running")

        with pytest.raises(RuntimeError, match="Docker exec creation failed"):
            await proxy.start()


class TestContainerProxyStop:
    """Tests for stopping the proxy and cleaning up."""

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, proxy):
        proxy._running = True

        async def cancelled_coro():
            raise asyncio.CancelledError

        task1 = asyncio.ensure_future(cancelled_coro())
        task2 = asyncio.ensure_future(cancelled_coro())

        proxy.ssh_to_container_task = task1
        proxy.container_to_ssh_task = task2

        mock_socket = MagicMock()
        proxy.exec_socket = mock_socket

        await proxy.stop()

        mock_socket.close.assert_called_once()
        assert proxy._running is False

    @pytest.mark.asyncio
    async def test_stop_noop_when_not_running(self, proxy):
        """Stop should be safe when proxy was never started."""
        await proxy.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_handles_socket_close_error(self, proxy):
        """Stop should not raise if socket close fails."""
        proxy._running = True
        proxy.exec_socket = MagicMock()
        proxy.exec_socket.close.side_effect = OSError("already closed")

        await proxy.stop()  # Should not raise


class TestContainerProxyResize:
    """Tests for terminal resize handling."""

    @pytest.mark.asyncio
    async def test_handle_resize_logs_without_error(self, proxy):
        """Resize handler should complete without error (currently a no-op)."""
        await proxy.handle_resize(200, 50)  # Should not raise


class TestContainerProxyWaitCompletion:
    """Tests for wait_completion."""

    @pytest.mark.asyncio
    async def test_wait_completion_returns_on_shutdown_event(self, proxy):
        """wait_completion should return once _shutdown_event is set."""
        # Set the event in a short delay
        async def set_event():
            await asyncio.sleep(0.01)
            proxy._shutdown_event.set()

        asyncio.create_task(set_event())
        await asyncio.wait_for(proxy.wait_completion(), timeout=1.0)


class TestSSHToContainer:
    """Tests for the _ssh_to_container streaming task."""

    @pytest.mark.asyncio
    async def test_ssh_disconnect_sets_shutdown(self, proxy, mock_process):
        """When stdin returns empty data, shutdown event should be set."""
        proxy._running = True
        proxy.exec_socket = MagicMock()
        mock_process.stdin.read = AsyncMock(return_value=b"")

        await proxy._ssh_to_container()

        assert proxy._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_broken_pipe_sets_shutdown(self, proxy, mock_process):
        """BrokenPipeError during write should set shutdown event."""
        proxy._running = True
        proxy.exec_socket = MagicMock()
        mock_process.stdin.read = AsyncMock(return_value=b"data")

        loop = asyncio.get_event_loop()
        with patch.object(loop, "sock_sendall", side_effect=BrokenPipeError):
            await proxy._ssh_to_container()

        assert proxy._shutdown_event.is_set()


class TestContainerToSSH:
    """Tests for the _container_to_ssh streaming task."""

    @pytest.mark.asyncio
    async def test_container_end_sets_shutdown(self, proxy, mock_process):
        """When exec socket returns empty, shutdown event should be set."""
        proxy._running = True
        proxy.exec_socket = MagicMock()

        loop = asyncio.get_event_loop()
        with patch.object(loop, "sock_recv", new_callable=AsyncMock, return_value=b""):
            await proxy._container_to_ssh()

        assert proxy._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_data_written_to_process_stdout(self, proxy, mock_process):
        """Data from container should be written to process.stdout."""
        proxy._running = True
        proxy.exec_socket = MagicMock()

        call_count = 0

        async def fake_recv(sock, size):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"hello from container"
            return b""

        loop = asyncio.get_event_loop()
        with patch.object(loop, "sock_recv", side_effect=fake_recv):
            await proxy._container_to_ssh()

        mock_process.stdout.write.assert_called_with(b"hello from container")


class TestContainerProxyRecorder:
    """Tests for recorder integration in ContainerProxy."""

    def test_recorder_defaults_to_none(self, proxy):
        assert proxy.recorder is None

    def test_recorder_stored(self, mock_container, pty_request, mock_process):
        recorder = MagicMock()
        p = ContainerProxy(
            container=mock_container,
            pty_request=pty_request,
            process=mock_process,
            session_id="test-rec",
            recorder=recorder,
        )
        assert p.recorder is recorder

    @pytest.mark.asyncio
    async def test_record_input_called(self, mock_container, pty_request, mock_process):
        """Recorder.record_input should be called with data from SSH stdin."""
        recorder = MagicMock()
        p = ContainerProxy(
            container=mock_container,
            pty_request=pty_request,
            process=mock_process,
            session_id="test-rec",
            recorder=recorder,
        )
        p._running = True
        p.exec_socket = MagicMock()

        call_count = 0

        async def fake_read(size):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"user input"
            return b""

        mock_process.stdin.read = fake_read

        loop = asyncio.get_event_loop()
        with patch.object(loop, "sock_sendall", new_callable=AsyncMock):
            await p._ssh_to_container()

        recorder.record_input.assert_called_with(b"user input")

    @pytest.mark.asyncio
    async def test_record_output_called(self, mock_container, pty_request, mock_process):
        """Recorder.record_output should be called with data from container."""
        recorder = MagicMock()
        p = ContainerProxy(
            container=mock_container,
            pty_request=pty_request,
            process=mock_process,
            session_id="test-rec",
            recorder=recorder,
        )
        p._running = True
        p.exec_socket = MagicMock()

        call_count = 0

        async def fake_recv(sock, size):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"container output"
            return b""

        loop = asyncio.get_event_loop()
        with patch.object(loop, "sock_recv", side_effect=fake_recv):
            await p._container_to_ssh()

        recorder.record_output.assert_called_with(b"container output")

    @pytest.mark.asyncio
    async def test_record_resize_called(self, mock_container, pty_request, mock_process):
        """Recorder.record_resize should be called from handle_resize."""
        recorder = MagicMock()
        p = ContainerProxy(
            container=mock_container,
            pty_request=pty_request,
            process=mock_process,
            session_id="test-rec",
            recorder=recorder,
        )
        await p.handle_resize(200, 50)
        recorder.record_resize.assert_called_once_with(200, 50)

    @pytest.mark.asyncio
    async def test_no_recorder_no_error(self, proxy, mock_process):
        """Proxy should work fine without a recorder."""
        proxy._running = True
        proxy.exec_socket = MagicMock()
        mock_process.stdin.read = AsyncMock(return_value=b"")

        await proxy._ssh_to_container()  # should not raise

"""
Unit tests for the container_session_handler in __main__.py.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sandtrap.__main__ import container_session_handler
from sandtrap.server.backend import PTYRequest, SessionInfo


@pytest.fixture
def session_info():
    return SessionInfo(
        session_id="handler-test-1",
        username="root",
        source_ip="10.0.0.5",
        source_port=9999,
        authenticated=True,
    )


@pytest.fixture
def pty_request():
    return PTYRequest(term_type="xterm", width=80, height=24)


@pytest.fixture
def mock_process():
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stderr = MagicMock()
    process.exit = MagicMock()
    return process


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.allocate = AsyncMock()
    pool.release = AsyncMock()
    return pool


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.id = "deadbeef1234"
    return container


class TestContainerSessionHandler:
    """Tests for the top-level container_session_handler."""

    @pytest.mark.asyncio
    async def test_allocates_and_releases_container(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """Should allocate a container and release it after proxy completes."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        mock_pool.allocate.assert_called_once_with("handler-test-1")
        mock_pool.release.assert_called_once_with("handler-test-1")

    @pytest.mark.asyncio
    async def test_creates_proxy_with_process(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """Should create ContainerProxy with the process object (not ssh_session)."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        MockProxy.assert_called_once_with(
            container=mock_container,
            pty_request=pty_request,
            process=mock_process,
            session_id="handler-test-1",
        )

    @pytest.mark.asyncio
    async def test_starts_and_waits_proxy(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """Should call proxy.start() then proxy.wait_completion()."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        proxy_instance.start.assert_called_once()
        proxy_instance.wait_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_stops_proxy_in_finally(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """Proxy.stop() should always be called during cleanup."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        proxy_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_allocation_failure_writes_error(
        self, session_info, pty_request, mock_process, mock_pool
    ):
        """Should write error to process.stdout when allocation fails."""
        mock_pool.allocate.side_effect = RuntimeError("pool exhausted")

        await container_session_handler(
            session_info, pty_request, mock_process, mock_pool
        )

        mock_process.stdout.write.assert_called_once()
        written = mock_process.stdout.write.call_args[0][0]
        assert b"Container allocation failed" in written

    @pytest.mark.asyncio
    async def test_allocation_failure_still_releases(
        self, session_info, pty_request, mock_process, mock_pool
    ):
        """Should not call release if allocation itself failed (no container)."""
        mock_pool.allocate.side_effect = RuntimeError("pool exhausted")

        await container_session_handler(
            session_info, pty_request, mock_process, mock_pool
        )

        mock_pool.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_proxy_start_failure_releases_container(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """If proxy.start() fails, container should still be released."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            proxy_instance.start.side_effect = RuntimeError("exec failed")
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        mock_pool.release.assert_called_once_with("handler-test-1")

    @pytest.mark.asyncio
    async def test_no_set_container_proxy_call(
        self, session_info, pty_request, mock_process, mock_pool, mock_container
    ):
        """Should not call set_container_proxy (removed in phase 4 fix)."""
        mock_pool.allocate.return_value = mock_container

        with patch(
            "sandtrap.__main__.ContainerProxy"
        ) as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance

            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )

        # The old code called ssh_session.set_container_proxy — verify it's gone
        assert not hasattr(mock_process, "set_container_proxy") or \
            not mock_process.set_container_proxy.called

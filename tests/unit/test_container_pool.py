"""
Unit tests for ContainerPool.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes.config import ContainerPoolConfig
from hermes.container.pool import ContainerPool


def _mock_container(container_id: str = "abc123456789") -> MagicMock:
    c = MagicMock()
    c.id = container_id
    c.stop = MagicMock()
    c.start = MagicMock()
    c.reload = MagicMock()
    return c


@pytest.fixture
def pool_config() -> ContainerPoolConfig:
    return ContainerPoolConfig(
        size=2,
        image="test-target:latest",
        spawn_timeout=5,
    )


@pytest.fixture
def docker_client() -> MagicMock:
    client = MagicMock()
    # Each call to containers.create returns a fresh mock container
    client.containers.create = MagicMock(side_effect=lambda **kw: _mock_container())
    return client


@pytest.fixture
def pool(docker_client: MagicMock, pool_config: ContainerPoolConfig) -> ContainerPool:
    return ContainerPool(docker_client, pool_config)


class TestContainerPoolInit:
    def test_initial_state(self, pool: ContainerPool):
        assert pool.ready_pool == []
        assert pool.active_sessions == {}
        assert pool.stopped_containers == []
        assert pool._shutdown is False

    def test_stores_config(self, pool: ContainerPool, pool_config: ContainerPoolConfig):
        assert pool.config is pool_config


class TestContainerPoolInitialize:
    @pytest.mark.asyncio
    async def test_creates_pool_size_containers(self, pool: ContainerPool, docker_client: MagicMock):
        await pool.initialize()
        assert len(pool.ready_pool) == 2

    @pytest.mark.asyncio
    async def test_initialize_failure_cleans_up(self, pool: ContainerPool, docker_client: MagicMock):
        docker_client.containers.create.side_effect = Exception("docker down")
        with pytest.raises(RuntimeError, match="Container pool initialization failed"):
            await pool.initialize()
        assert pool.ready_pool == []


class TestContainerPoolAllocate:
    @pytest.mark.asyncio
    async def test_allocate_from_ready_pool(self, pool: ContainerPool):
        container = _mock_container("ready1")
        pool.ready_pool.append(container)
        result = await pool.allocate("session-1")
        assert result is container
        assert pool.ready_pool == []
        assert pool.active_sessions["session-1"] is container

    @pytest.mark.asyncio
    async def test_allocate_creates_on_demand_when_empty(self, pool: ContainerPool, docker_client: MagicMock):
        assert pool.ready_pool == []
        result = await pool.allocate("session-1")
        assert result is not None
        assert "session-1" in pool.active_sessions

    @pytest.mark.asyncio
    async def test_allocate_failure_raises(self, pool: ContainerPool, docker_client: MagicMock):
        docker_client.containers.create.side_effect = Exception("no resources")
        with pytest.raises(RuntimeError, match="Container allocation failed"):
            await pool.allocate("session-1")

    @pytest.mark.asyncio
    async def test_allocate_spawns_replacement(self, pool: ContainerPool):
        container = _mock_container()
        pool.ready_pool.append(container)
        with patch.object(pool, "_spawn_replacement", new_callable=AsyncMock) as mock_spawn:
            await pool.allocate("s1")
            # Give the created task a chance to run
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_reload_failure_does_not_block(self, pool: ContainerPool):
        container = _mock_container()
        container.reload.side_effect = Exception("reload failed")
        pool.ready_pool.append(container)
        result = await pool.allocate("s1")
        assert result is container


class TestContainerPoolRelease:
    @pytest.mark.asyncio
    async def test_release_stops_container(self, pool: ContainerPool):
        container = _mock_container()
        pool.active_sessions["s1"] = container
        await pool.release("s1")
        container.stop.assert_called_once()
        assert "s1" not in pool.active_sessions

    @pytest.mark.asyncio
    async def test_release_tracks_stopped_container(self, pool: ContainerPool):
        container = _mock_container()
        pool.active_sessions["s1"] = container
        await pool.release("s1")
        assert len(pool.stopped_containers) == 1
        assert pool.stopped_containers[0][0] is container
        assert isinstance(pool.stopped_containers[0][1], datetime)

    @pytest.mark.asyncio
    async def test_release_unknown_session_no_error(self, pool: ContainerPool):
        await pool.release("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_release_stop_failure_still_removes_session(self, pool: ContainerPool):
        container = _mock_container()
        container.stop.side_effect = Exception("stop failed")
        pool.active_sessions["s1"] = container
        await pool.release("s1")
        assert "s1" not in pool.active_sessions


class TestContainerPoolShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_stops_active_containers(self, pool: ContainerPool):
        c1 = _mock_container("active1")
        pool.active_sessions["s1"] = c1
        await pool.shutdown()
        c1.stop.assert_called_once()
        assert pool.active_sessions == {}
        assert pool._shutdown is True

    @pytest.mark.asyncio
    async def test_shutdown_stops_ready_containers(self, pool: ContainerPool):
        c1 = _mock_container("ready1")
        pool.ready_pool.append(c1)
        await pool.shutdown()
        c1.stop.assert_called_once()
        assert pool.ready_pool == []

    @pytest.mark.asyncio
    async def test_shutdown_preserves_stopped_containers(self, pool: ContainerPool):
        c1 = _mock_container()
        pool.active_sessions["s1"] = c1
        await pool.shutdown()
        assert len(pool.stopped_containers) >= 1

    @pytest.mark.asyncio
    async def test_shutdown_tolerates_stop_failure(self, pool: ContainerPool):
        c1 = _mock_container()
        c1.stop.side_effect = Exception("fail")
        pool.active_sessions["s1"] = c1
        await pool.shutdown()  # should not raise


class TestContainerPoolSpawnReplacement:
    @pytest.mark.asyncio
    async def test_spawn_replacement_adds_to_pool(self, pool: ContainerPool, docker_client: MagicMock):
        await pool._spawn_replacement()
        assert len(pool.ready_pool) == 1

    @pytest.mark.asyncio
    async def test_spawn_replacement_skipped_during_shutdown(self, pool: ContainerPool, docker_client: MagicMock):
        pool._shutdown = True
        await pool._spawn_replacement()
        assert len(pool.ready_pool) == 0

    @pytest.mark.asyncio
    async def test_spawn_replacement_failure_does_not_raise(self, pool: ContainerPool, docker_client: MagicMock):
        docker_client.containers.create.side_effect = Exception("fail")
        await pool._spawn_replacement()  # should not raise


class TestContainerPoolHelpers:
    def test_generate_container_name_format(self, pool: ContainerPool):
        name = pool._generate_container_name()
        assert name.startswith("hermes-target-")

    def test_generate_container_name_with_session_id(self, pool: ContainerPool):
        name = pool._generate_container_name("abcdefghij")
        assert "abcdefgh" in name

    def test_get_stats(self, pool: ContainerPool):
        pool.ready_pool = [_mock_container()]
        pool.active_sessions = {"s1": _mock_container()}
        stats = pool.get_stats()
        assert stats["ready"] == 1
        assert stats["active"] == 1
        assert stats["stopped"] == 0
        assert stats["total"] == 2

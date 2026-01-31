"""
Integration tests for ContainerPool lifecycle.

These tests verify the full allocate → use → release → shutdown lifecycle
using mock Docker clients that simulate realistic container behavior.
Tests marked @pytest.mark.integration require a real Docker daemon.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from hermes.config import ContainerPoolConfig
from hermes.container.pool import ContainerPool


def _fake_container(cid: str = "abc123") -> MagicMock:
    """Create a mock container that behaves like a real Docker container."""
    c = MagicMock()
    c.id = cid + "0" * (12 - len(cid))
    c.stop = MagicMock()
    c.start = MagicMock()
    c.reload = MagicMock()
    c.status = "running"
    return c


def _docker_client_that_creates_containers() -> MagicMock:
    """Docker client where each create() returns a unique container."""
    counter = [0]

    def create(**kwargs):
        counter[0] += 1
        return _fake_container(f"container-{counter[0]:04d}")

    client = MagicMock()
    client.containers.create = MagicMock(side_effect=create)
    return client


class TestPoolInitializeAndAllocate:
    """Test the init → allocate → release full lifecycle."""

    @pytest.fixture
    def config(self) -> ContainerPoolConfig:
        return ContainerPoolConfig(size=3, image="test:latest")

    @pytest.fixture
    def client(self) -> MagicMock:
        return _docker_client_that_creates_containers()

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, config, client):
        """Initialize pool, allocate all containers, release them, shutdown."""
        pool = ContainerPool(client, config)
        await pool.initialize()

        assert len(pool.ready_pool) == 3
        assert pool.get_stats()["ready"] == 3

        # Allocate all 3
        containers = []
        for i in range(3):
            c = await pool.allocate(f"session-{i}")
            containers.append(c)

        assert pool.get_stats()["active"] == 3
        assert pool.get_stats()["ready"] == 0

        # Release all 3
        for i in range(3):
            await pool.release(f"session-{i}")

        assert pool.get_stats()["active"] == 0
        assert pool.get_stats()["stopped"] == 3

        # All containers had .stop() called
        for c in containers:
            c.stop.assert_called_once()

        # Shutdown
        await pool.shutdown()
        assert pool._shutdown is True

    @pytest.mark.asyncio
    async def test_allocate_beyond_pool_size_creates_on_demand(self, config, client):
        """When pool is exhausted, allocate creates containers on-demand."""
        pool = ContainerPool(client, config)
        await pool.initialize()

        # Drain the pool
        for i in range(3):
            await pool.allocate(f"s-{i}")

        # Clear replacement tasks
        await asyncio.sleep(0.05)

        # Pool is now empty; next allocate should create on-demand
        # (replacement spawns happen in background too)
        pool.ready_pool.clear()
        c = await pool.allocate("s-extra")
        assert c is not None
        assert "s-extra" in pool.active_sessions

    @pytest.mark.asyncio
    async def test_release_then_shutdown_preserves_all_stopped(self, config, client):
        """Stopped containers from both release and shutdown are preserved."""
        pool = ContainerPool(client, config)
        await pool.initialize()

        # Allocate and release one
        await pool.allocate("s1")
        await pool.release("s1")

        # Shutdown stops the remaining 2 ready containers
        await pool.shutdown()

        # 1 released + 2 from shutdown = 3 stopped
        # Plus replacement containers that may have spawned
        assert pool.get_stats()["stopped"] >= 3


class TestPoolConcurrentAllocations:
    """Test concurrent allocation behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_allocations(self):
        """Multiple allocations happening concurrently should not corrupt state."""
        config = ContainerPoolConfig(size=5, image="test:latest")
        client = _docker_client_that_creates_containers()
        pool = ContainerPool(client, config)
        await pool.initialize()

        # Concurrently allocate all 5
        tasks = [pool.allocate(f"session-{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert pool.get_stats()["active"] == 5

        # All should be unique containers
        container_ids = [c.id for c in results]
        assert len(set(container_ids)) == 5

    @pytest.mark.asyncio
    async def test_concurrent_release(self):
        """Multiple releases happening concurrently."""
        config = ContainerPoolConfig(size=3, image="test:latest")
        client = _docker_client_that_creates_containers()
        pool = ContainerPool(client, config)
        await pool.initialize()

        for i in range(3):
            await pool.allocate(f"s-{i}")

        tasks = [pool.release(f"s-{i}") for i in range(3)]
        await asyncio.gather(*tasks)

        assert pool.get_stats()["active"] == 0
        assert pool.get_stats()["stopped"] == 3


class TestPoolErrorRecovery:
    """Test pool behavior under error conditions."""

    @pytest.mark.asyncio
    async def test_container_stop_failure_doesnt_block_pool(self):
        """If container.stop() fails, the pool should keep working."""
        config = ContainerPoolConfig(size=2, image="test:latest")
        client = _docker_client_that_creates_containers()
        pool = ContainerPool(client, config)
        await pool.initialize()

        c = await pool.allocate("s1")
        c.stop.side_effect = Exception("Docker daemon unreachable")

        # Release should not raise even though stop fails
        await pool.release("s1")
        assert "s1" not in pool.active_sessions

        # Pool still works for new allocations
        await asyncio.sleep(0.05)
        c2 = await pool.allocate("s2")
        assert c2 is not None

    @pytest.mark.asyncio
    async def test_initialization_failure_leaves_clean_state(self):
        """If initialization fails, pool should be in a clean state."""
        config = ContainerPoolConfig(size=3, image="test:latest")
        client = MagicMock()
        client.containers.create.side_effect = Exception("image not found")

        pool = ContainerPool(client, config)
        with pytest.raises(RuntimeError):
            await pool.initialize()

        assert pool.ready_pool == []
        assert pool.active_sessions == {}

    @pytest.mark.asyncio
    async def test_shutdown_tolerates_mixed_failures(self):
        """Shutdown should handle some containers failing to stop."""
        config = ContainerPoolConfig(size=3, image="test:latest")
        client = _docker_client_that_creates_containers()
        pool = ContainerPool(client, config)
        await pool.initialize()

        # Allocate all, make one fail on stop
        for i in range(3):
            await pool.allocate(f"s-{i}")

        pool.active_sessions["s-1"].stop.side_effect = Exception("timeout")

        await pool.shutdown()
        # Should complete without raising
        assert pool._shutdown is True
        assert pool.active_sessions == {}

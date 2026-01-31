"""
Real Docker integration tests for ContainerPool.

These tests require a real Docker daemon and the sandtrap-target-ubuntu image.
Run with: pytest tests/integration/test_container_pool_docker.py -v -m docker

To ensure you have the required image:
  docker build -f docker/Dockerfile -t sandtrap-target-ubuntu:latest docker/

NOTE: These tests are designed to run in isolation or with adequate delays between
test runs. If running multiple times rapidly, clean up Docker containers first:
  docker container rm -f $(docker ps -aq --filter name=sandtrap)
"""

import asyncio
from pathlib import Path

import docker
import pytest

from sandtrap.config import ContainerPoolConfig
from sandtrap.container.pool import ContainerPool


@pytest.fixture(scope="session")
def docker_client() -> docker.DockerClient:
    """Get Docker client or skip tests if unavailable."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture(scope="session")
def target_image(docker_client: docker.DockerClient) -> str:
    """Ensure the target image exists."""
    image_name = "sandtrap-target-ubuntu:latest"
    try:
        docker_client.images.get(image_name)
        return image_name
    except docker.errors.ImageNotFound:
        pytest.skip(
            f"Image {image_name} not found. "
            f"Build with: docker build -f docker/Dockerfile -t {image_name} docker/"
        )


@pytest.mark.docker
class TestContainerPoolRealDocker:
    """Real Docker integration tests for container pool lifecycle."""

    @pytest.fixture
    def pool_config(self, target_image: str) -> ContainerPoolConfig:
        # Use a smaller pool for Docker tests to avoid naming conflicts
        # Override security config to use valid Docker options
        from sandtrap.config import ContainerSecurityConfig

        config = ContainerPoolConfig(
            size=1,
            image=target_image,
            spawn_timeout=30,
        )
        # Fix seccomp option which is not valid in the default config
        config.security.security_opt = ["no-new-privileges:true"]
        return config

    @pytest.fixture
    async def pool(
        self, docker_client: docker.DockerClient, pool_config: ContainerPoolConfig, request
    ):
        """Create and cleanup a real container pool."""
        import time
        import uuid

        # Use unique suffix to avoid naming conflicts
        test_id = f"{request.node.name}-{uuid.uuid4().hex[:8]}"

        # Pre-cleanup: remove any containers
        def cleanup_containers():
            try:
                containers = docker_client.containers.list(
                    all=True,
                    filters={"name": "sandtrap-target-"},
                )
                for c in containers:
                    try:
                        c.remove(force=True)
                    except Exception:
                        pass
            except Exception:
                pass

        cleanup_containers()

        # Small delay to ensure cleanup is complete
        await asyncio.sleep(0.5)

        pool = ContainerPool(docker_client, pool_config)
        yield pool

        # Cleanup: shutdown the pool
        try:
            await pool.shutdown()
        except Exception:
            pass

        # Remove any leftover containers
        cleanup_containers()

    @pytest.mark.asyncio
    async def test_initialize_creates_real_containers(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Initialize creates real Docker containers."""
        await pool.initialize()

        assert len(pool.ready_pool) == 1
        containers = pool.ready_pool

        # Verify containers actually exist in Docker
        for c in containers:
            assert c.id in [c.id for c in docker_client.containers.list()]
            # Reload to get fresh status
            c.reload()
            assert c.status == "running"

    @pytest.mark.asyncio
    async def test_allocate_returns_running_container(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Allocate returns a real running container."""
        await pool.initialize()

        container = await pool.allocate("test-session-001")

        # Verify it's a real Docker container
        assert container.id in [c.id for c in docker_client.containers.list()]
        assert container.status == "running"

        # Verify we can inspect it
        container.reload()
        assert container.status == "running"

    @pytest.mark.asyncio
    async def test_release_stops_container(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Release actually stops the container in Docker."""
        await pool.initialize()
        container = await pool.allocate("test-session-001")
        container_id = container.id

        await pool.release("test-session-001")

        # Verify container is stopped
        released = docker_client.containers.get(container_id)
        assert released.status == "exited"

    @pytest.mark.asyncio
    async def test_allocate_on_demand_when_pool_empty(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """When pool is empty, allocate creates container on-demand."""
        await pool.initialize()

        # Drain the ready pool
        for i in range(2):
            await pool.allocate(f"session-{i}")

        # Wait for any background spawning
        await asyncio.sleep(0.5)

        # Clear ready pool to force on-demand
        pool.ready_pool.clear()

        # This allocation should create on-demand
        container = await pool.allocate("session-on-demand")

        assert container is not None
        assert container.status == "running"
        assert container.id in [c.id for c in docker_client.containers.list()]

    @pytest.mark.asyncio
    async def test_concurrent_allocations_with_real_containers(
        self, pool: ContainerPool
    ):
        """Multiple concurrent allocations work with real containers."""
        await pool.initialize()

        # Allocate all at once
        tasks = [pool.allocate(f"concurrent-{i}") for i in range(2)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 2
        assert all(c.status == "running" for c in results)

        # All have unique IDs
        container_ids = [c.id for c in results]
        assert len(set(container_ids)) == 2

    @pytest.mark.asyncio
    async def test_pool_handles_container_restart(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """If a container is manually stopped, pool can still release it."""
        await pool.initialize()
        container = await pool.allocate("test-session-001")
        container_id = container.id

        # Manually stop the container from outside the pool
        docker_container = docker_client.containers.get(container_id)
        docker_container.stop()

        # Pool release should handle gracefully
        await pool.release("test-session-001")

        # Verify it's in stopped_containers
        assert len(pool.stopped_containers) > 0

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_real_containers(
        self, pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Complete lifecycle: init → allocate → use → release → shutdown."""
        # Initialize
        await pool.initialize()
        pool_size = pool.get_stats()["ready"]
        assert pool_size == 1  # pool_config.size is 1

        # Allocate all
        containers = []
        for i in range(pool_size):
            c = await pool.allocate(f"lifecycle-{i}")
            containers.append(c)

        assert pool.get_stats()["active"] == pool_size
        assert pool.get_stats()["ready"] == 0

        # Verify all running
        running = docker_client.containers.list()
        for c in containers:
            assert c.id in [rc.id for rc in running]

        # Release all
        for i in range(pool_size):
            await pool.release(f"lifecycle-{i}")

        assert pool.get_stats()["active"] == 0
        assert pool.get_stats()["stopped"] >= pool_size

        # Shutdown
        await pool.shutdown()
        assert pool._shutdown is True

        # All should be stopped
        for container in containers:
            docker_container = docker_client.containers.get(container.id)
            docker_container.reload()
            assert docker_container.status == "exited"

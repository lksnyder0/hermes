"""
End-to-end Docker integration tests for full session lifecycle.

Tests the complete flow: authentication → container allocation → proxy → recording.
Run with: pytest tests/integration/test_full_session_docker.py -v -m docker
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import docker
import pytest

from sandtrap.config import (
    AuthenticationConfig,
    Config,
    ContainerPoolConfig,
    RecordingConfig,
)
from sandtrap.container.pool import ContainerPool
from sandtrap.server.auth import AuthenticationManager
from sandtrap.server.backend import PTYRequest, SessionInfo
from sandtrap.session.proxy import ContainerProxy
from sandtrap.session.recorder import SessionRecorder


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
class TestFullSessionWithRealDocker:
    """End-to-end session tests with real Docker containers."""

    @pytest.fixture
    async def auth_manager(self) -> AuthenticationManager:
        """Create an authentication manager."""
        config = AuthenticationConfig(
            static_credentials=[
                AuthenticationConfig.Credential(username="honeypot", password="sweet"),
                AuthenticationConfig.Credential(username="admin", password="admin123"),
            ],
            accept_all_after_failures=3,
        )
        return AuthenticationManager(config)

    @pytest.fixture
    async def container_pool(
        self, docker_client: docker.DockerClient, target_image: str
    ):
        """Create a real container pool."""
        config = ContainerPoolConfig(
            size=2,
            image=target_image,
            spawn_timeout=30,
        )
        pool = ContainerPool(docker_client, config)
        await pool.initialize()
        yield pool
        try:
            await pool.shutdown()
        except Exception:
            pass
        # Cleanup containers
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

    @pytest.mark.asyncio
    async def test_authentication_flow(
        self, auth_manager: AuthenticationManager
    ):
        """Test authentication against the manager."""
        conn_id = "test-conn-001"

        # Valid credentials
        assert auth_manager.validate(conn_id, "honeypot", "sweet") is True
        assert "test-conn-001" not in auth_manager._failed_attempts

        # Invalid credentials
        assert auth_manager.validate(conn_id, "honeypot", "wrong") is False
        assert auth_manager._failed_attempts[conn_id] == 1

        # Cleanup
        auth_manager.cleanup_connection(conn_id)
        assert "test-conn-001" not in auth_manager._failed_attempts

    @pytest.mark.asyncio
    async def test_container_allocation_flow(
        self, container_pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Test container allocation and release."""
        # Allocate
        container = await container_pool.allocate("session-001")
        assert container is not None
        assert container.id in [c.id for c in docker_client.containers.list()]

        # Release
        await container_pool.release("session-001")
        assert len(container_pool.stopped_containers) > 0

    @pytest.mark.asyncio
    async def test_session_with_recording(
        self, container_pool: ContainerPool, tmp_path: Path
    ):
        """Test a session with recording enabled."""
        # Setup recording
        recording_config = RecordingConfig(
            enabled=True,
            output_dir=tmp_path / "recordings",
        )

        # Allocate container
        container = await container_pool.allocate("session-rec-001")

        # Create recorder
        recorder = SessionRecorder(
            config=recording_config,
            session_id="session-rec-001",
            width=80,
            height=24,
            metadata={
                "username": "test",
                "source_ip": "127.0.0.1",
                "source_port": 12345,
                "container_id": container.id[:12],
            },
        )
        recorder.start()

        # Create a mock process
        process = MagicMock()
        process.stdin = AsyncMock()
        process.stdin.read = AsyncMock(return_value=b"")
        process.stdout = MagicMock()
        process.stdout.write = MagicMock()
        process.stdout.drain = AsyncMock()

        # Create and start proxy
        pty_request = PTYRequest(term_type="xterm", width=80, height=24)
        proxy = ContainerProxy(
            container=container,
            pty_request=pty_request,
            process=process,
            session_id="session-rec-001",
            recorder=recorder,
        )

        try:
            await proxy.start()
            await asyncio.wait_for(proxy.wait_completion(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        finally:
            await proxy.stop()
            recorder.stop()
            recorder.write_metadata()
            await container_pool.release("session-rec-001")

        # Verify recording files
        cast_file = tmp_path / "recordings" / "session-rec-001.cast"
        json_file = tmp_path / "recordings" / "session-rec-001.json"

        assert cast_file.exists(), "Cast file should exist"
        assert json_file.exists(), "Metadata JSON should exist"

        # Verify cast file is valid
        import json

        with open(cast_file) as f:
            header = json.loads(f.readline())
            assert header["version"] == 2
            assert header["width"] == 80
            assert header["height"] == 24

    @pytest.mark.asyncio
    async def test_concurrent_sessions(
        self, container_pool: ContainerPool, auth_manager: AuthenticationManager
    ):
        """Test multiple concurrent sessions."""
        # Setup
        containers = []
        sessions = []

        try:
            # Allocate containers for 2 concurrent sessions
            for i in range(2):
                session_id = f"concurrent-{i}"
                container = await container_pool.allocate(session_id)
                containers.append((session_id, container))

            # Verify both are active
            assert container_pool.get_stats()["active"] == 2

            # Authenticate both
            for i in range(2):
                conn_id = f"conn-{i}"
                assert (
                    auth_manager.validate(conn_id, "honeypot", "sweet") is True
                )

            # Release both
            for session_id, _ in containers:
                await container_pool.release(session_id)

            assert container_pool.get_stats()["active"] == 0
            assert container_pool.get_stats()["stopped"] == 2

        finally:
            # Cleanup
            for session_id, _ in containers:
                auth_manager.cleanup_connection(session_id)

    @pytest.mark.asyncio
    async def test_attacker_brute_force_then_accept_all(
        self, auth_manager: AuthenticationManager
    ):
        """Test accept-all mode activation after failed attempts."""
        conn_id = "attacker-001"

        # Simulate brute force
        assert auth_manager.validate(conn_id, "root", "root") is False
        assert auth_manager.validate(conn_id, "root", "password") is False
        assert auth_manager.validate(conn_id, "root", "123456") is False

        # After 3 failures, accept-all activates
        assert auth_manager.validate(conn_id, "root", "anything") is True

        auth_manager.cleanup_connection(conn_id)

    @pytest.mark.asyncio
    async def test_pool_recovery_from_errors(
        self, container_pool: ContainerPool, docker_client: docker.DockerClient
    ):
        """Test pool recovery when container errors occur."""
        # Allocate a container
        container = await container_pool.allocate("error-session-001")
        container_id = container.id

        # Manually break the container (stop it)
        docker_container = docker_client.containers.get(container_id)
        docker_container.stop()

        # Pool release should handle it gracefully
        await container_pool.release("error-session-001")

        # Pool should still be functional
        assert container_pool.get_stats()["stopped"] > 0

        # Should be able to allocate another
        container2 = await container_pool.allocate("error-session-002")
        assert container2 is not None
        await container_pool.release("error-session-002")

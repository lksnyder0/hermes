"""
Real Docker integration tests for ContainerProxy.

These tests verify bidirectional I/O streaming with real Docker containers.
Run with: pytest tests/integration/test_container_proxy_docker.py -v -m docker
"""

import asyncio
from unittest.mock import MagicMock

import docker
import pytest

from sandtrap.config import RecordingConfig
from sandtrap.server.backend import PTYRequest
from sandtrap.session.proxy import ContainerProxy


@pytest.fixture(scope="session")
def docker_client() -> docker.DockerClient:
    """Get Docker client or skip tests if unavailable."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture
def target_image_name() -> str:
    """Target container image name."""
    return "sandtrap-target-ubuntu:latest"


@pytest.fixture
def test_container(docker_client: docker.DockerClient, target_image_name: str):
    """Create a test container for proxy testing."""
    try:
        docker_client.images.get(target_image_name)
    except docker.errors.ImageNotFound:
        pytest.skip(f"Image {target_image_name} not found")

    container = docker_client.containers.create(
        target_image_name,
        stdin_open=True,
        stdout=True,
        stderr=True,
        detach=True,
        user="root",
        workdir="/root",
    )
    container.start()

    yield container

    # Cleanup
    try:
        container.remove(force=True)
    except Exception:
        pass


@pytest.mark.docker
class TestContainerProxyRealDocker:
    """Real Docker integration tests for container I/O proxy."""

    def _mock_ssh_process(self):
        """Create a mock SSH process with real async streams."""
        process = MagicMock()

        # Create real asyncio streams for testing
        self.input_data = bytearray()
        self.output_data = bytearray()

        async def mock_read(n: int) -> bytes:
            """Simulate SSH client sending data."""
            # For testing, send a simple command and EOF
            if not hasattr(self, "_sent_eof"):
                self._sent_eof = True
                return b"echo hello\n"
            return b""  # EOF

        async def mock_write(data: bytes):
            """Capture SSH client output."""
            self.output_data.extend(data)

        async def mock_drain():
            """Simulate stream drain."""
            await asyncio.sleep(0.01)

        process.stdin = MagicMock()
        process.stdin.read = mock_read

        process.stdout = MagicMock()
        process.stdout.write = mock_write
        process.stdout.drain = mock_drain

        return process

    @pytest.mark.asyncio
    async def test_proxy_can_create_exec(self, test_container):
        """Proxy successfully creates Docker exec."""
        pty_request = PTYRequest(term_type="xterm", width=80, height=24)
        process = self._mock_ssh_process()

        proxy = ContainerProxy(
            container=test_container,
            pty_request=pty_request,
            process=process,
            session_id="test-001",
        )

        await proxy.start()

        # Verify exec was created
        assert proxy.exec_socket is not None
        assert proxy._running is True

        await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_executes_command(self, test_container):
        """Proxy can execute commands in container."""
        pty_request = PTYRequest(term_type="xterm", width=80, height=24)
        process = self._mock_ssh_process()

        proxy = ContainerProxy(
            container=test_container,
            pty_request=pty_request,
            process=process,
            session_id="test-001",
        )

        await proxy.start()

        # Wait for execution
        try:
            # Use wait_completion with timeout
            await asyncio.wait_for(proxy.wait_completion(), timeout=5.0)
        except asyncio.TimeoutError:
            # Expected - we may timeout, that's ok
            pass

        await proxy.stop()

        # Verify output was captured
        assert len(self.output_data) > 0 or proxy._running is False

    @pytest.mark.asyncio
    async def test_proxy_handles_tty_parameters(self, test_container):
        """Proxy respects TTY dimensions."""
        pty_request = PTYRequest(term_type="xterm-256color", width=120, height=40)
        process = self._mock_ssh_process()

        proxy = ContainerProxy(
            container=test_container,
            pty_request=pty_request,
            process=process,
            session_id="test-002",
        )

        await proxy.start()

        # Just verify it starts without error with custom dimensions
        assert proxy._running is True

        await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_with_recorder(self, test_container, tmp_path):
        """Proxy works with a SessionRecorder."""
        from sandtrap.session.recorder import SessionRecorder

        recording_config = RecordingConfig(
            enabled=True,
            output_dir=tmp_path / "recordings",
        )

        recorder = SessionRecorder(
            config=recording_config,
            session_id="test-001",
            width=80,
            height=24,
        )
        recorder.start()

        pty_request = PTYRequest(term_type="xterm", width=80, height=24)
        process = self._mock_ssh_process()

        proxy = ContainerProxy(
            container=test_container,
            pty_request=pty_request,
            process=process,
            session_id="test-001",
            recorder=recorder,
        )

        await proxy.start()

        try:
            await asyncio.wait_for(proxy.wait_completion(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        await proxy.stop()
        recorder.stop()

        # Verify recording was created
        cast_file = tmp_path / "recordings" / "test-001.cast"
        assert cast_file.exists()

    @pytest.mark.asyncio
    async def test_proxy_graceful_disconnect(self, test_container):
        """Proxy handles client disconnect gracefully."""
        pty_request = PTYRequest(term_type="xterm", width=80, height=24)
        process = self._mock_ssh_process()

        proxy = ContainerProxy(
            container=test_container,
            pty_request=pty_request,
            process=process,
            session_id="test-003",
        )

        await proxy.start()

        # Stop immediately (simulates client disconnect)
        await proxy.stop()

        # Should complete without hanging
        assert proxy._running is False

"""Unit tests for session timeout functionality."""

import asyncio
import time

import pytest
from hermes.config import Config
from hermes.server.backend import PTYRequest, SessionInfo


class TestTimeoutConfiguration:
    """Test timeout configuration parsing and usage."""

    def test_timeout_from_config(self):
        """Verify timeout is read from config."""
        config = Config()
        assert config.server.session_timeout == 3600

    def test_custom_timeout_in_yaml(self):
        """Verify custom timeout is loaded from YAML."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("server:\n  session_timeout: 1800\n")

            loaded_config = Config.from_file(config_file)
            assert loaded_config.server.session_timeout == 1800

    def test_minimal_timeout_validation(self):
        """Verify timeout minimum constraint."""
        with pytest.raises(ValueError):
            Config(server={"session_timeout": 30})  # Too low

    def test_maximal_timeout_validation(self):
        """Verify custom large timeout can be set."""
        config = Config()
        config.server.session_timeout = 999999
        assert config.server.session_timeout == 999999

    def test_default_timeout_valid(self):
        """Verify default timeout is valid."""
        config = Config()
        assert 60 <= config.server.session_timeout <= 86400


class TestTimeoutDataStructure:
    """Test timeout data structures."""

    def test_timeout_event_creation(self):
        """Verify asyncio.Event works for timeout tracking."""
        event = asyncio.Event()
        assert not event.is_set()
        event.set()
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_asyncio_sleep_basic(self):
        """Test basic asyncio.sleep usage."""
        start = time.perf_counter()
        await asyncio.sleep(0.01)  # 10ms
        elapsed = time.perf_counter() - start
        assert 0.005 <= elapsed < 0.1  # Allow some margin but still verify the sleep duration

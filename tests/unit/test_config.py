"""
Unit tests for configuration loading and validation.
"""

import pytest
from pathlib import Path

from hermes.config import (
    AuthenticationConfig,
    Config,
    ContainerPoolConfig,
    ContainerSecurityConfig,
    DockerConfig,
    LoggingConfig,
    RecordingConfig,
    ServerConfig,
)


class TestServerConfig:
    def test_defaults(self):
        c = ServerConfig()
        assert c.host == "0.0.0.0"
        assert c.port == 2222
        assert c.max_concurrent_sessions == 10
        assert c.session_timeout == 3600

    def test_port_bounds(self):
        with pytest.raises(Exception):
            ServerConfig(port=0)
        with pytest.raises(Exception):
            ServerConfig(port=70000)

    def test_session_timeout_minimum(self):
        with pytest.raises(Exception):
            ServerConfig(session_timeout=10)


class TestAuthenticationConfig:
    def test_defaults(self):
        c = AuthenticationConfig()
        assert c.static_credentials == []
        assert c.accept_all_after_failures == 3

    def test_credentials(self):
        c = AuthenticationConfig(
            static_credentials=[
                AuthenticationConfig.Credential(username="u", password="p")
            ]
        )
        assert len(c.static_credentials) == 1
        assert c.static_credentials[0].username == "u"

    def test_accept_all_zero_disables(self):
        c = AuthenticationConfig(accept_all_after_failures=0)
        assert c.accept_all_after_failures == 0


class TestContainerSecurityConfig:
    def test_defaults(self):
        c = ContainerSecurityConfig()
        assert c.network_mode == "none"
        assert c.memory_limit == "256m"
        assert c.cpu_quota == 0.5
        assert c.pids_limit == 100

    def test_capabilities_defaults(self):
        c = ContainerSecurityConfig()
        assert c.capabilities.drop == ["ALL"]
        assert "CHOWN" in c.capabilities.add

    def test_cpu_quota_bounds(self):
        with pytest.raises(Exception):
            ContainerSecurityConfig(cpu_quota=0.01)
        with pytest.raises(Exception):
            ContainerSecurityConfig(cpu_quota=10.0)

    def test_pids_limit_minimum(self):
        with pytest.raises(Exception):
            ContainerSecurityConfig(pids_limit=5)


class TestContainerPoolConfig:
    def test_defaults(self):
        c = ContainerPoolConfig()
        assert c.size == 3
        assert c.image == "hermes-target-ubuntu:latest"

    def test_size_minimum(self):
        with pytest.raises(Exception):
            ContainerPoolConfig(size=0)


class TestRecordingConfig:
    def test_defaults(self):
        c = RecordingConfig()
        assert c.enabled is True
        assert c.format == "asciinema"


class TestLoggingConfig:
    def test_defaults(self):
        c = LoggingConfig()
        assert c.level == "INFO"
        assert c.format == "json"


class TestDockerConfig:
    def test_defaults(self):
        c = DockerConfig()
        assert c.socket_path == Path("/var/run/docker.sock")
        assert c.base_url is None


class TestConfigFromFile:
    def test_load_from_yaml(self, test_config_path: Path):
        config = Config.from_file(test_config_path)
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 2222
        assert config.container_pool.size == 2

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            Config.from_file(tmp_path / "nonexistent.yaml")

    def test_default_config(self):
        config = Config()
        assert config.server.port == 2222
        assert config.authentication.accept_all_after_failures == 3

    def test_to_dict(self):
        config = Config()
        d = config.to_dict()
        assert "server" in d
        assert "authentication" in d
        assert "container_pool" in d

    def test_invalid_yaml_raises(self, tmp_path: Path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("server:\n  port: not_a_number\n")
        with pytest.raises(Exception):
            Config.from_file(bad_file)

    def test_empty_yaml(self, tmp_path: Path):
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        # yaml.safe_load returns None for empty file, which should fail
        with pytest.raises(Exception):
            Config.from_file(empty_file)

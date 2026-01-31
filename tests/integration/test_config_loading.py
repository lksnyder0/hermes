"""
Integration tests for configuration loading end-to-end.

Tests YAML file → Config object → component initialization flow.
"""

from pathlib import Path

import pytest

from sandtrap.config import Config
from sandtrap.container.security import build_container_config
from sandtrap.server.auth import AuthenticationManager


class TestConfigToAuthManager:
    """Test Config → AuthenticationManager integration."""

    def test_config_credentials_work_in_auth_manager(self, tmp_path: Path):
        """Credentials defined in YAML should be usable for authentication."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
server:
  host: "0.0.0.0"
  port: 2222

authentication:
  static_credentials:
    - username: "honeypot"
      password: "sweet"
    - username: "admin"
      password: "hunter2"
  accept_all_after_failures: 5
""")

        config = Config.from_file(config_file)
        auth = AuthenticationManager(config.authentication)

        assert auth.validate("c1", "honeypot", "sweet") is True
        assert auth.validate("c1", "admin", "hunter2") is True
        assert auth.validate("c1", "admin", "wrong") is False

    def test_accept_all_disabled_via_config(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
authentication:
  accept_all_after_failures: 0
""")

        config = Config.from_file(config_file)
        auth = AuthenticationManager(config.authentication)

        for _ in range(10):
            auth.validate("c1", "x", "x")
        assert auth.validate("c1", "x", "x") is False


class TestConfigToContainerSecurity:
    """Test Config → ContainerSecurityConfig → build_container_config flow."""

    def test_default_config_builds_valid_container_config(self):
        """Default config should produce a valid Docker container config."""
        config = Config()
        result = build_container_config(
            config=config.container_pool.security,
            image=config.container_pool.image,
            name="test-container",
        )

        assert result["image"] == "sandtrap-target-ubuntu:latest"
        assert result["network_mode"] == "none"
        assert result["mem_limit"] == "256m"
        assert result["cap_drop"] == ["ALL"]
        assert result["detach"] is True

    def test_custom_security_from_yaml(self, tmp_path: Path):
        """Custom security settings from YAML should propagate to container config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
container_pool:
  size: 5
  image: "custom-honeypot:v2"
  security:
    memory_limit: "512m"
    cpu_quota: 1.0
    pids_limit: 200
    network_mode: "bridge"
""")

        config = Config.from_file(config_file)
        result = build_container_config(
            config=config.container_pool.security,
            image=config.container_pool.image,
            name="custom-test",
        )

        assert result["image"] == "custom-honeypot:v2"
        assert result["mem_limit"] == "512m"
        assert result["cpu_quota"] == 100000  # 1.0 * 100000
        assert result["pids_limit"] == 200
        assert result["network_mode"] == "bridge"


class TestConfigFullYaml:
    """Test loading a comprehensive YAML configuration."""

    def test_full_config_loads_all_sections(self, tmp_path: Path):
        config_file = tmp_path / "full_config.yaml"
        config_file.write_text("""
server:
  host: "192.168.1.10"
  port: 22
  max_concurrent_sessions: 50
  session_timeout: 7200

authentication:
  static_credentials:
    - username: "root"
      password: "toor"
  accept_all_after_failures: 10

container_pool:
  size: 10
  image: "honeypot:latest"
  spawn_timeout: 60
  max_session_duration: 1800
  security:
    memory_limit: "1g"
    cpu_quota: 2.0
    pids_limit: 500

recording:
  enabled: true
  format: "asciinema"

logging:
  level: "DEBUG"
  format: "text"

docker:
  base_url: "tcp://docker:2375"
""")

        config = Config.from_file(config_file)

        assert config.server.host == "192.168.1.10"
        assert config.server.port == 22
        assert config.server.max_concurrent_sessions == 50
        assert config.authentication.accept_all_after_failures == 10
        assert config.container_pool.size == 10
        assert config.container_pool.security.memory_limit == "1g"
        assert config.container_pool.security.cpu_quota == 2.0
        assert config.recording.enabled is True
        assert config.logging.level == "DEBUG"
        assert config.docker.base_url == "tcp://docker:2375"

    def test_minimal_config_uses_defaults(self, tmp_path: Path):
        """A minimal config file should fill in all defaults."""
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("server:\n  port: 3333\n")

        config = Config.from_file(config_file)

        assert config.server.port == 3333
        assert config.server.host == "0.0.0.0"  # default
        assert config.container_pool.size == 3  # default
        assert config.authentication.accept_all_after_failures == 3  # default
        assert config.recording.enabled is True  # default


class TestConfigValidationErrors:
    """Test that invalid configurations are rejected."""

    def test_invalid_port_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server:\n  port: 99999\n")
        with pytest.raises(Exception):
            Config.from_file(config_file)

    def test_negative_pool_size_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("container_pool:\n  size: -1\n")
        with pytest.raises(Exception):
            Config.from_file(config_file)

    def test_cpu_quota_too_high_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("container_pool:\n  security:\n    cpu_quota: 100.0\n")
        with pytest.raises(Exception):
            Config.from_file(config_file)

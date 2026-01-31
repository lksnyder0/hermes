"""
Unit tests for container security configuration builder.
"""

import pytest

from hermes.config import ContainerSecurityConfig
from hermes.container.security import (
    build_container_config,
    format_cpu_quota,
    parse_memory_limit,
    _is_valid_memory_limit,
)


@pytest.fixture
def security_config() -> ContainerSecurityConfig:
    return ContainerSecurityConfig()


class TestIsValidMemoryLimit:
    @pytest.mark.parametrize("limit", ["256m", "1g", "512k", "100M", "2G", "1024K"])
    def test_valid_formats(self, limit: str):
        assert _is_valid_memory_limit(limit) is True

    @pytest.mark.parametrize("limit", ["", "256", "m256", "256mb", "256 m", "-1m", "0.5g"])
    def test_invalid_formats(self, limit: str):
        assert _is_valid_memory_limit(limit) is False


class TestParseMemoryLimit:
    def test_kilobytes(self):
        assert parse_memory_limit("100k") == 100 * 1024

    def test_megabytes(self):
        assert parse_memory_limit("256m") == 256 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_memory_limit("2g") == 2 * 1024 * 1024 * 1024

    def test_uppercase(self):
        assert parse_memory_limit("1G") == 1024 * 1024 * 1024

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid memory limit"):
            parse_memory_limit("bad")


class TestFormatCpuQuota:
    def test_one_core(self):
        assert format_cpu_quota(1.0) == "1 core"

    def test_less_than_one(self):
        result = format_cpu_quota(0.5)
        assert "0.5 cores" in result
        assert "50%" in result

    def test_more_than_one(self):
        assert format_cpu_quota(2.0) == "2.0 cores"


class TestBuildContainerConfig:
    def test_basic_config_keys(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img:latest", "test-name")
        assert result["image"] == "img:latest"
        assert result["name"] == "test-name"
        assert result["detach"] is True
        assert result["stdin_open"] is True
        assert result["tty"] is False

    def test_resource_limits(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert result["mem_limit"] == "256m"
        assert result["cpu_quota"] == int(0.5 * 100000)
        assert result["cpu_period"] == 100000
        assert result["pids_limit"] == 100

    def test_network_mode(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert result["network_mode"] == "none"

    def test_security_options(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert result["cap_drop"] == ["ALL"]
        assert "CHOWN" in result["cap_add"]
        assert "no-new-privileges:true" in result["security_opt"]

    def test_tmpfs(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert "/tmp" in result["tmpfs"]

    def test_labels_include_role(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert result["labels"]["hermes.role"] == "target"

    def test_session_id_in_labels(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n", session_id="sess-1")
        assert result["labels"]["hermes.session_id"] == "sess-1"

    def test_no_session_id_label_when_none(self, security_config: ContainerSecurityConfig):
        result = build_container_config(security_config, "img", "n")
        assert "hermes.session_id" not in result["labels"]

    def test_invalid_memory_limit_raises(self):
        config = ContainerSecurityConfig(memory_limit="bad")
        with pytest.raises(ValueError, match="Invalid memory limit"):
            build_container_config(config, "img", "n")

    def test_cpu_quota_calculation(self):
        config = ContainerSecurityConfig(cpu_quota=2.0)
        result = build_container_config(config, "img", "n")
        assert result["cpu_quota"] == 200000

"""
Configuration management for SandTrap.

This module handles loading, validating, and accessing configuration from YAML files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    """SSH server configuration."""

    host: str = Field(default="0.0.0.0", description="Host to bind SSH server")
    port: int = Field(default=2222, ge=1, le=65535, description="Port for SSH server")
    host_key_path: Path = Field(
        default=Path("/data/keys/ssh_host_rsa_key"), description="Path to SSH host key"
    )
    max_concurrent_sessions: int = Field(default=10, ge=1, description="Max concurrent sessions")
    session_timeout: int = Field(default=3600, ge=60, description="Session timeout in seconds")


class AuthenticationConfig(BaseModel):
    """Authentication configuration."""

    class Credential(BaseModel):
        """Username/password credential pair."""

        username: str
        password: str

    static_credentials: List[Credential] = Field(
        default_factory=list, description="List of valid username/password pairs"
    )
    accept_all_after_failures: int = Field(
        default=3, ge=0, description="Accept all auth after N failures (0 to disable)"
    )


class ContainerSecurityConfig(BaseModel):
    """Container security constraints."""

    network_mode: str = Field(default="none", description="Docker network mode")
    memory_limit: str = Field(default="256m", description="Memory limit")
    cpu_quota: float = Field(default=0.5, ge=0.1, le=8.0, description="CPU quota in cores")
    pids_limit: int = Field(default=100, ge=10, description="Process limit")
    tmpfs_size: str = Field(default="50m", description="Tmpfs size for /tmp")

    class CapabilityConfig(BaseModel):
        """Linux capabilities configuration."""

        drop: List[str] = Field(default_factory=lambda: ["ALL"])
        add: List[str] = Field(default_factory=lambda: ["CHOWN", "SETUID", "SETGID"])

    capabilities: CapabilityConfig = Field(default_factory=CapabilityConfig)
    security_opt: List[str] = Field(
        default_factory=lambda: ["no-new-privileges:true", "seccomp=default"]
    )


class ContainerPoolConfig(BaseModel):
    """Container pool configuration."""

    size: int = Field(default=3, ge=1, description="Number of containers in ready pool")
    spawn_timeout: int = Field(default=30, ge=5, description="Timeout for container spawn")
    image: str = Field(
        default="sandtrap-target-ubuntu:latest", description="Target container image"
    )
    max_session_duration: int = Field(
        default=3600, ge=60, description="Max session duration in seconds"
    )
    cleanup_stopped_after_days: int = Field(
        default=7, ge=0, description="Days to keep stopped containers (0 to keep forever)"
    )
    security: ContainerSecurityConfig = Field(default_factory=ContainerSecurityConfig)


class RecordingConfig(BaseModel):
    """Session recording configuration."""

    enabled: bool = Field(default=True, description="Enable session recording")
    output_dir: Path = Field(
        default=Path("/data/recordings"), description="Recording output directory"
    )
    format: str = Field(default="asciinema", description="Recording format (asciinema)")
    capture_metadata: List[str] = Field(
        default_factory=lambda: [
            "connection_info",
            "authentication_attempts",
            "session_duration",
            "container_id",
            "commands_executed",
        ]
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or text)")
    output_dir: Path = Field(default=Path("/data/logs"), description="Log output directory")
    include_fields: List[str] = Field(
        default_factory=lambda: [
            "timestamp",
            "session_id",
            "username",
            "source_ip",
            "event_type",
        ]
    )


class DockerConfig(BaseModel):
    """Docker connection configuration."""

    socket_path: Path = Field(
        default=Path("/var/run/docker.sock"), description="Path to Docker socket"
    )
    base_url: Optional[str] = Field(default=None, description="Docker API base URL")


class Config(BaseSettings):
    """Main SandTrap configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)
    container_pool: ContainerPoolConfig = Field(default_factory=ContainerPoolConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        """
        Load configuration from a YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            Config instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.model_dump()

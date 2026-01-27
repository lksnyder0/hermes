"""
Security configuration builder for Docker containers.

This module provides functions to build secure Docker container configurations
with all necessary security constraints applied.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from sandtrap.config import ContainerSecurityConfig

logger = logging.getLogger(__name__)


def build_container_config(
    config: ContainerSecurityConfig,
    image: str,
    name: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Docker container creation parameters with security constraints.

    This function converts the high-level security configuration into
    Docker API parameters, applying all necessary security constraints
    for container isolation and resource limits.

    Args:
        config: Security configuration from main config
        image: Docker image name (e.g., 'sandtrap-target-ubuntu:latest')
        name: Container name
        session_id: Optional session ID for labeling

    Returns:
        Dictionary of parameters for docker.containers.create()

    Raises:
        ValueError: If configuration values are invalid
    """
    # Validate memory limit format
    if not _is_valid_memory_limit(config.memory_limit):
        raise ValueError(
            f"Invalid memory limit format: {config.memory_limit}. "
            f"Expected format: <number>[k|m|g] (e.g., '256m')"
        )

    # Convert CPU quota from cores to Docker quota format
    # Docker CPU quota is in microseconds per period
    # cpu_period is typically 100000 (100ms)
    # cpu_quota = cores * cpu_period
    cpu_quota = int(config.cpu_quota * 100000)
    cpu_period = 100000

    logger.debug(
        f"Building container config: memory={config.memory_limit}, "
        f"cpu_quota={cpu_quota}/{cpu_period} ({config.cpu_quota} cores), "
        f"pids={config.pids_limit}, network={config.network_mode}"
    )

    # Build labels for tracking and identification
    labels = {
        "sandtrap.role": "target",
        "sandtrap.version": "mvp",
        "sandtrap.created": datetime.utcnow().isoformat(),
    }
    if session_id:
        labels["sandtrap.session_id"] = session_id

    # Build complete container configuration
    container_config = {
        "image": image,
        "name": name,
        "detach": True,
        "stdin_open": True,  # Keep stdin open for docker exec
        "tty": False,  # TTY is handled by exec, not container startup
        # Network isolation
        "network_mode": config.network_mode,
        # Resource limits
        "mem_limit": config.memory_limit,
        "cpu_quota": cpu_quota,
        "cpu_period": cpu_period,
        "pids_limit": config.pids_limit,
        # Tmpfs for /tmp (in-memory, size-limited)
        "tmpfs": {"/tmp": f"size={config.tmpfs_size}"},
        # Security options
        "security_opt": config.security_opt,
        "cap_drop": config.capabilities.drop,
        "cap_add": config.capabilities.add,
        # Labels for identification
        "labels": labels,
    }

    # Log warnings for unusual configurations
    if config.cpu_quota > 2.0:
        logger.warning(
            f"High CPU quota configured: {config.cpu_quota} cores. "
            f"Consider reducing to prevent resource exhaustion."
        )

    if config.pids_limit < 50:
        logger.warning(
            f"Very low PIDs limit: {config.pids_limit}. "
            f"Container may fail to spawn necessary processes."
        )

    return container_config


def _is_valid_memory_limit(limit: str) -> bool:
    """
    Validate memory limit format.

    Args:
        limit: Memory limit string (e.g., '256m', '1g', '512k')

    Returns:
        True if format is valid, False otherwise
    """
    # Docker accepts: <number>[k|m|g] (case-insensitive)
    pattern = r"^\d+[kmgKMG]$"
    return bool(re.match(pattern, limit))


def parse_memory_limit(limit: str) -> int:
    """
    Parse memory limit string to bytes.

    Args:
        limit: Memory limit string (e.g., '256m', '1g')

    Returns:
        Memory limit in bytes

    Raises:
        ValueError: If format is invalid
    """
    if not _is_valid_memory_limit(limit):
        raise ValueError(f"Invalid memory limit format: {limit}")

    # Extract number and unit
    number = int(limit[:-1])
    unit = limit[-1].lower()

    multipliers = {
        "k": 1024,
        "m": 1024 * 1024,
        "g": 1024 * 1024 * 1024,
    }

    return number * multipliers[unit]


def format_cpu_quota(cores: float) -> str:
    """
    Format CPU quota for human-readable display.

    Args:
        cores: Number of CPU cores (e.g., 0.5, 1.0, 2.0)

    Returns:
        Formatted string (e.g., '0.5 cores', '50% of 1 core')
    """
    if cores == 1.0:
        return "1 core"
    elif cores < 1.0:
        return f"{cores} cores ({int(cores * 100)}% of 1 core)"
    else:
        return f"{cores} cores"

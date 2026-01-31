"""
Pytest configuration and fixtures for Hermes tests.
"""

import pytest
from pathlib import Path

from hermes.config import Config


@pytest.fixture
def test_config_path(tmp_path: Path) -> Path:
    """Create a temporary config file for testing."""
    config_content = """
server:
  host: "127.0.0.1"
  port: 2222
  
authentication:
  static_credentials:
    - username: "test"
      password: "test123"
  accept_all_after_failures: 2

container_pool:
  size: 2
  image: "test-target:latest"
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def test_config(test_config_path: Path) -> Config:
    """Load a test configuration."""
    return Config.from_file(test_config_path)

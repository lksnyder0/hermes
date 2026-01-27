"""
SandTrap - SSH Honeypot with Docker Container Sandboxing

A security tool that accepts SSH connections from attackers and proxies them to
isolated Docker containers to capture malicious behavior while protecting the host system.
"""

__version__ = "0.1.0"
__author__ = "SandTrap Contributors"
__license__ = "MIT"

from sandtrap.config import Config

__all__ = ["Config", "__version__"]

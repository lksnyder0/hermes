"""
SandTrap entry point.

This module provides the main() function that starts the SSH honeypot server.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import docker

from sandtrap import __version__
from sandtrap.config import Config
from sandtrap.container.pool import ContainerPool
from sandtrap.server.asyncssh_backend import AsyncSSHBackend
from sandtrap.server.backend import PTYRequest, SessionInfo


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="SandTrap - SSH Honeypot with Docker Container Sandboxing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"SandTrap {__version__}",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config/config.yaml"),
        help="Path to configuration file (default: config/config.yaml)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    parser.add_argument(
        "--generate-keys",
        action="store_true",
        help="Generate SSH host keys and exit",
    )

    return parser.parse_args()


async def dummy_session_handler(
    session_info: SessionInfo, pty_request: PTYRequest, session: object
) -> None:
    """
    Temporary session handler until container management is implemented.

    Args:
        session_info: Information about the session
        pty_request: PTY request details
        session: SSH session object
    """
    logger = logging.getLogger(__name__)

    # Send welcome message
    welcome = (
        f"\r\nWelcome to SandTrap!\r\n"
        f"Session ID: {session_info.session_id}\r\n"
        f"User: {session_info.username}\r\n"
        f"Terminal: {pty_request.term_type} ({pty_request.width}x{pty_request.height})\r\n"
        f"\r\n"
        f"Container management not yet implemented.\r\n"
        f"Press Ctrl+D to exit.\r\n"
        f"\r\n"
    )

    session.stdout.write(welcome)

    # Simple echo loop for testing
    try:
        while True:
            data = await session.stdin.read(1024)
            if not data:
                break
            # Echo back (simple test)
            session.stdout.write(data)
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        logger.info(f"Session ended: {session_info.session_id}")


async def async_main(config_path: Path) -> int:
    """
    Asynchronous main function.

    Args:
        config_path: Path to configuration file

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)
    ssh_backend = None
    container_pool = None
    docker_client = None

    try:
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        config = Config.from_file(config_path)

        logger.info("SandTrap starting...")
        logger.info(f"SSH Server: {config.server.host}:{config.server.port}")
        logger.info(f"Host Key: {config.server.host_key_path}")
        logger.info(f"Container pool size: {config.container_pool.size}")
        logger.info(f"Max concurrent sessions: {config.server.max_concurrent_sessions}")

        # Initialize Docker client
        logger.info("Connecting to Docker...")
        if config.docker.base_url:
            docker_client = docker.DockerClient(base_url=config.docker.base_url)
        else:
            docker_client = docker.from_env()

        # Verify Docker connection
        docker_version = docker_client.version()
        logger.info(f"Connected to Docker {docker_version.get('Version', 'unknown')}")

        # Initialize container pool
        logger.info("Initializing container pool...")
        container_pool = ContainerPool(docker_client, config.container_pool)
        await container_pool.initialize()
        logger.info(f"Container pool ready with {config.container_pool.size} containers")

        # Initialize SSH backend
        logger.info("Initializing SSH backend...")
        ssh_backend = AsyncSSHBackend(config)

        # Register container pool with SSH backend
        ssh_backend.set_container_pool(container_pool)

        # Set temporary session handler (Phase 4 will use real container proxy)
        ssh_backend.set_session_handler(dummy_session_handler)

        # Start SSH server
        logger.info("Starting SSH server...")
        await ssh_backend.start()

        logger.info("SandTrap is running! Press Ctrl+C to stop.")

        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1
    except docker.errors.DockerException as e:
        logger.error(f"Docker error: {e}")
        logger.error("Make sure Docker is running and accessible")
        return 1
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        # Clean shutdown
        if ssh_backend:
            logger.info("Shutting down SSH server...")
            await ssh_backend.stop()

        if container_pool:
            logger.info("Shutting down container pool...")
            await container_pool.shutdown()

        if docker_client:
            logger.info("Closing Docker connection...")
            docker_client.close()

        logger.info("Shutdown complete")


def main() -> int:
    """
    Main entry point for SandTrap.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info(f"SandTrap v{__version__}")

    # Handle special commands
    if args.generate_keys:
        logger.info("Generating SSH host keys...")
        # TODO: Implement key generation
        logger.error("Key generation not yet implemented")
        return 1

    # Run async main
    try:
        return asyncio.run(async_main(args.config))
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        return 0


if __name__ == "__main__":
    sys.exit(main())

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

from sandtrap import __version__
from sandtrap.config import Config


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


async def async_main(config_path: Path) -> int:
    """
    Asynchronous main function.

    Args:
        config_path: Path to configuration file

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)

    try:
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        config = Config.from_file(config_path)

        # TODO: Initialize components
        logger.info("SandTrap starting...")
        logger.info(f"SSH Server: {config.server.host}:{config.server.port}")
        logger.info(f"Container pool size: {config.container_pool.size}")

        # TODO: Start the server
        # await server.start()

        logger.warning("Server implementation pending - exiting")
        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


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

#!/usr/bin/env python3
"""
Integration test script for SandTrap SSH honeypot.

Opens an interactive shell session (PTY) to the running SandTrap service,
sends a test command, captures output, and disconnects.

SandTrap only supports interactive shell sessions via process_factory,
so we must request a PTY and shell rather than using conn.run().

Prerequisites:
    1. SandTrap must be running:
       cd src && python -m hermes --config ../config/config.test.yaml --log-level DEBUG
    2. asyncssh must be installed:
       pip install asyncssh

Usage:
    python scripts/test_connect.py [--host HOST] [--port PORT] [--user USER] [--password PASS]
"""

import argparse
import asyncio
import sys

import asyncssh


COMMAND = 'echo "Hello, from docker container $HOSTNAME"\n'
# Marker to detect command output completion
EXIT_CMD = "exit\n"
TIMEOUT = 15


async def run_test(host: str, port: int, username: str, password: str) -> int:
    """
    Connect to SandTrap, open an interactive shell, run a command, and print output.

    Returns:
        0 on success, 1 on failure.
    """
    print(f"Connecting to {host}:{port} as {username}...")

    try:
        async with asyncssh.connect(
            host,
            port=port,
            username=username,
            password=password,
            known_hosts=None,
        ) as conn:
            print("Connected. Opening interactive shell...")

            _chan, process = await conn.create_session(
                asyncssh.SSHClientProcess,
                term_type="xterm",
                term_size=(80, 24),
                encoding=None,
            )

            # Wait briefly for the shell prompt to appear
            output = b""
            try:
                output += await asyncio.wait_for(
                    _read_until_idle(process.stdout, idle=1.0),
                    timeout=TIMEOUT,
                )
            except asyncio.TimeoutError:
                print("Timed out waiting for shell prompt.", file=sys.stderr)
                return 1

            print("Got shell prompt. Sending command...")

            # Send the test command
            process.stdin.write(COMMAND.encode())

            # Read command output
            try:
                output = await asyncio.wait_for(
                    _read_until_idle(process.stdout, idle=1.0),
                    timeout=TIMEOUT,
                )
            except asyncio.TimeoutError:
                print("Timed out waiting for command output.", file=sys.stderr)
                return 1

            decoded = output.decode(errors="replace")
            print("--- command output ---")
            print(decoded, end="")
            print("--- end output ---")

            # Send exit to cleanly close the shell
            process.stdin.write(EXIT_CMD.encode())

            # Check for expected output
            if "Hello, from docker container" in decoded:
                print("Test passed.")
                return 0
            else:
                print("Test failed: expected output not found.", file=sys.stderr)
                return 1

    except asyncssh.PermissionDenied:
        print("Authentication failed.", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Is SandTrap running? Start it with:", file=sys.stderr)
        print(
            "  cd src && python -m hermes --config ../config/config.test.yaml --log-level DEBUG",
            file=sys.stderr,
        )
        return 1


async def _read_until_idle(
    stream: asyncssh.SSHReader, idle: float = 1.0, chunk_size: int = 4096
) -> bytes:
    """
    Read from stream until no new data arrives for `idle` seconds.

    Args:
        stream: Async reader to consume from.
        idle: Seconds of silence before returning.
        chunk_size: Max bytes per read.

    Returns:
        All accumulated bytes.
    """
    buf = bytearray()
    while True:
        try:
            data = await asyncio.wait_for(stream.read(chunk_size), timeout=idle)
            if not data:
                break
            buf.extend(data)
        except asyncio.TimeoutError:
            break
    return bytes(buf)


def main() -> int:
    parser = argparse.ArgumentParser(description="SandTrap SSH connection test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2223)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="toor")
    args = parser.parse_args()

    return asyncio.run(run_test(args.host, args.port, args.user, args.password))


if __name__ == "__main__":
    sys.exit(main())

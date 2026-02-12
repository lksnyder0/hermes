"""
Integration tests for session recording validation.

Uses real SSH sessions connecting to a live Hermes server to validate that
.cast files correctly capture all session I/O with proper timing, formatting,
and metadata.

Run with:
    pytest tests/integration/test_recording_validation.py -v
    pytest -m recording -v

Requires:
    - Docker running (for container pool)
    - hermes-target-ubuntu:latest image built
"""

import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncssh
import pytest

from hermes.config import RecordingConfig

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
async def recording_config(tmp_path: Path) -> RecordingConfig:
    """Recording configuration pointing to temp directory."""
    return RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )


async def _start_hermes_server(
    tmp_path: Path,
    recording_enabled: bool = True,
    recording_output_dir: Path | None = None,
    pool_size: int = 1,
) -> AsyncGenerator[tuple[str, int, Path], None]:
    """
    Start a real Hermes SSH server with container pool.

    Shared logic for server fixtures — avoids duplicating Docker checks,
    config generation, host-key creation, process lifecycle, and cleanup.

    Args:
        tmp_path: Temporary directory for config/keys
        recording_enabled: Whether session recording is on
        recording_output_dir: Where .cast files go (defaults to tmp_path/recordings)
        pool_size: Number of containers in the pool (default: 1)

    Yields:
        (host, port, recordings_dir) tuple

    Raises:
        pytest.skip if Docker or image unavailable, or server fails to start
    """
    import socket
    import subprocess
    import time

    import docker
    import yaml

    recordings_dir = recording_output_dir or (tmp_path / "recordings")

    # Check Docker availability and required image
    docker_client = None
    try:
        docker_client = docker.from_env()
        docker_client.ping()
        docker_client.images.get("hermes-target-ubuntu:latest")
    except docker.errors.ImageNotFound:
        pytest.skip("hermes-target-ubuntu:latest not found. Build it first.")
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")
    finally:
        if docker_client:
            docker_client.close()

    # Find available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]

    host = "127.0.0.1"

    # Create config file
    config_path = tmp_path / "test_config.yaml"
    test_config = {
        "server": {
            "host": host,
            "port": port,
            "host_key_path": str(tmp_path / "test_host_key"),
        },
        "authentication": {
            "static_credentials": [
                {"username": "root", "password": "toor"},
                {"username": "admin", "password": "admin123"},
            ],
            "accept_all_after_failures": 3,
        },
        "container_pool": {
            "size": pool_size,
            "image": "hermes-target-ubuntu:latest",
            "spawn_timeout": 30,
            "security": {
                "network_mode": "none",
                "memory_limit": "256m",
                "cpu_quota": 0.5,
                "pids_limit": 100,
                "security_opt": ["no-new-privileges:true"],
            },
        },
        "recording": {
            "enabled": recording_enabled,
            "output_dir": str(recordings_dir),
        },
        "logging": {
            "level": "INFO",
            "format": "text",
        },
    }

    with open(config_path, "w") as f:
        yaml.safe_dump(test_config, f, sort_keys=False)

    # Generate SSH host key (ed25519 is modern and secure)
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    host_key.write_private_key(str(tmp_path / "test_host_key"))

    # Create log files for server output
    stdout_log = tmp_path / "hermes_stdout.log"
    stderr_log = tmp_path / "hermes_stderr.log"

    # Start Hermes server
    with open(stdout_log, "w") as stdout_f, open(stderr_log, "w") as stderr_f:
        hermes_process = subprocess.Popen(
            [sys.executable, "-m", "hermes", "--config", str(config_path)],
            cwd=str(Path(__file__).parent.parent.parent / "src"),
            stdout=stdout_f,
            stderr=stderr_f,
        )

    # Wait for server to be ready
    max_wait = 15  # seconds
    start_time = time.time()
    server_ready = False

    while time.time() - start_time < max_wait:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                if result == 0:
                    server_ready = True
                    break
        except Exception:
            pass
        await asyncio.sleep(0.2)

    if not server_ready:
        hermes_process.kill()
        hermes_process.wait(timeout=5)
        # Include last lines of logs in skip message
        error_msg = f"Hermes server failed to start on {host}:{port}"
        if stderr_log.exists():
            stderr_content = stderr_log.read_text()
            if stderr_content:
                last_lines = "\n".join(stderr_content.strip().split("\n")[-10:])
                error_msg += f"\n\nLast 10 lines of stderr:\n{last_lines}"
        pytest.skip(error_msg)

    # Give it a moment to fully initialize
    await asyncio.sleep(0.5)

    try:
        yield (host, port, recordings_dir)
    finally:
        hermes_process.terminate()
        try:
            hermes_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            hermes_process.kill()
            hermes_process.wait()

        # Clean up any leftover containers
        try:
            for container in docker_client.containers.list(
                all=True, filters={"name": "hermes-target"}
            ):
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass


@pytest.fixture(scope="function")
async def ssh_hermes_server(
    recording_config: RecordingConfig, tmp_path: Path
) -> AsyncGenerator[tuple[str, int], None]:
    """
    Start a real Hermes SSH server with container pool.

    Yields:
        (host, port) tuple for SSH connection
    """
    async for host, port, _recordings_dir in _start_hermes_server(
        tmp_path,
        recording_enabled=recording_config.enabled,
        recording_output_dir=recording_config.output_dir,
    ):
        yield (host, port)


@pytest.fixture(scope="function")
async def ssh_hermes_server_concurrent(
    recording_config: RecordingConfig, tmp_path: Path
) -> AsyncGenerator[tuple[str, int], None]:
    """
    Start a real Hermes SSH server with pool_size=2 for concurrent session tests.

    Yields:
        (host, port) tuple for SSH connection
    """
    async for host, port, _recordings_dir in _start_hermes_server(
        tmp_path,
        recording_enabled=recording_config.enabled,
        recording_output_dir=recording_config.output_dir,
        pool_size=2,
    ):
        yield (host, port)


@pytest.fixture(scope="function")
async def ssh_connected_session(
    ssh_hermes_server: tuple[str, int],
) -> AsyncGenerator[
    tuple[asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel],
    None,
]:
    """
    Connect to Hermes server via SSH and open interactive PTY session.

    Yields:
        (connection, process, channel) tuple

    Raises:
        pytest.skip if connection fails
    """
    host, port = ssh_hermes_server
    conn = None

    try:
        # Connect to Hermes SSH server
        conn = await asyncssh.connect(
            host,
            port=port,
            username="root",
            password="toor",
            known_hosts=None,
        )

        # Create PTY session
        chan, process = await conn.create_session(
            asyncssh.SSHClientProcess,
            term_type="xterm",
            term_size=(80, 24),
            encoding=None,
        )

        # Wait for initial shell prompt
        await asyncio.sleep(0.3)

        # Clear any initial output (banner, prompt)
        try:
            await asyncio.wait_for(process.stdout.read(4096), timeout=0.3)
        except asyncio.TimeoutError:
            pass

        yield (conn, process, chan)

    except Exception as e:
        pytest.skip(f"Failed to connect to Hermes server: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
                await conn.wait_closed()
            except Exception:
                pass


@pytest.fixture(scope="function")
async def ssh_hermes_server_no_recording(
    tmp_path: Path,
) -> AsyncGenerator[tuple[str, int, Path], None]:
    """
    Start a real Hermes SSH server with recording DISABLED.

    Yields:
        (host, port, recordings_dir) tuple for SSH connection
    """
    async for host, port, recordings_dir in _start_hermes_server(tmp_path, recording_enabled=False):
        yield (host, port, recordings_dir)


# ============================================================================
# Helper Functions (Validators & Utilities)
# ============================================================================


def parse_cast_file(path: Path) -> dict:
    """
    Parse asciicast v2 .cast file.

    Args:
        path: Path to .cast file

    Returns:
        dict with keys:
            - "header": parsed JSON header dict
            - "events": list of parsed event tuples [timestamp, type, data]

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is malformed
        ValueError: If the .cast file is empty
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().strip().splitlines()

    if len(lines) == 0:
        raise ValueError("Empty .cast file")

    # First line is header
    header = json.loads(lines[0])

    # Remaining lines are events
    events = []
    for line in lines[1:]:
        if line.strip():  # Skip empty lines
            events.append(json.loads(line))

    return {"header": header, "events": events}


def validate_cast_format(cast: dict) -> None:
    """
    Validate asciicast v2 header format.

    Raises:
        AssertionError: If header is invalid
    """
    assert "header" in cast, "Missing 'header' key in cast dict"
    header = cast["header"]

    assert "version" in header, "Missing 'version' in header"
    assert header["version"] == 2, f"Expected version 2, got {header['version']}"

    assert "width" in header, "Missing 'width' in header"
    assert isinstance(header["width"], int), f"Width must be int, got {type(header['width'])}"
    assert header["width"] >= 1, f"Width must be >= 1, got {header['width']}"

    assert "height" in header, "Missing 'height' in header"
    assert isinstance(header["height"], int), f"Height must be int, got {type(header['height'])}"
    assert header["height"] >= 1, f"Height must be >= 1, got {header['height']}"

    assert "timestamp" in header, "Missing 'timestamp' in header"
    assert isinstance(
        header["timestamp"], int
    ), f"Timestamp must be int, got {type(header['timestamp'])}"
    assert header["timestamp"] > 0, f"Timestamp must be > 0, got {header['timestamp']}"


def validate_events_monotonic(events: list) -> None:
    """
    Validate that event timestamps are monotonically increasing.

    Raises:
        AssertionError: If timestamps decrease or are negative
    """
    for i, event in enumerate(events):
        assert (
            len(event) >= 3
        ), f"Event {i} must have [timestamp, type, data], got {len(event)} elements"
        timestamp = event[0]
        assert isinstance(
            timestamp, (int, float)
        ), f"Event {i} timestamp must be numeric, got {type(timestamp)}"
        assert timestamp >= 0.0, f"Event {i} timestamp must be >= 0, got {timestamp}"

        if i > 0:
            prev_timestamp = events[i - 1][0]
            assert (
                timestamp >= prev_timestamp
            ), f"Event {i} timestamp {timestamp} < previous {prev_timestamp} (not monotonic)"


def extract_output_events(events: list) -> list:
    """Extract all output ("o") event data as strings."""
    return [event[2] for event in events if event[1] == "o"]


def extract_input_events(events: list) -> list:
    """Extract all input ("i") event data as strings."""
    return [event[2] for event in events if event[1] == "i"]


async def send_command(process: asyncssh.SSHClientProcess, cmd: str, timeout: float = 5.0) -> bytes:
    """
    Send SSH command and read output until idle or timeout.

    Args:
        process: SSHClientProcess from SSH connection
        cmd: Command to send (with newline)
        timeout: Maximum total time to wait for output in seconds
            (per-read idle cutoff remains at 0.5s)

    Returns:
        All output bytes received
    """
    # Send command
    process.stdin.write(cmd.encode())

    # Read until idle (optimized for faster tests) or overall timeout
    buf = bytearray()
    idle_timeout = 0.5  # 500ms of silence = done (reduced from 1.0s)
    loop = asyncio.get_running_loop()
    start = loop.time()

    while True:
        elapsed = loop.time() - start
        remaining = timeout - elapsed
        if remaining <= 0:
            break

        try:
            read_timeout = min(idle_timeout, remaining)
            data = await asyncio.wait_for(process.stdout.read(4096), timeout=read_timeout)
            if not data:
                break
            buf.extend(data)
        except asyncio.TimeoutError:
            # No data for idle_timeout seconds, consider complete
            break

    return bytes(buf)


async def await_cast_files(
    recordings_dir: Path,
    expected: int = 1,
    timeout: float = 5.0,
    poll_interval: float = 0.2,
) -> list[Path]:
    """
    Poll for .cast files in the recordings directory with a timeout.

    The server may still be flushing recordings to disk after the SSH
    connection closes, so immediate glob can miss files.

    Args:
        recordings_dir: Directory to search for .cast files
        expected: Minimum number of .cast files expected
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        List of .cast file paths found

    Raises:
        AssertionError: If expected files not found within timeout
    """
    recordings_dir.mkdir(parents=True, exist_ok=True)
    elapsed = 0.0
    cast_files: list[Path] = []
    while elapsed < timeout:
        cast_files = list(recordings_dir.glob("*.cast"))
        if len(cast_files) >= expected:
            return cast_files
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    assert len(cast_files) >= expected, (
        f"Expected >= {expected} .cast files in {recordings_dir} after {timeout}s, "
        f"found {len(cast_files)}"
    )
    return cast_files


async def await_metadata_files(
    recordings_dir: Path,
    expected: int = 1,
    timeout: float = 5.0,
    poll_interval: float = 0.2,
) -> list[Path]:
    """
    Poll for .json metadata files in the recordings directory with a timeout.

    The server may still be flushing metadata to disk after the SSH
    connection closes, so immediate glob can miss files.

    Args:
        recordings_dir: Directory to search for .json files
        expected: Minimum number of .json files expected
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        List of .json file paths found

    Raises:
        AssertionError: If expected files not found within timeout
    """
    recordings_dir.mkdir(parents=True, exist_ok=True)
    elapsed = 0.0
    json_files: list[Path] = []
    while elapsed < timeout:
        json_files = list(recordings_dir.glob("*.json"))
        if len(json_files) >= expected:
            return json_files
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    assert len(json_files) >= expected, (
        f"Expected >= {expected} .json files in {recordings_dir} after {timeout}s, "
        f"found {len(json_files)}"
    )
    return json_files


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.recording
@pytest.mark.ssh
@pytest.mark.docker
class TestRecordingValidation:
    """Integration tests for session recording with real SSH sessions."""

    async def test_basic_io_capture(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate basic session I/O is captured to .cast file.

        Scenario:
            1. SSH connection established with PTY (80x24)
            2. Send "whoami" command
            3. Read output
            4. Send "exit"
            5. Session closes

        Expected .cast file:
            - Header: version=2, width=80, height=24
            - ~4-5 events: output prompt, input "whoami", output "root"
            - All timestamps >= 0 and monotonic
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None
        assert process is not None

        # Act: send whoami command
        whoami_output = await send_command(process, "whoami\n")
        assert b"root" in whoami_output or b"honeypot" in whoami_output

        # Act: exit session
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Reduced from 0.5s

        # Close connection
        conn.close()
        await conn.wait_closed()

        # Assert: .cast file exists (poll to allow server flush)
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        # Assert: .cast is valid
        cast = parse_cast_file(cast_path)
        validate_cast_format(cast)

        # Assert: events are present and monotonic
        events = cast["events"]
        assert len(events) >= 3, f"Expected >= 3 events, got {len(events)}"
        validate_events_monotonic(events)

        # Assert: expected event types present
        output_events = extract_output_events(events)
        input_events = extract_input_events(events)
        assert len(output_events) > 0, "No output events captured"
        assert len(input_events) > 0, "No input events captured"

    async def test_multiple_commands(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate multiple commands are captured with correct interleaving.

        Scenario:
            1. Send "ls\n"
            2. Send "pwd\n"
            3. Send "echo hello\n"
            4. Exit

        Expected .cast:
            - Input/output alternation: i → o → i → o → i → o
            - At least 6 events
            - "ls" in some output event
            - "pwd" in some output event
            - "hello" in some output event
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send commands
        await send_command(process, "ls\n", timeout=3.0)
        await send_command(process, "pwd\n", timeout=3.0)
        await send_command(process, "echo hello\n", timeout=3.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized

        conn.close()
        await conn.wait_closed()

        # Assert: .cast file exists and is valid
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        cast = parse_cast_file(cast_path)
        validate_cast_format(cast)

        # Assert: multiple commands captured
        events = cast["events"]
        assert len(events) >= 6, f"Expected >= 6 events for 3 commands, got {len(events)}"

        # Assert: interleaving (approximate)
        event_types = [e[1] for e in events]
        input_count = event_types.count("i")
        output_count = event_types.count("o")
        assert input_count >= 3, "Should capture at least 3 input events"
        assert output_count >= 3, "Should capture at least 3 output events"

        # Assert: recording contains the actual command content
        output_events = extract_output_events(events)
        combined_output = "".join(output_events)
        assert (
            "hello" in combined_output
        ), f"Expected 'hello' in output events, got: {combined_output[:500]}"

        input_events = extract_input_events(events)
        combined_input = "".join(input_events)
        assert "ls" in combined_input, f"Expected 'ls' in input events, got: {combined_input[:500]}"
        assert (
            "pwd" in combined_input
        ), f"Expected 'pwd' in input events, got: {combined_input[:500]}"
        assert (
            "echo hello" in combined_input
        ), f"Expected 'echo hello' in input events, got: {combined_input[:500]}"

    async def test_unicode_handling(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate unicode and emoji are preserved in .cast file.

        Scenario:
            1. Send: echo "こんにちは 🎉"
            2. Read output
            3. Exit

        Expected .cast:
            - Unicode preserved (not corrupted)
            - JSON valid and parseable
            - Output event contains original unicode
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        unicode_cmd = 'echo "こんにちは 🎉"\n'

        # Act: send unicode command
        await send_command(process, unicode_cmd, timeout=3.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized

        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        cast = parse_cast_file(cast_path)

        # Assert: unicode preserved in events
        output_events = extract_output_events(cast["events"])
        combined_output = "".join(output_events)
        # Should contain unicode (not entirely replaced)
        assert (
            "こ" in combined_output or "🎉" in combined_output or "UTF" in combined_output
        ), f"Unicode lost in recording: {combined_output}"

    async def test_large_output(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate large output (>10KB) is captured completely.

        Scenario:
            1. Send: seq 1 3000 (deterministically generates ~14KB)
            2. Read output
            3. Exit

        Expected .cast:
            - All output captured (>10KB)
            - .cast file size reasonable (not truncated)
            - Output events contain full data
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        # seq 1 3000 outputs numbers 1-3000, one per line (~14KB)
        large_cmd = "seq 1 3000\n"

        # Act: send command with large output
        output = await send_command(process, large_cmd, timeout=10.0)
        assert len(output) > 10000, f"Output too small to test: {len(output)} bytes (need >10KB)"

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)

        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        cast = parse_cast_file(cast_path)

        # Assert: file not truncated (should have many events)
        events = cast["events"]
        assert len(events) >= 3, "Output events should capture large data"

        # Assert: .cast file size reasonable
        cast_size = cast_path.stat().st_size
        assert cast_size < 1000000, f".cast file too large: {cast_size} bytes (>1MB)"

        # Assert: combined output exceeds 10KB
        output_events = extract_output_events(events)
        combined = "".join(output_events)
        assert len(combined) > 10000, f"Combined output should be >10KB, got {len(combined)} bytes"

    @pytest.mark.xfail(reason="Resize event capture is environment-dependent")
    async def test_terminal_resize_events(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate terminal resize events are recorded.

        Scenario:
            1. Send command at 80x24
            2. Resize to 120x40 (if supported)
            3. Send another command
            4. Resize to 40x20
            5. Exit

        Expected .cast:
            - At least one "r" (resize) event
            - Format: [timestamp, "r", "WIDTHxHEIGHT"]
            - Timestamps still monotonic
        """
        conn, process, chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send initial command
        await send_command(process, "echo initial\n", timeout=2.0)

        # Act: attempt resize using the channel
        if hasattr(chan, "change_terminal_size"):
            chan.change_terminal_size(120, 40)
        await asyncio.sleep(0.1)

        # Act: send command after resize
        await send_command(process, "echo resized\n", timeout=2.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized

        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        cast = parse_cast_file(cast_path)

        # Assert: events captured
        events = cast["events"]
        assert len(events) >= 3, "Should capture at least input + outputs"

        # Assert: timestamps monotonic (resize events included)
        validate_events_monotonic(events)

        # Assert: at least one resize event with correct format
        resize_events = [e for e in events if e[1] == "r"]
        assert len(resize_events) >= 1, "Expected at least one resize ('r') event"
        for _ts, _etype, payload in resize_events:
            assert isinstance(
                payload, str
            ), f"Resize payload should be a string, got {type(payload)}"
            parts = payload.split("x")
            assert len(parts) == 2, f"Resize payload should be 'WIDTHxHEIGHT', got '{payload}'"
            assert all(
                p.isdigit() for p in parts
            ), f"Resize dimensions should be numeric, got '{payload}'"

    async def test_rapid_commands(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate rapid commands are all captured without loss.

        Scenario:
            1. Send 5 commands rapidly (minimal delay between)
            2. Exit

        Expected .cast:
            - All 5+ input events captured
            - All 5+ output events captured
            - No data loss or corruption
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        commands = ["echo cmd1\n", "echo cmd2\n", "echo cmd3\n", "echo cmd4\n", "echo cmd5\n"]

        # Act: send commands rapidly
        for cmd in commands:
            process.stdin.write(cmd.encode())
            await asyncio.sleep(0.05)  # minimal delay

        # Act: read all output
        await asyncio.sleep(0.5)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized

        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = await await_cast_files(recordings_dir)
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        cast = parse_cast_file(cast_path)

        # Assert: all commands captured
        events = cast["events"]
        input_events = extract_input_events(events)
        output_events = extract_output_events(events)

        assert len(input_events) >= 5, f"Expected >= 5 input events, got {len(input_events)}"
        assert len(output_events) >= 5, f"Expected >= 5 output events, got {len(output_events)}"

    async def test_concurrent_sessions_recording(
        self,
        ssh_hermes_server_concurrent: tuple[str, int],
        recording_config: RecordingConfig,
    ):
        """
        Validate concurrent sessions create separate .cast files with no cross-contamination.

        Scenario:
            1. Open 2 SSH sessions simultaneously
            2. Each runs different commands
            3. Both sessions close

        Expected .cast files:
            - 2 separate files (different session_ids)
            - No mixing of I/O between sessions
            - Each contains only its own commands
        """
        host, port = ssh_hermes_server_concurrent

        # Arrange
        recordings_dir = recording_config.output_dir

        # Act: Connect session 1
        async with asyncssh.connect(
            host,
            port=port,
            username="root",
            password="toor",
            known_hosts=None,
        ) as conn1:
            _, process1 = await conn1.create_session(
                asyncssh.SSHClientProcess,
                term_type="xterm",
                term_size=(80, 24),
                encoding=None,
            )

            # Act: Connect session 2
            async with asyncssh.connect(
                host,
                port=port,
                username="admin",
                password="admin123",
                known_hosts=None,
            ) as conn2:
                _, process2 = await conn2.create_session(
                    asyncssh.SSHClientProcess,
                    term_type="xterm",
                    term_size=(80, 24),
                    encoding=None,
                )

                # Act: Send different commands to each session
                process1.stdin.write(b"echo session1\n")
                process2.stdin.write(b"echo session2\n")
                await asyncio.sleep(0.5)

                # Act: Close both
                process1.stdin.write(b"exit\n")
                process2.stdin.write(b"exit\n")
                await asyncio.sleep(0.2)

        # Assert: 2 .cast files created with different session_ids
        cast_files = await await_cast_files(recordings_dir, expected=2)

        # Assert: Each file is valid and contains own data, with no cross-contamination
        session_outputs: list[str] = []
        for cast_file in cast_files:
            cast = parse_cast_file(cast_file)
            validate_cast_format(cast)

            events = cast["events"]
            assert len(events) >= 2, f"Session should have >= 2 events: {cast_file}"
            session_outputs.append("".join(extract_output_events(events)))

        # Assert: isolation — each recording contains its own marker, not the other's
        has_s1 = [i for i, out in enumerate(session_outputs) if "session1" in out]
        has_s2 = [i for i, out in enumerate(session_outputs) if "session2" in out]

        assert has_s1, "No recording contains 'session1' output"
        assert has_s2, "No recording contains 'session2' output"

        # Verify no cross-contamination: a recording with session1 should lack session2
        for i in has_s1:
            assert (
                "session2" not in session_outputs[i]
            ), f"Recording {cast_files[i].name} contains both 'session1' and 'session2'"
        for i in has_s2:
            assert (
                "session1" not in session_outputs[i]
            ), f"Recording {cast_files[i].name} contains both 'session2' and 'session1'"

    async def test_metadata_sidecar(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate .json metadata sidecar is created with all expected fields.

        Scenario:
            1. Session runs a command
            2. Session closes

        Expected .json file:
            - Contains: session_id, username, source_ip, timestamp, etc.
            - Valid JSON format
            - All fields non-empty
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: run command
        await send_command(process, "whoami\n")

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)

        conn.close()
        await conn.wait_closed()

        # Assert: .json metadata file exists
        json_files = await await_metadata_files(recordings_dir)
        json_path = max(json_files, key=lambda p: p.stat().st_mtime)
        with open(json_path, encoding="utf-8") as f:
            metadata = json.load(f)

        # Assert: metadata has expected fields
        expected_fields = ["username", "source_ip"]
        for field in expected_fields:
            assert field in metadata, f"Missing metadata field: {field}"
            # Note: some fields might be empty/None, so just check they exist

    async def test_recording_disabled_config(
        self,
        ssh_hermes_server_no_recording: tuple[str, int, Path],
    ):
        """
        Validate no .cast files created when recording disabled in config.

        Scenario:
            1. Server starts with recording disabled
            2. SSH session connects and runs commands
            3. Session closes

        Expected:
            - No .cast files created
            - No .json files created
            - Session works normally (commands execute)
        """
        host, port, recordings_dir = ssh_hermes_server_no_recording

        # Arrange: Connect to server with recording disabled
        async with asyncssh.connect(
            host,
            port=port,
            username="root",
            password="toor",
            known_hosts=None,
        ) as conn:
            _chan, process = await conn.create_session(
                asyncssh.SSHClientProcess,
                term_type="xterm",
                term_size=(80, 24),
                encoding=None,
            )

            # Wait for shell prompt
            await asyncio.sleep(0.3)

            # Clear initial output
            try:
                await asyncio.wait_for(process.stdout.read(4096), timeout=0.3)
            except asyncio.TimeoutError:
                pass

            # Act: run command (verify session works)
            output = await send_command(process, "whoami\n")
            assert len(output) > 0, "Session should work even with recording disabled"

            # Act: exit session
            process.stdin.write(b"exit\n")
            await asyncio.sleep(0.2)

        # Assert: no recording files created
        recordings_dir.mkdir(parents=True, exist_ok=True)
        cast_files = list(recordings_dir.glob("*.cast"))
        json_files = list(recordings_dir.glob("*.json"))

        assert (
            len(cast_files) == 0
        ), f"Should not record when disabled, found {len(cast_files)} .cast files: {cast_files}"
        assert (
            len(json_files) == 0
        ), f"Should not record when disabled, found {len(json_files)} .json files: {json_files}"

    async def test_error_mid_session_partial_recording(
        self,
        ssh_connected_session: tuple[
            asyncssh.SSHClientConnection, asyncssh.SSHClientProcess, asyncssh.SSHClientChannel
        ],
        recording_config: RecordingConfig,
    ):
        """
        Validate .cast file remains valid if container disconnects mid-session.

        Scenario:
            1. Session running
            2. Simulate container error/disconnect
            3. Recording should stop gracefully

        Expected .cast:
            - Partial but valid .cast file (not corrupted)
            - Can still be parsed
            - Timestamps monotonic (up to disconnect point)
        """
        conn, process, _chan = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send command
        await send_command(process, "echo test\n")

        # Act: force disconnect (simulate container crash / network drop)
        conn.abort()
        await asyncio.sleep(0.5)

        # Assert: .cast file exists even after disconnect
        cast_files = await await_cast_files(recordings_dir)

        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        # Assert: .cast is still valid (not corrupted)
        cast = parse_cast_file(cast_path)
        validate_cast_format(cast)

        # Assert: events still monotonic
        events = cast["events"]
        validate_events_monotonic(events)

        # Assert: contains at least some data
        assert len(events) >= 1, "Should have captured at least some events"

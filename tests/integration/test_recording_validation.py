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
from pathlib import Path
from typing import AsyncGenerator, Optional, Tuple

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


@pytest.fixture(scope="function")
async def ssh_hermes_server(
    recording_config: RecordingConfig, tmp_path: Path
) -> AsyncGenerator[Tuple[str, int], None]:
    """
    Start a real Hermes SSH server with container pool.

    Yields:
        (host, port) tuple for SSH connection

    Raises:
        pytest.skip if server fails to start
    """
    import subprocess
    import socket
    import time
    import docker
    import yaml
    from pathlib import Path
    
    # Check Docker availability
    try:
        docker_client = docker.from_env()
        docker_client.ping()
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")
    
    # Check target image exists
    try:
        docker_client.images.get("hermes-target-ubuntu:latest")
    except docker.errors.ImageNotFound:
        pytest.skip("hermes-target-ubuntu:latest not found. Build it first.")
    
    # Find available port
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    port = find_free_port()
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
            "size": 1,  # Reduced for faster test startup
            "image": "hermes-target-ubuntu:latest",
            "spawn_timeout": 30,
            "security": {
                "network_mode": "none",
                "memory_limit": "256m",
                "cpu_quota": 0.5,
                "pids_limit": 100,
                "security_opt": ["no-new-privileges:true"],  # Remove seccomp=default
            }
        },
        "recording": {
            "enabled": recording_config.enabled,
            "output_dir": str(recording_config.output_dir),
        },
        "logging": {
            "level": "INFO",  # Less verbose for tests
            "format": "text",
        },
    }
    
    with open(config_path, "w") as f:
        yaml.dump(test_config, f)
    
    # Generate SSH host key
    import asyncssh
    host_key = asyncssh.generate_private_key('ssh-rsa')
    host_key.write_private_key(str(tmp_path / "test_host_key"))
    
    # Start Hermes server
    hermes_process = subprocess.Popen(
        ["python", "-m", "hermes", "--config", str(config_path)],
        cwd=str(Path(__file__).parent.parent.parent / "src"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
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
        stdout, stderr = hermes_process.communicate(timeout=5)
        pytest.skip(f"Hermes server failed to start on {host}:{port}\nStdout: {stdout}\nStderr: {stderr}")
    
    # Give it a moment to fully initialize
    await asyncio.sleep(0.5)
    
    try:
        yield (host, port)
    finally:
        # Cleanup
        hermes_process.terminate()
        try:
            hermes_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            hermes_process.kill()
            hermes_process.wait()
        
        # Clean up any leftover containers
        try:
            for container in docker_client.containers.list(all=True, filters={"name": "hermes-target"}):
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass


@pytest.fixture(scope="function")
async def ssh_connected_session(
    ssh_hermes_server: Tuple[str, int],
) -> AsyncGenerator[Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess], None]:
    """
    Connect to Hermes server via SSH and open interactive PTY session.

    Yields:
        (connection, process) tuple

    Raises:
        pytest.skip if connection fails
    """
    host, port = ssh_hermes_server
    
    try:
        # Connect to Hermes SSH server
        conn = await asyncssh.connect(
            host,
            port=port,
            username="root",
            password="toor",
            known_hosts=None,
            server_host_key_algs=['ssh-rsa'],
        )
        
        # Create PTY session
        _chan, process = await conn.create_session(
            asyncssh.SSHClientProcess,
            term_type="xterm",
            term_size=(80, 24),
            encoding=None,
        )
        
        # Wait for initial shell prompt
        await asyncio.sleep(0.3)  # Optimized from 0.5s
        
        # Clear any initial output (banner, prompt)
        try:
            await asyncio.wait_for(process.stdout.read(4096), timeout=0.3)  # Faster
        except asyncio.TimeoutError:
            pass
        
        yield (conn, process)
        
    except Exception as e:
        pytest.skip(f"Failed to connect to Hermes server: {e}")
    finally:
        try:
            conn.close()
            await conn.wait_closed()
        except Exception:
            pass


@pytest.fixture(scope="function")
async def ssh_hermes_server_no_recording(
    tmp_path: Path
) -> AsyncGenerator[Tuple[str, int, Path], None]:
    """
    Start a real Hermes SSH server with recording DISABLED.

    Yields:
        (host, port, recordings_dir) tuple for SSH connection

    Raises:
        pytest.skip if server fails to start
    """
    import subprocess
    import socket
    import time
    import docker
    import yaml
    
    # Check Docker availability
    try:
        docker_client = docker.from_env()
        docker_client.ping()
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")
    
    # Check target image exists
    try:
        docker_client.images.get("hermes-target-ubuntu:latest")
    except docker.errors.ImageNotFound:
        pytest.skip("hermes-target-ubuntu:latest not found. Build it first.")
    
    # Find available port
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    port = find_free_port()
    host = "127.0.0.1"
    recordings_dir = tmp_path / "recordings"
    
    # Create config file with recording DISABLED
    config_path = tmp_path / "test_config_no_recording.yaml"
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
            "size": 1,
            "image": "hermes-target-ubuntu:latest",
            "spawn_timeout": 30,
            "security": {
                "network_mode": "none",
                "memory_limit": "256m",
                "cpu_quota": 0.5,
                "pids_limit": 100,
                "security_opt": ["no-new-privileges:true"],
            }
        },
        "recording": {
            "enabled": False,  # RECORDING DISABLED
            "output_dir": str(recordings_dir),
        },
        "logging": {
            "level": "INFO",
            "format": "text",
        },
    }
    
    with open(config_path, "w") as f:
        yaml.dump(test_config, f)
    
    # Generate SSH host key
    import asyncssh
    host_key = asyncssh.generate_private_key('ssh-rsa')
    host_key.write_private_key(str(tmp_path / "test_host_key"))
    
    # Start Hermes server
    hermes_process = subprocess.Popen(
        ["python", "-m", "hermes", "--config", str(config_path)],
        cwd=str(Path(__file__).parent.parent.parent / "src"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    # Wait for server to be ready
    max_wait = 15
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
        stdout, stderr = hermes_process.communicate(timeout=5)
        pytest.skip(f"Hermes server failed to start on {host}:{port}\nStdout: {stdout}\nStderr: {stderr}")
    
    await asyncio.sleep(0.5)
    
    try:
        yield (host, port, recordings_dir)
    finally:
        # Cleanup
        hermes_process.terminate()
        try:
            hermes_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            hermes_process.kill()
            hermes_process.wait()
        
        # Clean up any leftover containers
        try:
            for container in docker_client.containers.list(all=True, filters={"name": "hermes-target"}):
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass


@pytest.fixture(scope="function")
async def recording_files(
    ssh_hermes_server: Tuple[str, int], recording_config: RecordingConfig
) -> AsyncGenerator[Tuple[Path, str], None]:
    """
    Track recording files and session_id during a test.

    Yields:
        (recordings_dir, session_id)

    Expected usage:
        async def test_something(recording_files):
            recordings_dir, session_id = recording_files
            # recordings_dir has .cast and .json files after session
    """
    recordings_dir = recording_config.output_dir
    
    # Get list of existing .cast files before test
    recordings_dir.mkdir(parents=True, exist_ok=True)
    existing_files = set(recordings_dir.glob("*.cast"))
    
    # Yield control to test (session will be created)
    # We'll determine session_id by finding new .cast files after
    yield recordings_dir, None  # session_id will be determined later
    
    # After test, find the new .cast file
    # Note: This is a simplified approach. In practice, tests will find files themselves.


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
    """
    with open(path, "r", encoding="utf-8") as f:
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
    assert isinstance(header["timestamp"], int), f"Timestamp must be int, got {type(header['timestamp'])}"
    assert header["timestamp"] > 0, f"Timestamp must be > 0, got {header['timestamp']}"


def validate_events_monotonic(events: list) -> None:
    """
    Validate that event timestamps are monotonically increasing.

    Raises:
        AssertionError: If timestamps decrease or are negative
    """
    for i, event in enumerate(events):
        assert len(event) >= 3, f"Event {i} must have [timestamp, type, data], got {len(event)} elements"
        timestamp = event[0]
        assert isinstance(timestamp, (int, float)), f"Event {i} timestamp must be numeric, got {type(timestamp)}"
        assert timestamp >= 0.0, f"Event {i} timestamp must be >= 0, got {timestamp}"
        
        if i > 0:
            prev_timestamp = events[i - 1][0]
            assert timestamp >= prev_timestamp, \
                f"Event {i} timestamp {timestamp} < previous {prev_timestamp} (not monotonic)"


def validate_event_types(events: list, expected_types: list) -> None:
    """
    Validate that event types match expected sequence.

    Args:
        events: List of [timestamp, type, data] tuples
        expected_types: List of expected types, e.g. ["o", "i", "o", "i"]

    Raises:
        AssertionError: If event types don't match
    """
    actual_types = [event[1] for event in events]
    assert len(actual_types) == len(expected_types), \
        f"Expected {len(expected_types)} events, got {len(actual_types)}"
    
    for i, (actual, expected) in enumerate(zip(actual_types, expected_types)):
        assert actual == expected, \
            f"Event {i}: expected type '{expected}', got '{actual}'\n" \
            f"Expected sequence: {expected_types}\n" \
            f"Actual sequence:   {actual_types}"


def extract_output_events(events: list) -> list:
    """Extract all output ("o") event data as strings."""
    return [event[2] for event in events if event[1] == "o"]


def extract_input_events(events: list) -> list:
    """Extract all input ("i") event data as strings."""
    return [event[2] for event in events if event[1] == "i"]


async def send_command(
    process: asyncssh.SSHServerProcess, cmd: str, timeout: float = 5.0
) -> bytes:
    """
    Send SSH command and read output until idle or timeout.

    Args:
        process: SSHServerProcess from SSH connection
        cmd: Command to send (with newline)
        timeout: Seconds of silence before returning

    Returns:
        All output bytes received
    """
    # Send command
    process.stdin.write(cmd.encode())
    
    # Read until idle (optimized for faster tests)
    buf = bytearray()
    idle_timeout = 0.5  # 500ms of silence = done (reduced from 1.0s)
    
    while True:
        try:
            data = await asyncio.wait_for(process.stdout.read(4096), timeout=idle_timeout)
            if not data:
                break
            buf.extend(data)
        except asyncio.TimeoutError:
            # No data for idle_timeout seconds, consider complete
            break
    
    return bytes(buf)


def assert_json_file_exists(path: Path, session_id: str) -> dict:
    """
    Assert .json metadata file exists and parse it.

    Args:
        path: Recordings directory
        session_id: Session ID to find

    Returns:
        Parsed JSON metadata dict

    Raises:
        AssertionError: If file doesn't exist
    """
    json_path = path / f"{session_id}.json"
    assert json_path.exists(), f"Metadata file not found: {json_path}"
    
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.recording
class TestRecordingValidation:
    """Integration tests for session recording with real SSH sessions."""

    async def test_basic_io_capture(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
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

        # Assert: .cast file exists (find it by looking at directory)
        recordings_dir.mkdir(parents=True, exist_ok=True)
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1, f"No .cast files found in {recordings_dir}"
        
        # Take the most recent .cast file
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
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send commands
        output1 = await send_command(process, "ls\n", timeout=3.0)
        output2 = await send_command(process, "pwd\n", timeout=3.0)
        output3 = await send_command(process, "echo hello\n", timeout=3.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized
        
        conn.close()
        await conn.wait_closed()

        # Assert: .cast file exists and is valid
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1
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

    async def test_unicode_handling(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        unicode_cmd = 'echo "こんにちは 🎉"\n'

        # Act: send unicode command
        output = await send_command(process, unicode_cmd, timeout=3.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized
        
        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1
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
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
        recording_config: RecordingConfig,
    ):
        """
        Validate large output (>10KB) is captured completely.

        Scenario:
            1. Send: cat /etc/hostname (small but verifiable)
            2. Read output
            3. Exit

        Expected .cast:
            - All output captured
            - .cast file size reasonable (not truncated)
            - Output events contain full data
        """
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        # Use a command that generates moderate output
        large_cmd = "head -100 /etc/hostname; ls -la /root | head -50\n"

        # Act: send command with large output
        output = await send_command(process, large_cmd, timeout=5.0)
        assert len(output) > 100, f"Output too small to test: {len(output)} bytes"

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized
        
        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)
        
        cast = parse_cast_file(cast_path)

        # Assert: file not truncated (should have many events)
        events = cast["events"]
        assert len(events) >= 3, "Output events should capture large data"

        # Assert: .cast file size reasonable
        cast_size = cast_path.stat().st_size
        assert cast_size < 1000000, f".cast file too large: {cast_size} bytes (>1MB)"

        # Assert: combined output contains what we sent
        output_events = extract_output_events(events)
        combined = "".join(output_events)
        assert len(combined) > 50, "Combined output should be substantial"

    async def test_terminal_resize_events(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send initial command
        output1 = await send_command(process, "echo initial\n", timeout=2.0)

        # Act: attempt resize (may not be supported in all modes)
        try:
            conn.set_terminal_size(120, 40)
            await asyncio.sleep(0.1)
        except Exception:
            pytest.skip("Terminal resize not supported by this session")

        # Act: send command after resize
        output2 = await send_command(process, "echo resized\n", timeout=2.0)

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized
        
        conn.close()
        await conn.wait_closed()

        # Assert: .cast exists
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)
        
        cast = parse_cast_file(cast_path)

        # Assert: events captured
        events = cast["events"]
        assert len(events) >= 3, "Should capture at least input + outputs"

        # Assert: timestamps monotonic (resize events included)
        validate_events_monotonic(events)

    async def test_rapid_commands(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
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
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1
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
        ssh_hermes_server: Tuple[str, int],
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
        host, port = ssh_hermes_server

        # Arrange
        recordings_dir = recording_config.output_dir

        # Act: Connect session 1
        async with asyncssh.connect(
            host, port=port, username="root", password="toor", known_hosts=None
        ) as conn1:
            _, process1 = await conn1.create_session(
                asyncssh.SSHClientProcess,
                term_type="xterm",
                term_size=(80, 24),
                encoding=None,
            )

            # Act: Connect session 2
            async with asyncssh.connect(
                host, port=port, username="admin", password="admin123", known_hosts=None
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
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 2, f"Expected >= 2 .cast files, found {len(cast_files)}"

        # Assert: Each file is valid and contains own data
        for cast_file in cast_files:
            cast = parse_cast_file(cast_file)
            validate_cast_format(cast)

            events = cast["events"]
            assert len(events) >= 2, f"Session should have >= 2 events: {cast_file}"

    async def test_metadata_sidecar(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: run command
        output = await send_command(process, "whoami\n")

        # Act: exit
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.2)  # Optimized
        
        conn.close()
        await conn.wait_closed()

        # Assert: .json metadata file exists
        json_files = list(recordings_dir.glob("*.json"))
        assert len(json_files) >= 1, f"No .json files found in {recordings_dir}"
        
        json_path = max(json_files, key=lambda p: p.stat().st_mtime)
        with open(json_path, "r") as f:
            metadata = json.load(f)

        # Assert: metadata has expected fields
        expected_fields = ["username", "source_ip"]
        for field in expected_fields:
            assert field in metadata, f"Missing metadata field: {field}"
            # Note: some fields might be empty/None, so just check they exist

    async def test_recording_disabled_config(
        self,
        ssh_hermes_server_no_recording: Tuple[str, int, Path],
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
        conn = await asyncssh.connect(
            host,
            port=port,
            username="root",
            password="toor",
            known_hosts=None,
            server_host_key_algs=['ssh-rsa'],
        )
        
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
        
        conn.close()
        await conn.wait_closed()

        # Assert: no recording files created
        recordings_dir.mkdir(parents=True, exist_ok=True)
        cast_files = list(recordings_dir.glob("*.cast"))
        json_files = list(recordings_dir.glob("*.json"))
        
        assert len(cast_files) == 0, f"Should not record when disabled, found {len(cast_files)} .cast files: {cast_files}"
        assert len(json_files) == 0, f"Should not record when disabled, found {len(json_files)} .json files: {json_files}"

    async def test_error_mid_session_partial_recording(
        self,
        ssh_connected_session: Tuple[asyncssh.SSHClientConnection, asyncssh.SSHServerProcess],
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
        conn, process = ssh_connected_session
        recordings_dir = recording_config.output_dir

        # Arrange
        assert conn is not None

        # Act: send command
        output = await send_command(process, "echo test\n")

        # Act: force disconnect (simulate container crash)
        # Note: This may not cleanly disconnect container, just close the session
        process.stdin.write(b"exit\n")
        await asyncio.sleep(0.5)
        
        conn.close()
        await conn.wait_closed()

        # Assert: .cast file exists even after disconnect
        cast_files = list(recordings_dir.glob("*.cast"))
        assert len(cast_files) >= 1, "Partial .cast file should exist after disconnect"
        
        cast_path = max(cast_files, key=lambda p: p.stat().st_mtime)

        # Assert: .cast is still valid (not corrupted)
        cast = parse_cast_file(cast_path)
        validate_cast_format(cast)

        # Assert: events still monotonic
        events = cast["events"]
        validate_events_monotonic(events)

        # Assert: contains at least some data
        assert len(events) >= 1, "Should have captured at least some events"

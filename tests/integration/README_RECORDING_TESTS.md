# Session Recording Validation Tests

## Overview

Integration tests that validate session recording functionality using **real SSH sessions** connecting to a live Hermes server with Docker containers.

## Test Coverage

| Test | Purpose | Status |
|------|---------|--------|
| `test_basic_io_capture` | Validates basic I/O (input/output) recording | ✅ Pass |
| `test_multiple_commands` | Multiple commands with correct event interleaving | ✅ Pass |
| `test_unicode_handling` | Unicode and emoji preservation in recordings | ✅ Pass |
| `test_large_output` | Large output handling (>10KB) | ✅ Pass |
| `test_terminal_resize_events` | Terminal resize event recording | ⏭️ Skip (not supported) |
| `test_rapid_commands` | Rapid-fire commands without data loss | ✅ Pass |
| `test_concurrent_sessions_recording` | Multiple simultaneous sessions isolated | ✅ Pass |
| `test_metadata_sidecar` | JSON metadata sidecar file creation | ✅ Pass |
| `test_recording_disabled_config` | Verify no recording when disabled | ⏭️ Skip (TODO) |
| `test_error_mid_session_partial_recording` | Partial recording remains valid | ✅ Pass |

**Total: 8 passing, 2 skipped**

## Prerequisites

### 1. Docker Running
```bash
docker --version  # Verify Docker is installed
docker ps         # Verify Docker daemon is running
```

### 2. Target Container Image Built
```bash
# Build the Ubuntu target container
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/
```

### 3. Python Environment
```bash
source venv/bin/activate
pip install -r requirements-dev.txt
```

## Running Tests

### Run All Recording Tests
```bash
pytest tests/integration/test_recording_validation.py -v
```

### Run Specific Test
```bash
pytest tests/integration/test_recording_validation.py::TestRecordingValidation::test_basic_io_capture -v
```

### Run with Markers
```bash
# All recording validation tests
pytest -m recording -v

# All integration tests
pytest -m integration -v

# Skip slow tests
pytest -m "not slow" -v
```

### Run with Coverage
```bash
pytest tests/integration/test_recording_validation.py --cov=hermes.session --cov-report=term-missing
```

### Clean Docker Containers Before Running
```bash
docker ps -a --filter "name=hermes-target" -q | xargs -r docker rm -f
pytest tests/integration/test_recording_validation.py -v
```

## Test Architecture

### Fixtures

#### `recording_config`
- Creates a `RecordingConfig` with output to temp directory
- **Scope**: function
- **Usage**: All tests

#### `ssh_hermes_server`
- Starts a real Hermes SSH server on random port
- Initializes Docker container pool (1 container for tests)
- **Scope**: function
- **Yields**: `(host, port)` tuple
- **Cleanup**: Terminates server, removes containers

#### `ssh_connected_session`
- Connects to Hermes via SSH (asyncssh)
- Opens interactive PTY session (80x24)
- **Scope**: function
- **Yields**: `(connection, process)` tuple
- **Cleanup**: Closes SSH connection

### Helper Functions

#### `parse_cast_file(path: Path) -> dict`
Parses `.cast` file into header and events.

**Returns**:
```python
{
    "header": {"version": 2, "width": 80, "height": 24, ...},
    "events": [[0.123, "o", "data"], [0.456, "i", "cmd"], ...]
}
```

#### `validate_cast_format(cast: dict)`
Validates asciicast v2 header structure.

**Checks**:
- Version == 2
- Width/height are positive integers
- Timestamp is present

#### `validate_events_monotonic(events: list)`
Ensures event timestamps are non-decreasing.

#### `send_command(process, cmd: str) -> bytes`
Sends SSH command and reads output until idle.

**Optimizations**:
- 500ms idle timeout (reduced from 1.0s)
- 4KB read chunks

## What Tests Validate

### 1. Format Correctness
- `.cast` files are valid asciicast v2 format
- Header contains required fields (version, width, height, timestamp)
- Events are properly formatted `[timestamp, type, data]` tuples

### 2. I/O Accuracy
- **Input events** (`"i"`) capture user commands exactly
- **Output events** (`"o"`) capture container output exactly
- **Interleaving** is correct (input → output → input → output)

### 3. Timing Accuracy
- Timestamps start at 0.0
- Timestamps are monotonically increasing
- Elapsed time is realistic (not negative, not huge jumps)

### 4. Edge Cases
- **Unicode/emoji** preserved without corruption
- **Large output** (>10KB) captured completely
- **Rapid commands** don't lose data
- **Concurrent sessions** don't mix data
- **Partial recordings** (interrupted sessions) remain valid

### 5. Metadata
- `.json` sidecar files created alongside `.cast`
- Contain session metadata (username, source_ip, etc.)

## Performance

### Typical Execution Time
- **Single test**: ~2-4 seconds
- **Full suite (8 tests)**: ~25-30 seconds

### Performance Optimizations
- Reduced sleep times (0.2s instead of 0.5s)
- Faster idle detection (500ms instead of 1.0s)
- Single container pool (reduced from 2)
- Reuse fixtures where possible

## Troubleshooting

### Tests Skipped: "Docker not available"
```bash
# Verify Docker is running
docker ps

# Check Docker socket
ls -la /var/run/docker.sock
```

### Tests Skipped: "hermes-target-ubuntu:latest not found"
```bash
# Build the target image
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/
```

### Tests Fail: "Container name already in use"
```bash
# Clean up old containers
docker ps -a --filter "name=hermes-target" -q | xargs -r docker rm -f
```

### Tests Timeout
- Increase timeout in test command: `timeout 180 pytest ...`
- Check Docker performance: `docker info`

### Server Fails to Start: "Seccomp profile error"
- This was fixed by removing `seccomp=default` from test config
- Docker applies default seccomp automatically

## Known Issues

### test_recording_disabled_config (Skipped)
**Issue**: Test requires separate server fixture with recording disabled.

**Current Behavior**: Uses `ssh_connected_session` which starts server with recording enabled.

**Solution**: Create dedicated fixture for disabled recording server.

**Workaround**: Test is skipped with TODO marker.

### test_terminal_resize_events (Skipped)
**Issue**: Terminal resize not fully supported in current Docker exec implementation.

**Expected**: This is a known limitation, not a bug.

**Future**: May be supported with SIGWINCH forwarding.

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build Target Container
  run: docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/

- name: Run Recording Tests
  run: |
    source venv/bin/activate
    pytest tests/integration/test_recording_validation.py -v --tb=short
```

### Cleanup After Tests
```yaml
- name: Cleanup Containers
  if: always()
  run: docker ps -a --filter "name=hermes-target" -q | xargs -r docker rm -f
```

## Future Enhancements

1. **Parallel Test Execution**: Run tests in parallel with pytest-xdist
2. **Recording Playback Validation**: Verify `.cast` files play correctly with asciinema player
3. **Stress Testing**: 10+ concurrent sessions
4. **Binary Data Tests**: Test with truly binary data (not just unicode)
5. **Compression Tests**: Verify recordings are reasonably sized

## Contributing

When adding new recording validation tests:

1. **Follow TDD**: Write test first (RED), implement (GREEN), refactor
2. **Use fixtures**: Reuse `ssh_connected_session` when possible
3. **Document**: Add clear docstrings explaining what's being validated
4. **Optimize**: Keep timeouts minimal, clean up resources
5. **Mark appropriately**: Use `@pytest.mark.recording` marker

# Session Recording Validation — TDD Implementation Plan

## Goal
Enhance session recording testing with real SSH integration tests to validate that .cast files correctly capture all session I/O (input, output, timing, terminal events).

## Current State
- ✅ SessionRecorder fully implemented (asciicast v2 format)
- ✅ 22 unit tests for recorder component
- ✅ Integration tests with mocked containers
- ❌ **Missing**: Real SSH session integration tests validating I/O capture

## What We'll Build

### Integration Test Suite: `tests/integration/test_recording_validation.py`

**Core Feature**: Real SSH sessions → Hermes server → Docker container → Verify .cast file accuracy

#### Test 1: Basic Session Recording with Real I/O
```
Scenario: User connects, runs "whoami", exits
Expected:
  - .cast file exists with correct session_id
  - Header: version=2, width/height from PTY request
  - Event 1: "o" (output) - shell prompt "$ " or "#"
  - Event 2: "i" (input) - "whoami\n"
  - Event 3: "o" (output) - "root\n"
  - Event 4: "i" (input) - "exit\n"
  - All timestamps ≥ 0 and monotonic
```

#### Test 2: Multiple Commands in Single Session
```
Scenario: User runs: ls, pwd, echo "hello", exit
Expected:
  - All 3 commands captured as input events
  - All outputs captured as output events
  - Correct interleaving: input → output → input → output ...
  - ~8-10 events total (prompts + commands + outputs)
```

#### Test 3: Unicode and Binary Data Handling
```
Scenario: User echoes unicode: echo "こんにちは 🎉"
Expected:
  - Unicode properly captured (not corrupted)
  - Binary replacement char (U+FFFD) only for truly invalid bytes
  - Output readable in .cast file
```

#### Test 4: Large Command Output
```
Scenario: User runs: cat /etc/hostname (outputs ~20KB)
Expected:
  - Single "o" event with all output data
  - Output truncated gracefully if needed
  - File size reasonable (compressed JSON)
```

#### Test 5: Terminal Resize Events
```
Scenario: Session starts 80x24, resizes mid-session to 120x40, then 40x20
Expected:
  - Header: width=80, height=24 (initial)
  - After input, "r" event: "120x40" (if resize handled)
  - Another "r" event: "40x20"
  - Output still readable after resize
```

#### Test 6: Rapid Fire Commands
```
Scenario: User runs 10 commands rapidly with minimal delay
Expected:
  - All inputs captured
  - All outputs captured
  - No loss/corruption
  - Timing still accurate
```

#### Test 7: Concurrent Sessions Recording
```
Scenario: 2+ SSH sessions running simultaneously
Expected:
  - Each gets separate .cast file (unique session_id)
  - No cross-contamination of data
  - All timings accurate
```

#### Test 8: Metadata Validation
```
Scenario: Session completes, .json metadata file created
Expected:
  - .json contains:
    - session_id
    - username (from SSH auth)
    - source_ip
    - source_port
    - container_id
    - timestamp (or duration)
```

#### Test 9: Recording Disabled Config
```
Scenario: Recording disabled in config, session runs
Expected:
  - No .cast files created
  - No .json files created
  - Session works normally
```

#### Test 10: Recording with Error Mid-Session
```
Scenario: Container crashes/disconnects mid-session
Expected:
  - Recording stops gracefully
  - Partial .cast file valid (not corrupted)
  - Can still be replayed
```

## Test Infrastructure

### Fixtures Needed

1. **ssh_server_with_pool** - Starts real Hermes server
   - Config with recording enabled
   - Container pool initialized
   - SSH server listening on test port

2. **recording_config** - Recording configuration pointing to tmp_path

3. **ssh_client_connected** - Connects to Hermes SSH server
   - PTY session
   - Authenticated as test user
   - Returns asyncssh connection + process

4. **cast_file_parser** - Helper to parse .cast files
   - Validates format
   - Extracts events
   - Validates timing monotonicity

5. **event_validator** - Helper to validate event structure
   - Check [timestamp, type, data] format
   - Type validation ("i", "o", "r")
   - Data type validation (string)

### Helper Functions

```python
def parse_cast_file(path: Path) -> dict
    """Parse .cast file, return {header, events}"""
    
def validate_cast_format(cast: dict) -> bool
    """Check version, width, height, timestamp exist"""
    
def validate_events_monotonic(events: list) -> bool
    """Verify timestamps are monotonically increasing"""
    
def validate_event_types(events: list, expected: list) -> bool
    """Verify sequence of event types matches expected"""
    
async def send_command(process, cmd: str) -> bytes
    """Send command, read until prompt, return output"""
    
def extract_output_events(events: list) -> list[str]
    """Get all "o" event data in order"""
    
def extract_input_events(events: list) -> list[str]
    """Get all "i" event data in order"""
```

## Implementation Order (TDD: Red → Green → Refactor)

### Phase 1: Test Infrastructure
1. **Red**: Write fixture `ssh_server_with_pool`
   - Attempts to start real Hermes server
   - Test fails (server not running)
2. **Green**: Create minimal server context manager
   - Starts server in background
   - Returns connection details
3. **Refactor**: Clean up, add error handling

### Phase 2: Basic I/O Validation
1. **Red**: Test 1 - Basic session recording
   - Connects, runs "whoami", exits
   - Asserts .cast file exists
   - Asserts 5 events captured
2. **Green**: Implementation (proxy already works)
   - Connect, run command, verify file
3. **Refactor**: Extract helpers, add logging

### Phase 3: Event Validation
1. **Red**: Test event types and order
   - "o", "i", "o", "i" pattern
   - Event data matches what was sent/received
2. **Green**: Implement validators
   - Parse .cast file
   - Extract events
   - Compare to expected
3. **Refactor**: Reusable event validators

### Phase 4: Advanced Scenarios
1. **Red**: Tests 4-10 (large data, unicode, concurrent, etc.)
2. **Green**: Run through scenarios, verify capture
3. **Refactor**: Consolidate helpers, parameterize tests

### Phase 5: Documentation & Integration
1. Add test markers (@pytest.mark.recording, @pytest.mark.integration)
2. Document test running: `pytest tests/integration/test_recording_validation.py -v -m recording`
3. Add to CI/CD pipeline

## Test Markers & Execution

```bash
# Run all recording tests
pytest tests/integration/test_recording_validation.py -v

# Run specific test
pytest tests/integration/test_recording_validation.py::TestRecordingValidation::test_basic_io_capture -v

# Run with recording marker
pytest -m recording -v

# Run with docker marker (requires Docker)
pytest -m docker -v
```

## Expected Results

**After Implementation:**
- ✅ 10 new integration tests
- ✅ .cast file format validation
- ✅ Event sequence validation
- ✅ I/O accuracy verification
- ✅ Unicode/binary handling proof
- ✅ Concurrent recording validation
- ✅ Metadata completeness check
- ✅ Integration test infrastructure for future phases

## Files to Create/Modify

### New Files
- `tests/integration/test_recording_validation.py` - 600+ lines
- `tests/integration/conftest.py` (or extend) - Server fixtures

### Modified Files
- `tests/integration/conftest.py` - Add shared fixtures
- `pytest.ini` - Add recording marker

## Success Criteria

1. All 10 tests pass consistently
2. .cast files valid asciicast v2 format
3. I/O accurately captured (no loss/corruption)
4. Timing accurate (monotonic, realistic)
5. Edge cases handled gracefully
6. Tests run in <120 seconds total
7. Clear documentation for running tests

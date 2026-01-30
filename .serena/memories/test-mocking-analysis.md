# Test Mocking Analysis & Improvement Opportunities

## Current Mocking Patterns

### 1. **Fixture-level Mocking** (`test_container_proxy.py`)
- `mock_process`: Generic MagicMock with AsyncMock for I/O streams
  - `process.stdin = AsyncMock()`
  - `process.stdout.write = MagicMock()`
  - `process.stdout.drain = AsyncMock()`
  - `process.stderr = MagicMock()`
  
- `mock_container`: Simple MagicMock with hardcoded container ID
  - `container.id = "abc123def456"`

- `pty_request`: Real PTYRequest object (good practice)

**Issues:**
- No error-case fixtures (e.g., stdin that raises, container that fails)
- stdout and stderr are bare MagicMocks; don't track write order or content
- Process doesn't simulate realistic behavior (e.g., EOF on stdin, disconnects)

### 2. **Loop/Asyncio Mocking** (`test_container_proxy.py`)
Patterns like:
```python
with patch.object(loop, "sock_sendall", side_effect=BrokenPipeError):
with patch.object(loop, "sock_recv", new_callable=AsyncMock, return_value=b""):
```

**Issues:**
- Getting and patching `asyncio.get_event_loop()` each time is boilerplate
- No centralized fixtures for common event loop patches

### 3. **Handler Mocking** (`test_session_handler.py`)
Repeated pattern:
```python
with patch("hermes.__main__.ContainerProxy") as MockProxy, \
     patch("hermes.__main__.SessionRecorder") as MockRecorder:
    proxy_instance = AsyncMock()
    MockProxy.return_value = proxy_instance
    recorder_instance = MagicMock()
    MockRecorder.return_value = recorder_instance
```

**Issues:**
- Boilerplate repeated 5+ times
- Always returns `AsyncMock` for proxy and `MagicMock` for recorder (no variation)
- Could be abstracted into a fixture factory

### 4. **Recorder Mocking** (`test_container_proxy.py` and `test_session_handler.py`)
- Simple `recorder = MagicMock()` 
- No error case: recorder that fails to write, fails to start, etc.

## Improvement Opportunities

### High Priority

1. **Fixture Factory for Handler Mocks** (reduces repetition in `test_session_handler.py`)
   - Create `@pytest.fixture` that returns a factory function
   - Accepts optional kwargs to customize proxy/recorder behavior
   - Eliminates 5 repeated `patch()` blocks

2. **Process Fixture Variants** (enables better EOF/error testing)
   - `mock_process` (current)
   - `mock_process_eof` - stdin raises EOFError after first read
   - `mock_process_write_error` - stdout.write raises on second call
   - Reusable in both `test_container_proxy.py` and `test_session_handler.py`

3. **Container Fixture Variants** (tests error paths)
   - `mock_container` (current)
   - `mock_container_exec_fails` - exec_run raises RuntimeError
   - `mock_container_socket_error` - socket.setblocking raises OSError

### Medium Priority

4. **Event Loop Patch Fixtures**
   - `mock_sock_sendall` fixture (pre-patches loop.sock_sendall)
   - `mock_sock_recv` fixture
   - Reduces nesting in tests; cleaner parametrization

5. **Recorder Error Cases** (in `test_session_recorder.py`)
   - Already has one error case (file write fails)
   - Add: recorder start fails, file doesn't exist, permission denied

### Low Priority

6. **Socket Mock Class Reuse**
   - The `SocketMock` we created for `test_start_sets_socket_nonblocking` 
   - Could move to conftest.py as reusable utility
   - Add variants: `NonBlockingSocket`, `FailingSocket`, `ClosedSocket`

## Recommended Implementation Order

1. Create `tests/unit/conftest.py` with fixtures and utilities
2. Add fixture factory for handler patches (immediate 50-line reduction)
3. Add process/container variant fixtures (enables new error-case tests)
4. Refactor existing tests to use new fixtures
5. Add socket utilities to conftest.py

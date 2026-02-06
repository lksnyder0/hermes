# Fixtures Guide for Hermes Tests

Fixtures are the foundation of Hermes tests. This guide covers using and creating them effectively.

## Table of Contents
- [Using Shared Fixtures](#using-shared-fixtures)
- [Creating New Fixtures](#creating-new-fixtures)
- [Fixture Scope and Cleanup](#fixture-scope-and-cleanup)
- [Parametrized Fixtures](#parametrized-fixtures)

## Using Shared Fixtures

### Available Fixtures from `tests/unit/conftest.py`

#### `pty_request`
Standard PTY configuration used across most tests:

```python
@pytest.mark.asyncio
async def test_something(self, pty_request):
    # pty_request = PTYRequest(
    #     term_type="xterm-256color",
    #     width=120,
    #     height=40,
    # )
    proxy = ContainerProxy(container, pty_request)
```

#### `mock_process`
Mock SSH process with realistic async stdin/stdout:

```python
@pytest.mark.asyncio
async def test_something(self, mock_process):
    # mock_process.stdin = AsyncMock()
    # mock_process.stdout.write = MagicMock()
    # mock_process.stdout.drain = AsyncMock()
    mock_process.stdin.read.return_value = b"user input"
    await handle_process(mock_process)
```

#### `mock_pool`
Mock container pool for testing allocation/release:

```python
@pytest.mark.asyncio
async def test_something(self, mock_pool, mock_container):
    mock_pool.allocate.return_value = mock_container
    container = await pool.allocate("session-id")
    mock_pool.allocate.assert_called_once()
```

#### `mock_container`
Basic mock Docker container:

```python
@pytest.mark.asyncio
async def test_something(self, mock_container):
    # mock_container.id = "abc123def456"
    assert mock_container.id
```

#### `mock_recorder`
Mock SessionRecorder:

```python
@pytest.mark.asyncio
async def test_something(self, mock_recorder):
    recorder = mock_recorder
    await recorder.start()
    recorder.start.assert_called_once()
```

#### `patch_handler_deps()`
Factory fixture for patching dependencies in container_session_handler:

```python
@pytest.mark.asyncio
async def test_something(self, patch_handler_deps):
    with patch_handler_deps() as (MockProxy, MockRecorder, proxy_inst, recorder_inst):
        # MockProxy and MockRecorder are the patch objects
        # proxy_inst and recorder_inst are the mock instances
        await container_session_handler(...)
        proxy_inst.start.assert_called_once()
```

### Fixture Variants for Error Cases

Specialized fixtures for testing failure modes:

- **`mock_process_eof`**: Process that returns empty bytes (EOF) on stdin read
- **`mock_process_write_error`**: Process where stdout.write raises after first call
- **`mock_container_exec_fails`**: Container where exec_run raises RuntimeError
- **`mock_container_socket_error`**: Container where socket.setblocking raises

```python
@pytest.mark.asyncio
async def test_handles_socket_error(self, mock_container_socket_error):
    """Should gracefully handle socket errors."""
    proxy = ContainerProxy(mock_container_socket_error, pty_request)
    # Test behavior when socket operations fail
```

## Creating New Fixtures

### Simple Test Data Fixtures

For data that's used by one test or a few tests, create simple fixtures:

```python
@pytest.fixture
def session_info():
    """Standard session info for tests."""
    return SessionInfo(
        session_id="test-session-1",
        username="testuser",
        source_ip="192.168.1.100",
        source_port=12345,
        authenticated=True,
    )
```

### Fixtures that Extend Shared Ones

If you need a variant of a shared fixture, reuse the fixture by name:

```python
# In your test file
@pytest.fixture
def mock_pool(mock_pool):
    """Extend the shared mock_pool with additional behavior."""
    mock_pool.get_status = AsyncMock(return_value={"active": 2})
    return mock_pool

@pytest.fixture
def mock_process(mock_process):
    """Add handler-specific attributes to the shared mock_process."""
    mock_process.exit = MagicMock()
    return mock_process
```

### Fixtures with Parameters

Use `request.param` to create parametrized fixtures:

```python
@pytest.fixture(params=["xterm-256color", "xterm"])
def pty_request(request):
    """Test with different terminal types."""
    return PTYRequest(
        term_type=request.param,
        width=120,
        height=40,
    )
```

Then use with `indirect` in tests:

```python
@pytest.mark.parametrize("pty_request", ["xterm-256color", "xterm"], indirect=True)
@pytest.mark.asyncio
async def test_handles_terminal_types(self, pty_request):
    """Should work with different terminal types."""
    proxy = ContainerProxy(container, pty_request)
```

### Fixtures with Setup and Teardown

Use `yield` for setup/teardown:

```python
@pytest.fixture
async def temp_recording_dir():
    """Create and clean up a temporary recording directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
    # Cleanup happens automatically after yield
```

Or use context managers:

```python
@pytest.fixture
def recording_config(tmp_path):
    """Recording config pointing to temp directory."""
    config = RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )
    return config
```

## Fixture Scope and Cleanup

### Function Scope (Default)

Each test gets a fresh fixture instance:

```python
@pytest.fixture  # scope='function' is default
def mock_container():
    """Fresh container for each test."""
    return MagicMock()
```

Use this for most fixtures—it prevents test pollution.

### Module Scope

Reused across all tests in a module (faster but risky):

```python
@pytest.fixture(scope="module")
def shared_config():
    """Loaded once for all tests in module."""
    return load_config("test-config.yaml")
```

Only use module scope for truly immutable, read-only data.

### Cleanup with Yield

Use `yield` to run code after each test:

```python
@pytest.fixture
def cleanup_container():
    """Create container, ensure cleanup."""
    container = MagicMock()
    container.id = "test-123"
    yield container
    # Cleanup code here
    container.stop()
```

## Fixture Composition

Combine fixtures to build complex test scenarios:

```python
@pytest.fixture
def handler_test_setup(session_info, pty_request, mock_process, mock_pool, mock_container):
    """Complete setup for handler tests."""
    mock_pool.allocate.return_value = mock_container
    return {
        'session_info': session_info,
        'pty_request': pty_request,
        'process': mock_process,
        'pool': mock_pool,
        'container': mock_container,
    }

@pytest.mark.asyncio
async def test_using_composed_fixtures(self, handler_test_setup):
    setup = handler_test_setup
    await container_session_handler(
        setup['session_info'],
        setup['pty_request'],
        setup['process'],
        setup['pool'],
    )
```

## Best Practices

1. **One fixture per concern**: Create separate fixtures for session info, container, pool, etc.
2. **Use shared fixtures**: Don't recreate mocks already in conftest.py
3. **Name fixtures clearly**: `mock_process_eof` vs just `mock_process`
4. **Keep fixtures small**: If a fixture is doing too much setup, split it
5. **Avoid complex logic**: Fixtures should be simple; complex setup belongs in the test
6. **Use parametrization for variants**: Don't create 10 similar fixtures
7. **Clean up resources**: Use `yield` or context managers for temporary resources

# Real Test Patterns from Hermes

This document shows actual patterns extracted from the Hermes test suite that you should follow.

## Table of Contents
- [Class-Based Organization](#class-based-organization)
- [Fixture Patterns](#fixture-patterns)
- [Mocking Containers](#mocking-containers)
- [Testing Lifecycle Management](#testing-lifecycle-management)
- [Error Path Testing](#error-path-testing)

## Class-Based Organization

Organize tests using classes for logical grouping:

```python
class TestContainerSessionHandler:
    """Tests for the top-level container_session_handler."""
    
    @pytest.mark.asyncio
    async def test_allocates_and_releases_container(self, session_info, pty_request, mock_process, mock_pool, mock_container):
        """Should allocate a container and release it after proxy completes."""
        mock_pool.allocate.return_value = mock_container
        
        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy_instance = AsyncMock()
            MockProxy.return_value = proxy_instance
            
            await container_session_handler(
                session_info, pty_request, mock_process, mock_pool
            )
        
        mock_pool.allocate.assert_called_once_with("handler-test-1")
        mock_pool.release.assert_called_once_with("handler-test-1")
```

**Pattern:**
- Class name describes what's being tested: `TestContainerSessionHandler`
- Each method tests one behavior
- Methods are named descriptively: `test_allocates_and_releases_container`
- Use fixtures to avoid boilerplate
- Use `with patch(...)` for temporary patching

## Fixture Patterns

### Simple Fixtures

For simple setup, return the object directly:

```python
@pytest.fixture
def pty_request():
    """Standard PTY configuration for tests."""
    return PTYRequest(
        term_type="xterm-256color",
        width=120,
        height=40,
    )

@pytest.fixture
def session_info():
    return SessionInfo(
        session_id="handler-test-1",
        username="root",
        source_ip="10.0.0.5",
        source_port=9999,
        authenticated=True,
    )
```

### Fixture Extension

Extend fixtures from conftest.py by naming them the same:

```python
# In tests/unit/conftest.py
@pytest.fixture
def mock_process():
    """Mock SSHServerProcess with async stdin and stdout."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process

# In your test file
@pytest.fixture
def mock_process(mock_process):
    """Extend conftest's mock_process with handler-specific attributes."""
    mock_process.exit = MagicMock()
    return mock_process
```

### Fixture with Multiple Scenarios

Create multiple fixtures for different failure modes:

```python
@pytest.fixture
def mock_process_eof():
    """Mock process that returns empty bytes (EOF) on stdin read."""
    process = MagicMock()
    process.stdin = AsyncMock(return_value=b"")
    process.stdout = MagicMock()
    process.stdout.write = MagicMock()
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process

@pytest.fixture
def mock_process_write_error():
    """Mock process where stdout.write raises after first call."""
    process = MagicMock()
    process.stdin = AsyncMock()
    process.stdout = MagicMock()
    
    call_count = [0]
    def write_with_error(data):
        call_count[0] += 1
        if call_count[0] > 1:
            raise BrokenPipeError("stdout closed")
    
    process.stdout.write = MagicMock(side_effect=write_with_error)
    process.stdout.drain = AsyncMock()
    process.stderr = MagicMock()
    return process
```

## Mocking Containers

### Basic Container Mock

```python
@pytest.fixture
def mock_container():
    """Mock Docker container."""
    container = MagicMock()
    container.id = "abc123def456"
    return container
```

### Container with Exec Support

For testing container execution:

```python
def _mock_container():
    """Create a mock Docker container with exec support."""
    container = MagicMock()
    container.id = "integ123456789"
    container.stop = MagicMock()
    container.reload = MagicMock()
    
    # exec_run returns a result with a socket-like output
    sock = MagicMock()
    sock._sock = MagicMock()
    sock._sock.setblocking = MagicMock()
    sock._sock.close = MagicMock()
    
    exec_result = MagicMock()
    exec_result.output = sock
    container.exec_run = MagicMock(return_value=exec_result)
    return container
```

### Container with Failure Modes

```python
@pytest.fixture
def mock_container_exec_fails():
    """Mock container where exec_run raises RuntimeError."""
    container = MagicMock()
    container.id = "abc123def456"
    container.exec_run.side_effect = RuntimeError("Docker exec failed")
    return container

@pytest.fixture
def mock_container_socket_error():
    """Mock container where socket.setblocking raises."""
    container = MagicMock()
    container.id = "abc123def456"
    socket_io = type("SocketIO", (), {"_sock": FailingSocketMock()})()
    container.exec_run.return_value = MagicMock(output=socket_io)
    return container
```

## Testing Lifecycle Management

### Testing Allocate and Release

```python
@pytest.mark.asyncio
async def test_allocates_and_releases_container(self, session_info, pty_request, mock_process, mock_pool, mock_container):
    """Should allocate a container and release it after proxy completes."""
    mock_pool.allocate.return_value = mock_container
    
    with patch("hermes.__main__.ContainerProxy") as MockProxy:
        proxy_instance = AsyncMock()
        MockProxy.return_value = proxy_instance
        
        await container_session_handler(
            session_info, pty_request, mock_process, mock_pool
        )
    
    mock_pool.allocate.assert_called_once_with("handler-test-1")
    mock_pool.release.assert_called_once_with("handler-test-1")
```

### Testing Cleanup in Finally Block

Verify that cleanup runs even when operations fail:

```python
@pytest.mark.asyncio
async def test_stops_proxy_in_finally(self, session_info, pty_request, mock_process, mock_pool, mock_container):
    """Proxy.stop() should always be called during cleanup."""
    mock_pool.allocate.return_value = mock_container
    
    with patch("hermes.__main__.ContainerProxy") as MockProxy:
        proxy_instance = AsyncMock()
        MockProxy.return_value = proxy_instance
        
        await container_session_handler(
            session_info, pty_request, mock_process, mock_pool
        )
    
    proxy_instance.stop.assert_called_once()
```

### Testing Cleanup on Failure

```python
@pytest.mark.asyncio
async def test_releases_on_proxy_failure(self, session_info, pty_request, mock_process, mock_pool, mock_container):
    """If proxy.start() fails, container should still be released."""
    mock_pool.allocate.return_value = mock_container
    
    with patch("hermes.__main__.ContainerProxy") as MockProxy:
        proxy_instance = AsyncMock()
        proxy_instance.start.side_effect = RuntimeError("exec failed")
        MockProxy.return_value = proxy_instance
        
        await container_session_handler(
            session_info, pty_request, mock_process, mock_pool
        )
    
    mock_pool.release.assert_called_once_with("handler-test-1")
```

## Error Path Testing

### Testing Allocation Failure

```python
@pytest.mark.asyncio
async def test_allocation_failure_writes_error(self, session_info, pty_request, mock_process, mock_pool):
    """Should write error to process.stdout when allocation fails."""
    mock_pool.allocate.side_effect = RuntimeError("pool exhausted")
    
    await container_session_handler(
        session_info, pty_request, mock_process, mock_pool
    )
    
    mock_process.stdout.write.assert_called_once()
    written = mock_process.stdout.write.call_args[0][0]
    assert b"Container allocation failed" in written
```

### Testing Non-Release on Early Failure

```python
@pytest.mark.asyncio
async def test_allocation_failure_still_releases(self, session_info, pty_request, mock_process, mock_pool):
    """Should not call release if allocation itself failed (no container)."""
    mock_pool.allocate.side_effect = RuntimeError("pool exhausted")
    
    await container_session_handler(
        session_info, pty_request, mock_process, mock_pool
    )
    
    mock_pool.release.assert_not_called()
```

### Testing Recorder Cleanup on Proxy Failure

```python
@pytest.mark.asyncio
async def test_recorder_stopped_even_on_proxy_failure(self, tmp_path):
    """Recorder cleanup runs in finally block regardless of proxy errors."""
    recording_config = RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )
    
    pool = MagicMock(spec=ContainerPool)
    pool.allocate = AsyncMock(return_value=mock_container())
    pool.release = AsyncMock()
    
    with patch("hermes.__main__.ContainerProxy") as MockProxy:
        proxy_instance = AsyncMock()
        proxy_instance.start.side_effect = RuntimeError("boom")
        MockProxy.return_value = proxy_instance
        
        await container_session_handler(
            session_info=_session_info(),
            pty_request=_pty_request(),
            process=_mock_process(),
            container_pool=pool,
            recording_config=recording_config,
        )
    
    # Recording directory should still have been created (recorder.start ran)
    assert (tmp_path / "recordings").exists()
```

## Patching Pattern

Use `patch()` as a context manager for clean, scoped mocking:

```python
with patch("hermes.__main__.ContainerProxy") as MockProxy:
    proxy_instance = AsyncMock()
    MockProxy.return_value = proxy_instance
    
    # Test code here
    await container_session_handler(...)
    
    # Verify in this scope
    proxy_instance.start.assert_called_once()

# Patch is automatically reverted after this block
```

This ensures patches don't leak between tests and keeps the scope clear.

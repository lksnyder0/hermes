# Async/Await Patterns for Testing

This guide covers async/await best practices specific to Hermes tests.

## Table of Contents
- [AsyncMock vs MagicMock](#asyncmock-vs-magicmock)
- [Awaiting Async Calls](#awaiting-async-calls)
- [Testing Concurrent Operations](#testing-concurrent-operations)
- [Async Context Managers](#async-context-managers)
- [Common Pitfalls](#common-pitfalls)

## AsyncMock vs MagicMock

### MagicMock: For Synchronous Methods

Use `MagicMock` for methods that don't return awaitables:

```python
from unittest.mock import MagicMock

mock_container = MagicMock()
mock_container.id = "abc123"
mock_container.stop = MagicMock()  # sync method

# Call and verify
mock_container.stop()
mock_container.stop.assert_called_once()
```

### AsyncMock: For Async Methods

Use `AsyncMock` for async methods and coroutine-returning functions:

```python
from unittest.mock import AsyncMock

mock_pool = MagicMock()
mock_pool.allocate = AsyncMock()  # async method
mock_pool.allocate.return_value = mock_container

# Must await
container = await mock_pool.allocate("session-id")
```

### Mixed Mock: Sync and Async Together

Most objects have both sync and async methods:

```python
process = MagicMock()
process.stdin = AsyncMock()              # async attribute
process.stdout = MagicMock()             # sync attribute
process.stdout.write = MagicMock()       # sync method
process.stdout.drain = AsyncMock()       # async method
process.exit = MagicMock()               # sync method

# Usage
data = await process.stdin.read()        # await
process.stdout.write(data)               # don't await
await process.stdout.drain()             # await
process.exit()                           # don't await
```

## Awaiting Async Calls

### Always Await

Always await async function calls. Not awaiting them returns a coroutine object instead of the result:

```python
# ✓ Correct
result = await async_function()
assert result == expected

# ✗ Wrong - result is a coroutine, not the actual result
result = async_function()
assert result == expected  # Assertion fails
```

### Check AsyncMock Return Values

When setting `return_value` on AsyncMock, the return value is what you get after awaiting:

```python
mock_pool = MagicMock()
mock_pool.allocate = AsyncMock(return_value="my_container")

# This awaits and gets "my_container"
container = await mock_pool.allocate("session-id")
assert container == "my_container"

# If you forget to await, you get a coroutine
container = mock_pool.allocate("session-id")
# container is <coroutine object>, not "my_container"
```

### Side Effects with AsyncMock

Use `side_effect` to make async mocks raise exceptions:

```python
mock_pool = MagicMock()
mock_pool.allocate = AsyncMock(side_effect=RuntimeError("pool exhausted"))

# This raises the exception when awaited
try:
    await mock_pool.allocate("session-id")
except RuntimeError as e:
    assert str(e) == "pool exhausted"
```

## Testing Concurrent Operations

### Testing with asyncio.gather

When testing code that runs multiple async operations concurrently:

```python
@pytest.mark.asyncio
async def test_concurrent_allocations(self, mock_pool, mock_container):
    """Test allocating multiple containers concurrently."""
    mock_pool.allocate = AsyncMock(return_value=mock_container)
    
    # Run multiple allocations concurrently
    results = await asyncio.gather(
        mock_pool.allocate("session-1"),
        mock_pool.allocate("session-2"),
        mock_pool.allocate("session-3"),
    )
    
    assert len(results) == 3
    assert mock_pool.allocate.call_count == 3
```

### Testing with Tasks

For testing code that uses `asyncio.create_task`:

```python
@pytest.mark.asyncio
async def test_creates_background_task(self, mock_recorder):
    """Verify background task is created."""
    async def dummy_operation():
        await asyncio.sleep(0)  # Yield control
        return "done"
    
    task = asyncio.create_task(dummy_operation())
    await task
    assert task.done()
```

## Async Context Managers

### Testing Async Context Managers

For code that uses `async with`:

```python
@pytest.mark.asyncio
async def test_context_manager_lifecycle(self):
    """Test proper async context manager behavior."""
    class MockContextManager:
        async def __aenter__(self):
            self.entered = True
            return self
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.exited = True
    
    cm = MockContextManager()
    async with cm as resource:
        assert cm.entered
    
    assert cm.exited
```

### Patching Async Context Managers

When the code under test uses an async context manager:

```python
@pytest.mark.asyncio
async def test_with_async_context(self):
    """Test code that uses async with."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value="resource")
    mock_cm.__aexit__ = AsyncMock()
    
    with patch("hermes.module.AsyncContextManager", return_value=mock_cm):
        async with AsyncContextManager() as resource:
            assert resource == "resource"
        
        mock_cm.__aexit__.assert_called_once()
```

## Testing Async Generators

For code that yields values asynchronously:

```python
async def async_generator():
    yield 1
    yield 2
    yield 3

@pytest.mark.asyncio
async def test_async_generator(self):
    """Test async generator behavior."""
    results = []
    async for value in async_generator():
        results.append(value)
    
    assert results == [1, 2, 3]
```

## Testing Timeouts

### Using asyncio.wait_for

```python
@pytest.mark.asyncio
async def test_operation_completes_within_timeout(self):
    """Verify operation completes in reasonable time."""
    async def slow_operation():
        await asyncio.sleep(0.1)
        return "done"
    
    result = await asyncio.wait_for(slow_operation(), timeout=1.0)
    assert result == "done"

@pytest.mark.asyncio
async def test_operation_times_out(self):
    """Verify timeout is raised for slow operations."""
    async def very_slow_operation():
        await asyncio.sleep(10)
        return "done"
    
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(very_slow_operation(), timeout=0.1)
```

## Common Pitfalls

### Pitfall 1: Forgetting to Await

```python
# ✗ Wrong
result = async_function()  # Returns coroutine, doesn't execute

# ✓ Correct
result = await async_function()
```

### Pitfall 2: AsyncMock Return Value Not Set

```python
# ✗ Wrong - AsyncMock() returns None by default when awaited
mock = AsyncMock()
result = await mock()  # result is None

# ✓ Correct - Set return_value
mock = AsyncMock(return_value="expected")
result = await mock()  # result is "expected"
```

### Pitfall 3: Not Using @pytest.mark.asyncio

```python
# ✗ Wrong - test function is async but not marked
async def test_something(self):
    await some_async_function()

# ✓ Correct
@pytest.mark.asyncio
async def test_something(self):
    await some_async_function()
```

### Pitfall 4: Mixing Sync and Async

```python
# ✗ Wrong - mixing sync (process.write) with awaits
@pytest.mark.asyncio
async def test_something(self):
    process = AsyncMock()
    process.write = MagicMock()  # Sync, don't await
    
    await process.write("data")  # Can't await a MagicMock!

# ✓ Correct - use AsyncMock for async methods
process.write = AsyncMock()
await process.write("data")
```

### Pitfall 5: Suppressing Warnings

If pytest warns about unawaited coroutines, it means you forgot an `await`:

```python
# Pytest warning: "coroutine was never awaited"
# This is from forgetting to await:

async def test_something(self):
    result = async_function()  # Forgot await!
```

## Best Practices

1. **Use `@pytest.mark.asyncio` on all async tests** - Without it, pytest treats your test as sync
2. **Always await async calls** - Use await, never skip it
3. **AsyncMock for async, MagicMock for sync** - Match the type to what you're mocking
4. **Set return_value on AsyncMock** - Default is None, which might hide bugs
5. **Use AsyncMock(side_effect=Exception)** for error testing - Clean and explicit
6. **Test both happy path and error paths** - Especially with timeouts and exceptions
7. **Keep async tests fast** - Use mocks instead of real async operations
8. **Use asyncio.gather() for concurrent testing** - When you need to verify parallel behavior

## Example: Complete Async Test

```python
@pytest.mark.asyncio
async def test_handles_allocation_and_records_session(self, tmp_path):
    """Complete test of async session handling with recording."""
    # Arrange: Set up mocks
    recording_config = RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )
    
    mock_pool = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "container-123"
    mock_pool.allocate = AsyncMock(return_value=mock_container)
    mock_pool.release = AsyncMock()
    
    session_info = SessionInfo(
        session_id="test-session",
        username="testuser",
        source_ip="192.168.1.1",
        source_port=12345,
        authenticated=True,
    )
    
    # Act: Call async function
    with patch("hermes.__main__.ContainerProxy") as MockProxy:
        proxy = AsyncMock()
        MockProxy.return_value = proxy
        
        await container_session_handler(
            session_info=session_info,
            pty_request=PTYRequest(term_type="xterm", width=120, height=40),
            process=MagicMock(),
            container_pool=mock_pool,
            recording_config=recording_config,
        )
    
    # Assert: Verify behavior
    mock_pool.allocate.assert_called_once_with("test-session")
    mock_pool.release.assert_called_once_with("test-session")
    proxy.start.assert_called_once()
    proxy.wait_completion.assert_called_once()
    proxy.stop.assert_called_once()
    assert (tmp_path / "recordings").exists()
```

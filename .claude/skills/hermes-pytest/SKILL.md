---
name: "hermes-pytest: Writing Async Tests"
description: "Write async/await pytest tests for the Hermes project following established patterns. Use this skill when asked to 'Write the tests for this functionality' or similar requests. Covers unit and integration tests with realistic mocks, proper async handling, and error case coverage following Hermes conventions."
---

# Writing Pytest Tests for Hermes

This skill guides you in writing pytest tests following Hermes project patterns and conventions.

## Quick Start: Core Pattern

All Hermes tests follow this structure:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def my_fixture():
    """Description of what this fixture provides."""
    return setup_object()

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_describes_one_behavior(self, my_fixture):
        """Arrange / Act / Assert structure."""
        # Arrange: set up test state
        my_fixture.some_method.return_value = "expected"
        
        # Act: call the code being tested
        result = await code_under_test(my_fixture)
        
        # Assert: verify expected behavior
        assert result == "expected"
        my_fixture.some_method.assert_called_once()
```

**Key rules:**
- `async def` for all test functions; use `@pytest.mark.asyncio`
- One test = one behavior
- Avoid excessive mocking; use realistic object implementations
- Always test error cases alongside happy paths
- Name tests descriptively: `test_allocates_and_releases_container`

## Fixtures: Reusable Test Objects

### Using Shared Fixtures

Hermes provides common fixtures in `tests/unit/conftest.py`:

- **`pty_request`**: Standard PTY configuration (xterm-256color, 120x40)
- **`mock_process`**: Mock SSH process with stdin/stdout/stderr
- **`mock_container`**: Mock Docker container
- **`mock_pool`**: Mock ContainerPool
- **`mock_recorder`**: Mock SessionRecorder
- **`patch_handler_deps()`**: Factory for patching handler dependencies

See [fixtures-guide.md](fixtures-guide.md) for details on creating and extending fixtures.

### Custom Fixtures for Your Tests

Create fixtures in your test file or in `conftest.py` if they're reused across tests:

```python
@pytest.fixture
def my_domain_config():
    """Create a realistic config for domain tests."""
    return MyConfig(
        setting_a="value",
        setting_b=42,
    )
```

## Test Organization

### Unit Tests (`tests/unit/`)

Test isolated functionality with mocks for external dependencies.

```python
class TestContainerProxy:
    @pytest.mark.asyncio
    async def test_starts_exec_with_pty(self, mock_container, pty_request):
        """Verify proxy correctly configures the exec command."""
        proxy = ContainerProxy(mock_container, pty_request)
        await proxy.start()
        mock_container.exec_run.assert_called_with(...)
```

### Integration Tests (`tests/integration/`)

Test real interactions between components. Use fewer mocks, more real objects (though still mock Docker).

```python
@pytest.mark.asyncio
async def test_session_handler_lifecycle(tmp_path):
    """Verify session handler orchestrates pool, proxy, and recorder."""
    recording_config = RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )
    pool = MagicMock(spec=ContainerPool)
    pool.allocate = AsyncMock(return_value=mock_container())
    
    await container_session_handler(
        session_info=SessionInfo(...),
        pty_request=PTYRequest(...),
        process=_mock_process(),
        container_pool=pool,
        recording_config=recording_config,
    )
```

## Async Testing Essentials

### Awaiting Async Calls

Always `await` async function calls in tests—don't skip them:

```python
# ✓ Correct
result = await my_async_function()
assert result == expected

# ✗ Wrong
result = my_async_function()  # This returns a coroutine, not a result
assert result == expected  # Assertion fails incorrectly
```

### AsyncMock for Async Mocks

Use `AsyncMock` for methods that return awaitables:

```python
from unittest.mock import AsyncMock, MagicMock

mock_process = MagicMock()
mock_process.stdin = AsyncMock(return_value=b"data")  # Callable, returns awaitable
mock_process.stdout = MagicMock()                      # Regular mock for non-async
mock_process.stdout.write = MagicMock()                # Regular method
mock_process.stdout.drain = AsyncMock()                # Async method
```

See [async-patterns.md](async-patterns.md) for more async testing patterns.

## Error Cases Matter

Always test both success and failure paths:

```python
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_handles_allocation_failure(self, mock_pool, mock_process):
        """Verify error message written to client on failure."""
        mock_pool.allocate.side_effect = RuntimeError("pool exhausted")
        
        await container_session_handler(..., container_pool=mock_pool)
        
        mock_process.stdout.write.assert_called_once()
        written = mock_process.stdout.write.call_args[0][0]
        assert b"Container allocation failed" in written
    
    @pytest.mark.asyncio
    async def test_releases_on_proxy_failure(self, mock_pool, mock_container):
        """Verify cleanup runs even when proxy.start() fails."""
        mock_pool.allocate.return_value = mock_container
        
        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy = AsyncMock()
            proxy.start.side_effect = RuntimeError("exec failed")
            MockProxy.return_value = proxy
            
            await container_session_handler(...)
        
        mock_pool.release.assert_called_once()  # Still called despite error
```

## Marking Tests

Use pytest markers for organization:

```python
@pytest.mark.unit
class TestSomething:
    ...

@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_scenario():
    ...

@pytest.mark.slow
@pytest.mark.asyncio
async def test_heavyweight_operation():
    ...
```

Run tests selectively:
```bash
pytest -m unit                    # Only unit tests
pytest -m "integration and not slow"  # Integration tests excluding slow
pytest tests/unit/test_file.py::TestClass::test_name -vvs  # Single test
```

## Running Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run specific file/class/test
pytest tests/unit/test_config.py::TestConfigLoading::test_loads_valid_config -vvs

# Run unit tests only
pytest tests/unit/ -m unit

# Generate HTML coverage report
pytest --cov --cov-report=html
```

## Best Practices

1. **Minimize mock boilerplate**: Use shared fixtures from `conftest.py`
2. **Test behavior, not mocks**: Write tests that verify what the code does, not how it calls dependencies
3. **One test, one assertion**: Each test verifies one specific behavior
4. **Descriptive names**: Test names should describe what they verify, e.g. `test_releases_container_on_proxy_failure`
5. **Real implementations preferred**: Mock Docker/async dependencies, but use real config objects, real data structures
6. **Proper cleanup**: Use `finally` blocks and context managers to ensure resources are released
7. **Realistic error conditions**: Test with actual exception types and realistic failure modes

## Advanced Patterns

For specific patterns like mocking containers, using realistic implementations, and advanced async scenarios, see:

- [test-patterns.md](test-patterns.md) - Real patterns from Hermes codebase
- [fixtures-guide.md](fixtures-guide.md) - Creating and extending fixtures
- [async-patterns.md](async-patterns.md) - Advanced async/await patterns

---
name: "hermes-pytest: Writing Async Tests"
description: "Write async/await pytest tests for the Hermes project following established patterns. Use this skill when asked to 'Write the tests for this functionality' or similar requests. Covers unit and integration tests with realistic mocks, proper async handling, and error case coverage following Hermes conventions."
---

# Writing Pytest Tests for Hermes

This skill guides you in writing pytest tests following Hermes project patterns, Python best practices, and a TDD-first workflow.

---

## TDD Workflow

Always follow Red → Green → Refactor:

1. **Red** — Write a failing test that specifies the desired behavior. Run it and confirm it fails for the right reason.
2. **Green** — Write the minimal production code to make the test pass. Do not over-engineer.
3. **Refactor** — Clean up code and tests while keeping the suite green.

**Rules:**
- Write the test before (or alongside) the implementation — never after.
- A bug fix starts with a test that reproduces the bug.
- A feature is complete only when tests pass, coverage ≥ 80%, mypy passes, and linting is clean.

```bash
# Red: confirm the test fails
pytest tests/unit/test_my_feature.py::TestMyFeature::test_new_behavior -vvs

# Green: implement, then confirm it passes
pytest tests/unit/test_my_feature.py -v

# Full suite: verify nothing regressed
pytest
```

---

## Test Tiers

| Tier | Location | Marker | Needs Docker | Speed |
|------|----------|--------|--------------|-------|
| Unit | `tests/unit/` | `unit` | No | < 1s total |
| Mocked integration | `tests/integration/test_*.py` | `integration` | No | < 2s total |
| Real Docker integration | `tests/integration/test_*_docker.py` | `docker` | Yes | 10–60s |

Choose the lowest tier that adequately covers the behavior. Most new tests are unit tests.

---

## Core Test Pattern

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_describes_one_behavior(
        self, mock_pool: MagicMock, mock_container: MagicMock
    ) -> None:
        """One sentence: what is being tested."""
        # Arrange
        mock_pool.allocate = AsyncMock(return_value=mock_container)

        # Act
        result = await code_under_test(mock_pool)

        # Assert
        assert result == expected_value
        mock_pool.allocate.assert_called_once()
```

**Key rules:**
- `async def` + `@pytest.mark.asyncio` for all async tests
- Type-annotate test parameters and return `-> None`
- One test = one behavior
- Always test error cases alongside happy paths
- Descriptive names: `test_releases_container_on_proxy_failure`

---

## Python Best Practices

### Use `pytest.mark.parametrize` instead of duplicating tests

```python
@pytest.mark.parametrize("username,password,expected", [
    ("root", "toor", True),
    ("admin", "wrong", False),
    ("", "", False),
])
def test_validates_credentials(
    self, auth: AuthenticationManager, username: str, password: str, expected: bool
) -> None:
    assert auth.validate("conn1", username, password) is expected
```

### Use `pytest.raises` with `match=` to assert exception messages

```python
def test_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        SessionConfig(idle_timeout=-1)
```

### Use `spec=` with MagicMock to catch attribute typos

```python
# Without spec: mock_pool.typo_method() succeeds silently
# With spec: mock_pool.typo_method() raises AttributeError immediately
mock_pool = MagicMock(spec=ContainerPool)
mock_pool.allocate = AsyncMock(return_value=mock_container)
```

### Use `tmp_path` for temporary files (built-in pytest fixture)

```python
async def test_creates_recording_file(self, tmp_path: Path) -> None:
    recorder = SessionRecorder(output_dir=tmp_path / "recordings")
    await recorder.start(session_id="test-1")
    assert (tmp_path / "recordings" / "test-1.cast").exists()
```

### Use `caplog` to assert log output

```python
def test_logs_allocation_failure(
    self, mock_pool: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    mock_pool.allocate = AsyncMock(side_effect=RuntimeError("exhausted"))

    with caplog.at_level(logging.ERROR, logger="hermes"):
        await container_session_handler(..., container_pool=mock_pool)

    assert "Container allocation failed" in caplog.text
```

### Use `monkeypatch` for environment variables and config

```python
def test_reads_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_PORT", "2222")
    config = HermesConfig.from_env()
    assert config.port == 2222
```

### Avoid common anti-patterns

```python
# ✗ Testing implementation details
mock_pool.allocate.assert_called_with(session_id="abc", timeout=30)  # Too brittle

# ✓ Testing observable behavior
assert container.id == mock_container.id

# ✗ Multiple behaviors in one test
async def test_handler():
    # Tests allocation AND recording AND cleanup — split these up

# ✓ One assertion per test (or tightly related assertions)
async def test_releases_container_after_proxy_completes():
    ...
    mock_pool.release.assert_called_once_with(session_id)

# ✗ Bare except or swallowing exceptions in tests
try:
    await something()
except Exception:
    pass  # Never do this

# ✓ Let exceptions propagate or use pytest.raises
with pytest.raises(RuntimeError, match="pool exhausted"):
    await something()
```

---

## Fixtures: Reusable Test Objects

### Shared fixtures from `tests/unit/conftest.py`

- **`pty_request`**: Standard PTY configuration (xterm-256color, 120×40)
- **`mock_process`**: Mock SSH process with async stdin/stdout
- **`mock_container`**: Mock Docker container (`id = "abc123def456"`)
- **`mock_pool`**: Mock ContainerPool with `allocate` / `release` AsyncMocks
- **`mock_recorder`**: Mock SessionRecorder
- **`patch_handler_deps()`**: Factory that patches ContainerProxy and SessionRecorder together

### Shared fixtures from `tests/conftest.py`

Top-level fixtures available to all tests (unit + integration).

### Error-case fixtures

- `mock_process_eof` — stdin returns empty bytes (EOF)
- `mock_process_write_error` — stdout.write raises after first call
- `mock_container_exec_fails` — exec_run raises RuntimeError
- `mock_container_socket_error` — socket.setblocking raises

### Writing your own fixtures

Add to your test file when used only there; add to `conftest.py` when used in 2+ tests.

```python
@pytest.fixture
def session_info() -> SessionInfo:
    """Standard session for handler tests."""
    return SessionInfo(
        session_id="handler-test-1",
        username="root",
        source_ip="10.0.0.5",
        source_port=9999,
        authenticated=True,
    )

@pytest.fixture
def recording_config(tmp_path: Path) -> RecordingConfig:
    """Recording config pointing to a temporary directory."""
    return RecordingConfig(enabled=True, output_dir=tmp_path / "recordings")
```

See [fixtures-guide.md](fixtures-guide.md) for scope, teardown, and parametrized fixture patterns.

---

## Async Testing Essentials

```python
# AsyncMock for async methods; MagicMock for sync
mock_process = MagicMock()
mock_process.stdin = AsyncMock()           # async callable
mock_process.stdout.write = MagicMock()   # sync callable
mock_process.stdout.drain = AsyncMock()   # async callable

# Always await async calls
result = await my_async_function()   # ✓
result = my_async_function()         # ✗ returns coroutine

# side_effect for exceptions
mock_pool.allocate = AsyncMock(side_effect=RuntimeError("exhausted"))
```

See [async-patterns.md](async-patterns.md) for concurrent operations, async context managers, and common pitfalls.

---

## Error Cases Matter

```python
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_writes_error_on_allocation_failure(
        self, mock_pool: MagicMock, mock_process: MagicMock
    ) -> None:
        mock_pool.allocate = AsyncMock(side_effect=RuntimeError("pool exhausted"))

        await container_session_handler(..., container_pool=mock_pool)

        written = mock_process.stdout.write.call_args[0][0]
        assert b"Container allocation failed" in written

    @pytest.mark.asyncio
    async def test_releases_container_even_on_proxy_failure(
        self, mock_pool: MagicMock, mock_container: MagicMock
    ) -> None:
        mock_pool.allocate = AsyncMock(return_value=mock_container)

        with patch("hermes.__main__.ContainerProxy") as MockProxy:
            proxy = AsyncMock()
            proxy.start.side_effect = RuntimeError("exec failed")
            MockProxy.return_value = proxy

            await container_session_handler(..., container_pool=mock_pool)

        mock_pool.release.assert_called_once()
```

---

## Markers

```python
@pytest.mark.unit
class TestSomething: ...

@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_scenario(): ...

@pytest.mark.docker
@pytest.mark.asyncio
async def test_real_docker_container(): ...

@pytest.mark.slow
async def test_heavyweight_operation(): ...
```

---

## Coverage

The suite enforces **≥ 80% coverage** (`fail_under = 80` in `pyproject.toml`). Running `pytest` always measures coverage. If a new feature drops coverage, add tests for uncovered branches before marking the task done.

```bash
# See which lines are uncovered
pytest --cov=hermes --cov-report=term-missing

# HTML report at htmlcov/index.html
pytest --cov=hermes --cov-report=html
```

---

## Key Commands

```bash
# Run all tests (unit + mocked integration)
pytest

# Single test with full output
pytest tests/unit/test_file.py::TestClass::test_name -vvs

# Unit tests only
pytest tests/unit/ -v

# Mocked integration tests (no Docker needed)
pytest tests/integration/ -m "not docker" -v

# Real Docker tests
pytest tests/integration/ -m docker -v

# List available fixtures
pytest --fixtures tests/unit
```

---

## Advanced Patterns

- [test-patterns.md](test-patterns.md) — Real patterns from the Hermes codebase
- [fixtures-guide.md](fixtures-guide.md) — Creating, scoping, and extending fixtures
- [async-patterns.md](async-patterns.md) — Advanced async/await patterns and pitfalls

# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

Hermes is an SSH honeypot with Docker container sandboxing that captures attacker behavior. It accepts SSH connections, proxies them to isolated Ubuntu Docker containers, and records all activity as asciinema sessions.

**Stack**: Python 3.12–3.14, asyncssh, Docker SDK, Pydantic, PyYAML

## Code Style and Formatting

- **Line length**: 100 characters (enforced by Black and Ruff)
- **Formatter**: Black with `py312` target
- **Import sorting**: isort with Black profile
- **Linter**: Ruff (pycodestyle, pyflakes, isort, flake8-comprehensions, flake8-bugbear, pyupgrade)
- **Type checking**: mypy in strict mode — all functions must have type annotations (`disallow_untyped_defs`, `disallow_incomplete_defs`)
- Follow PEP 8, use async/await patterns throughout, include docstrings on public APIs

## Security Considerations

This project handles live attacker sessions. Code changes must never weaken security boundaries:

- Container isolation: network=none, 256MB RAM, 0.5 CPU, 100 PIDs, minimal capabilities, seccomp profiles
- Never bypass or relax container security constraints without explicit justification
- Validate all inputs from SSH sessions — treat everything from attackers as untrusted
- Stopped containers are preserved for forensic analysis; do not auto-remove them

## Test-Driven Development (TDD)

**Default approach**: Write tests before or alongside implementation. Do not write production code without a corresponding test.

### TDD Workflow

1. **Red**: Write a failing test that describes the desired behavior
2. **Green**: Write the minimal production code to make the test pass
3. **Refactor**: Clean up the code while keeping tests green

### When to write tests first

- New features or new public methods — always write the test first
- Bug fixes — write a test that reproduces the bug before fixing it
- Edge cases and error paths — specify them as tests before coding the handler

### What counts as "done"

A feature is complete when:
- All tests pass (`pytest`)
- Coverage remains at or above 80% (`fail_under = 80` in `pyproject.toml`)
- mypy passes with no errors
- No ruff or black violations

## Testing Standards

### Test tiers

| Tier | Location | Marker | Dependencies | Speed |
|------|----------|--------|--------------|-------|
| Unit | `tests/unit/` | `unit` | None (fully mocked) | < 1s total |
| Mocked integration | `tests/integration/test_*.py` (non-docker) | `integration` | None (Docker mocked) | < 2s total |
| Real Docker integration | `tests/integration/test_*_docker.py` | `docker` | Docker + image | 10–60s |

### Framework and configuration

- Framework: pytest with pytest-asyncio (`asyncio_mode = "auto"`)
- Coverage: `--cov=hermes` enabled by default; minimum threshold **80%** (`fail_under = 80`)
- Test paths: `tests/unit/`, `tests/integration/`
- Markers: `unit`, `integration`, `docker`, `slow`

### Test conventions

- Minimize mock boilerplate — use shared fixtures from `tests/unit/conftest.py` and `tests/conftest.py`
- Test behavior, not mock interactions; prefer realistic implementations over excessive mocking
- One test verifies one behavior
- Include error cases alongside happy paths
- Descriptive test names: `test_start_creates_exec_with_pty`, `test_handles_socket_error_gracefully`
- Arrange / Act / Assert structure

### Adding tests

**Unit test** (`tests/unit/test_*.py`):
- Mock all external dependencies (Docker, asyncssh, filesystem)
- Keep execution time under 100ms per test
- Use fixtures from `tests/unit/conftest.py`

**Mocked integration test** (`tests/integration/test_*.py`):
- Mock the Docker client; test component interaction across module boundaries
- Run in CI — no Docker daemon required

**Real Docker integration test** (`tests/integration/test_*_docker.py`):
- Mark with `@pytest.mark.docker`
- Include teardown/cleanup in fixtures
- Skips automatically when Docker is unavailable

## Project Structure

```
src/hermes/                  # Source code
  __main__.py                  # Entry point
  config.py                    # Pydantic configuration models
  server/                      # SSH server
    asyncssh_backend.py          # asyncssh server implementation
    auth.py                      # Authentication management
    backend.py                   # Server backend interface
  container/                   # Docker container management
    pool.py                      # Container pool lifecycle
    security.py                  # Security constraint helpers
  session/                     # Session handling
    proxy.py                     # SSH↔container proxy
    recorder.py                  # Asciinema session recording
  utils/                       # Utilities
containers/targets/            # Target container Dockerfiles
  ubuntu/                        # Ubuntu target image
config/                        # YAML configuration files
tests/
  conftest.py                  # Top-level shared fixtures
  unit/
    conftest.py                  # Unit-test fixtures and mocks
    test_auth.py
    test_asyncssh_backend.py
    test_config.py
    test_container_pool.py
    test_container_proxy.py
    test_container_security.py
    test_main.py
    test_session_handler.py
    test_session_recorder.py
    test_session_timeout.py
    test_session_timeout_handler.py
    test_timeout.py
  integration/
    test_auth_backend_integration.py
    test_config_loading.py
    test_container_pool_lifecycle.py
    test_recording_validation.py
    test_session_flow.py
    test_container_pool_docker.py   # @pytest.mark.docker
    test_container_proxy_docker.py  # @pytest.mark.docker
    test_full_session_docker.py     # @pytest.mark.docker
data/                          # Runtime data (recordings, logs)
```

## Key Commands

```bash
# Activate virtual environment (Python 3.14)
source venv/bin/activate

# Run all tests (unit + mocked integration) — default for everyday development
pytest

# Run only unit tests
pytest tests/unit/ -v

# Run a single test
pytest tests/unit/test_file.py::TestClass::test_name -vvs

# Run with coverage report (HTML at htmlcov/index.html)
pytest --cov=hermes --cov-report=term-missing --cov-report=html

# Run mocked integration tests only (no Docker required)
pytest tests/integration/ -m "not docker" -v

# Run real Docker integration tests (requires hermes-target-ubuntu:latest)
pytest tests/integration/ -m docker -v

# Linting and formatting
black src/ tests/
ruff check src/ tests/
isort src/ tests/
mypy src/

# Build target container
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/

# Run Hermes locally
python -m hermes --config config/config.test.yaml
```

## Code Review Focus Areas

When reviewing pull requests, pay particular attention to:

1. **Security**: Any change that affects container isolation, SSH handling, or attacker-facing surfaces must be scrutinized for weakened security boundaries
2. **Type safety**: All new code must pass mypy strict mode — no untyped definitions
3. **Test coverage**: New functionality must include tests written before or alongside the implementation; coverage must not drop below 80%
4. **Async correctness**: Proper use of async/await, no blocking calls in the event loop, correct resource cleanup
5. **Configuration validation**: Pydantic models should validate all config inputs with appropriate constraints
6. **Resource cleanup**: Containers, SSH sessions, and file handles must be properly closed in all code paths including error cases

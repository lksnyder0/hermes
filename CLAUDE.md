# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

Hermes is an SSH honeypot with Docker container sandboxing that captures attacker behavior. It accepts SSH connections, proxies them to isolated Ubuntu Docker containers, and records all activity.

**Stack**: Python 3.12+, asyncssh, Docker SDK, Pydantic, PyYAML

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

## Testing Standards

- Framework: pytest with pytest-asyncio (asyncio_mode = "auto")
- Coverage: `--cov=hermes` is enabled by default
- Test paths: `tests/unit/`, `tests/integration/`
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`

### Test conventions

- Minimize mock boilerplate — use shared fixtures from `tests/unit/conftest.py`
- Test behavior, not mock interactions; prefer realistic implementations over excessive mocking
- One test verifies one behavior
- Include error cases alongside happy paths
- Use `@pytest.mark.asyncio` for async tests and await all async calls
- Descriptive test names: `test_start_creates_exec_with_pty`, `test_handles_socket_error_gracefully`
- Arrange / Act / Assert structure

## Project Structure

```
src/hermes/          # Source code
  __main__.py          # Entry point
  config.py            # Pydantic configuration models
  server/              # SSH server (asyncssh backend, auth)
  container/           # Docker container pool and security
  session/             # Session proxy and asciinema recording
  utils/               # Utilities
containers/targets/    # Target container Dockerfiles
config/                # YAML configuration files
tests/                 # Unit and integration tests
```

## Key Commands

```bash
# Run tests
pytest
pytest tests/unit/ -v
pytest tests/unit/test_file.py::TestClass::test_name -vvs

# Linting and formatting
black src/ tests/
ruff check src/ tests/
isort src/ tests/
mypy src/

# Build target container
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/
```

## Code Review Focus Areas

When reviewing pull requests, pay particular attention to:

1. **Security**: Any change that affects container isolation, SSH handling, or attacker-facing surfaces must be scrutinized for weakened security boundaries
2. **Type safety**: All new code must pass mypy strict mode — no untyped definitions
3. **Test coverage**: New functionality should include tests; changes to existing code should not reduce coverage
4. **Async correctness**: Proper use of async/await, no blocking calls in the event loop, correct resource cleanup
5. **Configuration validation**: Pydantic models should validate all config inputs with appropriate constraints
6. **Resource cleanup**: Containers, SSH sessions, and file handles must be properly closed in all code paths including error cases

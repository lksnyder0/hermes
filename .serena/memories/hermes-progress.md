# Hermes - Progress Summary

**Project**: SSH Honeypot with Docker Container Sandboxing
**Location**: `/home/luke/code/hermes/`
**GitHub**: `git@github.com:lksnyder0/hermes.git`
**Active branch**: `add-session-timeouts` (PR #15 open against `main`)
**Python**: 3.14, venv at `venv/`

---

## Phase 1: Project Setup & Research ✅

Created the full project structure with Python packaging (pyproject.toml, requirements.txt), configuration system using Pydantic validation, and an authentication manager supporting static credentials with accept-all fallback. Researched asyncssh and Docker SDK APIs. Designed an abstract SSH backend interface to allow future library swaps.

---

## Phase 2: Core SSH Server ✅

Implemented the AsyncSSH-based SSH server. The `AsyncSSHBackend` class wraps asyncssh.listen() and delegates connection handling to `HermesSSHServer`, which tracks session metadata (IP, port, session ID) and validates credentials via the `AuthenticationManager`. PTY allocation and terminal resize events are handled through the session lifecycle.

**Key files**: `server/backend.py`, `server/asyncssh_backend.py`, `server/auth.py`, `config.py`.

---

## Phase 3: Container Pool Management ✅

Implemented Docker container pool with security constraints. The `ContainerPool` eagerly creates N containers at startup using `asyncio.gather()`. The `SecurityConfigBuilder` enforces: network isolation (`none`), 256MB memory, 0.5 CPU, 100 PIDs, ALL capabilities dropped (3 minimal added), `no-new-privileges`.

**Key files**: `container/pool.py`, `container/security.py`, `containers/targets/ubuntu/Dockerfile`.

---

## Phase 4: Command Proxying ✅

Connected SSH sessions to Docker containers with bidirectional I/O streaming. Uses asyncssh `process_factory` (not `session_factory` — they are mutually exclusive). `ContainerProxy` manages Docker exec with PTY, extracts the raw socket from `SocketIO._sock`, sets non-blocking mode, and runs two concurrent asyncio tasks for bidirectional streaming.

**Key files**: `session/proxy.py`, `server/asyncssh_backend.py`, `__main__.py`.

---

## Phase 5: Session Recording ✅

Asciinema v2 recorder with local filesystem storage and structured JSON logging. Comprehensive integration tests covering I/O capture, unicode, large output, concurrent session isolation, and metadata validation.

**Key files**: `session/recorder.py`.

---

## Phase 6: Config Integration ✅

Pydantic configuration models fully integrated throughout the codebase. `Config.from_file()` loads YAML. `ServerConfig.session_timeout` has `ge=60` validation.

---

## Phase 7: Session Timeouts ✅ (PR #15 open)

Branch: `add-session-timeouts`

`container_session_handler` now accepts a `Config` parameter and enforces a session timeout using `asyncio.wait(FIRST_COMPLETED)` with a `timeout_monitor` task. On timeout, a message is written to `process.stdout` and the container is released via the `finally` block.

**Key implementation details**:
- `timeout_task` initialized to `None` upfront (avoids `locals()` check)
- Pending tasks awaited after cancellation for graceful cleanup
- `container_task` exceptions propagated after `asyncio.wait`
- Timeout error written to `process.stdout` (not stdin)
- `except Exception` catches all handler errors (not just `RuntimeError`)
- Error message is generic: "Container allocation failed" — potential improvement is stage-specific messaging

**Copilot PR review**: All 14 comments addressed in commit `d912c9e`. Remaining known limitation: the `except Exception` block always sends "Container allocation failed" even for proxy failures — could be improved with separate try-excepts per stage.

**Test suite**: 292 tests passing (unit + mocked integration), 80%+ coverage enforced.

---

## Remaining MVP Phases

| Phase | Status | Summary |
|-------|--------|---------|
| 8. Containerization | Pending | Hermes Dockerfile (Alpine), docker-compose.yml |
| 9. Testing | In Progress | 292 tests passing; Docker integration tests exist |
| 10. Documentation | In Progress | README, SECURITY.md, CLAUDE.md updated |

---

## Key Technical Notes

- `container.stop()` in Docker SDK does NOT accept a timeout argument
- Config paths must be absolute (relative paths break when running from `src/`)
- Docker's default seccomp profile is applied implicitly — do not specify `seccomp=default`
- asyncssh `process_factory` and `session_factory` are mutually exclusive interfaces
- `ServerConfig.session_timeout` has `ge=60` Pydantic constraint — use `MagicMock` in tests requiring sub-60s timeouts
- `recorder.start()`, `recorder.stop()`, `recorder.write_metadata()` are sync methods — if mocked with `AsyncMock`, they generate RuntimeWarning (pre-existing issue)

---

## Quick Start

```bash
cd /home/luke/code/hermes && source venv/bin/activate

# Build target image (if not already built)
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/

# Run Hermes
python -m hermes --config config/config.test.yaml --log-level DEBUG

# Run tests
pytest                                              # all unit + mocked integration
pytest tests/integration/ -m docker -v             # real Docker tests
```

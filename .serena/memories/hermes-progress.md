# Hermes - Progress Summary

**Project**: SSH Honeypot with Docker Container Sandboxing
**Location**: `/home/luke/code/sandtrap/`
**GitHub**: `git@github.com:lksnyder0/hermes.git`
**Branch**: `main`
**Python**: 3.14, venv at `venv/`

---

## Phase 1: Project Setup & Research ✅

Commit: `49cdccd`

Created the full project structure with Python packaging (pyproject.toml, requirements.txt), configuration system using Pydantic validation, and an authentication manager supporting static credentials with accept-all fallback. Researched asyncssh and Docker SDK APIs. Designed an abstract SSH backend interface to allow future library swaps.

---

## Phase 2: Core SSH Server ✅

Commit: `349e174`

Implemented the AsyncSSH-based SSH server (~624 lines). The `AsyncSSHBackend` class wraps asyncssh.listen() and delegates connection handling to `HermesSSHServer`, which tracks session metadata (IP, port, session ID) and validates credentials via the `AuthenticationManager`. The auth manager supports static credential lists and an accept-all mode that activates after N failed attempts per connection. PTY allocation and terminal resize events are handled through the session lifecycle.

**Key files**: `server/backend.py` (abstract interface + dataclasses), `server/asyncssh_backend.py` (implementation), `server/auth.py` (auth manager), `config.py` (Pydantic models).

---

## Phase 3: Container Pool Management ✅

Commit: `d128ac2`

Implemented Docker container pool with security constraints (~540 lines across two files). The `ContainerPool` eagerly creates N containers at startup using `asyncio.gather()` for parallel creation (~0.24s for 3 containers). When a container is allocated to a session, a background task immediately spawns a replacement. Released containers are stopped (not removed) and tracked with timestamps for forensic preservation.

The `SecurityConfigBuilder` converts high-level config into Docker API parameters: network isolation (`none`), memory limits (256MB), CPU quota (0.5 cores via 50000/100000), PID limits (100), capability dropping (ALL dropped, 3 minimal added), and `no-new-privileges`. Docker's default seccomp profile is applied implicitly.

The Ubuntu 22.04 target container (~794MB) includes common attacker tools (curl, wget, netcat, vim, python3, git) and fake "interesting" files (DB credentials in `/etc/config/app.env`, access logs, bash history). Containers are named `hermes-target-{session_id[:8]}-{timestamp}` for forensic traceability.

**Key files**: `container/pool.py` (373 lines), `container/security.py` (166 lines), `containers/targets/ubuntu/Dockerfile`.

---

## Phase 4: Command Proxying ✅

Commit: `fd06d00`

Connected SSH sessions to Docker containers with bidirectional I/O streaming (~1374 lines added). The core fix was switching asyncssh from `session_factory` to `process_factory` — the session interface's callbacks (`pty_requested`, `shell_requested`) were never invoked because asyncssh treats the two interfaces as mutually exclusive. The `HermesSSHSession` class was removed entirely.

The new `_process_factory` method on `AsyncSSHBackend` receives an `SSHServerProcess` object, extracts PTY info via `process.get_terminal_type()` and `process.get_terminal_size()`, looks up session metadata, and delegates to the registered session handler.

`ContainerProxy` manages the Docker exec lifecycle: creates an exec instance with PTY (`tty=True`, `socket=True`), extracts the raw socket from the `SocketIO` wrapper (`._sock`), sets it to non-blocking mode, and spawns two concurrent asyncio tasks for bidirectional streaming — one forwarding `process.stdin` → exec socket, the other forwarding exec socket → `process.stdout`. The proxy handles graceful shutdown on disconnect, broken pipes, and connection resets.

The `container_session_handler` in `__main__.py` orchestrates the full lifecycle: allocate container → create proxy → start proxy → wait for completion → stop proxy → release container.

56 unit tests cover the backend, proxy, and session handler. An integration test script (`scripts/test_connect.py`) uses `asyncssh.SSHClientProcess` with PTY to verify end-to-end connectivity.

**Key files**: `session/proxy.py` (273 lines), `server/asyncssh_backend.py` (modified), `__main__.py` (modified), plus 3 test files.

**Notable bugs fixed**: Docker SDK `exec_run(socket=True)` returns a `SocketIO` wrapper, not a raw socket — fixed by extracting `._sock`. The `create_session()` client API returns `(channel, process)`, not `(process, channel)`.

---

## Phase 5: Session Recording | In Progress | Asciinema v2 recorder, local filesystem storage, structured JSON logging

Commit: `2a383d5`

Added comprehensive integration tests for session recording validation with 9 passing tests covering end-to-end I/O capture, including:
- Basic I/O recording validation
- Multiple command interleaving
- Unicode/emoji preservation
- Large output handling (>10KB deterministic)
- Rapid-fire command capture
- Concurrent session isolation
- JSON metadata file creation
- Recording disabled functionality
- Partial recording validity (abrupt disconnect)

Key fixes implemented:
- Fixed seccomp configuration bug where `seccomp=default` was incorrectly specified
- Fixed Docker SDK kwargs in test fixtures
- Added proper test infrastructure with fixtures and helper functions
- Updated pytest configuration with new markers (`recording`, `ssh`, `docker`)
- Added comprehensive documentation for running tests

The implementation now includes:
- Validation of asciicast v2 format correctness
- Proper I/O accuracy with event interleaving
- Timestamp validation and edge case handling
- Performance optimizations

---

## Remaining MVP Phases

| Phase | Status | Summary |
|-------|--------|---------|
| 6. Config Integration | ✅ Complete | Parser done (Pydantic), integrated throughout codebase |
| 7. Security Hardening | Partial | Config defined, enforcement verified, session timeouts implementation, input validation, rate limiting |
| 8. Containerization | In Progress | Hermes Dockerfile (Alpine), docker-compose.yml, helper scripts |
| 9. Testing | In Progress | Phase 2-9 unit tests passing (65 tests), Phase 5-6 integration tests, broader coverage |
| 10. Documentation | In Progress | README, SECURITY.md complete, deployment/dev guides |

---

## Quick Start

```bash
cd /home/luke/code/sandtrap && source venv/bin/activate

# Build target image (if not already built)
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/

# Clean old containers
docker ps -a --filter "name=hermes-target" -q | xargs -r docker rm -f

# Run Hermes
cd src && python -m hermes --config ../config/config.test.yaml --log-level DEBUG

# Test connection (separate terminal)
python scripts/test_connect.py  # connects to localhost:2223 as root/toor
```

## Key Technical Notes

- `container.stop()` in current Docker SDK does NOT accept a timeout argument
- Config paths must be absolute (relative paths break when running from `src/`)
- Docker's default seccomp profile is applied implicitly; don't specify `seccomp=default` explicitly
- asyncssh `process_factory` and `session_factory` are mutually exclusive interfaces
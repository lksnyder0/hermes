# SandTrap Development Session Summary

## Project Context
**Project**: SandTrap - SSH Honeypot with Docker Container Sandboxing  
**Location**: `/home/luke/code/sandtrap/`  
**GitHub**: `git@github.com:lksnyder0/sandtrap.git`  
**Python Version**: 3.14  
**Status**: Phase 3 Complete, Ready for Phase 4

---

## What We Accomplished This Session

### Phase 3: Container Pool Management (COMPLETED)

We successfully implemented complete Docker container management with security constraints. Here's what was built:

#### 1. **Security Configuration Builder** (`src/sandtrap/container/security.py` - 166 lines)
- Converts high-level config to Docker API parameters
- Applies all security constraints (network isolation, resource limits, capabilities)
- CPU quota conversion: cores → Docker quota format (0.5 cores = 50000/100000)
- Memory limit validation with regex
- Automatic label generation for container tracking
- Key function: `build_container_config(config, image, name, session_id)`

#### 2. **Container Pool Manager** (`src/sandtrap/container/pool.py` - 373 lines)
- **Eager initialization**: Creates all pool containers at startup (0.24s for 3 containers)
- **Instant allocation**: Pops from ready pool, spawns replacement in background
- **Session tracking**: `active_sessions` dict maps session_id → container
- **Forensic preservation**: Stopped containers tracked with timestamps
- **Graceful shutdown**: Stops all containers, preserves stopped ones
- **Error handling**: Single retry on Docker API failures
- Key methods:
  - `initialize()` - Parallel container creation
  - `allocate(session_id)` - Get container from pool
  - `release(session_id)` - Stop and track container
  - `shutdown()` - Clean shutdown
  - `_create_container()` - Build and start container with retry logic
  - `_spawn_replacement()` - Background task to maintain pool size

#### 3. **Target Container** (`containers/targets/ubuntu/Dockerfile` - 70 lines)
- Ubuntu 22.04 base image (~794MB)
- Attacker tools: curl, wget, netcat, vim, python3, git, openssh-client
- Fake "interesting" files for honeypot realism:
  - `/etc/config/app.env` - Fake DB credentials
  - `/var/log/access.log` - Fake internal URLs
  - `/home/admin/.bash_history` - Fake command history
- Environment: `HOSTNAME=prod-web-01`, `USER=root`
- Build: `docker buildx build -t sandtrap-target-ubuntu:latest containers/targets/ubuntu/`

#### 4. **Integration** (Modified files)
- **`src/sandtrap/__main__.py`**: Added Docker client init, pool lifecycle management
- **`src/sandtrap/server/asyncssh_backend.py`**: Added `set_container_pool()` method, `container_pool` attribute
- **`config/config.test.yaml`**: Fixed seccomp config, updated paths
- **`config/config.example.yaml`**: Documented seccomp behavior

---

## Security Constraints (VERIFIED)

All constraints tested via `docker inspect`:

```json
{
  "NetworkMode": "none",                    // Complete network isolation
  "Memory": 268435456,                      // 256MB limit
  "CpuQuota": 50000,                        // 0.5 cores
  "CpuPeriod": 100000,
  "PidsLimit": 100,                         // Max 100 processes
  "CapDrop": ["ALL"],                       // All capabilities dropped
  "CapAdd": ["CHOWN", "SETUID", "SETGID"], // Only 3 minimal added
  "SecurityOpt": ["no-new-privileges:true"] // Prevent privilege escalation
}
```

**Seccomp**: Docker's default seccomp profile automatically applied (blocks ~44 dangerous syscalls like reboot, mount, swapon). We don't specify it explicitly because Docker applies it by default when no seccomp option is given.

---

## Important Design Decisions

### Container Pool Strategy
- **Eager initialization**: All containers created at startup (not lazy)
- **Immediate replacement**: Background task spawns replacement as soon as allocated
- **Stop on release**: Containers stopped (not removed) for forensics
- **Session-based naming**: `sandtrap-target-{session_id[:8]}-{timestamp}`

### Security Approach
- **Network isolation**: `network_mode: none` - attackers can run commands but no network access
- **Resource limits**: Prevent DoS attacks
- **Capability dropping**: Defense-in-depth against container escapes
- **Seccomp default**: Automatically applied by Docker (not explicitly configured)

### Error Handling
- **Fail fast with retry**: Single retry with 2-second delay, then raise exception
- **Graceful degradation**: On-demand creation if pool empty (logs warning)
- **Comprehensive logging**: All Docker operations logged

---

## Key Files and Structure

```
sandtrap/
├── src/sandtrap/
│   ├── __main__.py              # ✅ Updated: Docker client + pool init
│   ├── config.py                # ✅ Complete: Pydantic models
│   ├── server/
│   │   ├── backend.py           # ✅ Complete: Abstract interface
│   │   ├── asyncssh_backend.py  # ✅ Updated: Pool reference added
│   │   └── auth.py              # ✅ Complete: Authentication manager
│   ├── container/               # 🆕 NEW
│   │   ├── pool.py              # ✅ Container pool manager (373 lines)
│   │   └── security.py          # ✅ Security config builder (166 lines)
│   └── session/                 # ⏳ Empty (Phase 4)
│       ├── proxy.py             # ❌ Not implemented yet
│       └── recorder.py          # ❌ Not implemented yet
├── containers/targets/ubuntu/
│   └── Dockerfile               # ✅ Ubuntu 22.04 target
├── config/
│   ├── config.example.yaml      # ✅ Updated: Seccomp docs
│   └── config.test.yaml         # ✅ Updated: Fixed seccomp, paths
└── README.md                    # ✅ Updated: Phase 3 complete
```

---

## Current State

### What Works
- ✅ SSH server accepts connections on port 2223
- ✅ Authentication with static credentials + accept-all mode
- ✅ Container pool initializes 3 containers in 0.24s
- ✅ All security constraints applied and verified
- ✅ Containers can be allocated/released
- ✅ Graceful shutdown preserves stopped containers
- ✅ Code pushed to GitHub (`lksnyder0/sandtrap`)

### What Doesn't Work Yet
- ❌ SSH sessions don't proxy to containers (Phase 4)
- ❌ No actual shell access in containers yet (Phase 4)
- ❌ Session recording not implemented (Phase 5)
- ❌ No I/O proxy between SSH and Docker exec (Phase 4)

### Testing Status
- ✅ Manual testing: Pool initialization verified
- ✅ Security verification: All constraints checked with `docker inspect`
- ✅ SandTrap starts successfully with pool
- ⚠️ Unit tests not written yet (Phase 9)
- ⚠️ Integration tests not written yet (Phase 9)

---

## Next Steps: Phase 4 - Command Proxying

The next phase will connect SSH sessions to containers:

### Phase 4 Tasks
1. **Implement I/O proxy** (`src/sandtrap/session/proxy.py`)
   - Docker exec integration with PTY support
   - Bidirectional streaming: SSH stdin/stdout ↔ Docker exec socket
   - Terminal dimensions forwarding
   - Terminal resize event handling

2. **Update session handler** in `__main__.py`
   - Replace `dummy_session_handler` with real container proxy
   - Allocate container from pool
   - Create Docker exec instance with PTY
   - Proxy I/O between SSH and container
   - Release container on session end

3. **Key challenges**:
   - Docker exec socket is binary, need proper streaming
   - PTY dimensions must match SSH client's terminal
   - Handle terminal resize events from SSH
   - Graceful cleanup on disconnect

### Files to Create/Modify
- **NEW**: `src/sandtrap/session/proxy.py` (estimated 200-250 lines)
- **MODIFY**: `src/sandtrap/__main__.py` (replace dummy handler)
- **MODIFY**: `src/sandtrap/server/asyncssh_backend.py` (pass container pool to session)

### Estimated Time
6-8 hours

---

## Important Notes

### Docker SDK API Changes
- `container.stop()` does NOT take a timeout argument in current SDK
- Use `container.stop()` without arguments
- Seccomp syntax: Don't use `seccomp=default`, just omit it (default is applied)

### Configuration Paths
- Use absolute paths in configs for SSH keys: `/home/luke/code/sandtrap/data/keys/ssh_host_rsa_key`
- Relative paths from project root don't work when running from `src/` directory

### Container Naming
- Pattern: `sandtrap-target-{session_id[:8]}-{timestamp}`
- Example: `sandtrap-target-a3f2b1c9-20260127-143022`
- Links container directly to session for forensics

### Virtual Environment
- Located at `/home/luke/code/sandtrap/venv`
- Activate with: `source venv/bin/activate`
- Dependencies installed: asyncssh, docker, pyyaml, pydantic

### Running SandTrap
```bash
cd /home/luke/code/sandtrap
source venv/bin/activate
cd src
python -m sandtrap --config ../config/config.test.yaml
```

### Cleanup Test Containers
```bash
docker ps -a --filter "name=sandtrap-target" --format "{{.ID}}" | xargs -r docker rm -f
```

---

## Git Status

### Current Branch: `main`
### Remote: `git@github.com:lksnyder0/sandtrap.git`

### Commits Pushed:
1. `49cdccd` - Initial commit: Phase 1 setup
2. `349e174` - Phase 2 complete: SSH server with authentication
3. `d128ac2` - Phase 3 complete: Container pool management with security constraints

### Working Tree: Clean
All Phase 3 changes committed and pushed.

---

## Memory Files Created

Located in `.serena/memories/`:
1. `sandtrap-project-specifications.md` - Complete project specs
2. `sandtrap-mvp-implementation-plan.md` - 10-phase implementation roadmap (Phases 1-3 complete)
3. `sandtrap-phase1-research-findings.md` - AsyncSSH and Docker SDK research
4. `sandtrap-phase3-design-specification.md` - Complete Phase 3 design
5. `sandtrap-security-verification-script-design.md` - Script design for Phase 7
6. `sandtrap-post-mvp-considerations.md` - Future enhancements

---

## Key Technical Decisions for Phase 4

When implementing Phase 4, keep in mind:

1. **Docker exec socket**: Use `docker.api.exec_create()` and `exec_start(socket=True)` for streaming
2. **PTY dimensions**: Pass from `PTYRequest` to Docker exec: `{'Tty': True, 'AttachStdin': True, ...}`
3. **Asyncio integration**: Use `asyncio.get_event_loop().run_in_executor()` for blocking Docker calls
4. **Terminal resize**: Listen for SSH `terminal_size_changed()` events, update container exec
5. **Cleanup**: Must properly close exec socket and release container on disconnect

---

## Questions to Ask at Start of Next Session

1. Any issues with the current implementation?
2. Ready to start Phase 4 (Command Proxying)?
3. Want to review any design decisions from Phase 3?
4. Need to adjust security constraints based on testing?

---

**Session End**: Phase 3 complete, all code committed and pushed to GitHub. Ready for Phase 4 implementation.
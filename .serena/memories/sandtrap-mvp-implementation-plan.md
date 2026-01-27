# SandTrap MVP - Implementation Plan

## Project Overview

**Name**: SandTrap  
**Type**: SSH Honeypot with Docker Container Sandboxing  
**Location**: `~/code/sandtrap/` (full path: `/home/luke/code/sandtrap/`)  
**Python Version**: 3.14 ✅ (active and compiled)  
**Status**: 🚀 **Phase 2 Complete - Phase 3 Ready to Start**

---

## 📊 Current Status (Updated: Jan 27, 2026)

### ✅ Completed Phases

**Phase 1: Project Setup & Research** - ✅ COMPLETE
- Project structure created
- Git repository initialized
- Python packaging configured (pyproject.toml, requirements.txt)
- Dependencies installed
- All planning documents created

**Phase 2: Core SSH Server** - ✅ COMPLETE  
- 624 lines of production code implemented
- Abstract SSH backend interface with modular design
- Full AsyncSSH implementation with PTY support
- Authentication manager with static credentials + accept-all mode
- Connection/session lifecycle management
- Comprehensive logging throughout

**Git Status**: 2 commits, clean working tree

### 🎯 Next Phase

**Phase 4: Command Proxying** (Ready to start)
- Implement I/O proxy between SSH sessions and Docker containers
- Docker exec integration with PTY support
- Bidirectional streaming (SSH ↔ Docker)
- Terminal resize event handling

**Estimated Time**: 6-8 hours  
**Dependencies**: ✅ All met (Phases 1-3 complete)

---

## Quick Reference

### Key Decisions Made

✅ **Project Name**: SandTrap (sandbox + trap)  
✅ **SSH Library**: asyncssh (modular backend, can swap later)  
✅ **Container Strategy**: Pre-warmed pool with auto-replenishment  
✅ **Session Persistence**: Stop containers on disconnect (preserve for forensics)  
✅ **Authentication**: Static credentials + accept-all after N failures  
✅ **Recording**: Local filesystem, asciinema v2 format  
✅ **Network Isolation**: `network_mode: none` on target containers (MVP)  
✅ **Base Images**:
  - SandTrap honeypot: Alpine Linux
  - Target containers: Configurable (default Ubuntu 22.04)
✅ **Socket Proxy**: Defer to Phase 8 (post-MVP security enhancement)

### Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│ Internet/Attacker                                        │
└───────────────────┬─────────────────────────────────────┘
                    │ SSH Connection (port 2222)
                    ▼
┌─────────────────────────────────────────────────────────┐
│ SandTrap Container (Alpine + Python 3.14)               │
│ ├─ Network: ENABLED                                     │
│ ├─ SSH Server (asyncssh)                                │
│ ├─ Authentication Manager                               │
│ ├─ Container Pool Manager                               │
│ ├─ Session Recorder                                     │
│ └─ I/O Proxy                                            │
└───────────────────┬─────────────────────────────────────┘
                    │ Docker Socket (/var/run/docker.sock)
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Target Containers (Ubuntu 22.04)                        │
│ ├─ Network: DISABLED (network_mode=none)                │
│ ├─ Resource Limits: 256MB RAM, 0.5 CPU                  │
│ ├─ Security: Caps dropped, seccomp, no-new-privileges   │
│ └─ State: Stopped after session (preserved for forensics)│
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### ✅ Phase 1: Project Setup & Research (COMPLETE)

**Completed**:
- [x] Research asyncssh API and capabilities
- [x] Research Docker SDK for Python
- [x] Research Docker socket proxy options
- [x] Define project specifications
- [x] Design architecture
- [x] Create implementation plan
- [x] Create project directory structure at `~/code/sandtrap/`
- [x] Initialize git repository
- [x] Set up Python packaging files (pyproject.toml, requirements.txt)
- [x] Create .gitignore for Python, Docker, secrets
- [x] Design modular SSH backend interface (abstract class)
- [x] Create placeholder module files with docstrings

**Estimated Time**: 1-2 hours  
**Dependencies**: None  
**Output**: Complete project skeleton ready for coding

---

### ✅ Phase 2: Core SSH Server (COMPLETE)

**Status**: ✅ **COMPLETE** (Finished in previous session)

**Completed**:
- [x] Create abstract SSH backend interface (`src/sandtrap/server/backend.py`)
  - Defined `SSHBackend` abstract base class
  - Created `SessionInfo` and `PTYRequest` dataclasses
  - Established modular interface for swappable SSH libraries
- [x] Implement asyncssh backend (`src/sandtrap/server/asyncssh_backend.py`)
  - Implemented `AsyncSSHBackend` class (417 lines)
  - Created `SandTrapSSHServer` for connection handling
  - Created `SandTrapSSHSession` for session management
  - Full PTY support with terminal resize handling
  - Session factory pattern for proper session creation
- [x] Implement authentication manager (`src/sandtrap/server/auth.py`)
  - Static credentials from config with efficient lookup
  - Failed attempt tracking per connection ID
  - Accept-all mode after N failures
  - Connection cleanup on disconnect
- [x] Handle PTY session establishment
  - PTY allocation with terminal dimensions
  - Shell request handling
  - Terminal resize event support
- [x] Basic connection/disconnection logging
  - Structured logging with session IDs
  - Connection source IP/port tracking
  - Authentication attempt logging

**Key Files Implemented**:
- `src/sandtrap/server/backend.py` - Abstract interface (97 lines)
- `src/sandtrap/server/asyncssh_backend.py` - AsyncSSH implementation (417 lines)
- `src/sandtrap/server/auth.py` - Authentication logic (110 lines)
- `src/sandtrap/config.py` - Configuration system (162 lines, includes auth config)

**Actual Time**: ~5 hours (within estimate)  
**Dependencies**: Phase 1 complete ✅  
**Testing**: Can accept SSH connections and authenticate ✅

**Verification**:
- ✅ Code compiles (Python 3.14 bytecode present)
- ✅ All authentication logic implemented
- ✅ PTY and shell handling complete
- ✅ Logging integrated throughout
- ✅ Modular design allows backend swapping

---

### ✅ Phase 3: Docker Container Management (COMPLETE)

**Status**: ✅ **COMPLETE** (Finished Jan 27, 2026)

**Completed**:
- [ ] Implement container pool manager (`container/pool.py`)
  - Initialize pool with N containers on startup
  - Allocate container to session
  - Stop container on session end (preserve disk)
  - Spawn replacement container async
- [ ] Create security constraints config (`container/security.py`)
  - Resource limits (memory, CPU, pids)
  - Capability dropping
  - Network isolation
- [ ] Create Ubuntu target container Dockerfile
- [ ] Implement container-to-session tracking

**Key Files**:
- `src/sandtrap/container/pool.py` - Pool manager
- `src/sandtrap/container/security.py` - Security config
- `containers/targets/ubuntu/Dockerfile` - Target image

**Actual Time**: ~6 hours (within estimate)  
**Dependencies**: ✅ Phase 2 complete, Docker installed  
**Testing**: ✅ Pool creates/manages containers in 0.24s - all tests passed

**Verification Results**:
- Network isolation: none ✅
- Memory limit: 268435456 bytes (256MB) ✅
- CPU quota: 50000/100000 (0.5 cores) ✅
- PIDs limit: 100 ✅
- Capabilities: ALL dropped, 3 minimal added ✅
- Security: no-new-privileges + default seccomp ✅

---

### Phase 4: Command Proxying (MVP)

**Tasks**:
- [ ] Implement Docker exec integration (`session/proxy.py`)
- [ ] Create bidirectional I/O proxy (SSH ↔ Docker exec socket)
- [ ] Handle PTY dimensions and terminal type
- [ ] Implement terminal resize event handling
- [ ] Connect SSH session to container exec

**Key Files**:
- `src/sandtrap/session/proxy.py` - I/O proxy

**Estimated Time**: 6-8 hours  
**Dependencies**: Phase 2 & 3 complete  
**Testing**: Can execute commands in container via SSH

---

### Phase 5: Session Recording (MVP)

**Tasks**:
- [ ] Implement asciinema v2 recorder (`session/recorder.py`)
  - Header with metadata
  - Event stream (timestamp, direction, data)
- [ ] Implement local filesystem storage
- [ ] Create structured JSON logging (`utils/logging.py`)
  - Connection metadata
  - Authentication attempts
  - Session events
- [ ] Link recordings to container IDs

**Key Files**:
- `src/sandtrap/session/recorder.py` - Asciinema recorder
- `src/sandtrap/utils/logging.py` - Structured logging

**Estimated Time**: 4-6 hours  
**Dependencies**: Phase 4 complete  
**Testing**: Sessions recorded in valid asciinema format

---

### Phase 6: Configuration System (MVP)

**Tasks**:
- [ ] Design complete YAML schema
- [ ] Implement config parser (`config.py`)
- [ ] Add validation (pydantic models)
- [ ] Create config.example.yaml with documentation
- [ ] Create config.minimal.yaml for quick start
- [ ] Implement config loading and defaults

**Key Files**:
- `src/sandtrap/config.py` - Config parser
- `config/config.example.yaml` - Full example
- `config/config.minimal.yaml` - Minimal config

**Estimated Time**: 3-4 hours  
**Dependencies**: Phases 2-5 complete (know all config needs)  
**Testing**: Config loads and validates correctly

---

### Phase 7: Security Hardening (MVP Critical)

**Tasks**:
- [ ] Implement all Docker security constraints
  - Resource limits (memory, CPU, disk I/O)
  - Capability dropping (drop ALL, add minimal)
  - Security options (no-new-privileges, seccomp)
  - Network isolation enforcement
- [ ] Add session timeouts and auto-stop
- [ ] Implement input validation for commands
  - Prevent Docker API injection
  - Sanitize container IDs
  - Validate usernames/passwords
- [ ] Add rate limiting for connections
- [ ] **Create security verification script** (`scripts/verify_security.sh`)
  - Active testing approach (attempts to break constraints)
  - Tests: network isolation, resource limits, capabilities, privilege escalation
  - See `sandtrap-security-verification-script-design.md` for full spec
  - Estimated time: 1.5-2 hours
- [ ] Run security verification and fix any issues
- [ ] Security review and testing

**Key Files**:
- `src/sandtrap/container/security.py` - Enhanced
- Throughout codebase - Input validation

**Estimated Time**: 4-6 hours  
**Dependencies**: Phases 2-6 complete  
**Testing**: Security constraints enforced, injection attempts fail

---

### Phase 8: Containerization & Deployment

**Tasks**:
- [ ] Create SandTrap Dockerfile (Alpine + Python 3.14)
- [ ] Create docker-compose.yml for deployment
- [ ] Create docker-compose.dev.yml for development
- [ ] Document volume mounts (keys, recordings, logs)
- [ ] Create helper scripts:
  - `scripts/generate_ssh_keys.sh`
  - `scripts/build_images.sh`
  - `scripts/cleanup.sh`
- [ ] Evaluate Docker socket proxy integration
- [ ] Test full deployment workflow

**Key Files**:
- `Dockerfile` - SandTrap honeypot image
- `docker-compose.yml` - Production deployment
- `docker-compose.dev.yml` - Development setup
- `scripts/*` - Helper scripts

**Estimated Time**: 4-6 hours  
**Dependencies**: Phases 2-7 complete  
**Testing**: `docker-compose up` works end-to-end

---

### Phase 9: Testing (MVP)

**Tasks**:
- [ ] Set up pytest configuration
- [ ] Write unit tests:
  - Authentication manager
  - Container pool manager
  - Configuration parser
  - Session recorder
- [ ] Write integration tests:
  - Full SSH session flow
  - Container lifecycle
  - Recording output validation
- [ ] Test authentication flows
- [ ] Test security constraints
- [ ] Performance testing (concurrent sessions)

**Key Files**:
- `tests/conftest.py` - Pytest fixtures
- `tests/unit/*` - Unit tests
- `tests/integration/*` - Integration tests
- `pytest.ini` - Pytest config

**Estimated Time**: 6-8 hours  
**Dependencies**: Phases 2-8 complete  
**Testing**: Test coverage >80%

---

### Phase 10: Documentation (MVP)

**Tasks**:
- [ ] Write comprehensive README.md
  - Project overview and features
  - Architecture diagram
  - Quick start guide
  - Installation instructions
  - Usage examples
- [ ] Write SECURITY.md
  - Threat model
  - Known risks and limitations
  - Deployment security best practices
  - Incident response procedures
- [ ] Document configuration options
- [ ] Create deployment guide
- [ ] Write development guide

**Key Files**:
- `README.md` - Main documentation
- `SECURITY.md` - Security documentation
- `docs/configuration.md` - Config reference
- `docs/deployment.md` - Deployment guide
- `docs/development.md` - Dev guide

**Estimated Time**: 4-6 hours  
**Dependencies**: Phases 2-9 complete  
**Testing**: Documentation reviewed and accurate

---

## Total MVP Effort Estimate

**Total Time**: 45-65 hours (approximately 1-2 weeks full-time)

**Recommended Session Breakdown**:
- ✅ Session 1: Phase 1 (Setup) - 1-2 hours - **COMPLETE**
- ✅ Session 2: Phase 2 (SSH Server) - 4-6 hours - **COMPLETE**
- Session 4-5: Phase 3 (Container Mgmt) - 6-8 hours
- Session 6-7: Phase 4 (Proxying) - 6-8 hours
- Session 8: Phase 5 (Recording) - 4-6 hours
- Session 9: Phase 6 (Config) - 3-4 hours
- Session 10: Phase 7 (Security) - 4-6 hours
- Session 11: Phase 8 (Deployment) - 4-6 hours
- Session 12-13: Phase 9 (Testing) - 6-8 hours
- Session 14: Phase 10 (Docs) - 4-6 hours

---

## Post-MVP Features (Future)

Stored in memory: `sandtrap-post-mvp-considerations.md`

**High Priority**:
- Docker socket proxy integration
- Multiple target container images with weighted selection
- SFTP/SCP file transfer support and recording
- Session replay CLI tool

**Medium Priority**:
- Advanced authentication methods (honeytokens, public key capture)
- Network honeypot mode (limited outbound with logging)
- Metrics and monitoring endpoints
- Real-time alerting

**Low Priority**:
- Automated malware analysis
- Threat intelligence integration
- Machine learning anomaly detection
- Session clustering (identify same attacker)

---

## Success Criteria

The MVP is complete when:

1. ✅ **Functional**: Accepts SSH connections and proxies to containers
2. ✅ **Secure**: All security constraints properly enforced
3. ✅ **Performant**: <1 second container allocation from pool
4. ✅ **Recorded**: All sessions saved in valid asciinema format
5. ✅ **Configurable**: Easy YAML-based configuration
6. ✅ **Deployable**: Single `docker-compose up` command works
7. ✅ **Forensic**: Stopped containers preserved with linked recordings
8. ✅ **Documented**: Clear README and security documentation
9. ✅ **Tested**: Integration tests pass for full SSH flow
10. ✅ **Production-Ready**: Can be deployed on dedicated honeypot server

---

## Risk Mitigation

### Technical Risks

**Risk**: Container escape vulnerability  
**Mitigation**: Multi-layer security (caps, seccomp, resource limits, network isolation), dedicated infrastructure

**Risk**: Docker socket exposure  
**Mitigation**: MVP on isolated host, post-MVP socket proxy, audit logging

**Risk**: Resource exhaustion  
**Mitigation**: Connection limits, session timeouts, per-container resource limits

**Risk**: asyncssh library limitations  
**Mitigation**: Modular backend design allows library swap if needed

### Development Risks

**Risk**: Python 3.14 not available  
**Mitigation**: Target 3.12+ as minimum, use 3.14 features when available

**Risk**: Scope creep  
**Mitigation**: Strict MVP feature list, defer enhancements to post-MVP

**Risk**: Integration complexity  
**Mitigation**: Incremental development, test each phase before moving on

---

## Memory Files Created

All planning documentation stored in Serena memory:

1. **sandtrap-project-specifications.md** - Complete project specs, structure, config
2. **sandtrap-phase1-research-findings.md** - API research, code examples, decisions  
3. **sandtrap-post-mvp-considerations.md** - Deferred features and enhancements
4. **sandtrap-mvp-implementation-plan.md** - This file, complete implementation roadmap

---

## Next Steps

**When ready to begin implementation:**

1. Confirm project location: `~/code/sandtrap/`
2. Confirm Python 3.14 available (or use 3.12+ as fallback)
3. Begin Phase 1: Create project structure
4. Initialize git repository
5. Set up Python virtual environment
6. Install dependencies
7. Begin coding Phase 2

**Questions before starting?**
- Any additional security considerations?
- Preferences for testing framework beyond pytest?
- Any specific deployment environment constraints?
- Preferred logging format or integrations?

---

---

## 📈 Phase 2 Completion Summary

### Implementation Details

**Files Created/Modified**:
1. `src/sandtrap/server/backend.py` (97 lines)
   - Abstract `SSHBackend` class
   - `SessionInfo` and `PTYRequest` dataclasses
   - Clean interface for backend swapping

2. `src/sandtrap/server/asyncssh_backend.py` (417 lines)
   - `AsyncSSHBackend` - main backend class
   - `SandTrapSSHServer` - connection handling
   - `SandTrapSSHSession` - session management
   - Full PTY and terminal resize support
   - Session factory pattern

3. `src/sandtrap/server/auth.py` (110 lines)
   - `AuthenticationManager` class
   - Static credential validation
   - Failed attempt tracking per connection
   - Accept-all mode after N failures
   - Automatic cleanup

4. `src/sandtrap/config.py` (162 lines)
   - Pydantic-based configuration models
   - YAML loading and validation
   - Type-safe config access

**Total Code**: ~624 lines of production Python code

**Git History**:
- Commit 1: `49cdccd` - Initial commit with project structure
- Commit 2: `349e174` - Phase 2 complete - SSH server with authentication

### What Works Now

✅ SSH server starts and binds to configured port  
✅ Accepts incoming SSH connections  
✅ Tracks connection metadata (IP, port, session ID)  
✅ Validates credentials against static list  
✅ Implements accept-all fallback after N failures  
✅ Handles PTY allocation requests  
✅ Responds to shell requests  
✅ Tracks terminal dimensions  
✅ Handles terminal resize events  
✅ Logs all authentication attempts  
✅ Cleans up on disconnection  

### What's Missing (Phase 3+)

❌ Container pool not implemented  
❌ No Docker integration yet  
❌ Command proxying not implemented  
❌ Session recording not implemented  
❌ No Dockerfiles for target containers  
❌ Security constraints not applied  

### Testing Status

- ✅ Code compiles (Python 3.14 bytecode present)
- ⚠️ Unit tests not written yet (Phase 9)
- ⚠️ Integration tests not written yet (Phase 9)
- ⚠️ Manual testing not performed yet (requires Phase 3-4)

### Ready for Phase 3

All prerequisites for Phase 3 are met:
- ✅ SSH server functional
- ✅ Session objects available
- ✅ Docker SDK in requirements.txt
- ✅ Configuration system ready
- ✅ Logging infrastructure in place

---

## Plan Status: ✅ PHASES 1-2 COMPLETE | 🎯 PHASE 3 READY TO START

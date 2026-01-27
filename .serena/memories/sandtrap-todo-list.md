# SandTrap MVP - Task List

## Status: Phase 1 Complete ✅

**Last Updated**: Session 1  
**Project Location**: `~/code/sandtrap/`  
**Git Status**: Initial commit created (49cdccd)

---

## Completed Tasks ✅

### Phase 1: Project Setup & Research (100% Complete)
- [x] Create project structure for SandTrap with proper Python package layout
- [x] Set up project files (.gitignore, README.md, requirements.txt, pyproject.toml)
- [x] Research asyncssh API and capabilities for SSH server implementation
- [x] Research Docker SDK for Python (docker-py) for container management
- [x] Research Docker socket proxy options and capabilities
- [x] Design modular SSH backend interface to allow future library swaps
- [x] Create example configuration file
- [x] Initialize git repository with initial commit

**Deliverables Completed**:
- Complete directory structure at `~/code/sandtrap/`
- Configuration system with Pydantic validation (100% functional)
- Authentication manager with accept-all mode (100% functional)
- Abstract SSH backend interface (100% designed)
- Comprehensive README and documentation
- Test infrastructure ready
- Git repository initialized

---

## Pending Tasks 📋

### Phase 2: Core SSH Server (MVP) - NEXT PRIORITY
**Status**: Ready to begin  
**Estimated Time**: 4-6 hours

- [ ] Implement AsyncSSH backend class (`server/asyncssh_backend.py`)
- [ ] Connect authentication manager to SSH server
- [ ] Implement SSH server start/stop methods
- [ ] Handle SSH shell session establishment
- [ ] Implement PTY allocation and terminal handling
- [ ] Add basic connection/disconnection logging
- [ ] Wire up session handler callback mechanism

**Key Files to Create**:
- `src/sandtrap/server/asyncssh_backend.py`

**Testing**:
- Can accept SSH connections on port 2222
- Authentication works (static credentials + accept-all)
- PTY sessions established correctly
- Logging captures connection events

---

### Phase 3: Docker Container Management (MVP)
**Status**: Pending Phase 2  
**Estimated Time**: 6-8 hours

- [ ] Implement container pool manager (`container/pool.py`)
  - [ ] Pool initialization with N pre-warmed containers
  - [ ] Container allocation to sessions
  - [ ] Container stop on session end (preserve disk)
  - [ ] Async container spawning to refill pool
  - [ ] Container-to-session tracking dictionary
- [ ] Create security constraints config (`container/security.py`)
  - [ ] Resource limits (memory, CPU, pids)
  - [ ] Capability dropping configuration
  - [ ] Network isolation settings
- [ ] Create Ubuntu target container Dockerfile (`containers/targets/ubuntu/Dockerfile`)
  - [ ] Install common tools (bash, curl, wget, vim, etc.)
  - [ ] Create fake interesting files
  - [ ] Set up convincing environment variables

**Key Files to Create**:
- `src/sandtrap/container/pool.py`
- `src/sandtrap/container/security.py`
- `containers/targets/ubuntu/Dockerfile`
- `containers/targets/ubuntu/entrypoint.sh` (if needed)

**Testing**:
- Pool creates containers successfully
- Containers have correct security constraints
- Allocation/deallocation works
- Pool auto-refills after allocation

---

### Phase 4: Command Proxying (MVP)
**Status**: Pending Phase 2 & 3  
**Estimated Time**: 6-8 hours

- [ ] Implement I/O proxy (`session/proxy.py`)
  - [ ] Docker exec integration
  - [ ] Bidirectional I/O streaming (SSH ↔ Docker exec socket)
  - [ ] Handle PTY dimensions
  - [ ] Terminal resize event handling
  - [ ] Signal forwarding (SIGINT, SIGTERM, etc.)
- [ ] Connect SSH session to container exec
- [ ] Handle exec session lifecycle

**Key Files to Create**:
- `src/sandtrap/session/proxy.py`

**Testing**:
- Can execute commands in container via SSH
- I/O streams correctly in both directions
- Terminal resizing works
- Signals forwarded correctly

---

### Phase 5: Session Recording (MVP)
**Status**: Pending Phase 4  
**Estimated Time**: 4-6 hours

- [ ] Implement asciinema v2 recorder (`session/recorder.py`)
  - [ ] Header generation with metadata
  - [ ] Event stream recording (timestamp, direction, data)
  - [ ] File writing and management
- [ ] Implement local filesystem storage
  - [ ] Directory structure for recordings
  - [ ] Filename generation (timestamp, session ID)
- [ ] Implement structured JSON logging (`utils/logging.py`)
  - [ ] Connection metadata logging
  - [ ] Authentication attempt logging
  - [ ] Session event logging
- [ ] Link recordings to stopped container IDs

**Key Files to Create**:
- `src/sandtrap/session/recorder.py`
- `src/sandtrap/utils/logging.py`

**Testing**:
- Sessions recorded in valid asciinema v2 format
- Recordings can be replayed with asciinema
- Metadata correctly captured
- Container IDs linked to recordings

---

### Phase 6: Configuration System (MVP)
**Status**: Config parser complete, integration pending  
**Estimated Time**: 3-4 hours

- [x] Design YAML configuration schema ✅
- [x] Implement configuration parser with Pydantic ✅
- [x] Create config.example.yaml with full documentation ✅
- [ ] Create config.minimal.yaml for quick start
- [ ] Integrate configuration throughout codebase
- [ ] Add configuration validation tests
- [ ] Document all configuration options

**Key Files to Create/Update**:
- `config/config.minimal.yaml`
- `tests/unit/test_config.py`

**Testing**:
- Configuration loads correctly
- Validation catches invalid values
- Defaults work as expected

---

### Phase 7: Security Hardening (MVP Critical)
**Status**: Config defined, enforcement pending  
**Estimated Time**: 4-6 hours

- [ ] Enforce Docker security constraints in container creation
  - [x] Resource limits configured ✅
  - [ ] Actually applied to containers
  - [x] Capability dropping configured ✅
  - [ ] Actually enforced
  - [x] Network isolation configured ✅
  - [ ] Verified working
- [ ] Implement session timeouts and auto-stop
- [ ] Add input validation throughout
  - [ ] Validate container IDs before Docker API calls
  - [ ] Sanitize usernames and passwords
  - [ ] Prevent command injection in exec calls
- [ ] Add connection rate limiting
- [ ] Security testing and review

**Key Files to Update**:
- `src/sandtrap/container/pool.py`
- `src/sandtrap/session/proxy.py`
- Throughout codebase for input validation

**Testing**:
- Security constraints actually enforced
- Resource limits prevent abuse
- Input validation blocks injection attempts
- Containers properly isolated

---

### Phase 8: Containerization & Deployment
**Status**: Pending most implementation  
**Estimated Time**: 4-6 hours

- [ ] Create SandTrap Dockerfile (`Dockerfile`)
  - [ ] Alpine base image
  - [ ] Python 3.12+ installation
  - [ ] Dependency installation
  - [ ] Application code copying
  - [ ] Proper user/permissions
- [ ] Create docker-compose.yml
  - [ ] SandTrap service definition
  - [ ] Volume mounts (data, keys, recordings, logs)
  - [ ] Port mappings
  - [ ] Docker socket mounting
- [ ] Create docker-compose.dev.yml for development
- [ ] Create helper scripts
  - [ ] `scripts/generate_ssh_keys.sh`
  - [ ] `scripts/build_images.sh`
  - [ ] `scripts/cleanup.sh`
- [ ] Document deployment process
- [ ] Evaluate Docker socket proxy integration

**Key Files to Create**:
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.dev.yml`
- `scripts/*.sh`

**Testing**:
- `docker-compose up` works end-to-end
- Containers build successfully
- Volume mounts work correctly
- Can SSH to running honeypot

---

### Phase 9: Testing (MVP)
**Status**: Infrastructure ready, tests pending  
**Estimated Time**: 6-8 hours

- [ ] Set up pytest with async support
- [ ] Write unit tests
  - [ ] `tests/unit/test_auth.py` - Authentication manager tests
  - [ ] `tests/unit/test_pool.py` - Container pool manager tests
  - [ ] `tests/unit/test_config.py` - Configuration parser tests
  - [ ] `tests/unit/test_recorder.py` - Session recorder tests
- [ ] Write integration tests
  - [ ] `tests/integration/test_ssh_session.py` - Full SSH flow
  - [ ] `tests/integration/test_container_lifecycle.py` - Container management
- [ ] Test authentication flows
- [ ] Test security constraints
- [ ] Performance testing (concurrent sessions)
- [ ] Achieve >80% code coverage

**Key Files to Create**:
- `tests/unit/*.py`
- `tests/integration/*.py`

**Testing Goals**:
- All unit tests pass
- Integration tests pass
- Code coverage >80%
- No critical security issues

---

### Phase 10: Documentation (MVP)
**Status**: README created, others pending  
**Estimated Time**: 4-6 hours

- [x] Write comprehensive README.md ✅
  - [x] Project overview ✅
  - [x] Architecture diagram ✅
  - [x] Quick start guide ✅
  - [ ] Update installation instructions (once working)
- [ ] Write SECURITY.md
  - [ ] Threat model
  - [ ] Known risks and limitations
  - [ ] Deployment security best practices
  - [ ] Incident response procedures
- [ ] Create deployment guide (`docs/deployment.md`)
  - [ ] Prerequisites
  - [ ] Step-by-step deployment
  - [ ] Configuration examples
  - [ ] Troubleshooting
- [ ] Create development guide (`docs/development.md`)
  - [ ] Development setup
  - [ ] Code structure
  - [ ] Testing guidelines
  - [ ] Contributing guidelines
- [ ] Document configuration options (`docs/configuration.md`)
- [ ] Create CHANGELOG.md
- [ ] Add LICENSE file (MIT)

**Key Files to Create**:
- `SECURITY.md`
- `docs/deployment.md`
- `docs/development.md`
- `docs/configuration.md`
- `CHANGELOG.md`
- `LICENSE`

---

## Post-MVP Enhancements (Future)

See `sandtrap-post-mvp-considerations.md` memory for detailed list.

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

---

## Progress Summary

| Phase | Status | Completion |
|-------|--------|------------|
| 1. Setup & Research | ✅ Complete | 100% |
| 2. SSH Server | 🔴 Pending | 0% |
| 3. Container Mgmt | 🔴 Pending | 0% |
| 4. Command Proxy | 🔴 Pending | 0% |
| 5. Recording | 🔴 Pending | 0% |
| 6. Configuration | 🟡 Partial | 60% |
| 7. Security | 🟡 Partial | 30% |
| 8. Deployment | 🔴 Pending | 0% |
| 9. Testing | 🟡 Infra Ready | 10% |
| 10. Documentation | 🟡 Partial | 40% |

**Overall MVP Progress**: ~14% complete (1/10 phases + partials)

---

## Next Session Plan

**Start with Phase 2**: Core SSH Server Implementation

1. Create `src/sandtrap/server/asyncssh_backend.py`
2. Implement AsyncSSH server class
3. Wire up authentication manager
4. Handle PTY sessions
5. Test SSH connection acceptance

**Session Goal**: Be able to SSH into the honeypot and authenticate (even without container backend yet)

---

## Quick Reference Links

**Memory Files**:
- `sandtrap-project-specifications.md` - Complete project specs
- `sandtrap-phase1-research-findings.md` - API research and code examples
- `sandtrap-post-mvp-considerations.md` - Future enhancements
- `sandtrap-mvp-implementation-plan.md` - Detailed phase breakdown
- `sandtrap-todo-list.md` - This file

**Project Location**: `~/code/sandtrap/`  
**Git Branch**: `main`  
**Last Commit**: Initial commit (49cdccd)

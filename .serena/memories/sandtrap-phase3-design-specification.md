# SandTrap Phase 3 - Container Pool Manager Design Specification

## Overview

Phase 3 implements Docker container management with a pre-warmed pool strategy for fast session allocation. This document captures all design decisions, architecture, and implementation details.

**Status**: Design Complete, Ready for Implementation  
**Created**: Jan 27, 2026  
**Target Duration**: 6-8 hours

---

## Design Decisions (Approved)

### 1. Pool Initialization Strategy
**Decision**: ✅ **Eager Initialization**
- Create all pool containers at startup
- Ensures sub-second allocation goal
- Higher memory usage when idle (acceptable tradeoff)
- Simpler pool management logic

### 2. Container Replenishment Strategy
**Decision**: ✅ **Immediate Background Spawn**
- Spawn replacement as soon as container allocated
- Pool always maintained at target size
- Uses `asyncio.create_task()` for non-blocking execution
- Consistent performance during burst traffic

### 3. Container Lifecycle After Session
**Decision**: ✅ **Stop and Track, Defer Automated Cleanup**
- Stop container immediately on session end
- Keep container object with all disk state intact
- Track with timestamp for manual/future cleanup
- Automated cleanup task deferred to Phase 7
- Config: `cleanup_stopped_after_days: 7` (for future use)

### 4. Container Naming Strategy
**Decision**: ✅ **Session-Based with Timestamp**
- Pattern: `sandtrap-target-{session_id[:8]}-{timestamp}`
- Example: `sandtrap-target-a3f2b1c9-20260127-143022`
- Direct link to session for forensics
- Timestamp for easy chronological identification
- Unique across all containers

### 5. Error Handling for Container Spawn Failures
**Decision**: ✅ **Fail Fast with Single Retry**
- Log error with full context (image, config, Docker error)
- Retry once with 2-second delay
- If retry fails, raise exception to caller
- Session handler will catch and gracefully fail connection
- Prevents hanging connections on Docker issues

### 6. Dockerfile Content
**Decision**: ✅ **Moderate Fake Data**
- Common attacker tools (curl, wget, netcat, vim, python3)
- A few "interesting" files (config with fake password, logs)
- Not overly elaborate (keep it realistic)
- Focus on Ubuntu 22.04 for MVP

### 7. Development Pool Size
**Decision**: ✅ **Keep Default at 3**
- Config default: `size: 3`
- Reasonable for development (~768MB RAM with 256MB/container)
- Can be adjusted via config for resource-constrained environments
- Production may use 5-10 depending on expected traffic

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│ SSH Server (Phase 2)                                     │
│ ├─ Session Handler                                       │
│ └─ Calls pool.allocate(session_id)                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ ContainerPool (Phase 3)                                  │
│ ├─ ready_pool: List[Container]                          │
│ ├─ active_sessions: Dict[session_id, Container]         │
│ ├─ stopped_containers: List[(Container, timestamp)]     │
│ └─ Methods: initialize, allocate, release, shutdown     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Docker API (via docker-py SDK)                          │
│ ├─ containers.create()                                   │
│ ├─ container.start()                                     │
│ ├─ container.stop()                                      │
│ └─ container.remove()                                    │
└─────────────────────────────────────────────────────────┘
```

### State Machine

```
Container States:
┌──────────┐
│ CREATING │ (pool initialization or replacement spawn)
└────┬─────┘
     │
     ▼
┌──────────┐
│  READY   │ (in ready_pool, waiting for allocation)
└────┬─────┘
     │
     ▼
┌──────────┐
│  ACTIVE  │ (allocated to session, in active_sessions)
└────┬─────┘
     │
     ▼
┌──────────┐
│ STOPPED  │ (stopped, in stopped_containers for forensics)
└────┬─────┘
     │
     ▼
┌──────────┐
│ REMOVED  │ (deleted from Docker, future cleanup phase)
└──────────┘
```

---

## Implementation Details

### File 1: `src/sandtrap/container/security.py`

**Purpose**: Security configuration builder for Docker containers

**Estimated Lines**: ~80-100 lines

**Key Functions**:

```python
def build_container_config(
    config: ContainerSecurityConfig,
    image: str,
    name: str
) -> Dict[str, Any]:
    """
    Build Docker container creation parameters with security constraints.
    
    Args:
        config: Security configuration from main config
        image: Docker image name
        name: Container name
        
    Returns:
        Dictionary of Docker API parameters
    """
    # Convert CPU quota from cores to Docker quota format
    # Build complete container config with all security options
    # Add labels for identification and tracking
    # Return config dict ready for docker.containers.create(**config)
```

**Configuration Mapping**:
- `memory_limit`: Direct pass-through (e.g., "256m")
- `cpu_quota`: Convert cores to quota (0.5 cores = 50000 quota)
- `cpu_period`: Fixed at 100000 (standard)
- `network_mode`: Direct pass-through ("none")
- `pids_limit`: Direct pass-through (100)
- `tmpfs`: Build dict `{'/tmp': 'size=50m'}`
- `capabilities`: Build cap_drop and cap_add lists
- `security_opt`: Direct pass-through list

**Labels Added**:
- `sandtrap.role=target`
- `sandtrap.version=mvp`
- `sandtrap.created={iso_timestamp}`
- `sandtrap.session_id={session_id}` (when allocated)

**Error Handling**:
- Validate memory limit format (regex: `^\d+[kmg]$`)
- Validate CPU quota range (0.1 to 8.0 cores)
- Log warnings for unusual configurations

---

### File 2: `src/sandtrap/container/pool.py`

**Purpose**: Container pool manager with lifecycle management

**Estimated Lines**: ~250-300 lines

**Class: `ContainerPool`**

#### Attributes:
```python
class ContainerPool:
    docker_client: docker.DockerClient
    config: ContainerPoolConfig
    ready_pool: List[docker.models.containers.Container]
    active_sessions: Dict[str, docker.models.containers.Container]
    stopped_containers: List[Tuple[docker.models.containers.Container, datetime]]
    _lock: asyncio.Lock  # Protect pool access
    _shutdown: bool  # Shutdown flag
```

#### Methods:

**`__init__(client: docker.DockerClient, config: ContainerPoolConfig)`**
- Store client and config
- Initialize empty collections
- Create asyncio lock
- Log initialization

**`async initialize() -> None`**
- Log pool initialization start
- Create `config.size` containers in parallel
- Use `asyncio.gather()` for parallel creation
- Start each container
- Add to ready_pool
- Log completion with timing
- Raise exception if any container fails

**`async allocate(session_id: str) -> docker.models.containers.Container`**
- Acquire lock
- Check if ready_pool has containers
  - If empty: create on-demand (fallback, log warning)
  - If available: pop from ready_pool
- Add to active_sessions[session_id]
- Add session_id label to container
- Spawn replacement task (non-blocking)
- Release lock
- Log allocation
- Return container

**`async release(session_id: str) -> None`**
- Acquire lock
- Get container from active_sessions
- Stop container with timeout
- Add to stopped_containers with timestamp
- Remove from active_sessions
- Release lock
- Log release with session_id and container_id

**`async shutdown() -> None`**
- Set shutdown flag
- Stop all active containers
- Stop all ready containers
- Log shutdown complete
- Note: Don't remove stopped containers (forensics)

**`async _create_container(session_id: Optional[str] = None) -> Container`**
- Generate unique name with timestamp
- Build container config via security.build_container_config()
- Call docker.containers.create()
- Start container
- Log creation
- Return container

**`async _spawn_replacement() -> None`** (background task)
- If shutdown flag set, return
- Try to create and add container to ready_pool
- Log success or failure
- Don't raise exception (background task)

**`_generate_container_name(session_id: Optional[str] = None) -> str`**
- If session_id: use first 8 chars
- Else: generate random UUID
- Format: `sandtrap-target-{id}-{timestamp}`
- Timestamp format: YYYYMMDD-HHMMSS

#### Error Handling:
- Wrap Docker API calls in try/except
- Catch `docker.errors.DockerException`
- Log all errors with full context
- Single retry on failure with 2-second delay
- Raise after retry fails

#### Logging Events:
- Pool initialization start/complete
- Container creation (with timing)
- Container allocation (session_id, container_id)
- Container release (session_id, container_id, duration)
- Replacement spawn success/failure
- On-demand creation (should be rare)
- All errors and warnings

---

### File 3: `containers/targets/ubuntu/Dockerfile`

**Purpose**: Target container image for attacker sandboxing

**Estimated Lines**: ~30 lines

**Base Image**: `ubuntu:22.04`

**Installed Tools**:
- **Core**: bash, coreutils, procps
- **Editors**: vim, nano
- **Network**: curl, wget, netcat-traditional, net-tools, iputils-ping, dnsutils
- **Languages**: python3, python3-pip
- **SSH Client**: openssh-client (for attacker testing)
- **VCS**: git
- **Misc**: file, less, man-db (optional)

**Fake Data Files**:
1. `/etc/config/app.env` - Fake database password
2. `/var/log/access.log` - Fake internal URL
3. `/home/admin/.bash_history` - Fake command history
4. `/root/.ssh/config` - Empty but exists (tempting)

**Environment Variables**:
- `HOSTNAME=prod-web-01`
- `USER=root`

**Working Directory**: `/root`

**CMD**: `["/bin/bash"]` (will be overridden by exec)

**Build Command** (for docs):
```bash
docker build -t sandtrap-target-ubuntu:latest containers/targets/ubuntu/
```

---

### File 4: Update `src/sandtrap/__main__.py`

**Purpose**: Integrate container pool into application startup

**Changes Required**:

1. **Import Docker and Pool**:
```python
import docker
from sandtrap.container.pool import ContainerPool
```

2. **Initialize Docker Client** (in main or startup):
```python
# Connect to Docker
if config.docker.base_url:
    docker_client = docker.DockerClient(base_url=config.docker.base_url)
else:
    docker_client = docker.from_env()

logger.info(f"Connected to Docker: {docker_client.version()}")
```

3. **Initialize Container Pool**:
```python
# Initialize container pool
logger.info("Initializing container pool...")
pool = ContainerPool(docker_client, config.container_pool)
await pool.initialize()
logger.info(f"Container pool ready with {config.container_pool.size} containers")
```

4. **Pass Pool to Backend**:
```python
backend = AsyncSSHBackend(config)
backend.set_container_pool(pool)  # New method needed
```

5. **Graceful Shutdown**:
```python
async def shutdown():
    logger.info("Shutting down SandTrap...")
    await backend.stop()
    await pool.shutdown()
    docker_client.close()
    logger.info("Shutdown complete")

# Register shutdown handler
loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(shutdown()))
loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(shutdown()))
```

**Estimated Lines Changed**: ~30-40 lines

---

### File 5: Update `src/sandtrap/server/asyncssh_backend.py`

**Purpose**: Store pool reference for session handler

**Changes Required**:

1. **Add Pool Attribute**:
```python
class AsyncSSHBackend(SSHBackend):
    def __init__(self, config: Config):
        super().__init__(config)
        # ... existing code ...
        self.container_pool: Optional[ContainerPool] = None
```

2. **Add Setter Method**:
```python
def set_container_pool(self, pool: ContainerPool) -> None:
    """Set the container pool for session handling."""
    self.container_pool = pool
    logger.info("Container pool registered with SSH backend")
```

3. **Update Session Handler Signature** (for Phase 4 integration):
```python
# In _session_factory, pass pool to session:
return SandTrapSSHSession(
    session_info=session_info,
    session_handler=self.session_handler,
    container_pool=self.container_pool,  # New
)
```

**Estimated Lines Changed**: ~10-15 lines

---

## Configuration

The configuration is already complete in `src/sandtrap/config.py`:

### Relevant Config Sections:

```yaml
container_pool:
  size: 3                              # Pool size
  spawn_timeout: 30                    # Container spawn timeout
  image: "sandtrap-target-ubuntu:latest"  # Target image
  max_session_duration: 3600           # Max session time
  cleanup_stopped_after_days: 7        # Cleanup policy (Phase 7)
  
  security:
    network_mode: "none"               # Network isolation
    memory_limit: "256m"               # Memory limit
    cpu_quota: 0.5                     # CPU cores
    pids_limit: 100                    # Process limit
    tmpfs_size: "50m"                  # /tmp size
    
    capabilities:
      drop: ["ALL"]                    # Drop all caps
      add: ["CHOWN", "SETUID", "SETGID"]  # Add minimal
    
    security_opt:
      - "no-new-privileges:true"       # No privilege escalation
      - "seccomp=default"              # Seccomp profile

docker:
  socket_path: "/var/run/docker.sock"  # Docker socket
  base_url: null                       # Or tcp://proxy:2375
```

---

## Testing Strategy (Phase 9, but keep in mind)

### Unit Tests (`tests/unit/test_pool.py`):
- Test pool initialization creates correct number of containers
- Test allocation/release cycle
- Test on-demand creation when pool empty
- Test container naming format
- Test security config builder
- Test error handling and retry logic
- Mock Docker client for all tests

### Integration Tests (`tests/integration/test_container_lifecycle.py`):
- Test full lifecycle with real Docker
- Test concurrent allocations
- Test replacement spawn timing
- Test stopped container tracking
- Test graceful shutdown
- Requires Docker available in test environment

### Performance Tests:
- Measure pool initialization time
- Measure allocation latency (<1 second goal)
- Test pool under load (10+ concurrent sessions)
- Monitor memory usage

---

## Implementation Checklist

### Phase 3: Docker Container Management

**Step 1: Security Configuration** (~1 hour)
- [ ] Create `src/sandtrap/container/security.py`
- [ ] Implement `build_container_config()` function
- [ ] Add memory limit validation
- [ ] Add CPU quota conversion (cores → Docker quota)
- [ ] Add label generation
- [ ] Add docstrings and type hints
- [ ] Log configuration details

**Step 2: Container Pool Manager** (~3-4 hours)
- [ ] Create `src/sandtrap/container/pool.py`
- [ ] Implement `ContainerPool` class
- [ ] Implement `__init__` and `initialize()`
- [ ] Implement `allocate()` with lock protection
- [ ] Implement `release()` and stopped tracking
- [ ] Implement `_create_container()` with retry logic
- [ ] Implement `_spawn_replacement()` background task
- [ ] Implement `_generate_container_name()`
- [ ] Implement `shutdown()` cleanup
- [ ] Add comprehensive logging throughout
- [ ] Add error handling with retries

**Step 3: Target Container Dockerfile** (~0.5 hour)
- [ ] Create `containers/targets/ubuntu/Dockerfile`
- [ ] Install all required tools
- [ ] Create fake data files
- [ ] Set environment variables
- [ ] Test build locally: `docker build -t sandtrap-target-ubuntu:latest containers/targets/ubuntu/`
- [ ] Verify image size is reasonable (<500MB)
- [ ] Test container starts: `docker run -it --rm sandtrap-target-ubuntu:latest`

**Step 4: Integration with Main** (~1 hour)
- [ ] Update `src/sandtrap/__main__.py`
- [ ] Import Docker client and ContainerPool
- [ ] Initialize Docker client with config
- [ ] Initialize container pool at startup
- [ ] Add graceful shutdown for pool
- [ ] Handle Docker connection errors
- [ ] Log Docker version and connection info

**Step 5: Integration with SSH Backend** (~0.5 hour)
- [ ] Update `src/sandtrap/server/asyncssh_backend.py`
- [ ] Add `container_pool` attribute
- [ ] Add `set_container_pool()` method
- [ ] Pass pool reference to session objects
- [ ] Add logging for pool registration

**Step 6: Manual Testing** (~1 hour)
- [ ] Build target container image
- [ ] Start SandTrap application
- [ ] Verify pool initialization (check logs)
- [ ] Verify containers created: `docker ps -a | grep sandtrap`
- [ ] Check container names follow pattern
- [ ] Verify security constraints: `docker inspect <container_id>`
- [ ] Stop application and verify graceful shutdown
- [ ] Verify containers stopped (not removed)

**Step 7: Documentation Updates** (~0.5 hour)
- [ ] Update README.md with Phase 3 completion
- [ ] Update implementation plan memory
- [ ] Create Phase 3 completion notes
- [ ] Document any issues or learnings

---

## Success Criteria

Phase 3 is complete when:

1. ✅ `ContainerPool` class fully implemented and tested
2. ✅ Security configuration builder working correctly
3. ✅ Target Ubuntu Dockerfile builds successfully
4. ✅ Pool initializes N containers at startup
5. ✅ Containers created with all security constraints
6. ✅ Container naming follows session-based pattern
7. ✅ Allocation/release cycle works correctly
8. ✅ Replacement spawn happens in background
9. ✅ Stopped containers tracked for forensics
10. ✅ Graceful shutdown stops all containers
11. ✅ All Docker errors handled with logging
12. ✅ Integration with SSH backend complete
13. ✅ Manual testing passes all scenarios

---

## Known Limitations & Future Work

### Current Limitations (MVP):
- No automated cleanup of stopped containers (deferred to Phase 7)
- Single target image only (multi-image in Post-MVP)
- No container health checks
- No metrics/monitoring of pool state
- No persistent tracking across restarts

### Future Enhancements (Post-MVP):
- Automated cleanup task for old containers
- Multiple target images with weighted selection
- Container health monitoring
- Pool metrics (allocation rate, spawn time, etc.)
- Persistent container metadata storage
- Dynamic pool sizing based on load
- Container reuse (stop/restart instead of new)

---

## Risk Mitigation

### Technical Risks:

**Risk**: Docker daemon not available  
**Mitigation**: Fail fast at startup, clear error message, check in initialization

**Risk**: Slow container spawn affects performance  
**Mitigation**: Pre-warmed pool, background replacement, on-demand fallback

**Risk**: Memory exhaustion from too many containers  
**Mitigation**: Configurable pool size, resource limits per container

**Risk**: Container escape vulnerability  
**Mitigation**: Multi-layer security (Phase 7 will add more), network isolation

**Risk**: Disk space exhaustion from stopped containers  
**Mitigation**: Document manual cleanup, plan automated cleanup for Phase 7

### Development Risks:

**Risk**: Docker API complexity  
**Mitigation**: Use high-level docker-py SDK, reference Phase 1 research

**Risk**: Race conditions in pool management  
**Mitigation**: Use asyncio.Lock for all pool operations

**Risk**: Incorrect security constraints  
**Mitigation**: Manual inspection of created containers, security review in Phase 7

---

## Dependencies

### Required for Phase 3:
- ✅ Phase 1 complete (project structure)
- ✅ Phase 2 complete (SSH server)
- ✅ Docker installed on host
- ✅ docker-py SDK in requirements.txt
- ✅ Python 3.14 with asyncio support
- ✅ Configuration system (config.py)

### Will Enable:
- Phase 4: Command Proxying (needs container to proxy to)
- Phase 5: Session Recording (needs session with container)
- Phase 7: Security Hardening (security constraints ready)

---

## File Summary

**New Files** (3):
1. `src/sandtrap/container/security.py` (~80-100 lines)
2. `src/sandtrap/container/pool.py` (~250-300 lines)
3. `containers/targets/ubuntu/Dockerfile` (~30 lines)

**Modified Files** (2):
1. `src/sandtrap/__main__.py` (~30-40 lines changed)
2. `src/sandtrap/server/asyncssh_backend.py` (~10-15 lines changed)

**Total New Code**: ~400-450 lines  
**Total Modified Code**: ~40-55 lines  
**Total Effort**: 6-8 hours (as estimated)

---

## Next Steps After Phase 3

Once Phase 3 is complete:

1. **Phase 4**: Implement I/O proxy between SSH sessions and containers
2. **Manual Testing**: Actually connect via SSH and see container allocation
3. **Verify**: Container isolation, security constraints, resource limits
4. **Document**: Any issues or improvements discovered

---

## Design Specification Status

✅ **COMPLETE AND APPROVED**  
Ready for implementation when user confirms to proceed.

All design decisions documented and agreed upon.
Implementation plan detailed with clear success criteria.

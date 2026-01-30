# Hermes Phase 1 - Research Findings

## AsyncSSH Library

**Library**: asyncssh (ronf/asyncssh)
**Documentation**: High quality, 133 code snippets, benchmark score 79.1

### Key Capabilities for Hermes

#### 1. Custom Authentication
- Subclass `asyncssh.SSHServer` to implement custom auth logic
- Override `begin_auth()`, `password_auth_supported()`, `validate_password()`
- Support for both password and public key authentication
- Can track failed authentication attempts per connection

#### 2. Server Implementation Pattern
```python
class MySSHServer(asyncssh.SSHServer):
    def connection_made(self, conn):
        # Called when connection is established
        
    def begin_auth(self, username):
        # Return False to skip auth (accept-all mode)
        
    def password_auth_supported(self):
        return True
        
    def validate_password(self, username, password):
        # Custom validation logic
        # Return True to accept, False to reject
```

#### 3. PTY Session Handling
- `asyncssh.listen()` accepts `process_factory` parameter for handling sessions
- `process_factory` receives `asyncssh.SSHServerProcess` object
- Process object provides:
  - `process.stdin`, `process.stdout`, `process.stderr` for I/O
  - `process.get_extra_info('username')` for connection metadata
  - `process.channel` for channel-specific info
  - `process.exit(code)` to close session

#### 4. Session Management
- Override `session_requested()` method to customize session setup
- Can return custom `SSHServerSession` objects for advanced control
- Terminal size and type can be configured: `term_size=(rows, cols)`, `term_type='xterm'`

### Implementation Notes for MVP

1. **Modular Backend Interface**: Create abstract class with methods like:
   - `start_server(host, port, config)`
   - `authenticate(username, password, failed_attempts)`
   - `handle_session(session_id, container)`
   
2. **AsyncSSH Backend**: Implement the interface using asyncssh
   - Store failed attempt counter per connection in `connection_made()`
   - Use `begin_auth()` to check if should skip to accept-all mode
   - Use `process_factory` to bridge SSH session to Docker container

3. **PTY Forwarding**: 
   - AsyncSSH handles PTY on SSH side automatically
   - Need to forward to Docker exec with tty=True
   - Terminal resize events available via session callbacks

---

## Docker SDK for Python

**Library**: docker (docker-py)
**Documentation**: Multiple high-quality sources, extensive examples

### Key Capabilities for Hermes

#### 1. Container Creation with Security Constraints
```python
client = docker.from_env()
container = client.containers.create(
    image='hermes-target:latest',
    detach=True,
    # Network isolation
    network_mode='none',
    # Resource limits
    mem_limit='256m',
    cpu_quota=50000,  # 0.5 CPU (50000/100000)
    cpu_period=100000,
    # Security options
    security_opt=[
        'no-new-privileges:true',
        'seccomp=default'
    ],
    cap_drop=['ALL'],
    cap_add=['CHOWN', 'SETUID', 'SETGID'],
    read_only=False,  # Need write for attacker
    tmpfs={'/tmp': 'size=50m'},
    pids_limit=100
)
```

#### 2. Container Lifecycle Management
```python
# Start container
container.start()

# Stop container (preserves disk state)
container.stop(timeout=10)

# Remove container (deletes disk state)
container.remove(force=True)

# Get container by ID or name
container = client.containers.get('container_id')

# List all containers
containers = client.containers.list(all=True)
```

#### 3. Exec with PTY Support
```python
# Create exec instance
exec_instance = client.api.exec_create(
    container.id,
    cmd='/bin/bash',
    stdin=True,
    stdout=True,
    stderr=True,
    tty=True,  # Allocate PTY
    privileged=False,
    user='root'
)

# Start exec and get socket for bidirectional I/O
exec_socket = client.api.exec_start(
    exec_instance['Id'],
    detach=False,
    tty=True,
    socket=True  # Returns socket object for streaming
)

# Socket is a file-like object that can be read/written
# This is key for proxying SSH I/O to Docker
```

#### 4. Container Pool Management Strategy
```python
class ContainerPool:
    def __init__(self, client, pool_size=3):
        self.client = client
        self.pool_size = pool_size
        self.ready = []  # Ready containers
        self.active = {}  # session_id -> container
        self.stopped = []  # Stopped for forensics
        
    async def initialize(self):
        # Create initial pool
        for _ in range(self.pool_size):
            container = self._create_container()
            container.start()
            self.ready.append(container)
            
    async def allocate(self, session_id):
        if self.ready:
            container = self.ready.pop()
        else:
            # Fallback: create on demand
            container = self._create_container()
            container.start()
        
        self.active[session_id] = container
        # Spawn replacement in background
        asyncio.create_task(self._spawn_replacement())
        return container
        
    async def release(self, session_id):
        container = self.active.pop(session_id)
        container.stop()
        self.stopped.append(container)
```

### Security Constraints Implementation

All container security options should be in a centralized config:

```python
CONTAINER_SECURITY_CONFIG = {
    'network_mode': 'none',
    'mem_limit': '256m',
    'cpu_quota': 50000,
    'cpu_period': 100000,
    'security_opt': [
        'no-new-privileges:true',
        'seccomp=default'
    ],
    'cap_drop': ['ALL'],
    'cap_add': ['CHOWN', 'SETUID', 'SETGID'],
    'read_only': False,
    'tmpfs': {'/tmp': 'size=50m'},
    'pids_limit': 100,
    'stop_timeout': 10
}
```

---

## Docker Socket Proxy

**Source**: Tecnativa/docker-socket-proxy (GitHub)
**Technology**: HAProxy-based proxy for Docker socket

### Capabilities

#### What It Does
- Acts as a security proxy between applications and Docker socket
- Uses HAProxy to filter Docker API requests
- Returns HTTP 403 for blocked operations
- Environment variable based permission system

#### Supported Permissions (Environment Variables)
Each set to `0` (deny) or `1` (allow):

**Security Critical (Denied by default)**:
- `AUTH` - Authentication endpoints
- `SECRETS` - Docker secrets management
- `POST` - All POST/PUT/DELETE operations (write access)

**Operational (Allowed by default)**:
- `EVENTS` - Event stream
- `PING` - Health checks
- `VERSION` - Version info

**Container Management (Denied by default)**:
- `CONTAINERS` - Container listing/inspection
- `ALLOW_START` - containers/{id}/start
- `ALLOW_STOP` - containers/{id}/stop
- `ALLOW_RESTARTS` - containers/{id}/restart|kill
- `EXEC` - Container exec operations
- `IMAGES` - Image operations
- `VOLUMES` - Volume management
- `NETWORKS` - Network management

#### Usage for Hermes

**Required Permissions for MVP**:
```yaml
# docker-compose.yml example
docker-socket-proxy:
  image: tecnativa/docker-socket-proxy
  environment:
    - CONTAINERS=1    # Need to list/inspect
    - POST=1          # Need to create/start/stop
    - EXEC=1          # Need to exec commands
    - IMAGES=1        # Need to pull/inspect images
    - BUILD=0         # Don't need building
    - SECRETS=0       # Don't need secrets
    - SWARM=0         # Don't need swarm
    - VOLUMES=0       # Don't need volumes (using tmpfs)
    - NETWORKS=0      # Don't need networks (network_mode=none)
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
  ports:
    - 127.0.0.1:2375:2375
```

**Hermes connects to proxy instead of socket**:
```python
# Instead of:
client = docker.from_env()

# Use:
client = docker.DockerClient(base_url='tcp://docker-socket-proxy:2375')
```

### Decision for MVP

**Recommendation**: Start WITHOUT socket proxy for MVP, add in Phase 8 (Containerization)

**Reasoning**:
1. MVP is already on dedicated/isolated machine
2. Adds complexity during development
3. Still need privileged access for container creation
4. Better to perfect core functionality first
5. Can add as security hardening step

**Post-MVP**: Implement socket proxy with minimal permissions
- Reduces attack surface if Hermes is compromised
- Provides audit trail of Docker API calls
- Defense in depth strategy

---

## Project Structure Design

Based on research, recommended structure:

```
sandtrap/
├── src/
│   └── hermes/
│       ├── __init__.py
│       ├── __main__.py           # Entry point
│       ├── config.py              # Config parser
│       │
│       ├── server/                # SSH server components
│       │   ├── __init__.py
│       │   ├── backend.py         # Abstract SSH backend interface
│       │   ├── asyncssh_backend.py  # AsyncSSH implementation
│       │   └── auth.py            # Authentication manager
│       │
│       ├── container/             # Docker container management
│       │   ├── __init__.py
│       │   ├── pool.py            # Container pool manager
│       │   └── security.py        # Security constraints config
│       │
│       ├── session/               # Session handling
│       │   ├── __init__.py
│       │   ├── proxy.py           # I/O proxy (SSH <-> Docker)
│       │   └── recorder.py        # Asciinema recorder
│       │
│       └── utils/
│           ├── __init__.py
│           └── logging.py         # Structured logging
│
├── containers/                     # Container images
│   └── target/
│       └── Dockerfile             # Target container image
│
├── config/
│   └── config.example.yaml        # Example config
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── Dockerfile                      # Hermes honeypot container
├── docker-compose.yml              # Deployment
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── README.md
└── SECURITY.md
```

---

## Next Steps for Phase 1

1. ✅ Research completed for asyncssh, docker-py, and socket proxy
2. Create project structure with proper files
3. Design modular SSH backend interface
4. Set up initial configuration schema
5. Create placeholder implementations to validate architecture

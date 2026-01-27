# SandTrap Project Specifications

## Project Configuration

### Location
- **Project path**: `~/code/sandtrap/`
- **Full path**: `/home/luke/code/sandtrap/`

### Python Version
- **Target**: Python 3.14 (latest)
- **Minimum**: Python 3.12+ (for compatibility testing)

### Container Images

#### SandTrap Honeypot Container
- **Base image**: Alpine Linux (latest stable)
- **Rationale**: Minimal size, security-focused, efficient for honeypot host
- **Requirements**:
  - Python 3.14 runtime
  - Docker client/socket access
  - SSH server libraries (asyncssh)
  - Minimal attack surface

#### Target Container Images (Configurable)
- **Configuration**: User can specify different base images per deployment
- **Default images to support**:
  1. **ubuntu:latest** - Most common attacker target
  2. **alpine:latest** - Lightweight option
  3. **debian:latest** - Alternative popular target
  4. **centos:stream9** - Enterprise target simulation
  
- **Configuration format** (in YAML):
  ```yaml
  container_pool:
    images:
      - name: "ubuntu:latest"
        weight: 50  # 50% of containers
      - name: "alpine:latest"
        weight: 30  # 30% of containers
      - name: "debian:latest"
        weight: 20  # 20% of containers
  ```

- **Image customization**:
  - Each image can have custom Dockerfile in `containers/targets/`
  - Pre-installed tools configurable per image
  - Fake data seeding options
  - Environment variables

### MVP Target Image
- **Initial implementation**: Single configurable image
- **Default**: `ubuntu:22.04` (most realistic for attackers)
- **Tools included**: bash, coreutils, vim, curl, wget, netcat, python3
- **Post-MVP**: Multiple image profiles and weighted selection

---

## Directory Structure

```
~/code/sandtrap/
├── src/
│   └── sandtrap/
│       ├── __init__.py
│       ├── __main__.py                 # Entry point
│       ├── config.py                   # Config parser & validation
│       │
│       ├── server/                     # SSH server components
│       │   ├── __init__.py
│       │   ├── backend.py              # Abstract SSH backend interface
│       │   ├── asyncssh_backend.py     # AsyncSSH implementation
│       │   └── auth.py                 # Authentication manager
│       │
│       ├── container/                  # Docker container management
│       │   ├── __init__.py
│       │   ├── pool.py                 # Container pool manager
│       │   ├── security.py             # Security constraints config
│       │   └── image_manager.py        # Image selection & management
│       │
│       ├── session/                    # Session handling
│       │   ├── __init__.py
│       │   ├── proxy.py                # I/O proxy (SSH <-> Docker)
│       │   └── recorder.py             # Asciinema recorder
│       │
│       └── utils/
│           ├── __init__.py
│           └── logging.py              # Structured logging
│
├── containers/                          # Container image definitions
│   ├── honeypot/
│   │   └── Dockerfile                  # SandTrap honeypot (Alpine-based)
│   │
│   └── targets/                        # Target container images
│       ├── ubuntu/
│       │   ├── Dockerfile
│       │   └── entrypoint.sh
│       ├── alpine/
│       │   ├── Dockerfile
│       │   └── entrypoint.sh
│       ├── debian/
│       │   └── Dockerfile
│       └── README.md                   # Guide for adding custom images
│
├── config/
│   ├── config.example.yaml             # Full example config
│   └── config.minimal.yaml             # Minimal working config
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Pytest fixtures
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_pool.py
│   │   ├── test_config.py
│   │   └── test_recorder.py
│   └── integration/
│       ├── test_ssh_session.py
│       └── test_container_lifecycle.py
│
├── docs/
│   ├── architecture.md                 # System architecture
│   ├── configuration.md                # Config reference
│   ├── deployment.md                   # Deployment guide
│   └── development.md                  # Development guide
│
├── scripts/
│   ├── generate_ssh_keys.sh            # SSH host key generation
│   ├── build_images.sh                 # Build all container images
│   └── cleanup.sh                      # Clean up stopped containers
│
├── data/                                # Runtime data (gitignored)
│   ├── keys/                           # SSH host keys
│   ├── recordings/                     # Session recordings
│   ├── logs/                           # Application logs
│   └── containers/                     # Container metadata
│
├── .gitignore
├── .dockerignore
├── README.md
├── SECURITY.md
├── CHANGELOG.md
├── LICENSE
│
├── Dockerfile                           # SandTrap honeypot container
├── docker-compose.yml                   # Easy deployment
├── docker-compose.dev.yml               # Development environment
│
├── pyproject.toml                       # Modern Python project config
├── requirements.txt                     # Production dependencies
├── requirements-dev.txt                 # Development dependencies
└── pytest.ini                           # Pytest configuration
```

---

## Configuration Schema Design

### Main Configuration File (config.yaml)

```yaml
# SandTrap Configuration
# See config.example.yaml for full documentation

server:
  # SSH server settings
  host: "0.0.0.0"
  port: 2222
  host_key_path: "/data/keys/ssh_host_rsa_key"
  
  # Connection limits
  max_concurrent_sessions: 10
  session_timeout: 3600  # seconds

authentication:
  # Static credential list
  static_credentials:
    - username: "root"
      password: "toor"
    - username: "admin"
      password: "admin"
    - username: "admin"
      password: "admin123"
    - username: "user"
      password: "user"
  
  # Accept-all mode after N failures
  accept_all_after_failures: 3

container_pool:
  # Pool configuration
  size: 3
  spawn_timeout: 30  # seconds to wait for container spawn
  
  # Target container image configuration
  # MVP: Single image, Post-MVP: Multiple with weights
  image: "sandtrap-target-ubuntu:latest"
  
  # Future: Multiple images with weighted selection
  # images:
  #   - name: "sandtrap-target-ubuntu:latest"
  #     weight: 50
  #   - name: "sandtrap-target-alpine:latest"
  #     weight: 30

  # Container lifecycle
  max_session_duration: 3600  # seconds
  cleanup_stopped_after_days: 7
  
  # Container security constraints
  security:
    network_mode: "none"
    memory_limit: "256m"
    cpu_quota: 0.5  # 0.5 CPU cores
    pids_limit: 100
    tmpfs_size: "50m"
    
    capabilities:
      drop: ["ALL"]
      add: ["CHOWN", "SETUID", "SETGID"]
    
    security_opt:
      - "no-new-privileges:true"
      - "seccomp=default"

recording:
  enabled: true
  output_dir: "/data/recordings"
  format: "asciinema"  # v2 format
  
  # Metadata to capture
  capture_metadata:
    - connection_info
    - authentication_attempts
    - session_duration
    - container_id
    - commands_executed

logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  format: "json"  # json or text
  output_dir: "/data/logs"
  
  # Structured logging fields
  include_fields:
    - timestamp
    - session_id
    - username
    - source_ip
    - event_type

# Docker connection
docker:
  # MVP: Direct socket connection
  socket_path: "/var/run/docker.sock"
  
  # Post-MVP: Socket proxy
  # base_url: "tcp://docker-socket-proxy:2375"
  # socket_proxy:
  #   enabled: false
  #   host: "docker-socket-proxy"
  #   port: 2375
```

---

## Python Dependencies

### Production (requirements.txt)
```
asyncssh>=2.14.0
docker>=7.0.0
pyyaml>=6.0
pydantic>=2.5.0  # For config validation
```

### Development (requirements-dev.txt)
```
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-docker>=2.0.0
pytest-cov>=4.1.0
black>=23.0.0
ruff>=0.1.0
mypy>=1.7.0
pre-commit>=3.5.0
```

---

## Image Build Strategy

### SandTrap Honeypot (Alpine-based)

**Dockerfile** (`containers/honeypot/Dockerfile`):
```dockerfile
FROM alpine:latest

# Install Python 3.14 (when available) or latest
RUN apk add --no-cache \
    python3 \
    py3-pip \
    docker-cli \
    && python3 --version

# Create app user (non-root when possible)
RUN addgroup -g 1000 sandtrap && \
    adduser -D -u 1000 -G sandtrap sandtrap

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directories
RUN mkdir -p /data/keys /data/recordings /data/logs && \
    chown -R sandtrap:sandtrap /data

# Expose SSH port
EXPOSE 2222

# Run as sandtrap user (if Docker socket permissions allow)
# USER sandtrap

ENTRYPOINT ["python3", "-m", "sandtrap"]
```

### Target Container (Ubuntu-based - MVP)

**Dockerfile** (`containers/targets/ubuntu/Dockerfile`):
```dockerfile
FROM ubuntu:22.04

# Install common tools attackers expect
RUN apt-get update && apt-get install -y \
    bash \
    coreutils \
    vim \
    nano \
    curl \
    wget \
    netcat-traditional \
    python3 \
    python3-pip \
    openssh-client \
    net-tools \
    iputils-ping \
    dnsutils \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create fake "interesting" files for attackers
RUN mkdir -p /var/log /etc/config /home/user
RUN echo "export DB_PASSWORD=not_a_real_password" > /etc/config/app.env
RUN echo "Admin credentials in /etc/shadow" > /var/log/setup.log

# Set up a convincing environment
ENV HOSTNAME=prod-web-01
ENV USER=root

# Start bash by default (will be overridden by exec)
CMD ["/bin/bash"]
```

---

## Development Workflow

### Initial Setup
1. Create project structure at `~/code/sandtrap/`
2. Initialize git repository
3. Set up Python virtual environment (venv) with Python 3.14
4. Install dependencies
5. Generate SSH host keys
6. Build container images

### Development Cycle
1. Write code in `src/sandtrap/`
2. Run tests with pytest
3. Build and test locally with docker-compose.dev.yml
4. Iterate and refine

### Testing Strategy
- **Unit tests**: Test individual components (auth, pool, config)
- **Integration tests**: Test full SSH flow with real containers
- **Security tests**: Test escape attempts, injection, resource limits
- **Performance tests**: Concurrent sessions, container spawn time

---

## Security Considerations

### Network Architecture Clarification

**Two Separate Network Contexts**:

1. **SandTrap Honeypot Container** (SSH Server)
   - Network: ENABLED (bridge or host mode)
   - Port 2222: EXPOSED to internet/network
   - Needs network to accept incoming SSH connections
   - Has Docker socket access to manage target containers

2. **Target Containers** (Attacker Sandboxes)
   - Network: DISABLED (`network_mode: none`)
   - Completely isolated from network
   - Attackers' commands run here but cannot access network
   - Network commands fail realistically (curl, ping, wget, etc.)

**Attacker Flow**:
```
Attacker → SandTrap (network enabled) → I/O Proxy → Target Container (network disabled)
```

**Result**: Attackers get shell access but cannot:
- Download malware from C2 servers
- Perform lateral movement
- Exfiltrate data
- Scan networks

### Container Escape Prevention
1. **No privileged containers**
2. **Drop all capabilities** except minimal required
3. **Network isolation** (network_mode=none)
4. **Resource limits** enforced
5. **Read-only rootfs** where possible (MVP: read-write for realism)
6. **Seccomp and AppArmor** profiles active

### Input Validation
1. **No direct string interpolation** into Docker API calls
2. **Validate all user inputs** (usernames, passwords, commands)
3. **Sanitize container IDs** before operations
4. **Rate limiting** on connections and auth attempts

### Logging & Monitoring
1. **Structured JSON logging** for easy parsing
2. **Session recordings** in standard format (asciinema)
3. **Container forensics** via stopped container preservation
4. **Audit trail** of all Docker API operations

---

## MVP Feature Checklist

### Phase 1: Setup ✓ (Research Complete)
- [x] Research asyncssh capabilities
- [x] Research Docker SDK capabilities  
- [x] Research Docker socket proxy
- [ ] Create project structure
- [ ] Set up Python packaging
- [ ] Design SSH backend interface

### Phase 2: Core SSH Server
- [ ] Modular SSH backend interface
- [ ] AsyncSSH backend implementation
- [ ] Static credential authentication
- [ ] Accept-all after N failures
- [ ] PTY session handling

### Phase 3: Container Management
- [ ] Container pool manager
- [ ] Ubuntu target container image
- [ ] Pool initialization
- [ ] Session allocation
- [ ] Container stop on disconnect
- [ ] Automatic pool replenishment

### Phase 4: Command Proxying
- [ ] Docker exec integration
- [ ] Bidirectional I/O streaming
- [ ] Terminal resize handling

### Phase 5: Recording
- [ ] Asciinema v2 recorder
- [ ] Local filesystem storage
- [ ] Structured JSON logging
- [ ] Container ID linking

### Phase 6: Configuration
- [ ] YAML schema design
- [ ] Config parser with validation
- [ ] Example configuration files

### Phase 7: Security Hardening
- [ ] Resource limits implementation
- [ ] Security constraints (caps, seccomp)
- [ ] Network isolation
- [ ] Session timeouts
- [ ] Input validation

### Phase 8: Deployment
- [ ] SandTrap Dockerfile (Alpine)
- [ ] docker-compose.yml
- [ ] Volume mount documentation
- [ ] Socket proxy evaluation

### Phase 9: Testing
- [ ] Unit tests
- [ ] Integration tests
- [ ] Auth flow tests
- [ ] Recording validation tests

### Phase 10: Documentation
- [ ] README.md
- [ ] SECURITY.md
- [ ] Configuration guide
- [ ] Deployment guide

---

## Post-MVP Roadmap

### Phase 11: Multi-Image Support
- [ ] Image manager component
- [ ] Weighted image selection
- [ ] Multiple target Dockerfiles
- [ ] Dynamic image rotation

### Phase 12: Enhanced Recording
- [ ] SFTP/SCP file transfer recording
- [ ] File upload capture and storage
- [ ] Malware analysis integration

### Phase 13: Analysis Tools
- [ ] Session replay CLI tool
- [ ] Search and filter interface
- [ ] Pattern detection
- [ ] Threat intelligence integration

### Phase 14: Advanced Security
- [ ] Docker socket proxy integration
- [ ] Network honeypot mode
- [ ] Advanced input validation
- [ ] Real-time alerting

---

## Success Criteria for MVP

1. **Functional**: Accept SSH connections and proxy to containers
2. **Secure**: All security constraints properly applied
3. **Performant**: Sub-second container allocation from pool
4. **Recorded**: All sessions saved in asciinema format
5. **Configurable**: Easy YAML configuration
6. **Deployable**: Single docker-compose up command
7. **Forensic**: Stopped containers preserved for analysis
8. **Documented**: Clear setup and deployment instructions

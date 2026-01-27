# SandTrap 🪤

**SSH Honeypot with Docker Container Sandboxing**

SandTrap is a security research tool that accepts SSH connections from attackers and proxies them to isolated Docker containers. It captures all commands, session recordings, and attacker behavior while protecting the host system through multiple layers of security.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ⚠️ Status: Alpha / Work in Progress

This project is currently in active development. Not all features are implemented yet.

## Features

- **SSH Honeypot**: Convincing SSH server that accepts attacker connections
- **Container Sandboxing**: Each session runs in an isolated Docker container
- **Container Pooling**: Pre-warmed containers for fast response times
- **Configurable Authentication**: Static credentials + accept-all fallback mode
- **Session Recording**: Full session recordings in asciinema format
- **Security Hardening**: Multi-layer protection (network isolation, resource limits, capability dropping)
- **Forensic Analysis**: Stopped containers preserved for post-analysis

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Attacker                                                 │
└───────────────────┬─────────────────────────────────────┘
                    │ SSH Connection (port 2222)
                    ▼
┌─────────────────────────────────────────────────────────┐
│ SandTrap Container (Alpine + Python)                    │
│ ├─ Network: ENABLED                                     │
│ ├─ SSH Server (asyncssh)                                │
│ ├─ Authentication Manager                               │
│ ├─ Container Pool Manager                               │
│ └─ Session Recorder                                     │
└───────────────────┬─────────────────────────────────────┘
                    │ Docker Socket
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Target Containers (Ubuntu 22.04)                        │
│ ├─ Network: DISABLED (network_mode=none)                │
│ ├─ Resource Limits: 256MB RAM, 0.5 CPU                  │
│ ├─ Security: Capabilities dropped, seccomp enabled      │
│ └─ State: Stopped after session (preserved)             │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12 or higher (for local development)
- At least 2GB RAM and 10GB disk space

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/sandtrap.git
cd sandtrap

# Copy example configuration
cp config/config.example.yaml config/config.yaml

# Edit configuration as needed
nano config/config.yaml

# Build container images (TODO: implement build script)
# ./scripts/build_images.sh

# Start SandTrap
# docker-compose up -d
```

### Development Setup

```bash
# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Install in editable mode
pip install -e .

# Run tests
pytest

# Run locally (for development)
python -m sandtrap --config config/config.yaml
```

## Configuration

SandTrap is configured via YAML. See [config/config.example.yaml](config/config.example.yaml) for a fully documented configuration file.

Key configuration sections:

- **server**: SSH server host, port, and connection limits
- **authentication**: Static credentials and accept-all mode
- **container_pool**: Pool size, container image, security constraints
- **recording**: Session recording settings
- **logging**: Application logging configuration
- **docker**: Docker socket or API connection

## Security Considerations

### Deployment

**⚠️ WARNING**: This tool is designed to interact with malicious actors. Deploy with extreme caution.

- Run on a **dedicated, isolated machine**
- Use a **separate network segment** (DMZ)
- **Monitor for container escapes** and kernel exploits
- **Do not run** on machines with sensitive data
- **Keep Docker and kernel updated** for latest security patches

### Multi-Layer Security

SandTrap implements defense-in-depth:

1. **Network Isolation**: Target containers have `network_mode: none`
2. **Resource Limits**: CPU, memory, and process limits enforced
3. **Capability Dropping**: All Linux capabilities dropped except minimal required
4. **Seccomp/AppArmor**: Security profiles active
5. **Read-Only Root**: (Planned) Read-only root filesystem
6. **Session Timeouts**: Automatic session termination

### Known Limitations

- Container escape exploits may still be possible (kernel vulnerabilities)
- Docker socket access gives SandTrap root-equivalent permissions
- Stopped containers accumulate disk space (configure cleanup)

See [SECURITY.md](SECURITY.md) (coming soon) for detailed security documentation.

## Project Structure

```
sandtrap/
├── src/sandtrap/          # Python source code
│   ├── server/            # SSH server implementation
│   ├── container/         # Docker container management
│   ├── session/           # Session handling and recording
│   └── utils/             # Utilities and logging
├── containers/            # Container image definitions
│   ├── honeypot/          # SandTrap honeypot (Alpine)
│   └── targets/           # Target containers (Ubuntu, etc.)
├── config/                # Configuration files
├── tests/                 # Unit and integration tests
├── docs/                  # Documentation
└── scripts/               # Helper scripts
```

## Roadmap

### MVP (Current Phase)

- [x] Project setup and planning
- [ ] Core SSH server with asyncssh
- [ ] Container pool management
- [ ] Command proxying (SSH ↔ Docker)
- [ ] Session recording (asciinema format)
- [ ] Configuration system
- [ ] Security hardening
- [ ] Deployment (Docker Compose)
- [ ] Testing suite
- [ ] Documentation

### Post-MVP

- [ ] Multi-image support (weighted selection)
- [ ] SFTP/SCP file transfer recording
- [ ] Session replay CLI tool
- [ ] Docker socket proxy integration
- [ ] Advanced authentication (honeytokens, public key capture)
- [ ] Metrics and monitoring endpoints
- [ ] Real-time alerting
- [ ] Network honeypot mode (limited outbound with logging)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) (coming soon) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is for **security research and educational purposes only**. The authors are not responsible for any misuse or damage caused by this software. Always obtain proper authorization before deploying honeypots on networks you do not own or have explicit permission to test.

## Acknowledgments

- Built with [AsyncSSH](https://github.com/ronf/asyncssh)
- Container management via [Docker SDK for Python](https://github.com/docker/docker-py)
- Session recording format: [asciinema](https://asciinema.org/)

---

**SandTrap** - Trapping attackers in sandboxes since 2026

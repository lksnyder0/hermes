# SandTrap - AI Assistant Instructions

**SSH Honeypot with Docker Container Sandboxing**

Repository: https://github.com/lksnyder0/sandtrap

---

## Getting Started

**REQUIRED**: Before working on this project, read these memory files for full context:
1. `.serena/memories/sandtrap-mvp-implementation-plan.md` - 10-phase implementation roadmap with current status
2. `.serena/memories/sandtrap-project-specifications.md` - Complete project specifications and technical decisions

These files contain complete project specifications, architectural decisions, and implementation details.

---

## Project Status

### MVP Progress (Current Phase + Next 2)

- [x] **Phase 3: Container Pool Management** (COMPLETE)
  - [x] Container pool manager with eager initialization
  - [x] Security configuration builder
  - [x] Ubuntu 22.04 target container with fake files
  - [x] Security constraints verified (network isolation, resource limits, capabilities)

- [ ] **Phase 4: Command Proxying** (CURRENT - Ready to Start)
  - [ ] I/O proxy implementation (`src/sandtrap/session/proxy.py`)
  - [ ] Docker exec integration with PTY support
  - [ ] Bidirectional streaming (SSH ↔ Docker exec socket)
  - [ ] Terminal resize event handling
  - [ ] Session handler integration

- [ ] **Phase 5: Session Recording** (NEXT)
  - [ ] Asciinema v2 recorder implementation
  - [ ] Local filesystem storage
  - [ ] Structured JSON logging
  - [ ] Link recordings to container IDs

---

## Session Context

**Previous Session Summary**: 
Phase 3 complete - Implemented container pool manager with eager initialization (0.24s for 3 containers), security configuration builder, Ubuntu 22.04 target container with convincing fake files, and verified all security constraints (network isolation, resource limits, dropped capabilities, seccomp). All code committed and pushed to GitHub.

**Current State**:
- ✅ SSH server accepts connections on port 2223
- ✅ Authentication works (static credentials + accept-all fallback)
- ✅ Container pool initializes and manages containers
- ✅ All security constraints applied and verified
- ❌ SSH sessions don't proxy to containers yet (Phase 4)
- ❌ No shell access in containers yet
- ❌ Session recording not implemented (Phase 5)

---

## Development Workflow (ENFORCED)

### Phase 1: PLANNING (Read-Only)
**When to use**: Research, design, architecture decisions, code exploration

**Mode setting**: Use `switch_modes` tool with modes: `["planning", "one-shot", "no-onboarding"]`

**Allowed activities**:
- Read files and search codebase
- Analyze existing implementations
- Research APIs and libraries
- Create detailed plans and specifications
- Ask clarifying questions

**FORBIDDEN**:
- Any file edits or modifications
- Running tests or builds
- Git commits or pushes
- System configuration changes

### Phase 2: EXECUTION (Implementation)
**When to use**: After user approves the plan from Planning phase

**Mode setting**: Use `switch_modes` tool with modes: `["editing", "interactive", "no-onboarding"]`

**Activities**:
- Implement code changes
- Write/update tests
- Run tests and verify functionality
- Create git commits (when user requests)
- Update documentation

**Transition rule**: Only switch to EXECUTION after user explicitly approves your plan.

---

## Project-Specific Guidelines

### Python Style
- **PEP 8 compliance** required
- **Type hints** for all function signatures
- **Docstrings** for all public functions and classes
- **Async/await patterns** (project uses asyncssh and asyncio)
- **Error handling** with proper logging

### Security Focus
**Security**: This is a honeypot dealing with attackers. See README.md security section for deployment warnings. During development, always verify security constraints after changes.

**Development requirements**:
- Always verify security constraints after container changes
- Never bypass security measures during testing
- Document all security decisions and trade-offs
- Run security verification before commits (`docker inspect <container>`)
- Use isolated test infrastructure (never production systems)

### Performance Considerations
- Container pool optimization (target: <1 second allocation)
- Memory-efficient implementations
- Async operations for I/O-bound tasks
- Avoid blocking calls in async contexts

### Testing Requirements
- Unit tests for new functionality
- Security constraint verification tests
- Integration tests for full SSH→Container flows
- Manual testing checklist before phase completion

---

## Key Commands

### Development
```bash
# Navigate to project
cd /home/luke/code/sandtrap

# Activate virtual environment
source venv/bin/activate

# Run SandTrap (from src/ directory)
cd src
python -m sandtrap --config ../config/config.test.yaml

# Run tests
pytest

# Run tests with coverage
pytest --cov=sandtrap
```

### Docker Operations
```bash
# Build target container
docker buildx build -t sandtrap-target-ubuntu:latest containers/targets/ubuntu/

# Verify security constraints
docker inspect <container-id>

# Cleanup test containers
docker ps -a --filter "name=sandtrap-target" --format "{{.ID}}" | xargs -r docker rm -f

# View container logs
docker logs <container-id>
```

### Git Workflow
```bash
# Check status
git status

# View recent commits
git log --oneline -5

# Create commit (only when user requests)
git add <files>
git commit -m "Phase N complete: Brief description"
git push origin main
```

---

## Important Technical Notes

### Docker SDK Quirks
- `container.stop()` does **NOT** take a timeout argument in current SDK
- Use `container.stop()` without arguments
- Seccomp: Don't specify `seccomp=default`, just omit it (Docker applies default automatically)

### Configuration
- **Use absolute paths** for SSH keys and configs (not relative paths)
- Example: `/home/luke/code/sandtrap/data/keys/ssh_host_rsa_key`
- Relative paths from project root don't work when running from `src/` directory

### Container Naming Convention
- Pattern: `sandtrap-target-{session_id[:8]}-{timestamp}`
- Example: `sandtrap-target-a3f2b1c9-20260127-143022`
- Links container directly to session for forensic analysis

### Virtual Environment
- Location: `/home/luke/code/sandtrap/venv`
- Python version: 3.14 (or 3.12+ as fallback)
- Dependencies: asyncssh, docker, pyyaml, pydantic, pytest

### Security Constraints (Must Verify After Changes)
- Network mode: `none` (complete isolation)
- Memory limit: 256MB (268435456 bytes)
- CPU quota: 0.5 cores (50000/100000)
- PIDs limit: 100 processes max
- Capabilities: ALL dropped, only CHOWN, SETUID, SETGID added
- Security options: `no-new-privileges:true`
- Seccomp: Default profile (automatically applied)

---

## Git Workflow

### Repository
- **Branch**: `main`
- **Remote**: `git@github.com:lksnyder0/sandtrap.git`
- **Current commits**: 3 commits (Phases 1-3 complete)

### Commit Message Style
**Format**: `Phase N complete: Brief description`

**Examples** (from existing commits):
- `Phase 2 complete: SSH server with authentication`
- `Phase 3 complete: Container pool management with security constraints`

**Guidelines**:
- Focus on what was accomplished, not implementation details
- Reference phase number for tracking
- Keep message concise (1 line preferred)
- Only commit when user explicitly requests

---

## Documentation Maintenance

### When to Update Documentation
- **README.md**: Update phase completion status in roadmap
- **Memory files**: Update at end of significant sessions
- **Code comments**: Add docstrings for new functions/classes
- **Config examples**: Update when adding new config options

### Memory File Updates
At end of session, consider updating:
- Session summary memory (create new or update existing)
- Implementation plan (if phases completed or timeline changed)
- Don't duplicate information - reference existing memories

---

## Quick Reference

### Project Structure
```
sandtrap/
├── src/sandtrap/          # Python source
│   ├── __main__.py        # Entry point
│   ├── config.py          # Configuration system
│   ├── server/            # SSH server (Phases 2)
│   ├── container/         # Docker management (Phase 3)
│   └── session/           # Proxying & recording (Phases 4-5)
├── containers/targets/    # Target container Dockerfiles
├── config/                # YAML configurations
├── tests/                 # Unit & integration tests
└── data/                  # Runtime data (keys, recordings, logs)
```

### Common Issues
- **Import errors**: Ensure virtual environment is activated
- **Docker errors**: Verify Docker daemon is running
- **Permission errors**: Check Docker socket permissions
- **SSH connection refused**: Verify port 2223 is not in use

---

## Additional Resources

- **Full specifications**: `.serena/memories/sandtrap-project-specifications.md`
- **Phase 1 research**: `.serena/memories/sandtrap-phase1-research-findings.md`
- **Phase 3 design**: `.serena/memories/sandtrap-phase3-design-specification.md`
- **Security verification**: `.serena/memories/sandtrap-security-verification-script-design.md`
- **Post-MVP features**: `.serena/memories/sandtrap-post-mvp-considerations.md`

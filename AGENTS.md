# Hermes - AI Assistant Instructions

**SSH Honeypot with Docker Container Sandboxing**

Repository: https://github.com/lksnyder0/hermes

---

## Getting Started

**REQUIRED**: Read these memory files for full project context:
1. `.serena/memories/hermes-progress.md` - Implementation roadmap and current status
2. `.serena/memories/hermes-project-specifications.md` - Project specifications and technical decisions

---

## MCP Server Tools

### Context7 - Documentation Lookup

**Purpose**: Access up-to-date documentation and code examples for programming libraries and frameworks.

**When to use**: Understanding library APIs, finding code examples, researching framework capabilities, checking API changes.

**Workflow**:
1. `mcp_context7_resolve-library-id` - Get library identifier
2. `mcp_context7_query-docs` - Query documentation with specific questions

**Limits**: Maximum 3 calls per question. Be specific in queries. Never include secrets.

### Serena - Code Navigation and File Operations

**Purpose**: Navigate codebases, read/edit files, search code, perform symbol-based operations.

**Key principle**: Instead of shell tools (`cat`, `sed`, `awk`, `grep`, `find`, `ls`), always consider if a Serena MCP tool is more appropriate first.

**Common operations**:
- **Navigation**: `list_dir`, `find_file`
- **Understanding code**: `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`
- **Searching**: `search_for_pattern`
- **Editing**: `replace_content`, `replace_symbol_body`, `insert_after_symbol`, `insert_before_symbol`, `rename_symbol`
- **Memory**: `list_memories`, `read_memory`, `write_memory`, `edit_memory`
- **Reflection**: `think_about_collected_information`, `think_about_task_adherence`, `think_about_whether_you_are_done`

**Workflow**: Start with `get_symbols_overview` when exploring new files. Use symbolic tools for precise code modifications. Call thinking tools at key decision points (after searches, before edits, when potentially done).

---



## Development Workflow

### Planning Phase (Read-Only)
**When**: Research, design, architecture decisions, code exploration

**Mode**: `switch_modes([\"planning\", \"one-shot\", \"no-onboarding\"])`

**Activities**: Read files, analyze code, research APIs, create plans, ask questions

**Forbidden**: File edits, tests, commits, configuration changes

### Execution Phase (Implementation)
**When**: After user approves plan

**Mode**: `switch_modes([\"editing\", \"interactive\", \"no-onboarding\"])`

**Activities**: Implement changes, write tests, verify functionality, create commits (when requested)

**Rule**: Only switch to execution after explicit user approval.

---

## Project Guidelines

### Python Style
- PEP 8 compliance, type hints, docstrings
- Async/await patterns (asyncssh, asyncio)
- Proper error handling and logging

### Security (Critical)
This is a honeypot dealing with attackers. Always verify security constraints after container changes. Never bypass security measures. See README.md for deployment warnings.

### Testing
Unit tests, security constraint verification, integration tests for SSH→Container flows

---

## Key Commands

```bash
# Run Hermes (from src/)
source ../venv/bin/activate
python -m hermes --config ../config/config.test.yaml

# Tests
pytest
pytest --cov=hermes

# Docker
docker buildx build -t hermes-target-ubuntu:latest containers/targets/ubuntu/
docker inspect <container-id>  # Verify security constraints

# Git (only when user requests)
git add <files>
git commit -m "Phase N complete: Brief description"
git push origin main
```

---

## Technical Notes

- **Docker SDK**: `container.stop()` takes no timeout argument; omit `seccomp=default` (Docker applies automatically)
- **Config paths**: Use absolute paths for SSH keys (not relative); project root != working directory
- **Container naming**: `hermes-target-{session_id[:8]}-{timestamp}`
- **Security constraints**: Network=none, 256MB RAM, 0.5 CPU, 100 PIDs, minimal capabilities (see memories for details)
- **Virtual env**: `/home/luke/code/hermes/venv`, Python 3.14+

---

## Git Workflow

**Repository**: `git@github.com:lksnyder0/hermes.git` (branch: `main`)

**Commit format**: `Phase N complete: Brief description`

**Guidelines**: Focus on accomplishments, reference phase number, concise messages, only commit when requested

---



## Project Structure

```
hermes/
├── src/hermes/          # Python source
│   ├── __main__.py        # Entry point
│   ├── config.py          # Configuration
│   ├── server/            # SSH server
│   ├── container/         # Docker management
│   └── session/           # Proxying & recording
├── containers/targets/    # Target Dockerfiles
├── config/                # YAML configs
├── tests/                 # Tests
└── data/                  # Runtime data
```

## Memory Files

Use `list_memories` and `read_memory` to access:
- Project specifications and MVP implementation plan
- Phase-specific design documents and research findings
- Security verification procedures
- Session summaries and todo lists
- Post-MVP considerations

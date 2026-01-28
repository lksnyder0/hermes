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

## MCP Server Tools

### Context7 - Documentation Lookup (ALWAYS USE FOR LIBRARY RESEARCH)

**Purpose**: Access up-to-date documentation and code examples for ANY programming library or framework.

**When to use Context7**:
- ✅ Understanding ANY programming language features (Python, JavaScript, Rust, etc.)
- ✅ Learning library APIs (asyncssh, docker-py, asyncio, pydantic, etc.)
- ✅ Finding code examples and best practices
- ✅ Researching framework capabilities (FastAPI, Flask, React, etc.)
- ✅ Understanding package-specific patterns and conventions
- ✅ Checking latest API changes or deprecations

**CRITICAL RULE**: When you need to understand how to use ANY library or programming language feature, you MUST use Context7 tools FIRST before attempting implementation or making assumptions.

**Available tools**:

1. **`mcp_context7_resolve-library-id`** - Find the correct library identifier
   - Call this FIRST to get the proper Context7 library ID
   - Example: `resolve-library-id("asyncssh", "How to handle PTY sessions in asyncssh")`
   - Returns: `/python/asyncssh` or similar identifier

2. **`mcp_context7_query-docs`** - Query library documentation
   - Use the library ID from resolve-library-id
   - Ask specific, detailed questions
   - Example: `query-docs("/python/asyncssh", "How to handle terminal resize events in PTY sessions")`

**Workflow example**:
```
1. Need to implement Docker exec with PTY support
2. Call resolve-library-id("docker-py", "Docker exec with PTY streaming")
3. Get library ID: "/docker/docker-py"
4. Call query-docs("/docker/docker-py", "How to create Docker exec with PTY and stream I/O bidirectionally")
5. Implement based on documentation
```

**Important limits**:
- Maximum 3 calls per question (plan your queries efficiently)
- Be specific in queries - "How to handle PTY in asyncssh sessions" (GOOD) vs "asyncssh" (BAD)
- Never include secrets or credentials in queries

---

### Serena - Code Navigation and File Operations (ALWAYS USE FOR FILE SYSTEM)

**Purpose**: Navigate codebases, read/edit files, search code, and perform symbol-based operations.

**CRITICAL RULE**: When interacting with the file system, you MUST use Serena tools instead of bash commands like `cat`, `sed`, `awk`, `find`, or `ls`.

#### Directory and File Navigation

**Use these instead of `ls` or `find`**:

1. **`mcp_serena_list_dir`** - List directory contents
   - Example: `list_dir(".", recursive=true)` for full project tree
   - Example: `list_dir("src/sandtrap", recursive=false)` for single level
   - Respects .gitignore by default

2. **`mcp_serena_find_file`** - Find files by pattern
   - Example: `find_file("*.py", "src")` finds all Python files
   - Example: `find_file("config*.yaml", "config")` finds config files
   - Uses wildcards: `*` (any chars), `?` (single char)

#### Reading Files

**Use this instead of `cat`, `head`, or `tail`**:

3. **`mcp_serena_get_symbols_overview`** - Get file structure overview
   - Shows classes, functions, methods at a glance
   - ALWAYS use this FIRST when exploring a new file
   - Example: `get_symbols_overview("src/sandtrap/container/pool.py", depth=1)`
   - Returns: Compact view of all symbols (classes, methods, functions)

#### Code Search

**Use these instead of `grep` or `rg`**:

4. **`mcp_serena_search_for_pattern`** - Search code by regex pattern
   - Example: `search_for_pattern("async def.*session", restrict_search_to_code_files=true)`
   - Supports context lines before/after matches
   - Can restrict to specific paths or file types

5. **`mcp_serena_find_symbol`** - Find code symbols (classes, functions, methods)
   - Example: `find_symbol("ContainerPool", include_body=false)` finds class definition
   - Example: `find_symbol("allocate", relative_path="src/sandtrap/container")` finds method
   - Supports substring matching: `find_symbol("get", substring_matching=true)` matches `getValue`, `getData`
   - Can retrieve symbol body and children (depth parameter)

6. **`mcp_serena_find_referencing_symbols`** - Find where symbols are used
   - Example: `find_referencing_symbols("allocate", "src/sandtrap/container/pool.py")`
   - Shows all places where a function/method is called

#### File Editing

**Use these instead of `sed`, `awk`, or manual editing**:

7. **`mcp_serena_replace_content`** - Replace file content
   - **Literal mode**: Exact string replacement
     ```
     replace_content("src/file.py", "old_text", "new_text", mode="literal")
     ```
   - **Regex mode**: Pattern-based replacement (PREFERRED for large changes)
     ```
     replace_content("src/file.py", "def old.*?end", "def new_function():\n    pass", mode="regex")
     ```
   - Use regex with `.*?` (non-greedy) to avoid over-matching
   - Set `allow_multiple_occurrences=true` to replace all matches

8. **`mcp_serena_replace_symbol_body`** - Replace entire symbol definition
   - Example: Replace a function body while keeping signature
   - Only use when you know the exact symbol structure

9. **`mcp_serena_insert_after_symbol`** - Insert code after a symbol
   - Example: Add new method after existing method in class
   - Example: Add new function after another function

10. **`mcp_serena_insert_before_symbol`** - Insert code before a symbol
    - Example: Add import statements before first function
    - Example: Add new class before existing class

11. **`mcp_serena_rename_symbol`** - Rename symbol throughout codebase
    - Renames in all files, handles all references
    - Example: `rename_symbol("old_name", "src/file.py", "new_name")`

#### Memory System

**Project knowledge persistence**:

12. **`mcp_serena_list_memories`** - List available memory files
13. **`mcp_serena_read_memory`** - Read project memory
14. **`mcp_serena_write_memory`** - Save project knowledge
15. **`mcp_serena_edit_memory`** - Update existing memory

**When to use memories**:
- At start of session: Read relevant memories for context
- During research: Document findings and decisions
- End of session: Update session summaries and progress

#### Thinking Tools (IMPORTANT)

**Use these at key decision points**:

16. **`mcp_serena_think_about_collected_information`** 
    - ALWAYS call after completing searches (find_symbol, search_for_pattern, read_file)
    - Helps organize and reflect on gathered information
    - Ensures you have sufficient context before proceeding

17. **`mcp_serena_think_about_task_adherence`**
    - ALWAYS call before making code changes
    - Ensures you're still on track with original task
    - Critical for long conversations

18. **`mcp_serena_think_about_whether_you_are_done`**
    - ALWAYS call when you believe task is complete
    - Final verification checklist

---

### Tool Selection Priority

When you need to perform an operation, follow this priority:

1. **Documentation/Library research** → Use Context7
2. **List directories** → Use `mcp_serena_list_dir` (NOT `ls`)
3. **Find files** → Use `mcp_serena_find_file` (NOT `find`)
4. **Read files** → Use `mcp_serena_get_symbols_overview` then Read tool (NOT `cat`)
5. **Search code** → Use `mcp_serena_search_for_pattern` or `mcp_serena_find_symbol` (NOT `grep`)
6. **Edit files** → Use `mcp_serena_replace_content` or symbol tools (NOT `sed`/`awk`)
7. **Terminal operations** (git, npm, docker, pytest) → Use Bash tool

**Example: Wrong approach ❌**
```bash
cat src/sandtrap/container/pool.py
grep "async def" src/sandtrap/**/*.py
sed -i 's/old/new/g' src/file.py
```

**Example: Correct approach ✅**
```
1. mcp_serena_get_symbols_overview("src/sandtrap/container/pool.py")
2. mcp_serena_search_for_pattern("async def", restrict_search_to_code_files=true)
3. mcp_serena_replace_content("src/file.py", "old", "new", mode="literal")
```

---

### Research Workflow Best Practices

**When starting work on a new feature:**

1. **Read Context**: Check relevant memory files first
   ```
   mcp_serena_list_memories()
   mcp_serena_read_memory("sandtrap-phase4-design")  # if exists
   ```

2. **Understand Codebase**: Use Serena for exploration
   ```
   mcp_serena_list_dir("src/sandtrap", recursive=true)
   mcp_serena_get_symbols_overview("src/sandtrap/main.py")
   mcp_serena_find_symbol("SessionHandler")
   ```

3. **Research Libraries**: Use Context7 for APIs
   ```
   mcp_context7_resolve-library-id("asyncssh", "PTY session handling")
   mcp_context7_query-docs("/python/asyncssh", "How to handle bidirectional I/O in PTY sessions")
   ```

4. **Reflect**: Think about collected information
   ```
   mcp_serena_think_about_collected_information()
   ```

5. **Plan**: Create detailed implementation plan

6. **Verify**: Before implementation
   ```
   mcp_serena_think_about_task_adherence()
   ```

---

### SandTrap-Specific Tool Usage Examples

#### Example 1: Implementing Phase 4 Command Proxying

**Step 1 - Research asyncssh PTY handling**:
```
mcp_context7_resolve-library-id("asyncssh", "PTY session handling and terminal I/O")
mcp_context7_query-docs("/python/asyncssh", "How to read stdin and write stdout in PTY sessions with proper async handling")
```

**Step 2 - Research Docker exec API**:
```
mcp_context7_resolve-library-id("docker-py", "Docker exec with PTY and streaming")
mcp_context7_query-docs("/docker/docker-py", "How to create exec instance with PTY and handle bidirectional socket streaming")
```

**Step 3 - Explore existing session code**:
```
mcp_serena_get_symbols_overview("src/sandtrap/server/asyncssh_backend.py", depth=1)
mcp_serena_find_symbol("SandTrapSSHSession", relative_path="src/sandtrap/server", include_body=false)
```

**Step 4 - Find container pool integration points**:
```
mcp_serena_find_symbol("allocate", relative_path="src/sandtrap/container/pool.py")
mcp_serena_find_referencing_symbols("allocate", "src/sandtrap/container/pool.py")
```

**Step 5 - Reflect and plan**:
```
mcp_serena_think_about_collected_information()
```

#### Example 2: Understanding Security Constraints

**Step 1 - Find security configuration code**:
```
mcp_serena_list_dir("src/sandtrap/container", recursive=false)
mcp_serena_get_symbols_overview("src/sandtrap/container/security.py")
```

**Step 2 - Research Docker security options**:
```
mcp_context7_resolve-library-id("docker-py", "Container security constraints")
mcp_context7_query-docs("/docker/docker-py", "How to set security_opt, capabilities, and resource limits when creating containers")
```

**Step 3 - Find where security is applied**:
```
mcp_serena_find_symbol("build_container_config", relative_path="src/sandtrap/container/security.py", include_body=true)
mcp_serena_find_referencing_symbols("build_container_config", "src/sandtrap/container/security.py")
```

#### Example 3: Adding New Configuration Options

**Step 1 - Understand current config structure**:
```
mcp_serena_get_symbols_overview("src/sandtrap/config.py", depth=1)
mcp_serena_find_symbol("ContainerPoolConfig", relative_path="src/sandtrap/config.py", include_body=true)
```

**Step 2 - Research Pydantic validation**:
```
mcp_context7_resolve-library-id("pydantic", "Config validation and field types")
mcp_context7_query-docs("/pydantic/pydantic", "How to add field validators and custom validation logic to Pydantic models")
```

**Step 3 - Find all config usage locations**:
```
mcp_serena_find_referencing_symbols("ContainerPoolConfig", "src/sandtrap/config.py")
```

**Step 4 - Update config with validation**:
```
mcp_serena_replace_symbol_body("ContainerPoolConfig", "src/sandtrap/config.py", "<new config class body>")
```

#### Example 4: Debugging Session Management

**Step 1 - Search for session-related code**:
```
mcp_serena_search_for_pattern("session_id", restrict_search_to_code_files=true, relative_path="src/sandtrap")
```

**Step 2 - Find session tracking implementation**:
```
mcp_serena_find_symbol("active_sessions", relative_path="src/sandtrap")
```

**Step 3 - Trace session lifecycle**:
```
mcp_serena_find_symbol("session_started", substring_matching=true)
mcp_serena_find_symbol("session_ended", substring_matching=true)
```

**Step 4 - Check asyncio patterns**:
```
mcp_context7_query-docs("/python/asyncio", "Best practices for managing concurrent session state in asyncio applications")
```

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

# SandTrap Security Verification Script Design

## Overview

**Purpose**: Active security testing script that attempts to break through security constraints rather than just checking configuration.

**Status**: Design deferred until end of project (after Phase 7 Security Hardening)  
**Location**: `scripts/verify_security.sh`  
**Estimated Time**: 1.5-2 hours  
**Created**: Jan 27, 2026

---

## Design Philosophy

Instead of passively checking Docker configuration with `docker inspect`, this script will:

1. **Create a dedicated test container** with full security constraints
2. **Actively attempt to break through each security layer**
3. **Verify that all breakout attempts fail as expected**
4. **Report results with clear pass/fail indicators**

---

## Test Categories

### 1. Network Isolation Tests (6 tests)

**Goal**: Verify complete network isolation

- [ ] `ping 8.8.8.8` - Should fail (no network)
- [ ] `curl https://google.com` - Should fail (no network)
- [ ] `wget http://example.com` - Should fail (no network)
- [ ] `nc -l 4444` - Should fail to bind (no network interface)
- [ ] Check `/sys/class/net/` - Should only have `lo` (loopback)
- [ ] DNS resolution `nslookup google.com` - Should fail (no network)

**Expected**: All operations fail with "network unreachable" or similar

---

### 2. Resource Limit Tests (3 tests)

**Goal**: Verify resource limits are enforced

**Memory Test (256MB limit)**:
```bash
docker exec <container> stress --vm 1 --vm-bytes 300M --timeout 10s
```
- Should be OOM killed (exit code 137 or 143)
- Container memory never exceeds 256MB

**CPU Test (0.5 core limit)**:
```bash
docker exec <container> /bin/bash -c 'while true; do :; done' &
docker stats --no-stream <container>
```
- CPU usage should max at ~50% (0.5 cores)
- Verify with `docker stats`

**PIDs Test (100 process limit)**:
```bash
docker exec <container> /bin/bash -c ':(){ :|:& };:'
docker exec <container> ps aux | wc -l
```
- Fork bomb should stop at 100 processes
- Should not crash host or other containers

---

### 3. Capability Tests (5 tests)

**Goal**: Verify capabilities are properly dropped

- [ ] `ping 127.0.0.1` - Requires CAP_NET_RAW (should fail)
- [ ] `insmod <module>` - Requires CAP_SYS_MODULE (should fail)
- [ ] `mount -t tmpfs test /mnt` - Requires CAP_SYS_ADMIN (should fail)
- [ ] `reboot` - Requires CAP_SYS_BOOT (should fail)
- [ ] Verify CHOWN works: `touch /tmp/test && chown nobody /tmp/test` (should succeed)

**Expected**: Only explicitly added capabilities work (CHOWN, SETUID, SETGID)

---

### 4. Privilege Escalation Tests (4 tests)

**Goal**: Verify no-new-privileges blocks escalation

- [ ] Try `sysctl -w kernel.hostname=hacked` - Should fail
- [ ] Try to write `/proc/sys/kernel/*` - Should fail (read-only)
- [ ] Try setuid binary: `chmod u+s /tmp/test && /tmp/test` - Should not escalate
- [ ] Try `docker` command inside container - Should fail (no Docker socket access)

**Expected**: All privilege escalation attempts blocked

---

### 5. Filesystem Tests (3 tests)

**Goal**: Verify filesystem constraints

**Tmpfs Test (/tmp with 50MB limit)**:
```bash
docker exec <container> dd if=/dev/zero of=/tmp/bigfile bs=1M count=60
```
- Should fail when tmpfs full (~50MB)
- Check: `docker exec <container> df -h /tmp`

**Rootfs Test** (read-write for realism):
```bash
docker exec <container> touch /root/test_write
```
- Should succeed (MVP uses read-write for realism)

**Host Filesystem Isolation**:
- Verify no access to host paths
- Verify no volume mounts to sensitive locations

---

### 6. Seccomp Profile Tests (3 tests)

**Goal**: Verify blocked syscalls

- [ ] `reboot` syscall - Should be blocked by seccomp
- [ ] `swapon` - Should be blocked
- [ ] `mount` - Should be blocked

**Expected**: Blocked syscalls fail with "Operation not permitted"

---

## Script Architecture

### Approach: Dedicated Test Container

**Rationale**:
- Safe: No impact on active honeypot sessions
- Comprehensive: Can run all destructive tests
- Repeatable: Same results every time
- CI/CD ready: Can be automated

**Process**:
1. Create test container with exact security config from `config.py`
2. Run each test in isolation via `docker exec`
3. Monitor results from outside container
4. Clean up test container after completion

**Example**:
```bash
# Create test container
TEST_CONTAINER=$(docker run -d \
    --name sandtrap-security-test \
    --network none \
    --memory 256m \
    --cpu-quota 50000 \
    --cpu-period 100000 \
    --pids-limit 100 \
    --cap-drop ALL \
    --cap-add CHOWN \
    --cap-add SETUID \
    --cap-add SETGID \
    --security-opt no-new-privileges:true \
    --security-opt seccomp=default \
    --tmpfs /tmp:size=50m \
    --label sandtrap.role=security-test \
    sandtrap-target-ubuntu:latest \
    sleep 300)

# Run tests (18 total)
section "Network Isolation Tests"
test_ping "$TEST_CONTAINER"
test_curl "$TEST_CONTAINER"
# ... more tests

section "Resource Limit Tests"
test_memory_limit "$TEST_CONTAINER"
# ... more tests

# Cleanup
docker rm -f "$TEST_CONTAINER"
```

---

## Script Structure

```bash
#!/bin/bash
# SandTrap Security Verification Script
# Actively tests security constraints through breakout attempts
# Usage: ./scripts/verify_security.sh [options]
# Options:
#   --container <id>   Test specific container
#   --all             Test all sandtrap containers
#   --verbose         Show detailed output
#   --no-cleanup      Don't remove test container

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() { echo -e "${GREEN}✓${NC} $1"; ((PASSED++)); }
fail() { echo -e "${RED}✗${NC} $1"; ((FAILED++)); }
warn() { echo -e "${YELLOW}⚠${NC} $1"; ((WARNINGS++)); }
section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Test functions
test_network_isolation() { ... }
test_resource_limits() { ... }
test_capabilities() { ... }
test_privilege_escalation() { ... }
test_filesystem() { ... }
test_seccomp() { ... }

# Main execution
main() {
    # Parse arguments
    # Check dependencies (docker, jq, stress)
    # Create test container
    # Run all tests
    # Print summary
    # Cleanup
    # Exit with appropriate code
}

# Cleanup trap
trap cleanup EXIT

main "$@"
```

---

## Design Decisions (To Be Finalized)

### 1. Test Scope
**Options**:
- A: Test all sandtrap containers (finds by label)
- B: Test specific container (passed as argument)
- C: Both (default all, or specific if provided)

**Recommendation**: Option C for maximum flexibility

### 2. Dependencies
**Required**:
- `docker` - Container management
- `jq` - JSON parsing for docker inspect
- `stress` or `stress-ng` - Memory/CPU stress testing (optional, could use bash loops)

**Approach**: Check for dependencies, fail gracefully with clear message if missing

### 3. Test Timeout
Each test should have timeout to prevent hangs:
- Individual test: 10 seconds
- Total script: 120 seconds
- Use `timeout` command wrapper

### 4. Failure Threshold
**Question**: Should script exit with error if:
- A: ANY test fails (strict)
- B: Only critical tests fail (network, resource limits)
- C: Configurable via flag

**Recommendation**: Option A (strict) - all security constraints must hold

### 5. Logging
**Options**:
- A: Stdout only (simple)
- B: Stdout + log file (persistent record)
- C: Structured JSON output (CI/CD friendly)

**Recommendation**: Start with A (stdout), add B/C in future

### 6. CI/CD Integration
Design for future automation:
- Exit codes: 0 = all pass, 1 = any fail
- Optional JSON output mode
- Silent mode for non-interactive runs
- Could integrate into Phase 9 testing

---

## Success Criteria

Script is complete when:

1. ✅ Creates dedicated test container with full security config
2. ✅ Runs all 18+ security tests
3. ✅ Properly detects pass/fail for each test
4. ✅ Provides clear colored output
5. ✅ Cleans up test container on exit
6. ✅ Exits with appropriate error code
7. ✅ Handles errors gracefully (missing dependencies, Docker down, etc.)
8. ✅ Documented with usage examples
9. ✅ Tested on both running and stopped containers

---

## When to Implement

**Recommended Phase**: After Phase 7 (Security Hardening)

**Rationale**:
- Phase 7 finalizes all security constraints
- Phase 7 may add additional hardening (AppArmor, read-only rootfs, etc.)
- Script can test complete security posture
- Can be part of Phase 7 verification
- Useful for Phase 9 (Testing) automation

**Alternative**: Could implement basic version in Phase 3, enhance in Phase 7

---

## Integration Points

### Phase 3 (Current):
- Manual verification of containers created
- Basic `docker inspect` checks
- Defer active testing to Phase 7

### Phase 7 (Security Hardening):
- Implement full security verification script
- Test all hardening measures
- Document any findings
- Fix any issues discovered

### Phase 9 (Testing):
- Integrate into automated test suite
- Run in CI/CD pipeline
- Part of pre-deployment checks

---

## Future Enhancements

**Post-MVP**:
- Add container escape attempt tests (exploit patterns)
- Test kernel vulnerability protections
- Benchmark performance impact of security constraints
- Test Docker socket proxy (when implemented)
- Test multiple target images
- Add network honeypot mode tests (limited outbound)
- Integration with malware analysis tools

---

## Open Questions (To Resolve Before Implementation)

1. Should we test active containers or always create dedicated test container?
2. What timeout values are appropriate for each test?
3. Should we log results to file or stdout only?
4. Exit code strategy: strict (any fail) or tiered (critical only)?
5. Should we add a `--fix` mode that attempts to correct issues?
6. Integration with monitoring/alerting systems?

---

## File Location

**Path**: `scripts/verify_security.sh`  
**Permissions**: `chmod +x` (executable)  
**Dependencies**: Listed in script header  
**Documentation**: Usage in script comments + README section

---

## Related Documentation

- Phase 3 Design: Container security configuration
- Phase 7 Plan: Security hardening measures
- Phase 9 Plan: Testing strategy
- Security considerations in project specs

---

## Status

📋 **DESIGN COMPLETE - DEFERRED TO PHASE 7**

This design is ready for implementation when Phase 7 (Security Hardening) is reached. The script will validate all security constraints through active testing.

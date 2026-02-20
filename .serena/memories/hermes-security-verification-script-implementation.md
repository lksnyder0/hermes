# Hermes Security Verification Script Implementation

Based on the project analysis, I'm implementing the security verification script that was designed for Phase 7 but has been deferred until now. This script will perform active tests to verify that the security constraints defined for containers are properly enforced.

## Key Security Constraints from Configuration:
1. Network mode: "none" (no network access)
2. Memory limit: "256m"
3. CPU quota: 0.5 cores 
4. PIDs limit: 100
5. Tmpfs size for /tmp: "50m"
6. Capabilities: Drop ALL, add CHOWN, SETUID, SETGID
7. Security options: "no-new-privileges:true"
8. Docker default seccomp profile (blocks ~44 dangerous syscalls)
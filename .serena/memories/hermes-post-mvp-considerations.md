# Hermes Post-MVP Considerations

## Security & Operational Considerations (Deferred from MVP)

### Resource Exhaustion & Limits
**Context**: Attackers could DoS by opening many sessions, filling disks, or exhausting CPU/memory.

**Questions to address**:
- Specific limits for max concurrent sessions (currently planned: 10)
- Per-container disk usage limits
- Global disk usage monitoring and alerts
- CPU/memory limits tuning based on real-world usage

**Current MVP approach**:
- Max sessions limit in config
- Per-container resource limits (256MB memory, 0.5 CPU)
- Session timeouts (1 hour default)

---

### Data Retention & Storage Management
**Context**: Stopped containers accumulate rapidly (1GB × 100 sessions = 100GB).

**Questions to address**:
- Should we compress/archive old containers automatically?
- Maximum storage limit before refusing new sessions?
- Automated cleanup strategy beyond simple age-based deletion
- Export to external storage (S3, archive server)?

**Current MVP approach**:
- Configurable cleanup after N days (default: 7)
- Simple age-based deletion

**Possible enhancements**:
- Compress stopped containers (tar.gz or docker export)
- Tiered storage (hot/warm/cold)
- Automatic export to object storage
- Storage usage monitoring and alerts

---

### Network Isolation Strategy
**Context**: Trade-off between security and realism.

**Current MVP approach**: `network_mode: 'none'` (complete isolation)

**Options to consider post-MVP**:
1. **No network** (most secure, less realistic) ← MVP choice
2. **Firewalled network** - Allow limited outbound, log all attempts
   - Could reveal C2 servers, download URLs, lateral movement attempts
   - Requires careful firewall rules and logging
3. **Fake internet** - Respond to common requests with fake data
   - Extremely complex to implement
   - Could reveal more attacker intent
4. **Honeypot network** - Connect to other honeypot services
   - Create fake "internal network" to explore
   - Reveals lateral movement techniques

**Questions to address**:
- What attacker behaviors are we most interested in capturing?
- Is network traffic analysis valuable enough to justify the risk?
- Should we create fake services on an isolated network segment?

---

### Docker Socket Security
**Context**: Mounting `/var/run/docker.sock` gives root-equivalent access to host.

**Research needed**: Docker socket proxy capabilities and limitations

**Options**:
1. **Direct socket mount** (current assumption)
   - Simplest implementation
   - Highest risk if Hermes is compromised
   
2. **Docker socket proxy** (e.g., Tecnativa/docker-socket-proxy)
   - Limits API access to only required operations
   - Need to research: Does it support all operations we need?
   - Operations needed: container create/start/stop/exec
   
3. **Least-privilege alternatives**
   - Run Hermes as non-root user (Docker group membership)
   - Use Docker API authorization plugins
   - Consider rootless Docker

**Action items**:
- Research docker-socket-proxy capabilities
- Identify minimum required Docker API permissions
- Evaluate if proxy supports exec streaming
- Document security trade-offs of each approach

---

## Feature Enhancements (Post-MVP)

### Authentication Methods
- Honeytokens (specific passwords trigger high-priority alerts)
- Public key authentication (capture attacker SSH keys)
- Time-based rotating passwords (correlate with deployment timing)
- Geographic-aware authentication (different creds for different regions)

### File Transfer Support
- SFTP server implementation
- SCP support
- Record all uploaded/downloaded files
- Malware analysis integration for uploaded files

### Analysis & Monitoring Tools
- Session replay CLI tool (asciinema player wrapper)
- Search and filter recorded sessions
- Pattern detection (common exploit tools, scripts)
- Metrics and monitoring (Prometheus endpoints)
- Real-time alerting (webhook notifications)

### Container Images
- Multiple OS profiles (Ubuntu, CentOS, Alpine, Debian)
- Application-specific images (web server, database, etc.)
- Configurable installed tools and software
- Fake data seeding (files, databases, etc.)

### Advanced Features
- Session clustering (identify same attacker across sessions)
- Automatic malware extraction and sandboxing
- Integration with threat intelligence platforms
- Machine learning for anomaly detection

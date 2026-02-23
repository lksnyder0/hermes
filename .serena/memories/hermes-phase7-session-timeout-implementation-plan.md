# Phase 7: Session Timeout Implementation Plan

## Overview
Session time monitoring and auto-termination to prevent resource exhaustion from long-running sessions.

## Problem Statement
Configuration defines `session_timeout` (default 3600s) but enforcement code is missing. Sessions can run indefinitely until explicit disconnection.

## Current State
- Config schema: ✅ Defined (`config.py:24`)
- Config integration: ✅ Available in `server/backend.py:46` (`self.config.session_timeout`)
- Enforcement: ❌ Missing (no code that checks/times out sessions)
- Cleanup: ✅ Graceful shutdown on disconnect (`session/proxy.py:69, 209`)

## Target Implementation

### 1. Session Timeout Handler in Container Session Handler
**Location**: `__main__.py:71-160` (`container_session_handler`)

**Required Changes**:
```python
async def container_session_handler(
    session_info: SessionInfo,
    pty_request: PTYRequest,
    process: object,
    container_pool: ContainerPool,
    recording_config=None,
) -> None:
    container = None
    proxy = None
    recorder = None
    timeout_task = None  # NEW
    start_time = datetime.utcnow()  # NEW

    try:
        # Allocate container
        container = await container_pool.allocate(session_info.session_id)

        # Create recorder
        if recording_config:
            recorder = SessionRecorder(...)

        # Create proxy
        proxy = ContainerProxy(...)

        # Start proxy
        await proxy.start()

        # NEW: Setup session timeout monitoring
        timeout_seconds = session_info.config.session_timeout

        # Track timeout separately for cleanup
        timeout_expired = asyncio.Event()

        async def timeout_monitor():
            """Monitor session duration and trigger cleanup on timeout."""
            logger.info(f"Session timeout set to {timeout_seconds}s for {session_info.session_id}")
            await asyncio.sleep(timeout_seconds)
            timeout_expired.set()
            logger.warning(f"Session {session_info.session_id} timeout expired, initiating cleanup")

        timeout_task = asyncio.create_task(timeout_monitor())

        # NEW: Wait for completion with timeout
        wait_task = asyncio.create_task(proxy.wait_completion())
        done, pending = await asyncio.wait(
            {wait_task, timeout_expired},
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel unused tasks
        for task in pending:
            task.cancel()

        # Handle timeout expiration
        if timeout_expired.is_set():
            logger.info(f"Session {session_info.session_id} timed out, releasing container")
            try:
                error_msg = b"\r\nSession timeout - connection closed\r\n"
                process.stdin.write(error_msg)
                process.stdin.drain()
            except Exception:
                pass

    except Exception as e:
        logger.exception(f"Session error for {session_info.session_id}: {e}")

    finally:
        # NEW: Cancel timeout monitor
        if timeout_task:
            timeout_task.cancel()
            try:
                await timeout_task
            except asyncio.CancelledError:
                pass

        if proxy:
            await proxy.stop()

        if recorder:
            recorder.stop()
            recorder.write_metadata()

        if container:
            await container_pool.release(container)
            logger.info(f"Container released for {session_info.session_id}")
```

### 2. Timeout Tracking in SSH Server
**Location**: `server/asyncssh_backend.py` (HermesSSHServer class)

**Required Changes**:
```python
# Add to HermesSSHServer class
def auth_password_succeeded(self, username: str) -> None:
    """Called when authentication succeeds - reset timeout counter."""
    # Optional: Implement per-connection timeout state
    # This is primarily handled by session handler now
    pass
```

### 3. Update SessionInfo Dataclass
**Location**: `server/backend.py:16-25` (SessionInfo dataclass)

**Optional Enhancement**:
```python
@dataclass
class SessionInfo:
    session_id: str
    username: str
    source_ip: str
    source_port: int
    authenticated: bool = False
    failed_attempts: int = 0
    timeout_seconds: Optional[int] = None  # NEW: Configurable per session
```

## Implementation Steps

### Step 1: Modify session handler timeout logic
- Add `timeout_seconds` from config
- Create `timeout_monitor()` async coroutine
- Add timeout event (`timeout_expired`)
- Use `asyncio.wait()` with multiple futures
- Cancel timeout task in finally block

### Step 2: Update imports (if needed)
Add `datetime` import to `__main__.py`

### Step 3: Add comprehensive logging
Log when timeout starts, expires, and cleanup sequence

### Step 4: Add unit tests
Test that timeout cleanup releases container properly

### Step 5: Integration test
Verify timeout triggers correct cleanup flow

## Expected Behavior

### Normal disconnect (user closes SSH):
1. SSH disconnect → `_ssh_to_container()` exits → wait for completion
2. Session cleanup proceeds normally, releases container

### Timeout expiration:
1. 3600s elapse → `timeout_expired` event set
2. `asyncio.wait()` returns completed timeout task
3. Cancel `wait_task` (proxy completion)
4. Gracefully disconnect SSH (write timeout message)
5. Release container on timeout expiration

### Exception during session:
1. Any exception → proxy cleanup
2. `finally` block cancels timeout task
3. Container released safely

## Edge Cases

1. **Timeout during command execution**: Task is cancelled, command interrupted gracefully
2. **Rapid reconnection**: New session gets new container, timeout resets
3. **Container allocation timeout**: Handled by pool itself (asyncio.TimeoutError)
4. **Concurrent sessions**: Each has independent timeout task and event

## Benefits

1. **Resource protection**: Prevents unbounded memory/CPU usage
2. **Attack mitigation**: Limits reconnaissance window for attackers
3. **Pool replenishment**: Forced releases keep pool healthy
4. **Predictable behavior**: Known maximum session duration
5. **Security hygiene**: Reduces attack surface exposure time

## Backward Compatibility

✅ Fully backward compatible
- Timeout starts when session becomes active (proxy.start())
- Existing cleanup logic preserved
- Optional feature (timeout can be disabled by setting to large value)
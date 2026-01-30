# Phase 5: Session Recording — Implementation Plan

**Status**: Complete
**Branch**: main

---

## Goal

Record all SSH session I/O to asciicast v2 `.cast` files with JSON metadata sidecars, streamed to disk in real-time.

## Asciicast v2 Format

- **Line 1**: JSON header — `{"version": 2, "width": 80, "height": 24, "timestamp": <epoch>, "env": {...}}`
- **Subsequent lines**: Event tuples — `[elapsed_seconds, "o"|"i"|"r", "data"]`
  - `"o"` = output (container → client), `"i"` = input (client → container), `"r"` = resize (`"COLSxROWS"`)
- File extension: `.cast`, UTF-8, newline-delimited JSON

## Design Decisions

- **File I/O**: Synchronous `open()` + `write()` + `flush()` per event. No `aiofiles` dependency.
- **Error isolation**: Every public method catches all exceptions. Recording failure never kills the session.
- **Timestamps**: `time.monotonic()` for elapsed, `time.time()` for header epoch.
- **Binary data**: `data.decode("utf-8", errors="replace")` — lossy but safe.
- **Record both**: Input ("i") and output ("o") events captured. Asciinema player ignores "i" but forensic tooling uses them.
- **Output dir**: Uses `RecordingConfig.output_dir` as-is (defaults to `/data/recordings`, overridden in test config).

## Tasks

### Task 1: Create SessionRecorder unit tests ✅ COMPLETED

**File**: `tests/unit/test_session_recorder.py`

22 test cases across 5 classes:
- `TestSessionRecorderInit` (3): disabled config, no file creation, param storage
- `TestSessionRecorderStart` (8): dir creation, file creation, active flag, header version/dimensions/timestamp/metadata, permission error resilience
- `TestSessionRecorderEvents` (9): output/input/resize formats, elapsed time ordering, binary data replacement, no-ops when not started/disabled, event count, write error resilience
- `TestSessionRecorderStop` (5): inactive after stop, double stop, never-started stop, metadata JSON, disabled metadata
- `TestSessionRecorderFullLifecycle` (2): complete session with all event types parsed and validated, lifecycle with metadata sidecar

### Task 2: Create SessionRecorder implementation ✅ COMPLETED

**File to create**: `src/hermes/session/recorder.py`

```python
class SessionRecorder:
    __init__(config: RecordingConfig, session_id: str, width: int, height: int, metadata: dict | None)
    @property active -> bool        # True when file is open
    start() -> None                 # mkdir, open .cast, write JSON header
    record_input(data: bytes)       # [elapsed, "i", text]
    record_output(data: bytes)      # [elapsed, "o", text]
    record_resize(w: int, h: int)   # [elapsed, "r", "WxH"]
    stop() -> None                  # close file, safe to call multiple times
    write_metadata() -> None        # write .json sidecar
    _record_event(type: str, data: bytes)  # internal shared logic
```

Key internals:
- `_file`: open file handle (None when inactive)
- `_start_time`: `time.monotonic()` set at start
- `_event_count`: int counter
- Compact JSON with `separators=(",", ":")`

### Task 3: Integrate recorder into proxy and handler ✅ COMPLETED

**Files to modify**:

1. `src/hermes/session/proxy.py`:
   - `__init__`: Add optional `recorder: SessionRecorder | None = None` parameter
   - `_ssh_to_container`: After reading data + empty check, call `recorder.record_input(data)`
   - `_container_to_ssh`: After reading data + empty check, call `recorder.record_output(data)`
   - `handle_resize`: Call `recorder.record_resize(width, height)`
   - All guarded by `if self.recorder:`

2. `src/hermes/__main__.py`:
   - Import `SessionRecorder`
   - `container_session_handler`: Add `recording_config` parameter, create recorder after container allocation, call `start()`, pass to `ContainerProxy`, call `stop()` + `write_metadata()` in finally
   - `session_handler_with_pool` closure: Pass `config.recording`

3. `tests/unit/test_container_proxy.py`:
   - Test `recorder.record_input()` called during SSH→container flow
   - Test `recorder.record_output()` called during container→SSH flow
   - Test `recorder.record_resize()` called from `handle_resize`
   - Test proxy works normally when `recorder=None`

4. `tests/unit/test_session_handler.py`:
   - Update calls to include `recording_config`
   - Test recorder created/started during session
   - Test `stop()` + `write_metadata()` in finally block
   - Test recording failure doesn't prevent session

## Implementation Order

1. ✅ Write tests (`test_session_recorder.py`)
2. ✅ Create `recorder.py` → run recorder tests
3. ✅ Modify `proxy.py` → update proxy tests → run
4. ✅ Modify `__main__.py` → update handler tests → run
5. ✅ Full test suite pass

## Verification

```bash
pytest tests/unit/test_session_recorder.py -v
pytest tests/unit/test_container_proxy.py -v
pytest tests/unit/test_session_handler.py -v
pytest  # full suite
```

Optional manual test:
```bash
cd src && python -m hermes --config ../config/config.test.yaml --log-level DEBUG
# connect with: python scripts/test_connect.py
# check data/recordings/ for .cast and .json files
```

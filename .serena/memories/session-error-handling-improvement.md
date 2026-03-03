# Session Error Handling Improvement

## Problem Addressed
The original `container_session_handler` had a single broad `except Exception` block that always displayed "Session error - connection closed" regardless of where exactly the failure occurred in the session lifecycle.

## Solution Implemented
Modified `container_session_handler` in `src/hermes/__main__.py` to implement stage-specific exception handling:

1. **Container allocation failures** → "Container allocation failed - connection closed"
2. **Proxy initialization failures** → "Proxy initialization failed - connection closed"  
3. **Other generic failures** → "Session error - connection closed" (fallback)

## Key Changes
- Added `_stage` tracking variable to identify failure point in session lifecycle
- Implemented stage-specific error message logic based on the `_stage` variable
- Preserved all existing timeout functionality, cleanup processes, and logging

## Tests Verified
- All 13 tests in `test_session_handler.py` pass
- All 4 tests in `test_session_timeout_handler.py` pass  
- Error message behavior properly tested in unit tests
- Session timeout mechanism remains fully functional

This addresses the comment about misleading error messages where "Container allocation failed" was displayed even when failures occurred during proxy execution.
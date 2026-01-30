# Write Test Skill

Workflow for writing Python unit tests aligned with project conventions and established patterns.

## Core Principles

- Minimize mock boilerplate by using conftest fixtures
- Test behavior, not mock interactions; prefer realistic implementations
- One test verifies one behavior
- Include error cases alongside happy paths

## Getting Started

1. **Explore existing code**: Read the function/class being tested
   - Identify inputs, outputs, side effects, error cases
   - Check what's already tested: `grep -r "def test_" tests/`

2. **Check conftest.py**: Review available fixtures
   - Run: `pytest --fixtures tests/unit` to list all fixtures
   - Fixtures reduce mock setup boilerplate

3. **Run existing tests**: Understand current test organization
   - `pytest tests/unit/ -v`
   - Study similar test files for patterns

## Test Structure

```python
@pytest.mark.asyncio
async def test_behavior_description(self, fixture1, fixture2):
    """One sentence: what is being tested."""
    # Arrange
    obj = MyClass(fixture1, fixture2)
    
    # Act
    result = await obj.do_something()
    
    # Assert
    assert result == expected_value
```

## Naming

Use descriptive names that explain the scenario and outcome:
- `test_start_creates_exec_with_pty`
- `test_record_input_called_on_ssh_data`
- `test_handles_socket_error_gracefully`

Explore `tests/unit/` for naming patterns used across the codebase.

## Testing Async Code

- Use `@pytest.mark.asyncio` decorator
- Await all async calls
- Patches for asyncio: see `conftest.py` for examples

## Error Scenarios

Check if variant fixtures exist for error cases:
- `mock_process_eof` - simulates EOF
- `mock_container_exec_fails` - Docker exec failure
- `mock_recorder_start_fails` - recording startup failure

Create new fixtures in `conftest.py` if testing new error paths.

## Fixtures and Conftest

Fixtures used in 2+ tests belong in `tests/unit/conftest.py`. 

To add a fixture:
1. Read `conftest.py` to understand conventions
2. Add fixture following existing patterns
3. Document its purpose briefly
4. Run tests to verify

## Mock Patterns Worth Following

Look at existing tests for these patterns:
- Real state tracking (e.g., `SocketMock.blocking` instead of mock assertions)
- `side_effect` for multi-call scenarios
- `patch.object` for method-level patches
- `patch_handler_deps` fixture factory for repeated patch blocks

Explore `tests/unit/test_*.py` for examples.

## Debugging

- Run single test: `pytest tests/unit/test_file.py::TestClass::test_name -vvs`
- Examine mock calls: `print(mock_obj.call_args_list)`
- Verify mock setup: `print(dir(fixture))`

## Workflow

```bash
# Feature branch
git checkout -b test/<feature-name>

# Write and iterate
pytest tests/unit/ -q

# Commit
git commit -m "test: description of new tests"

# Push
git push -u origin test/<feature-name>
```

## Exploration Tools

- `pytest --fixtures tests/unit` - List available fixtures
- `grep -r "def test_" tests/unit/` - Find similar tests
- `grep -r "@pytest.fixture" tests/unit/` - Find fixture definitions
- `pytest tests/unit/test_file.py -v` - Run single test file

Review conftest.py, test files, and pytest documentation as needed.

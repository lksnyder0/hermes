# GitHub Actions Workflows

This directory contains CI/CD workflows for SandTrap.

## Workflows

### `tests.yml` - Test Pipeline

**Triggers**: Push to `main`/`develop`, and on all PRs

**What it does**:
1. Sets up Python 3.12+ environment
2. Installs project dependencies
3. Runs unit tests with coverage reporting
4. Runs mocked integration tests with coverage reporting
5. Enforces 80% code coverage threshold
6. Uploads coverage reports to Codecov
7. Comments on PR with test results

**Test execution**:
- Unit tests: ~750ms
- Mocked integration tests: ~530ms
- **Total**: ~1.3 seconds

**Coverage requirement**: Tests fail if overall coverage < 80%

**Example PR comment**:
```
## Test Results

✅ Coverage report generated

### Tests
- Unit tests: Run
- Integration tests (mocked): Run
- Coverage threshold: 80% minimum

[View full test output](...)
```

### `claude.yml` - Claude Code Integration

**Triggers**: Comments/reviews mentioning `@claude`

Allows Claude Code to assist with issues and PRs.

### `claude-code-review.yml` - Code Review

Automated code review workflow.

## Local Testing

Before pushing, run tests locally:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all unit tests
pytest tests/unit/ -v

# Run mocked integration tests
pytest tests/integration/test_auth_backend_integration.py \
        tests/integration/test_config_loading.py \
        tests/integration/test_container_pool_lifecycle.py \
        tests/integration/test_session_flow.py \
        -v

# Run with coverage
pytest tests/ --cov=hermes --cov-report=term-missing --cov-report=html

# Check coverage threshold
coverage report --fail-under=80
```

## What Gets Tested

### Unit Tests (94 tests)
- `server/auth.py`: Authentication logic
- `container/pool.py`: Container pool lifecycle
- `container/security.py`: Security configuration
- `config.py`: Configuration loading and validation

### Mocked Integration Tests (33 tests)
- Auth manager multi-connection flows
- Config loading with component wiring
- Container pool lifecycle with mocks
- Session handler end-to-end with mocks

### NOT Tested in CI
- Real Docker integration tests (require Docker daemon)
- SSH protocol tests (require actual SSH)
- Full honeypot operation

These can be run locally with: `pytest tests/integration/test_*_docker.py -v -m docker`

## Coverage Requirements

- **Minimum threshold**: 80%
- **Enforced by**: `coverage report --fail-under=80`
- **Reported to**: Codecov (if configured)

## Adding New Tests

1. Add tests to `tests/unit/` or `tests/integration/`
2. Mark with `@pytest.mark.unit` or `@pytest.mark.integration`
3. If using Docker, use `@pytest.mark.docker` and test locally first
4. Ensure new code maintains 80%+ coverage
5. Push to PR - pipeline will verify

## Troubleshooting

### Tests fail locally but pass in CI
- Ensure you're using Python 3.12+
- Run `pip install -e ".[dev]"` to get all dependencies
- Check for any `.pytest_cache` artifacts: `rm -rf .pytest_cache`

### Coverage below 80%
Run coverage locally to identify gaps:
```bash
pytest tests/ --cov=hermes --cov-report=term-missing
```

Look for lines marked with `0` and add tests for those code paths.

### Docker tests failing
See `TESTING.md` for Docker test setup:
```bash
docker build -f docker/Dockerfile -t hermes-target-ubuntu:latest docker/
docker container rm -f $(docker ps -aq --filter name=hermes)
pytest tests/integration/test_*_docker.py -v -m docker
```

## Customization

### Changing Python version
Edit `python-version` in `tests.yml`

### Changing coverage threshold
Edit `fail_under=80` in `tests.yml` and `pyproject.toml`

### Adding new test markers
1. Add to `pyproject.toml` under `[tool.pytest.ini_options]`
2. Use in tests: `@pytest.mark.your_marker`
3. Filter in CI: `pytest -m your_marker`

## Security

- No secrets stored in workflows
- All dependencies pinned in `pyproject.toml`
- Code review required before merge to main
- Coverage reports uploaded to Codecov (public)

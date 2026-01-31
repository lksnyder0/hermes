# Testing Hermes

This guide covers running the test suite, including unit tests, mocked integration tests, and real Docker integration tests.

## Test Organization

- **Unit tests** (`tests/unit/`): Fast, isolated tests with mocked dependencies. Run in CI pipelines. No external dependencies required.
- **Mocked integration tests** (`tests/integration/test_*.py` except Docker): Component interaction tests with Docker mocked. Run in CI pipelines. No external dependencies required.
- **Real Docker integration tests** (`tests/integration/test_*_docker.py`): End-to-end tests with real Docker containers. Run locally for verification. Requires Docker and `hermes-target-ubuntu:latest` image.

## Quick Start

### Run all tests (unit + mocked integration)

```bash
pytest tests/
```

### Run only unit tests

```bash
pytest tests/unit/ -v
```

### Run only mocked integration tests

```bash
pytest tests/integration/test_auth_backend_integration.py \
        tests/integration/test_config_loading.py \
        tests/integration/test_container_pool_lifecycle.py \
        tests/integration/test_session_flow.py -v
```

### Run with coverage report

```bash
pytest tests/ --cov=hermes --cov-report=term-missing --cov-report=html
```

This generates an HTML coverage report at `htmlcov/index.html`.

## Real Docker Integration Tests

These tests require:
1. Docker daemon running
2. `hermes-target-ubuntu:latest` image available

### Prerequisites

Build the target image:

```bash
docker build -f docker/Dockerfile -t hermes-target-ubuntu:latest docker/
```

Verify Docker is available:

```bash
docker ps
```

### Run all Docker integration tests

```bash
pytest tests/integration/test_*_docker.py -v -m docker
```

### Run specific Docker test file

```bash
# Container pool lifecycle with real Docker
pytest tests/integration/test_container_pool_docker.py -v -m docker

# Container proxy with real Docker
pytest tests/integration/test_container_proxy_docker.py -v -m docker

# Full end-to-end session tests
pytest tests/integration/test_full_session_docker.py -v -m docker
```

### Run Docker tests with output

```bash
# Show container creation/destruction
pytest tests/integration/test_*_docker.py -v -s -m docker

# Show timestamps for slow operations
pytest tests/integration/test_*_docker.py -v --durations=5 -m docker
```

## Test Coverage Thresholds

The test suite enforces a **minimum of 80% code coverage**. This is configured in `pyproject.toml`:

```
[tool.coverage.report]
fail_under = 80
```

If coverage falls below 80%, tests will fail.

## Running Tests in Different Environments

### CI Pipeline (GitHub Actions, etc.)

Run unit and mocked integration tests:

```bash
# No Docker required
pytest tests/unit/ tests/integration/test_auth_backend_integration.py \
        tests/integration/test_config_loading.py \
        tests/integration/test_container_pool_lifecycle.py \
        tests/integration/test_session_flow.py \
        --cov=hermes --cov-report=term-missing
```

### Local Laptop (with Docker)

Run everything including real Docker tests:

```bash
# Build the target image first
docker build -f docker/Dockerfile -t hermes-target-ubuntu:latest docker/

# Run all tests
pytest tests/ -v -m "not docker or docker" --cov=hermes

# Or run Docker tests separately
pytest tests/ -v --ignore=tests/integration/test_*_docker.py  # everything else
pytest tests/integration/test_*_docker.py -v -m docker       # Docker tests only
```

## Understanding Test Markers

Tests use pytest markers to control execution:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests (mocked)
pytest tests/integration/ -m "not docker"

# Run only Docker tests
pytest -m docker

# Run everything except slow tests
pytest -m "not slow"

# Run unit tests and Docker tests (skip mocked integration)
pytest -m "unit or docker"
```

## Test Structures

### Unit Tests

Example: `tests/unit/test_auth.py`

```python
def test_valid_credentials_accepted(self, auth: AuthenticationManager):
    assert auth.validate("conn1", "root", "toor") is True
```

- No external dependencies
- Fast execution (< 1s total)
- Fully isolated with mocks

### Mocked Integration Tests

Example: `tests/integration/test_container_pool_lifecycle.py`

```python
@pytest.mark.asyncio
async def test_full_lifecycle(self, config, client):
    pool = ContainerPool(client, config)
    await pool.initialize()
    # ...
```

- Docker client is mocked
- Tests component interaction
- Run in CI pipelines

### Real Docker Integration Tests

Example: `tests/integration/test_container_pool_docker.py`

```python
@pytest.mark.docker
@pytest.mark.asyncio
async def test_initialize_creates_real_containers(self, pool: ContainerPool):
    await pool.initialize()
    assert len(pool.ready_pool) == 2
    # Verify real Docker containers exist
```

- Uses real Docker containers
- Tests actual behavior
- Takes longer to run (5-30s per test)
- Skips gracefully if Docker unavailable

## Troubleshooting

### Tests skip with "Docker not available"

This is expected in CI environments. The tests are marked with `@pytest.mark.docker` and skip if Docker is unavailable.

To run on your laptop, ensure Docker is running:

```bash
docker ps
```

If Docker is installed but not running:

```bash
# macOS
open -a Docker

# Linux
sudo systemctl start docker

# Windows
# Start Docker Desktop from the application menu
```

### Image not found error

Build the target image:

```bash
docker build -f docker/Dockerfile -t hermes-target-ubuntu:latest docker/
```

### Tests hang or timeout

This may indicate Docker performance issues. Try:

1. Increase test timeout:
   ```bash
   pytest tests/integration/test_*_docker.py --timeout=60 -m docker
   ```

2. Check Docker resource limits:
   ```bash
   docker stats
   docker system df
   ```

3. Clean up old containers:
   ```bash
   docker container prune
   ```

### Coverage below 80%

Run coverage report to identify uncovered lines:

```bash
pytest tests/ --cov=hermes --cov-report=term-missing
```

Look for lines marked with `0` in the report and add tests for those code paths.

## Writing New Tests

### Adding a unit test

1. Create test in `tests/unit/test_*.py`
2. Use mocks for external dependencies
3. Keep execution time under 100ms

### Adding a mocked integration test

1. Create test in `tests/integration/test_*.py`
2. Mock external dependencies (Docker, network)
3. Test component interaction

### Adding a real Docker integration test

1. Create test in `tests/integration/test_*_docker.py`
2. Mark with `@pytest.mark.docker`
3. Use real Docker containers
4. Include cleanup in fixtures

Example:

```python
@pytest.mark.docker
@pytest.mark.asyncio
async def test_my_feature(self, docker_client, target_image):
    # Your test here
    pass
```

## Performance Notes

| Test Type | Count | Avg Time | Total |
|-----------|-------|----------|-------|
| Unit | 94 | 8ms | ~750ms |
| Mocked Integration | 26 | 20ms | ~520ms |
| Real Docker Integration | 15+ | 500ms-5s | 10-60s |

**Total**: ~1.3s for unit + mocked, 10-60s for Docker tests.

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run tests (no Docker)
  run: |
    pytest tests/unit/ \
            tests/integration/test_auth_backend_integration.py \
            tests/integration/test_config_loading.py \
            tests/integration/test_container_pool_lifecycle.py \
            tests/integration/test_session_flow.py \
            --cov=hermes

- name: Run Docker tests (optional)
  if: success()
  run: |
    docker build -f docker/Dockerfile -t hermes-target-ubuntu:latest docker/
    pytest tests/integration/test_*_docker.py -v -m docker
```

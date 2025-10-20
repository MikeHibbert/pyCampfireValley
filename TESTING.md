# CampfireValley Testing Guide

This guide provides comprehensive information about testing the CampfireValley project, including Phase 1 (core infrastructure) and Phase 2 (enterprise features).

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Phase 1 Tests](#phase-1-tests)
- [Phase 2 Tests](#phase-2-tests)
- [Integration Tests](#integration-tests)
- [Performance Tests](#performance-tests)
- [Test Configuration](#test-configuration)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)

## Overview

CampfireValley uses pytest as the primary testing framework with comprehensive test coverage across all components. The test suite includes:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Performance Tests**: Validate performance characteristics
- **End-to-End Tests**: Test complete workflows

## Test Structure

```
tests/
├── conftest.py                 # Pytest configuration and fixtures
├── test_key_manager.py         # Key management tests
├── test_redis_broker.py        # Redis MCP broker tests
├── test_torch.py              # Torch serialization tests
├── test_campfire.py           # Campfire tests
├── test_dock.py               # Dock tests
├── test_valley.py             # Valley tests
├── test_vali_services.py      # VALI services tests
├── test_justice_system.py     # Justice system tests
├── test_specialist_campfires.py # Specialist campfires tests
├── test_advanced_routing.py   # Advanced routing tests
├── test_monitoring.py         # Monitoring & logging tests
├── test_config_manager.py     # Configuration management tests
├── test_hierarchical_storage.py # Hierarchical storage tests
├── integration/               # Integration tests
│   ├── test_full_workflow.py
│   ├── test_phase1_integration.py
│   └── test_phase2_integration.py
├── performance/               # Performance tests
│   ├── test_throughput.py
│   ├── test_latency.py
│   └── test_scalability.py
└── fixtures/                  # Test data and fixtures
    ├── sample_configs/
    ├── test_data/
    └── mock_services/
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=campfirevalley --cov-report=html

# Run specific test file
pytest tests/test_campfire.py

# Run specific test function
pytest tests/test_campfire.py::test_campfire_creation

# Run tests matching pattern
pytest -k "test_monitoring"
```

### Test Categories

```bash
# Run only unit tests
pytest -m "unit"

# Run only integration tests
pytest -m "integration"

# Run only performance tests
pytest -m "performance"

# Run Phase 1 tests
pytest -m "phase1"

# Run Phase 2 tests
pytest -m "phase2"
```

### Parallel Test Execution

```bash
# Install pytest-xdist for parallel execution
pip install pytest-xdist

# Run tests in parallel
pytest -n auto

# Run with specific number of workers
pytest -n 4
```

## Test Categories

### Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.phase1` - Phase 1 component tests
- `@pytest.mark.phase2` - Phase 2 component tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.redis` - Tests requiring Redis
- `@pytest.mark.network` - Tests requiring network access

## Phase 1 Tests

### Core Infrastructure Components

#### Key Manager Tests (`test_key_manager.py`)
- Key generation and validation
- Encryption/decryption operations
- Key rotation and lifecycle management
- Security compliance verification

#### Redis MCP Broker Tests (`test_redis_broker.py`)
- Connection management
- Message publishing and subscription
- Channel operations
- Error handling and reconnection

#### Torch Serialization Tests (`test_torch.py`)
- Torch creation and serialization
- Attachment handling
- Metadata management
- Compression and decompression

#### Campfire Tests (`test_campfire.py`)
- Campfire lifecycle management
- Message processing
- Error handling
- Resource management

#### Dock Tests (`test_dock.py`)
- Gateway operations
- Torch routing
- Connection management
- Load balancing

#### Valley Tests (`test_valley.py`)
- Valley initialization
- Campfire orchestration
- Service discovery
- Health monitoring

## Phase 2 Tests

### Enterprise Features

#### VALI Services Tests (`test_vali_services.py`)
- Content validation
- Signature verification
- Security scanning
- Service integration

#### Justice System Tests (`test_justice_system.py`)
- Policy enforcement
- Violation detection
- Audit logging
- Access control

#### Specialist Campfires Tests (`test_specialist_campfires.py`)
- Sanitizer campfire functionality
- Validator campfire operations
- Router campfire logic
- Custom rule processing

#### Advanced Routing Tests (`test_advanced_routing.py`)
- Load balancing algorithms
- Health checking
- Failover mechanisms
- Performance optimization

#### Monitoring Tests (`test_monitoring.py`)
- Metrics collection
- Alert management
- Performance monitoring
- Log handling

#### Configuration Management Tests (`test_config_manager.py`)
- Configuration loading
- Validation and schema checking
- Environment-specific configs
- Dynamic updates

#### Hierarchical Storage Tests (`test_hierarchical_storage.py`)
- Multi-tier storage
- Data lifecycle management
- Compression and deduplication
- Storage optimization

## Integration Tests

### Full Workflow Tests

```python
# Example integration test
@pytest.mark.integration
async def test_complete_torch_workflow():
    """Test complete torch processing workflow."""
    # Setup valley with all services
    valley = await create_test_valley()
    
    # Create and send torch
    torch = create_test_torch()
    result = await valley.process_torch(torch)
    
    # Verify processing
    assert result.success
    assert result.processed_by_vali
    assert result.stored_hierarchically
```

### Component Integration Tests

- Valley + Campfire integration
- VALI + Justice system integration
- Monitoring + Configuration integration
- Storage + Routing integration

## Performance Tests

### Throughput Tests

```python
@pytest.mark.performance
async def test_torch_processing_throughput():
    """Test torch processing throughput."""
    valley = await create_performance_valley()
    
    # Process multiple torches concurrently
    torches = [create_test_torch() for _ in range(1000)]
    
    start_time = time.time()
    results = await asyncio.gather(*[
        valley.process_torch(torch) for torch in torches
    ])
    end_time = time.time()
    
    # Verify performance metrics
    throughput = len(torches) / (end_time - start_time)
    assert throughput > 100  # torches per second
```

### Latency Tests

```python
@pytest.mark.performance
async def test_torch_processing_latency():
    """Test torch processing latency."""
    valley = await create_performance_valley()
    torch = create_test_torch()
    
    # Measure processing latency
    start_time = time.time()
    result = await valley.process_torch(torch)
    latency = time.time() - start_time
    
    # Verify latency requirements
    assert latency < 0.1  # 100ms max latency
```

## Test Configuration

### Environment Variables

```bash
# Test environment configuration
export CAMPFIRE_TEST_MODE=true
export CAMPFIRE_LOG_LEVEL=DEBUG
export REDIS_TEST_URL=redis://localhost:6379/15
export TEST_DATA_PATH=./tests/fixtures/test_data
```

### Test Configuration File (`pytest.ini`)

```ini
[tool:pytest]
minversion = 6.0
addopts = 
    -ra
    --strict-markers
    --strict-config
    --cov=campfirevalley
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=90

testpaths = tests

markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    phase1: Phase 1 component tests
    phase2: Phase 2 component tests
    slow: Slow-running tests
    redis: Tests requiring Redis
    network: Tests requiring network access

filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

### Fixtures (`conftest.py`)

Common test fixtures are defined in `conftest.py`:

```python
@pytest.fixture
async def test_valley():
    """Create a test valley instance."""
    valley = Valley(name="test_valley")
    await valley.initialize()
    yield valley
    await valley.cleanup()

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        "valley": {"name": "test", "max_campfires": 10},
        "monitoring": {"enabled": True},
        "storage": {"type": "memory"}
    }
```

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10", "3.11"]
    
    services:
      redis:
        image: redis:latest
        ports:
          - 6379:6379
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest --cov=campfirevalley --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Troubleshooting

### Common Issues

#### Redis Connection Issues

```bash
# Check Redis is running
redis-cli ping

# Use test Redis database
export REDIS_TEST_URL=redis://localhost:6379/15
```

#### Import Errors

```bash
# Install in development mode
pip install -e .

# Check Python path
python -c "import sys; print(sys.path)"
```

#### Slow Tests

```bash
# Run only fast tests
pytest -m "not slow"

# Profile slow tests
pytest --durations=10
```

#### Memory Issues

```bash
# Run tests with memory profiling
pytest --memray

# Limit parallel workers
pytest -n 2
```

### Test Data Management

#### Cleaning Test Data

```bash
# Clean test databases
redis-cli -n 15 FLUSHDB

# Remove test files
rm -rf ./test_storage/
rm -rf ./test_logs/
```

#### Generating Test Data

```python
# Use factory functions for test data
def create_test_torch(size="small"):
    """Create test torch with specified size."""
    if size == "small":
        return Torch(data=b"small test data")
    elif size == "large":
        return Torch(data=b"x" * 1024 * 1024)  # 1MB
```

### Debugging Tests

#### Verbose Output

```bash
# Maximum verbosity
pytest -vvv

# Show local variables on failure
pytest --tb=long

# Drop into debugger on failure
pytest --pdb
```

#### Logging Configuration

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# In test functions
def test_something(caplog):
    with caplog.at_level(logging.DEBUG):
        # Test code here
        pass
    
    # Check logs
    assert "expected message" in caplog.text
```

## Best Practices

### Test Organization

1. **One test per behavior**: Each test should verify one specific behavior
2. **Descriptive names**: Test names should clearly describe what is being tested
3. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
4. **Independent tests**: Tests should not depend on each other

### Test Data

1. **Use factories**: Create test data using factory functions
2. **Minimal data**: Use the smallest amount of data necessary
3. **Realistic data**: Test data should represent real-world scenarios
4. **Clean up**: Always clean up test data after tests

### Performance Testing

1. **Baseline measurements**: Establish performance baselines
2. **Consistent environment**: Run performance tests in consistent environments
3. **Statistical significance**: Run multiple iterations for reliable results
4. **Resource monitoring**: Monitor CPU, memory, and I/O during tests

### Mocking

1. **Mock external dependencies**: Mock Redis, file systems, network calls
2. **Verify interactions**: Assert that mocks are called correctly
3. **Realistic mocks**: Mocks should behave like real dependencies
4. **Minimal mocking**: Only mock what's necessary

This testing guide ensures comprehensive coverage of all CampfireValley components and provides clear guidance for maintaining high code quality through effective testing practices.
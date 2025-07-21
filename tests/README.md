# Redis Session Tests

This directory contains comprehensive tests for the Redis-based session storage implementation for OpenAI Agents SDK.

## Test Structure

- **`conftest.py`** - Pytest configuration with Docker-based Redis (default)
- **`conftest_local.py`** - Alternative configuration for local Redis
- **`test_smoke.py`** - Basic smoke tests to verify functionality
- **`test_redis_session.py`** - Unit tests for the `RedisSession` class
- **`test_redis_session_manager.py`** - Unit tests for the `RedisSessionManager` class
- **`test_integration.py`** - Integration tests for complete workflows

## Prerequisites & Setup Options

### Option 1: Docker-based Testing (Recommended)

The default setup uses Docker to run Redis in a container, providing:
- ✅ Isolated test environment
- ✅ No conflicts with local Redis
- ✅ Consistent across different machines
- ✅ Automatic cleanup

**Requirements:**
```bash
# Install Docker
# macOS: Download from https://docker.com
# Ubuntu: sudo apt-get install docker.io
# Windows: Download Docker Desktop

# Verify Docker is running
docker --version
docker run hello-world
```

**No additional Redis setup needed** - tests will automatically start/stop Redis containers.

### Option 2: Local Redis Testing

If you prefer to use a local Redis instance:

```bash
# 1. Install and start Redis locally
brew install redis          # macOS
sudo apt-get install redis  # Ubuntu
# Windows: Download from https://redis.io

# 2. Start Redis
brew services start redis   # macOS
sudo systemctl start redis  # Ubuntu
redis-server                 # Direct execution

# 3. Switch to local testing
mv conftest.py conftest_docker.py
mv conftest_local.py conftest.py
```

## Test Dependencies

```bash
# Install all dependencies
uv sync

# Or with pip
pip install -e ".[dev]"
```

## Running Tests

### Quick Start with Docker (Recommended)

```bash
# Run smoke tests first
uv run pytest tests/test_smoke.py -v

# Run all tests
uv run pytest

# Run specific test types
uv run pytest tests/test_redis_session.py        # Unit tests
uv run pytest tests/test_integration.py          # Integration tests

# With coverage
uv run pytest --cov=src --cov-report=html --cov-report=term
```

### Running Tests with Local Redis

```bash
# Make sure Redis is running first
redis-cli ping  # Should return "PONG"

# Switch to local configuration (one-time setup)
mv conftest.py conftest_docker.py
mv conftest_local.py conftest.py

# Run tests
uv run pytest tests/test_smoke.py -v
```

### Advanced Options

```bash
# Verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Run specific test
uv run pytest tests/test_smoke.py::test_basic_workflow

# Skip slow tests
uv run pytest -m "not slow"

# Parallel execution (install pytest-xdist first)
uv add --dev pytest-xdist
uv run pytest -n auto
```

## Test Configuration

### Docker Testing (Default)

- **Container**: `redis-test-container`
- **Image**: `redis:7-alpine`
- **Port**: `6380` (mapped from container's 6379)
- **Database**: `15` (test database)
- **Lifecycle**: Container started once per test session, cleaned up automatically

### Local Redis Testing

- **Host**: `localhost:6379`
- **Database**: `15` (test database, isolated from your app data)
- **Cleanup**: Test database flushed after each test

## Test Database

Both configurations use Redis database 15 to avoid conflicts with your application data. The test fixtures automatically:

- Use database 15 for all Redis operations
- Clean up test data after each test
- Skip tests if Redis is not available

## Test Coverage

The tests cover:

### RedisSession Class
- ✅ Initialization and configuration
- ✅ Redis client management
- ✅ Session metadata handling
- ✅ Adding and retrieving conversation items
- ✅ Item limits and pagination
- ✅ Popping items from session
- ✅ Session clearing
- ✅ TTL (time-to-live) functionality
- ✅ Error handling for invalid JSON
- ✅ Async context manager support
- ✅ Connection management

### RedisSessionManager Class
- ✅ Connection pooling
- ✅ Session creation and management
- ✅ Listing sessions with pattern matching
- ✅ Session deletion
- ✅ Multiple session isolation
- ✅ Concurrent access handling
- ✅ Error recovery

### Integration Tests
- ✅ Complete conversation workflows
- ✅ Session persistence across instances
- ✅ Concurrent session access
- ✅ TTL expiration behavior
- ✅ Large conversation handling
- ✅ Error recovery scenarios
- ✅ Memory management simulation
- ✅ Context management with limits
- ✅ Session metadata tracking

## Troubleshooting

### Redis Connection Issues

If you see connection errors:

```bash
# Check if Redis is running
redis-cli ping
# Should return "PONG"

# Check Redis configuration
redis-cli info server
```

### Test Database Conflicts

Tests use database 15. If you need to use a different database:

```python
# In conftest.py, change the db parameter:
client = redis.from_url("redis://localhost:6379", db=14, decode_responses=True)
```

### Memory Issues

For the large conversation test, if you encounter memory issues:

```python
# Reduce the conversation size in test_integration.py:
# Change from 1000 to a smaller number
for i in range(100):  # Instead of range(1000)
```

## Adding New Tests

When adding new tests:

1. Use the existing fixtures in `conftest.py`
2. Follow the naming convention `test_*`
3. Use appropriate markers (`@pytest.mark.asyncio` for async tests)
4. Clean up resources in test teardown
5. Test both success and error conditions

Example:

```python
async def test_new_feature(redis_session, sample_items):
    """Test description."""
    # Test implementation
    await redis_session.new_method()
    # Assertions
    assert expected == actual
```

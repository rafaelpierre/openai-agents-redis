"""Alternative conftest.py for testing without Docker.

To use this instead of Docker:
1. Rename conftest.py to conftest_docker.py
2. Rename this file to conftest.py
3. Make sure you have Redis running locally on port 6379

Usage: mv conftest.py conftest_docker.py && mv conftest_local.py conftest.py
"""

import asyncio
import pytest
import redis.asyncio as redis
from typing import AsyncGenerator

from agents_redis.session import RedisSession, RedisSessionManager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Provide a Redis client for testing against local Redis."""
    client = redis.from_url("redis://localhost:6379", db=15, decode_responses=True)
    
    # Test Redis connection
    try:
        await client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis server not available on localhost:6379")
    
    yield client
    
    # Cleanup: flush the test database
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def redis_session(redis_client: redis.Redis) -> AsyncGenerator[RedisSession, None]:
    """Provide a RedisSession instance for testing."""
    session = RedisSession(
        session_id="test_session_123",
        redis_url="redis://localhost:6379",
        db="default",  # Use test database
        session_prefix="test_agent_session",
        messages_prefix="test_agent_messages"
    )
    
    yield session
    
    # Cleanup
    await session.clear_session()
    await session.close()


@pytest.fixture
async def redis_session_manager(redis_client: redis.Redis) -> AsyncGenerator[RedisSessionManager, None]:
    """Provide a RedisSessionManager instance for testing."""
    manager = RedisSessionManager(
        redis_url="redis://localhost:6379",
        db="default",  # Use test database
        session_prefix="test_agent_session",
        messages_prefix="test_agent_messages",
        default_ttl=3600,
        max_connections=5
    )
    
    yield manager
    
    # Cleanup
    await manager.close()


@pytest.fixture
def sample_items():
    """Provide sample conversation items for testing."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you! How can I help you today?"},
        {"role": "user", "content": "Can you explain quantum computing?"},
        {"role": "assistant", "content": "Quantum computing uses quantum mechanics principles..."},
    ]


@pytest.fixture
def single_item():
    """Provide a single conversation item for testing."""
    return {"role": "user", "content": "Test message"}


# Mock fixture that provides the same interface as docker_redis
@pytest.fixture
def docker_redis():
    """Mock fixture to provide same interface as Docker version for local Redis."""
    return {
        "url": "redis://localhost:6379",
        "host": "localhost", 
        "port": 6379,
        "container_name": "localhost"
    }

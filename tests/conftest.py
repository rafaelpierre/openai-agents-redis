"""Pytest configuration and fixtures for Redis session tests."""

import asyncio
import subprocess
import time
import pytest
import pytest_asyncio
import redis.asyncio as redis
from typing import Generator, AsyncGenerator

from src.agents_redis.session import RedisSession, RedisSessionManager


@pytest.fixture(scope="session")
def docker_redis() -> Generator[dict, None, None]:
    """Start a Redis container for testing and clean it up after tests."""
    container_name = "redis-test-container"
    redis_port = "6380"  # Use different port to avoid conflicts
    
    # Check if Docker is available
    try:
        subprocess.run(
            ["docker", "--version"], 
            check=True, 
            capture_output=True, 
            text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker is not available")
    
    # Stop any existing container with the same name
    subprocess.run(
        ["docker", "stop", container_name],
        capture_output=True
    )
    subprocess.run(
        ["docker", "rm", container_name],
        capture_output=True
    )
    
    # Start Redis container
    try:
        subprocess.run([
            "docker", "run", 
            "-d",  # Run in detached mode
            "--name", container_name,
            "-p", f"{redis_port}:6379",  # Map to different host port
            "redis:7-alpine",
            "redis-server", "--appendonly", "yes"
        ], check=True, capture_output=True, text=True)
        
        # Wait for Redis to be ready
        redis_url = f"redis://localhost:{redis_port}"
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                # Use sync redis client for the health check
                import redis as sync_redis
                client = sync_redis.from_url(redis_url)
                client.ping()
                client.close()
                break
            except redis.ConnectionError:
                if attempt == max_attempts - 1:
                    raise pytest.skip("Redis container failed to start")
                time.sleep(1)
        
        # Yield connection info
        yield {
            "url": redis_url,
            "host": "localhost", 
            "port": int(redis_port),
            "container_name": container_name
        }
        
    finally:
        # Cleanup: stop and remove the container
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True
        )
        subprocess.run(
            ["docker", "rm", container_name], 
            capture_output=True
        )


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()



@pytest_asyncio.fixture
async def redis_client(docker_redis) -> AsyncGenerator[redis.Redis, None]:
    """Provide a Redis client connected to the test container."""
    client = redis.from_url(
        docker_redis["url"], 
        db=15,  # Use test database (integer, not string)
        decode_responses=True
    )
    
    # Test connection
    await client.ping()
    
    yield client
    
    # Cleanup: flush the test database and close
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def redis_session(docker_redis) -> AsyncGenerator[RedisSession, None]:
    """Provide a RedisSession instance connected to test container."""
    session = RedisSession(
        session_id="test_session_123",
        redis_url=docker_redis["url"],
        db=15,  # Use test database (integer, not string)
        session_prefix="test_agent_session",
        messages_prefix="test_agent_messages"
    )
    
    # Clean up any existing test data before yielding
    client = redis.from_url(docker_redis["url"], db=15, decode_responses=True)
    await client.flushdb()
    await client.aclose()
    
    yield session
    
    # Cleanup
    await session.clear_session()
    await session.close()


@pytest_asyncio.fixture
async def redis_session_manager(docker_redis) -> AsyncGenerator[RedisSessionManager, None]:
    """Provide a RedisSessionManager instance connected to test container."""
    manager = RedisSessionManager(
        redis_url=docker_redis["url"],
        db=15,  # Use test database (integer, not string)
        session_prefix="test_agent_session",
        messages_prefix="test_agent_messages",
        default_ttl=3600,
        max_connections=5
    )
    
    # Clean up any existing test data before yielding
    client = redis.from_url(docker_redis["url"], db=15, decode_responses=True)
    await client.flushdb()
    await client.aclose()
    
    yield manager
    
    # Cleanup after test
    await manager.close()
    
    # Flush database after each test to ensure clean state
    client = redis.from_url(docker_redis["url"], db=15, decode_responses=True)
    await client.flushdb()
    await client.aclose()


# Alternative fixture for when Docker is not available
@pytest_asyncio.fixture
async def redis_client_local() -> AsyncGenerator[redis.Redis, None]:
    """Provide a Redis client for testing against local Redis (fallback)."""
    try:
        client = redis.from_url("redis://localhost:6379", db=15, decode_responses=True)
        await client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis server not available (neither Docker nor local)")
    
    yield client
    
    # Cleanup: flush the test database
    await client.flushdb()
    await client.aclose()


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

"""Smoke tests to verify basic functionality works."""

import pytest
import redis.asyncio as redis
from agents_redis.session import RedisSession, RedisSessionManager


@pytest.mark.asyncio
async def test_redis_connection(docker_redis):
    """Test that we can connect to Redis."""
    client = redis.from_url(docker_redis["url"], db=15)
    pong = await client.ping()
    assert pong is True
    await client.aclose()

@pytest.mark.asyncio
async def test_session_creation(docker_redis):
    """Test that we can create a session."""
    session = RedisSession("smoke_test", redis_url=docker_redis["url"], db=15)
    assert session.session_id == "smoke_test"
    await session.close()

@pytest.mark.asyncio
async def test_manager_creation(docker_redis):
    """Test that we can create a session manager."""
    manager = RedisSessionManager(redis_url=docker_redis["url"], db=15)
    session = manager.get_session("smoke_test")
    assert session.session_id == "smoke_test"
    await session.close()
    await manager.close()

@pytest.mark.asyncio
async def test_basic_workflow(docker_redis):
    """Test basic add/get workflow."""
    session = RedisSession("workflow_test", redis_url=docker_redis["url"], db=15)
    
    try:
        # Add an item
        test_item = {"role": "user", "content": "Hello"}
        await session.add_items([test_item])
        
        # Get items back
        items = await session.get_items()
        assert len(items) == 1
        assert items[0] == test_item
        
        # Clean up
        await session.clear_session()
        
    finally:
        await session.close()

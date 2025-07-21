"""Unit tests for RedisSession class."""

import pytest
import json
import time
import asyncio
from unittest.mock import AsyncMock, patch
from typing import Any

from agents_redis.session import RedisSession


class TestRedisSession:
    """Test cases for RedisSession class."""

    def test_init(self):
        """Test RedisSession initialization."""
        session = RedisSession(
            session_id="test_123",
            redis_url="redis://localhost:6379",
            db=1,
            session_prefix="custom_session",
            messages_prefix="custom_messages",
            ttl=3600
        )
        
        assert session.session_id == "test_123"
        assert session.redis_url == "redis://localhost:6379"
        assert session.db == 1
        assert session.session_prefix == "custom_session"
        assert session.messages_prefix == "custom_messages"
        assert session.ttl == 3600
        assert session.session_key == "custom_session:test_123"
        assert session.messages_key == "custom_messages:test_123"
        assert session._redis_client is None

    def test_init_defaults(self):
        """Test RedisSession initialization with defaults."""
        session = RedisSession("test_123")
        
        assert session.session_id == "test_123"
        assert session.redis_url == "redis://localhost:6379"
        assert session.db == 0
        assert session.session_prefix == "agent_session"
        assert session.messages_prefix == "agent_messages"
        assert session.ttl is None
        assert session.session_key == "agent_session:test_123"
        assert session.messages_key == "agent_messages:test_123"

    @pytest.mark.asyncio
    async def test_get_redis_client(self, redis_session):
        """Test getting Redis client."""
        client = await redis_session._get_redis_client()
        
        assert client is not None
        assert redis_session._redis_client is client
        
        # Should return the same client on subsequent calls
        client2 = await redis_session._get_redis_client()
        assert client is client2

    @pytest.mark.asyncio
    async def test_ensure_session_exists(self, redis_session, redis_client):
        """Test ensuring session metadata exists."""
        # Clear any existing session data
        await redis_client.delete(redis_session.session_key)
        
        # Ensure session exists
        await redis_session._ensure_session_exists(redis_client)
        
        # Check session metadata was created
        session_data = await redis_client.hgetall(redis_session.session_key)
        assert session_data["session_id"] == redis_session.session_id
        assert "created_at" in session_data
        assert "updated_at" in session_data

    @pytest.mark.asyncio
    async def test_ensure_session_exists_with_ttl(self, redis_client):
        """Test ensuring session exists with TTL."""
        session = RedisSession(
            session_id="ttl_test",
            redis_url="redis://localhost:6380",  # Use test Redis port
            db=15,
            session_prefix="test_agent_session",
            messages_prefix="test_agent_messages",
            ttl=60  # 1 minute TTL
        )
        
        try:
            await session._ensure_session_exists(redis_client)
            
            # Check session TTL was set
            session_ttl = await redis_client.ttl(session.session_key)
            assert session_ttl > 0 and session_ttl <= 60
            
            # Messages key might not exist yet, so TTL could be -2 (key doesn't exist)
            messages_ttl = await redis_client.ttl(session.messages_key)
            # TTL should be either -2 (key doesn't exist) or positive (TTL set)
            assert messages_ttl == -2 or (messages_ttl > 0 and messages_ttl <= 60)
            
            # Now add a message and check that TTL gets set on messages key
            await session.add_items([{"role": "user", "content": "test"}])
            messages_ttl_after_add = await redis_client.ttl(session.messages_key)
            assert messages_ttl_after_add > 0 and messages_ttl_after_add <= 60
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_update_session_timestamp(self, redis_session, redis_client):
        """Test updating session timestamp."""
        # Create session first
        await redis_session._ensure_session_exists(redis_client)
        
        # Get initial timestamp
        initial_data = await redis_client.hgetall(redis_session.session_key)
        initial_timestamp = float(initial_data["updated_at"])
        
        # Wait a bit and update
        await asyncio.sleep(0.01)  # Small delay
        await redis_session._update_session_timestamp(redis_client)
        
        # Check timestamp was updated
        updated_data = await redis_client.hgetall(redis_session.session_key)
        updated_timestamp = float(updated_data["updated_at"])
        
        assert updated_timestamp > initial_timestamp

    @pytest.mark.asyncio
    async def test_add_items(self, redis_session, sample_items):
        """Test adding items to session."""
        await redis_session.add_items(sample_items)
        
        # Check items were added to Redis
        client = await redis_session._get_redis_client()
        raw_items = await client.lrange(redis_session.messages_key, 0, -1)
        
        assert len(raw_items) == len(sample_items)
        
        # Check items are in correct order
        for i, raw_item in enumerate(raw_items):
            item = json.loads(raw_item)
            assert item == sample_items[i]

    @pytest.mark.asyncio
    async def test_add_empty_items(self, redis_session):
        """Test adding empty list of items."""
        await redis_session.add_items([])
        
        # Should not create any entries
        client = await redis_session._get_redis_client()
        exists = await client.exists(redis_session.messages_key)
        assert not exists

    @pytest.mark.asyncio
    async def test_get_items_all(self, redis_session, sample_items):
        """Test getting all items from session."""
        # Add items first
        await redis_session.add_items(sample_items)
        
        # Get all items
        retrieved_items = await redis_session.get_items()
        
        assert len(retrieved_items) == len(sample_items)
        assert retrieved_items == sample_items

    @pytest.mark.asyncio
    async def test_get_items_with_limit(self, redis_session, sample_items):
        """Test getting limited number of items."""
        # Add items first
        await redis_session.add_items(sample_items)
        
        # Get last 2 items
        retrieved_items = await redis_session.get_items(limit=2)
        
        assert len(retrieved_items) == 2
        assert retrieved_items == sample_items[-2:]

    @pytest.mark.asyncio
    async def test_get_items_empty_session(self, redis_session):
        """Test getting items from empty session."""
        items = await redis_session.get_items()
        assert items == []

    @pytest.mark.asyncio
    async def test_get_items_with_invalid_json(self, redis_session, redis_client):
        """Test getting items when Redis contains invalid JSON."""
        # Add invalid JSON directly to Redis
        await redis_client.rpush(redis_session.messages_key, "invalid_json", '{"valid": "json"}')
        
        items = await redis_session.get_items()
        
        # Should skip invalid JSON and return only valid items
        assert len(items) == 1
        assert items[0] == {"valid": "json"}

    @pytest.mark.asyncio
    async def test_pop_item(self, redis_session, sample_items):
        """Test popping the most recent item."""
        # Add items first
        await redis_session.add_items(sample_items)
        
        # Pop the most recent item
        popped_item = await redis_session.pop_item()
        
        assert popped_item == sample_items[-1]
        
        # Check item was removed
        remaining_items = await redis_session.get_items()
        assert len(remaining_items) == len(sample_items) - 1
        assert remaining_items == sample_items[:-1]

    @pytest.mark.asyncio
    async def test_pop_item_empty_session(self, redis_session):
        """Test popping from empty session."""
        popped_item = await redis_session.pop_item()
        assert popped_item is None

    @pytest.mark.asyncio
    async def test_pop_item_invalid_json(self, redis_session, redis_client):
        """Test popping item with invalid JSON."""
        # Add invalid JSON directly to Redis
        await redis_client.rpush(redis_session.messages_key, "invalid_json")
        
        popped_item = await redis_session.pop_item()
        assert popped_item is None

    @pytest.mark.asyncio
    async def test_clear_session(self, redis_session, sample_items):
        """Test clearing session data."""
        # Add items first
        await redis_session.add_items(sample_items)
        
        # Verify items exist
        client = await redis_session._get_redis_client()
        session_exists = await client.exists(redis_session.session_key)
        messages_exists = await client.exists(redis_session.messages_key)
        assert session_exists
        assert messages_exists
        
        # Clear session
        await redis_session.clear_session()
        
        # Verify items are deleted
        session_exists = await client.exists(redis_session.session_key)
        messages_exists = await client.exists(redis_session.messages_key)
        assert not session_exists
        assert not messages_exists

    @pytest.mark.asyncio
    async def test_get_session_info(self, redis_session, sample_items):
        """Test getting session metadata."""
        # Add items to create session
        await redis_session.add_items(sample_items)
        
        # Get session info
        info = await redis_session.get_session_info()
        
        assert info is not None
        assert info["session_id"] == redis_session.session_id
        assert "created_at" in info
        assert "updated_at" in info

    @pytest.mark.asyncio
    async def test_get_session_info_nonexistent(self, redis_session):
        """Test getting info for non-existent session."""
        info = await redis_session.get_session_info()
        assert info is None

    @pytest.mark.asyncio
    async def test_get_session_size(self, redis_session, sample_items):
        """Test getting session size."""
        # Empty session
        size = await redis_session.get_session_size()
        assert size == 0
        
        # Add items
        await redis_session.add_items(sample_items)
        size = await redis_session.get_session_size()
        assert size == len(sample_items)

    @pytest.mark.asyncio
    async def test_close(self, redis_session):
        """Test closing Redis connection."""
        # Get client to ensure it's created
        client = await redis_session._get_redis_client()
        assert redis_session._redis_client is not None
        
        # Close connection
        await redis_session.close()
        assert redis_session._redis_client is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self, docker_redis, sample_items):
        """Test using RedisSession as async context manager."""
        async with RedisSession("context_test", redis_url=docker_redis["url"], db=15) as session:
            await session.add_items(sample_items)
            items = await session.get_items()
            assert len(items) == len(sample_items)
        
        # Session should be closed after context
        assert session._redis_client is None

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_session, sample_items):
        """Test concurrent operations on the same session."""
        import asyncio
        
        # Split items into chunks
        chunk1 = sample_items[:2]
        chunk2 = sample_items[2:]
        
        # Add chunks concurrently
        await asyncio.gather(
            redis_session.add_items(chunk1),
            redis_session.add_items(chunk2)
        )
        
        # Check all items were added
        all_items = await redis_session.get_items()
        assert len(all_items) == len(sample_items)
        
        # Items should be in some order (may not be the original due to concurrency)
        assert set(json.dumps(item, sort_keys=True) for item in all_items) == \
               set(json.dumps(item, sort_keys=True) for item in sample_items)


# Import asyncio for the timestamp test
import asyncio

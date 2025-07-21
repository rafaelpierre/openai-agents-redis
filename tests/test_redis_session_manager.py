"""Unit tests for RedisSessionManager class."""

import pytest
import asyncio
from unittest.mock import patch

from agents_redis.session import RedisSessionManager, RedisSession


class TestRedisSessionManager:
    """Test cases for RedisSessionManager class."""

    def test_init(self):
        """Test RedisSessionManager initialization."""
        manager = RedisSessionManager(
            redis_url="redis://localhost:6379",
            db=1,
            session_prefix="custom_session",
            messages_prefix="custom_messages",
            default_ttl=7200,
            max_connections=20
        )
        
        assert manager.redis_url == "redis://localhost:6379"
        assert manager.db == 1
        assert manager.session_prefix == "custom_session"
        assert manager.messages_prefix == "custom_messages"
        assert manager.default_ttl == 7200
        assert manager._redis_pool is not None

    def test_init_defaults(self):
        """Test RedisSessionManager initialization with defaults."""
        manager = RedisSessionManager()
        
        assert manager.redis_url == "redis://localhost:6379"
        assert manager.db == 0
        assert manager.session_prefix == "agent_session"
        assert manager.messages_prefix == "agent_messages"
        assert manager.default_ttl is None

    @pytest.mark.asyncio
    async def test_get_session(self, redis_session_manager):
        """Test getting a session instance."""
        session = redis_session_manager.get_session("test_session")
        
        assert isinstance(session, RedisSession)
        assert session.session_id == "test_session"
        assert session.redis_url == redis_session_manager.redis_url
        assert session.db == redis_session_manager.db
        assert session.session_prefix == redis_session_manager.session_prefix
        assert session.messages_prefix == redis_session_manager.messages_prefix
        assert session._redis_client is not None  # Should have shared pool connection

    @pytest.mark.asyncio
    async def test_get_session_with_custom_ttl(self, redis_session_manager):
        """Test getting a session with custom TTL."""
        custom_ttl = 1800
        session = redis_session_manager.get_session("test_session", ttl=custom_ttl)
        
        assert session.ttl == custom_ttl

    def test_get_session_with_default_ttl(self):
        """Test getting a session with manager's default TTL."""
        manager = RedisSessionManager(default_ttl=3600)
        session = manager.get_session("test_session")
        
        assert session.ttl == 3600

    @pytest.mark.asyncio
    async def test_multiple_sessions_share_pool(self, redis_session_manager):
        """Test that multiple sessions share the connection pool."""
        session1 = redis_session_manager.get_session("session_1")
        session2 = redis_session_manager.get_session("session_2")
        
        client1 = await session1._get_redis_client()
        client2 = await session2._get_redis_client()
        
        # They should use the same connection pool
        assert client1.connection_pool is client2.connection_pool
        assert client1.connection_pool is redis_session_manager._redis_pool

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, redis_session_manager):
        """Test listing sessions when none exist."""
        sessions = await redis_session_manager.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_with_data(self, redis_session_manager, sample_items):
        """Test listing sessions with existing data."""
        # Create some sessions with data
        session1 = redis_session_manager.get_session("user_123")
        session2 = redis_session_manager.get_session("user_456")
        session3 = redis_session_manager.get_session("user_789")
        
        try:
            # Add data to sessions to ensure they're created
            await session1.add_items([sample_items[0]])
            await session2.add_items([sample_items[1]])
            await session3.add_items([sample_items[2]])
            
            # List all sessions
            sessions = await redis_session_manager.list_sessions()
            
            assert len(sessions) == 3
            assert "user_123" in sessions
            assert "user_456" in sessions
            assert "user_789" in sessions
        finally:
            await session1.close()
            await session2.close()
            await session3.close()

    @pytest.mark.asyncio
    async def test_list_sessions_with_pattern(self, redis_session_manager, sample_items):
        """Test listing sessions with pattern filtering."""
        # Create sessions with different patterns
        admin_session = redis_session_manager.get_session("admin_123")
        user_session1 = redis_session_manager.get_session("user_456")
        user_session2 = redis_session_manager.get_session("user_789")
        
        try:
            # Add data to ensure sessions are created
            await admin_session.add_items([sample_items[0]])
            await user_session1.add_items([sample_items[1]])
            await user_session2.add_items([sample_items[2]])
            
            # List only user sessions
            user_sessions = await redis_session_manager.list_sessions("user_*")
            
            assert len(user_sessions) == 2
            assert "user_456" in user_sessions
            assert "user_789" in user_sessions
            assert "admin_123" not in user_sessions
        finally:
            await admin_session.close()
            await user_session1.close()
            await user_session2.close()

    @pytest.mark.asyncio
    async def test_delete_session_exists(self, redis_session_manager, sample_items):
        """Test deleting an existing session."""
        # Create and populate a session
        session = redis_session_manager.get_session("delete_test")
        
        try:
            await session.add_items(sample_items)
            
            # Verify session exists
            info = await session.get_session_info()
            assert info is not None
            
            # Delete session
            deleted = await redis_session_manager.delete_session("delete_test")
            assert deleted is True
            
            # Verify session is gone
            info = await session.get_session_info()
            assert info is None
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_delete_session_not_exists(self, redis_session_manager):
        """Test deleting a non-existent session."""
        deleted = await redis_session_manager.delete_session("nonexistent_session")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_close(self, redis_session_manager):
        """Test closing the session manager."""
        # Create a session to establish connection pool usage
        session = redis_session_manager.get_session("test_session")
        client = await session._get_redis_client()
        
        # Close manager
        await redis_session_manager.close()
        
        # Connection pool should be closed
        # Note: We can't easily test this without accessing internal state
        # This test mainly ensures no exceptions are raised
        await session.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, docker_redis, sample_items):
        """Test using RedisSessionManager as async context manager."""
        async with RedisSessionManager(redis_url=docker_redis["url"], db=15) as manager:
            session = manager.get_session("context_test")
            await session.add_items(sample_items)
            
            sessions = await manager.list_sessions()
            assert "context_test" in sessions
            
            await session.close()

    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, redis_session_manager, sample_items):
        """Test concurrent operations across multiple sessions."""
        sessions = [
            redis_session_manager.get_session(f"concurrent_test_{i}")
            for i in range(5)
        ]
        
        try:
            # Add items to all sessions concurrently
            await asyncio.gather(*[
                session.add_items([sample_items[i % len(sample_items)]])
                for i, session in enumerate(sessions)
            ])
            
            # Verify all sessions have data
            results = await asyncio.gather(*[
                session.get_items()
                for session in sessions
            ])
            
            for i, items in enumerate(results):
                assert len(items) == 1
                assert items[0] == sample_items[i % len(sample_items)]
        finally:
            # Close all sessions
            await asyncio.gather(*[session.close() for session in sessions])

    @pytest.mark.asyncio
    async def test_session_isolation(self, redis_session_manager, sample_items):
        """Test that sessions are properly isolated."""
        session1 = redis_session_manager.get_session("isolation_test_1")
        session2 = redis_session_manager.get_session("isolation_test_2")
        
        try:
            # Add different items to each session
            await session1.add_items([sample_items[0]])
            await session2.add_items([sample_items[1], sample_items[2]])
            
            # Verify session contents are separate
            items1 = await session1.get_items()
            items2 = await session2.get_items()
            
            assert len(items1) == 1
            assert len(items2) == 2
            assert items1[0] == sample_items[0]
            assert items2 == sample_items[1:3]
        finally:
            await session1.close()
            await session2.close()

    @pytest.mark.asyncio
    async def test_error_handling_in_list_sessions(self, redis_session_manager):
        """Test error handling in list_sessions method."""
        with patch.object(redis_session_manager._redis_pool, 'get_connection') as mock_get_conn:
            # Mock a connection error
            mock_get_conn.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception, match="Connection failed"):
                await redis_session_manager.list_sessions()

    @pytest.mark.asyncio
    async def test_manager_reuse(self, redis_session_manager, sample_items):
        """Test that manager can be reused multiple times."""
        # First use
        session1 = redis_session_manager.get_session("reuse_test_1")
        await session1.add_items([sample_items[0]])
        sessions = await redis_session_manager.list_sessions()
        assert "reuse_test_1" in sessions
        await session1.close()
        
        # Second use
        session2 = redis_session_manager.get_session("reuse_test_2")
        await session2.add_items([sample_items[1]])
        sessions = await redis_session_manager.list_sessions()
        assert "reuse_test_1" in sessions  # Still there
        assert "reuse_test_2" in sessions  # New one added
        await session2.close()

    @pytest.mark.asyncio
    async def test_large_number_of_sessions(self, redis_session_manager):
        """Test creating a large number of sessions."""
        num_sessions = 50
        sessions = []
        
        try:
            # Create many sessions
            for i in range(num_sessions):
                session = redis_session_manager.get_session(f"bulk_test_{i}")
                await session.add_items([{"id": i, "message": f"Message {i}"}])
                sessions.append(session)
            
            # List all sessions
            session_ids = await redis_session_manager.list_sessions()
            
            # Verify all sessions exist
            bulk_sessions = [sid for sid in session_ids if sid.startswith("bulk_test_")]
            assert len(bulk_sessions) == num_sessions
        finally:
            # Cleanup
            await asyncio.gather(*[session.close() for session in sessions])

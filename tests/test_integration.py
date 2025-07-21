"""Integration tests for Redis session functionality."""

import pytest
import asyncio
import json
import time
from typing import List, Any

from src.agents_redis.session import RedisSession, RedisSessionManager


class TestRedisSessionIntegration:
    """Integration tests that test the complete workflow."""

    @pytest.mark.asyncio
    async def test_complete_conversation_workflow(self, redis_session_manager):
        """Test a complete conversation workflow with multiple turns."""
        session = redis_session_manager.get_session("conversation_test")
        
        try:
            # Simulate a conversation
            conversation = [
                {"role": "user", "content": "Hello, I need help with Python programming."},
                {"role": "assistant", "content": "I'd be happy to help you with Python! What specific topic would you like to learn about?"},
                {"role": "user", "content": "How do I work with async/await?"},
                {"role": "assistant", "content": "Async/await is used for asynchronous programming in Python. Here's how it works..."},
                {"role": "user", "content": "Can you show me an example?"},
                {"role": "assistant", "content": "Sure! Here's a simple example: async def fetch_data():..."}
            ]
            
            # Add conversation turn by turn
            for message in conversation:
                await session.add_items([message])
                
                # Verify conversation grows
                current_items = await session.get_items()
                assert len(current_items) <= len(conversation)
            
            # Get full conversation
            full_conversation = await session.get_items()
            assert len(full_conversation) == len(conversation)
            assert full_conversation == conversation
            
            # Test getting limited recent context
            recent_context = await session.get_items(limit=3)
            assert len(recent_context) == 3
            assert recent_context == conversation[-3:]
            
            # Test conversation size
            size = await session.get_session_size()
            assert size == len(conversation)
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_persistence_across_instances(self, redis_session_manager, sample_items):
        """Test that session data persists across different session instances."""
        session_id = "persistence_test"
        
        # Create first session instance and add data
        session1 = redis_session_manager.get_session(session_id)
        try:
            await session1.add_items(sample_items[:2])
            items1 = await session1.get_items()
            assert len(items1) == 2
        finally:
            await session1.close()
        
        # Create second session instance with same ID
        session2 = redis_session_manager.get_session(session_id)
        try:
            # Should see the same data
            items2 = await session2.get_items()
            assert len(items2) == 2
            assert items2 == sample_items[:2]
            
            # Add more data
            await session2.add_items(sample_items[2:])
            items3 = await session2.get_items()
            assert len(items3) == len(sample_items)
            assert items3 == sample_items
        finally:
            await session2.close()

    @pytest.mark.asyncio
    async def test_concurrent_session_access(self, redis_session_manager, sample_items):
        """Test concurrent access to the same session from multiple instances."""
        session_id = "concurrent_access_test"
        
        session1 = redis_session_manager.get_session(session_id)
        session2 = redis_session_manager.get_session(session_id)
        
        try:
            # Concurrently add items from different session instances
            await asyncio.gather(
                session1.add_items([sample_items[0]]),
                session2.add_items([sample_items[1]]),
            )
            
            # Both instances should see all items
            items1 = await session1.get_items()
            items2 = await session2.get_items()
            
            assert len(items1) == 2
            assert len(items2) == 2
            assert set(json.dumps(item, sort_keys=True) for item in items1) == \
                   set(json.dumps(item, sort_keys=True) for item in [sample_items[0], sample_items[1]])
        finally:
            await session1.close()
            await session2.close()

    @pytest.mark.asyncio
    async def test_ttl_expiration_simulation(self, docker_redis):
        """Test TTL functionality with a short expiration time."""
        # Create session with very short TTL
        session = RedisSession(
            session_id="ttl_test",
            redis_url=docker_redis["url"],
            db=15,
            ttl=1  # 1 second TTL
        )
        
        try:
            # Add some items
            await session.add_items([{"role": "user", "content": "Test message"}])
            
            # Verify items exist
            items = await session.get_items()
            assert len(items) == 1
            
            # Wait for TTL to expire
            await asyncio.sleep(1.5)
            
            # Items should be expired
            items = await session.get_items()
            assert len(items) == 0
            
            # Session info should also be expired
            info = await session.get_session_info()
            assert info is None
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_large_conversation_handling(self, redis_session_manager):
        """Test handling of large conversations."""
        session = redis_session_manager.get_session("large_conversation")
        
        try:
            # Create a large conversation (1000 messages)
            large_conversation = []
            for i in range(1000):
                role = "user" if i % 2 == 0 else "assistant"
                message = {
                    "role": role,
                    "content": f"This is message number {i} in the conversation. " * 10  # Make it longer
                }
                large_conversation.append(message)
            
            # Add messages in batches
            batch_size = 100
            for i in range(0, len(large_conversation), batch_size):
                batch = large_conversation[i:i + batch_size]
                await session.add_items(batch)
            
            # Verify all messages were stored
            all_messages = await session.get_items()
            assert len(all_messages) == 1000
            
            # Test getting recent messages
            recent_messages = await session.get_items(limit=50)
            assert len(recent_messages) == 50
            assert recent_messages == large_conversation[-50:]
            
            # Test session size
            size = await session.get_session_size()
            assert size == 1000
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_error_recovery(self, redis_session_manager, sample_items):
        """Test error recovery and resilience."""
        session = redis_session_manager.get_session("error_recovery_test")
        
        try:
            # Add some valid data
            await session.add_items(sample_items)
            
            # Simulate corrupted data by adding invalid JSON directly
            client = await session._get_redis_client()
            await client.rpush(session.messages_key, "invalid_json_data")
            
            # Should still be able to retrieve valid items
            items = await session.get_items()
            assert len(items) == len(sample_items)
            assert items == sample_items
            
            # Pop operation should handle invalid JSON gracefully
            # First pop the invalid JSON
            popped = await session.pop_item()
            assert popped is None  # Invalid JSON should return None
            
            # Next pop should get valid item
            popped = await session.pop_item()
            assert popped == sample_items[-1]
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_memory_management_simulation(self, redis_session_manager):
        """Test memory management by creating and destroying many sessions."""
        session_count = 100
        sessions_created = []
        
        try:
            # Create many sessions
            for i in range(session_count):
                session_id = f"memory_test_{i}"
                session = redis_session_manager.get_session(session_id)
                
                # Add some data
                await session.add_items([{
                    "role": "user",
                    "content": f"Test message for session {i}"
                }])
                
                sessions_created.append(session)
            
            # Verify all sessions exist
            all_sessions = await redis_session_manager.list_sessions()
            memory_test_sessions = [s for s in all_sessions if s.startswith("memory_test_")]
            assert len(memory_test_sessions) == session_count
            
            # Close half the sessions
            for i in range(0, session_count, 2):
                await sessions_created[i].close()
            
            # Delete some sessions through manager
            for i in range(0, session_count, 4):
                await redis_session_manager.delete_session(f"memory_test_{i}")
            
            # Remaining sessions should still work
            remaining_sessions = await redis_session_manager.list_sessions()
            memory_test_remaining = [s for s in remaining_sessions if s.startswith("memory_test_")]
            assert len(memory_test_remaining) < session_count
            
        finally:
            # Cleanup remaining sessions
            for session in sessions_created:
                try:
                    await session.close()
                except:
                    pass  # Ignore errors for already closed sessions

    @pytest.mark.asyncio
    async def test_conversation_context_management(self, redis_session_manager):
        """Test managing conversation context with different limits."""
        session = redis_session_manager.get_session("context_management")
        
        try:
            # Simulate a long conversation
            conversation = []
            for i in range(20):
                user_msg = {"role": "user", "content": f"User message {i}"}
                assistant_msg = {"role": "assistant", "content": f"Assistant response {i}"}
                
                conversation.extend([user_msg, assistant_msg])
                await session.add_items([user_msg, assistant_msg])
            
            # Test different context window sizes
            full_context = await session.get_items()
            assert len(full_context) == 40  # 20 pairs
            
            recent_10 = await session.get_items(limit=10)
            assert len(recent_10) == 10
            assert recent_10 == conversation[-10:]
            
            recent_5 = await session.get_items(limit=5)
            assert len(recent_5) == 5
            assert recent_5 == conversation[-5:]
            
            # Test popping items to manage context size
            original_size = await session.get_session_size()
            assert original_size == 40
            
            # Pop oldest items to maintain context window
            for _ in range(10):
                # Note: pop_item removes from the end, so we'd need to implement
                # a pop_first method for this use case. For now, test the current behavior
                popped = await session.pop_item()
                assert popped is not None
            
            new_size = await session.get_session_size()
            assert new_size == 30
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_metadata_tracking(self, redis_session_manager, sample_items):
        """Test session metadata tracking and updates."""
        session = redis_session_manager.get_session("metadata_test")
        
        try:
            # Initially no session info
            info = await session.get_session_info()
            assert info is None
            
            # Add items - should create session metadata
            await session.add_items(sample_items[:1])
            
            info = await session.get_session_info()
            assert info is not None
            assert info["session_id"] == "metadata_test"
            
            created_at = float(info["created_at"])
            initial_updated_at = float(info["updated_at"])
            
            # Add more items after a delay
            await asyncio.sleep(0.01)  # Small delay is sufficient with float precision
            await session.add_items(sample_items[1:])
            
            # Check that updated_at changed
            updated_info = await session.get_session_info()
            new_updated_at = float(updated_info["updated_at"])
            
            assert float(updated_info["created_at"]) == created_at  # Should not change
            assert new_updated_at > initial_updated_at  # Should be updated
            
            # Pop item should also update timestamp
            await asyncio.sleep(0.01)
            await session.pop_item()
            
            final_info = await session.get_session_info()
            final_updated_at = float(final_info["updated_at"])
            assert final_updated_at > new_updated_at
            
        finally:
            await session.close()

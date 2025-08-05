"""
Integration module that combines Redis session management with context persistence.

This module provides a unified interface that works seamlessly with both your
existing RedisSession infrastructure and the new context management system.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from .session import RedisSessionManager
from .context import DistributedContextManager, ContextMiddleware

try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("redis package is required")


class UnifiedSessionManager:
    """
    Unified manager that handles both message history (via your RedisSession)
    and context persistence (via DistributedContextManager).
    
    This gives you a single entry point for all session and context management.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        db: int = 0,
        session_prefix: str = "agent_session",
        messages_prefix: str = "agent_messages", 
        context_prefix: str = "agent_context",
        default_ttl: int = 3600,  # 1 hour
        max_connections: int = 20,
    ):
        """Initialize unified session and context management."""
        
        # Initialize your existing session manager
        self.session_manager = RedisSessionManager(
            redis_url=redis_url,
            db=db,
            session_prefix=session_prefix,
            messages_prefix=messages_prefix,
            default_ttl=default_ttl,
            max_connections=max_connections,
        )
        
        # Create Redis client for context manager (shares same connection pool concept)
        self._redis_client = redis.from_url(
            redis_url,
            db=db,
            decode_responses=True,
            retry_on_error=[redis.BusyLoadingError, redis.ConnectionError],
            retry_on_timeout=True,
        )
        
        # Initialize context manager
        self.context_manager = DistributedContextManager(
            redis_client=self._redis_client,
            context_class=AgentMemoryContext,
            key_prefix=context_prefix,
            default_ttl=default_ttl
        )
        
        # Initialize context middleware with specific type
        self.context_middleware = ContextMiddleware[AgentMemoryContext](self.context_manager)
    
    def get_redis_session(self, session_id: str, ttl: Optional[int] = None):
        """Get a Redis session (your existing implementation) for openai-agents."""
        return self.session_manager.get_session(session_id, ttl)
    
    async def get_or_create_context(
        self,
        session_id: str,
        user_id: str,
        name: str = "User",
        ttl: Optional[int] = None
    ) -> AgentMemoryContext:
        """Get or create context for a session."""
        # Create default context if it doesn't exist
        default_context = AgentMemoryContext(
            user_id=user_id,
            session_id=session_id,
            name=name
        )
        
        return await self.context_middleware.get_or_create_context(
            session_id, default_context, ttl
        )
    
    async def save_context(
        self,
        session_id: str,
        context: AgentMemoryContext,
        ttl: Optional[int] = None
    ) -> None:
        """Save context to Redis."""
        await self.context_middleware.save_context(session_id, context, ttl)
    
    async def delete_session_completely(self, session_id: str) -> Dict[str, bool]:
        """Delete both session messages and context."""
        results = {}
        
        # Delete session messages (your existing method)
        results["messages_deleted"] = await self.session_manager.delete_session(session_id)
        
        # Delete context
        results["context_deleted"] = await self.context_middleware.clear_context(session_id)
        
        return results
    
    async def get_session_overview(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive overview of session and context."""
        # Get session info (your existing method)
        redis_session = self.get_redis_session(session_id)
        session_info = await redis_session.get_session_info()
        
        # Get context
        context = await self.context_manager.get_context(session_id)
        
        return {
            "session_info": session_info,
            "context": context.get_context_summary() if context else None,
            "has_messages": bool(session_info),
            "has_context": context is not None,
        }
    
    async def list_all_sessions(self) -> Dict[str, Any]:
        """Get overview of all sessions."""
        # Get sessions with messages
        message_sessions = await self.session_manager.list_sessions()
        
        # Get sessions with contexts
        context_sessions = await self.context_manager.get_all_sessions()
        
        # Combine for overview
        all_sessions = set(message_sessions + context_sessions)
        
        return {
            "total_sessions": len(all_sessions),
            "sessions_with_messages": len(message_sessions),
            "sessions_with_contexts": len(context_sessions),
            "session_ids": list(all_sessions),
        }
    
    async def cleanup_expired_data(self) -> Dict[str, int]:
        """Clean up expired sessions and contexts."""
        # Note: Your RedisSession uses TTL, so expired messages are automatically cleaned
        # We just need to clean up any orphaned contexts
        expired_contexts = await self.context_manager.cleanup_expired_contexts()
        
        return {
            "expired_contexts_cleaned": expired_contexts,
        }
    
    async def close(self) -> None:
        """Close all connections."""
        await self.session_manager.close()
        await self._redis_client.aclose()


class AgentSessionWrapper:
    """
    Convenience wrapper that provides a unified interface for a single session.
    Perfect for FastAPI endpoints where you're working with one session at a time.
    """
    
    def __init__(
        self,
        unified_manager: UnifiedSessionManager,
        session_id: str,
        user_id: str,
        name: str = "User",
        ttl: Optional[int] = None
    ):
        self.unified_manager = unified_manager
        self.session_id = session_id
        self.user_id = user_id
        self.name = name
        self.ttl = ttl
        
        self._redis_session = None
        self._context = None
    
    def get_redis_session(self):
        """Get Redis session for openai-agents Runner."""
        if self._redis_session is None:
            self._redis_session = self.unified_manager.get_redis_session(
                self.session_id, self.ttl
            )
        return self._redis_session
    
    async def get_context(self) -> AgentMemoryContext:
        """Get or create context."""
        if self._context is None:
            self._context = await self.unified_manager.get_or_create_context(
                self.session_id, self.user_id, self.name, self.ttl
            )
        return self._context
    
    async def save_context(self, context: Optional[AgentMemoryContext] = None) -> None:
        """Save context (uses cached context if none provided)."""
        context_to_save = context or self._context
        if context_to_save:
            await self.unified_manager.save_context(
                self.session_id, context_to_save, self.ttl
            )
            # Update cached context
            self._context = context_to_save
    
    async def refresh_context(self) -> AgentMemoryContext:
        """Refresh context from Redis."""
        self._context = await self.unified_manager.get_or_create_context(
            self.session_id, self.user_id, self.name, self.ttl
        )
        return self._context
    
    async def get_session_overview(self) -> Dict[str, Any]:
        """Get overview of this session."""
        return await self.unified_manager.get_session_overview(self.session_id)
    
    async def delete_completely(self) -> Dict[str, bool]:
        """Delete both messages and context for this session."""
        return await self.unified_manager.delete_session_completely(self.session_id)


# FastAPI integration helper
def create_agent_session(
    unified_manager: UnifiedSessionManager,
    session_id: str,
    user_id: str,
    name: str = "User",
    ttl: Optional[int] = None
) -> AgentSessionWrapper:
    """
    Factory function to create an AgentSessionWrapper.
    Perfect for FastAPI dependency injection.
    """
    return AgentSessionWrapper(
        unified_manager=unified_manager,
        session_id=session_id,
        user_id=user_id,
        name=name,
        ttl=ttl
    )
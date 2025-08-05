"""
Context management for openai-agents with Redis persistence.

This module provides distributed context management that works across
FastAPI workers and requests, designed to integrate with the openai-agents
framework's RunContextWrapper pattern.
"""

from __future__ import annotations

from typing import TypeVar, Generic, Optional, Dict, Any, Type, List

try:
    import redis.asyncio as redis
    from pydantic import BaseModel
except ImportError:
    raise ImportError("redis and pydantic packages are required")

T = TypeVar('T', bound=BaseModel)

class DistributedContextManager(Generic[T]):
    """
    Redis-backed context manager that persists RunContextWrapper context
    across FastAPI requests and uvicorn workers.
    """
    
    def __init__(
        self, 
        redis_client: redis.Redis, 
        context_class: Type[T],
        key_prefix: str = "agent_context",
        default_ttl: int = 3600  # 1 hour default
    ):
        self.redis = redis_client
        self.context_class = context_class
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
    
    def _get_key(self, session_id: str) -> str:
        """Generate Redis key for session context."""
        return f"{self.key_prefix}:{session_id}"
    
    def _serialize_context(self, context: T) -> str:
        """Serialize context object to JSON string."""
        return context.model_dump_json()
    
    def _deserialize_context(self, context_json: str) -> T:
        """Deserialize JSON string back to context object."""
        return self.context_class.model_validate_json(context_json)
    
    async def store_context(
        self, 
        session_id: str, 
        context: T, 
        ttl: Optional[int] = None
    ) -> None:
        """Store context in Redis with optional TTL."""
        key = self._get_key(session_id)
        context_json = self._serialize_context(context)
        
        # Store with TTL
        ttl = ttl or self.default_ttl
        await self.redis.setex(key, ttl, context_json)
    
    async def get_context(self, session_id: str) -> Optional[T]:
        """Retrieve context from Redis."""
        key = self._get_key(session_id)
        context_json = await self.redis.get(key)
        
        if context_json is None:
            return None
        
        try:
            return self._deserialize_context(context_json)
        except Exception:
            return None
    
    async def update_context(
        self, 
        session_id: str, 
        updates: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> Optional[T]:
        """Update specific fields in the context."""
        context = await self.get_context(session_id)
        if context is None:
            return None
        
        # Update fields
        context_data = context.model_dump()
        context_data.update(updates)
        updated_context = self.context_class.model_validate(context_data)
        
        # Store updated context
        await self.store_context(session_id, updated_context, ttl)
        return updated_context
    
    async def get_or_create_context(
        self, 
        session_id: str, 
        default_context: T,
        ttl: Optional[int] = None
    ) -> T:
        """Get existing context or create with default values."""
        context = await self.get_context(session_id)
        if context is None:
            await self.store_context(session_id, default_context, ttl)
            return default_context
        return context
    
    async def delete_context(self, session_id: str) -> bool:
        """Delete context from Redis."""
        key = self._get_key(session_id)
        return bool(await self.redis.delete(key))
    
    async def extend_ttl(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """Extend TTL for a context."""
        key = self._get_key(session_id)
        ttl = ttl or self.default_ttl
        return bool(await self.redis.expire(key, ttl))
    
    async def get_all_sessions(self) -> List[str]:
        """Get all active session IDs."""
        pattern = f"{self.key_prefix}:*"
        keys = await self.redis.keys(pattern)
        prefix_len = len(self.key_prefix) + 1
        return [key[prefix_len:] for key in keys]
    
    async def cleanup_expired_contexts(self) -> int:
        """Clean up expired contexts. Returns count of cleaned contexts."""
        pattern = f"{self.key_prefix}:*"
        keys = await self.redis.keys(pattern)
        
        expired_count = 0
        for key in keys:
            ttl = await self.redis.ttl(key)
            if ttl == -2:  # Key doesn't exist (expired)
                expired_count += 1
        
        return expired_count



class ContextMiddleware(Generic[T]):
    """
    Generic middleware-like helper for FastAPI that handles context persistence
    across requests using your existing Redis infrastructure.
    
    Type parameter T should be your Pydantic context model class.
    """
    
    def __init__(self, context_manager: DistributedContextManager[T]):
        self.context_manager = context_manager
    
    async def get_or_create_context(
        self, 
        session_id: str, 
        default_context: T,
        ttl: Optional[int] = None
    ) -> T:
        """Get existing context or create with provided default."""
        # Try to get existing context
        context = await self.context_manager.get_context(session_id)
        
        if context is None:
            # Use the provided default context
            await self.context_manager.store_context(session_id, default_context, ttl)
            return default_context
        else:
            # Update TTL for existing context
            await self.context_manager.extend_ttl(session_id, ttl)
            return context
    
    async def save_context(
        self, 
        session_id: str, 
        context: T,
        ttl: Optional[int] = None
    ) -> None:
        """Save context back to Redis."""
        await self.context_manager.store_context(session_id, context, ttl)
    
    async def update_context_fields(
        self,
        session_id: str,
        updates: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> Optional[T]:
        """Update specific context fields."""
        return await self.context_manager.update_context(session_id, updates, ttl)
    
    async def clear_context(self, session_id: str) -> bool:
        """Clear context for a session."""
        return await self.context_manager.delete_context(session_id)
    
    async def get_all_active_sessions(self) -> List[str]:
        """Get all sessions with active contexts."""
        return await self.context_manager.get_all_sessions()
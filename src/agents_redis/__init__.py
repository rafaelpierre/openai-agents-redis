"""
Redis plugin for openai-agents with session and context management.

This package provides:
1. RedisSession and RedisSessionManager (your existing message history)
2. DistributedContextManager and related classes (new context persistence)
3. UnifiedSessionManager (combines both for easy usage)
"""

from .session import RedisSession, RedisSessionManager
 
from .context import (
    DistributedContextManager,
    ContextMiddleware
)

from .integration import (
    UnifiedSessionManager,
    AgentSessionWrapper,
    create_agent_session,
)

__all__ = [
    "RedisSession",
    "RedisSessionManager",
    "DistributedContextManager", 
    "ContextMiddleware",
    "AgentMemoryContext",
    "UnifiedSessionManager",
    "AgentSessionWrapper", 
    "create_agent_session",
]
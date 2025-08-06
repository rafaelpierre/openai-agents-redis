from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from agents_redis.context import DistributedContextManager, ContextMiddleware
from contextlib import asynccontextmanager
from agents import Runner
from agents_redis import RedisSession
import asyncio
import redis.asyncio as redis


# Custom context implementation
class MyCustomAgentContext(BaseModel):
    """Custom context implementation with different fields."""
    
    # Required fields
    user_id: str
    session_id: str
    
    # Custom business logic fields
    customer_tier: Literal["standard", "premium", "vip"] = "standard"
    product_interest: Optional[str] = None
    region: Literal["us", "eu", "asia"] = ""
    
    # Custom memory contexts
    current_inquiry: Optional[str] = None
    agent_notes: List[str] = Field(default_factory=list)
    escalation_needed: bool = False
    
    # Metadata
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_updated: float = Field(default_factory=lambda: datetime.now().timestamp())
    
    
    def update_region(self, region: Literal["us", "eu", "asia"]) -> None:
        """Update region."""
        self.region = region
        self._update_timestamp()

        
    def update_inquiry(self, inquiry: str) -> None:
        """Update current inquiry."""
        self.current_inquiry = inquiry
        self._update_timestamp()
    
    def add_agent_note(self, note: str) -> None:
        """Add an agent note."""
        timestamped_note = f"[{datetime.now().isoformat()}] {note}"
        self.agent_notes.append(timestamped_note)
        self._update_timestamp()
    
    def request_escalation(self, reason: str) -> None:
        """Request escalation with reason."""
        self.escalation_needed = True
        self.add_agent_note(f"ESCALATION REQUESTED: {reason}")
    
    def _update_timestamp(self) -> None:
        """Update last modified timestamp."""
        self.last_updated = datetime.now().timestamp()
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get summary of context for API responses."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "customer_tier": self.customer_tier,
            "current_inquiry": self.current_inquiry,
            "region": self.region,
            "agent_notes_count": len(self.agent_notes),
            "escalation_needed": self.escalation_needed,
            "last_updated": datetime.fromtimestamp(self.last_updated).isoformat(),
        }
    
# Custom context factory function
def create_custom_context(
    session_id: str, 
    user_id: str, 
    customer_tier: str = "standard"
) -> MyCustomAgentContext:
    """Factory function to create custom context with defaults."""
    return MyCustomAgentContext(
        session_id=session_id,
        user_id=user_id,
        customer_tier=customer_tier
    )

# Usage example with generic ContextMiddleware
async def setup_custom_context_system():
    """Example of setting up the context system with custom context type."""
    
    # Create Redis client
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    
    # Create context manager with your custom type
    context_manager = DistributedContextManager[MyCustomAgentContext](
        redis_client=redis_client,
        context_class=MyCustomAgentContext,
        key_prefix="custom_agent_context",
        default_ttl=7200  # 2 hours
    )
    
    # Create generic middleware with your custom type
    context_middleware = ContextMiddleware[MyCustomAgentContext](context_manager)
    
    # Return both middleware and redis client for locking
    return context_middleware, redis_client


# Context manager with Redis distributed lock (default, safe for concurrent access)
@asynccontextmanager
async def managed_context(
    middleware: ContextMiddleware[MyCustomAgentContext],
    redis_client: redis.Redis,
    session_id: str,
    user_id: str,
    message: str,
    customer_tier: str = "standard",
    lock_timeout: int = 30
):
    """
    Context manager with distributed lock to prevent concurrent modifications
    to the same session. This is the default and recommended approach.
    
    Usage:
        async with managed_context(
            middleware, redis_client, session_id, user_id, message, customer_tier
        ) as context:
            result = await Runner.run(
                starting_agent=custom_agent,
                input=message,
                context=context,
                session=RedisSession(redis_url="redis://localhost:6379", session_id=session_id),
            )
            # context is automatically saved after the block
    """
    lock_key = f"session_lock:{session_id}"
    lock_acquired = False
    
    try:
        # Try to acquire lock with timeout
        lock_acquired = await redis_client.set(
            lock_key, "1", nx=True, ex=lock_timeout
        )
        
        if not lock_acquired:
            # Wait and retry with backoff
            retries = 5
            for i in range(retries):
                await asyncio.sleep(0.5 * (i + 1))
                lock_acquired = await redis_client.set(
                    lock_key, "1", nx=True, ex=lock_timeout
                )
                if lock_acquired:
                    break
            
            if not lock_acquired:
                raise Exception(f"Could not acquire lock for session {session_id}")
        
        # Now proceed with context management
        default_context = create_custom_context(session_id, user_id, customer_tier)
        context = await middleware.get_or_create_context(session_id, default_context)
        context.update_inquiry(message)
        
        yield context
        
        # Save updated context
        await middleware.save_context(session_id, context)
        
    finally:
        # Release lock if we acquired it
        if lock_acquired:
            await redis_client.delete(lock_key)


# Optional: Unsafe context manager without locking (use only if you're certain of no concurrency)
@asynccontextmanager
async def managed_context_no_lock(
    middleware: ContextMiddleware[MyCustomAgentContext],
    session_id: str,
    user_id: str,
    message: str,
    customer_tier: str = "standard"
):
    """
    Context manager WITHOUT distributed lock. Only use if you're certain
    there won't be concurrent access to the same session.
    
    WARNING: This can lead to race conditions with multiple agents or concurrent requests!
    """
    # Create default context for this customer
    default_context = create_custom_context(session_id, user_id, customer_tier)
    
    # Get or create context using generic middleware
    context = await middleware.get_or_create_context(session_id, default_context)
    
    # Update current inquiry
    context.update_inquiry(message)
    
    try:
        yield context
    finally:
        # Save updated context
        await middleware.save_context(session_id, context)
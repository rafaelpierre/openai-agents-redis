"""
Example showing how users can create their own context implementations
using the generic ContextMiddleware.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from examples.ecommerce.llm import get_openai_chat_model
from dotenv import load_dotenv

load_dotenv()

from agents_redis import (
    DistributedContextManager,
    ContextMiddleware,
    RedisSession
)

# Custom context implementation
class MyCustomAgentContext(BaseModel):
    """Custom context implementation with different fields."""
    
    # Required fields
    user_id: str
    session_id: str
    
    # Custom business logic fields
    customer_tier: str = "standard"  # standard, premium, enterprise
    product_interest: Optional[str] = None
    previous_purchases: List[str] = Field(default_factory=list)
    support_tickets: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Custom memory contexts
    current_inquiry: Optional[str] = None
    agent_notes: List[str] = Field(default_factory=list)
    escalation_needed: bool = False
    
    # Metadata
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_updated: float = Field(default_factory=lambda: datetime.now().timestamp())
    
    # Custom methods
    def add_purchase(self, product: str) -> None:
        """Add a purchase to history."""
        self.previous_purchases.append(product)
        self._update_timestamp()
    
    def add_support_ticket(self, ticket_id: str, issue: str, priority: str = "medium") -> None:
        """Add a support ticket."""
        ticket = {
            "ticket_id": ticket_id,
            "issue": issue,
            "priority": priority,
            "created_at": datetime.now().timestamp()
        }
        self.support_tickets.append(ticket)
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
            "previous_purchases_count": len(self.previous_purchases),
            "open_tickets_count": len(self.support_tickets),
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
    
    import redis.asyncio as redis
    
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
    
    return context_middleware


# Example FastAPI usage with custom context
from fastapi import FastAPI
from agents import Agent, Runner, function_tool, RunContextWrapper

app = FastAPI()

# Initialize your custom context middleware
custom_context_middleware = None  # Will be set in startup

@app.on_event("startup")
async def startup():
    global custom_context_middleware
    custom_context_middleware = await setup_custom_context_system()

# Tool functions using your custom context
@function_tool
async def get_customer_info(wrapper: RunContextWrapper[MyCustomAgentContext]) -> str:
    """Get customer information from context."""
    context = wrapper.context
    
    info = [
        f"Customer Tier: {context.customer_tier}",
        f"Previous Purchases: {len(context.previous_purchases)}",
        f"Open Tickets: {len(context.support_tickets)}",
    ]
    
    if context.current_inquiry:
        info.append(f"Current Inquiry: {context.current_inquiry}")
    
    return "\n".join(info)

@function_tool
async def add_customer_note(
    wrapper: RunContextWrapper[MyCustomAgentContext],
    note: str
) -> str:
    """Add a note about the customer interaction."""
    context = wrapper.context
    context.add_agent_note(note)
    return f"Added note: {note}"

@function_tool
async def escalate_to_human(
    wrapper: RunContextWrapper[MyCustomAgentContext],
    reason: str
) -> str:
    """Escalate the conversation to a human agent."""
    context = wrapper.context
    context.request_escalation(reason)
    return f"Escalation requested: {reason}. A human agent will join shortly."

# Create agent with custom context type
custom_agent = Agent[MyCustomAgentContext](
    name="CustomerServiceAgent",
    tools=[get_customer_info, add_customer_note, escalate_to_human],
    instructions="You are a customer service agent. Use the tools to help customers and escalate when needed.",
    model=get_openai_chat_model()
)

@app.post("/custom-chat")
async def custom_chat_endpoint(
    session_id: str,
    user_id: str,
    message: str,
    customer_tier: str = "standard"
):
    """Chat endpoint using custom context."""
    
    # Create default context for this customer
    default_context = create_custom_context(session_id, user_id, customer_tier)
    
    # Get or create context using generic middleware
    context = await custom_context_middleware.get_or_create_context(
        session_id, default_context
    )
    
    # Update current inquiry
    context.update_inquiry(message)
    
    # Run agent with custom context
    result = await Runner.run(
        starting_agent=custom_agent,
        input=message,
        context=context,
        session = RedisSession(redis_url="redis://localhost:6379", session_id=session_id),
    )
    
    # Save updated context
    await custom_context_middleware.save_context(session_id, context)
    
    return {
        "response": result.final_output,
        "context_summary": context.get_context_summary(),
        "escalation_needed": context.escalation_needed
    }

if __name__ == "__main__":
    print("Example of custom context implementation with generic ContextMiddleware")
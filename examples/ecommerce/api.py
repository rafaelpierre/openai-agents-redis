"""
Example showing how users can create their own context implementations
using the generic ContextMiddleware.
"""

from ecommerce.context import setup_custom_context_system, managed_context
from ecommerce.agent import custom_agent
from fastapi import FastAPI
from agents import InputGuardrailTripwireTriggered, Runner
from agents_redis import RedisSession
from contextlib import asynccontextmanager

custom_context_middleware = None  # Will be set in startup
redis_client = None  # Will be set in startup

@asynccontextmanager
async def startup(app: FastAPI):
    global custom_context_middleware, redis_client
    custom_context_middleware, redis_client = await setup_custom_context_system()
    yield

app = FastAPI(lifespan=startup)


@app.post("/chat")
async def custom_chat_endpoint(
    session_id: str,
    user_id: str,
    message: str,
    customer_tier: str = "standard"
):
    """Chat endpoint using custom context."""
    
    # Use context manager with distributed lock for thread safety
    async with managed_context(
        custom_context_middleware,
        redis_client,
        session_id, 
        user_id, 
        message, 
        customer_tier
    ) as context:
        
        try:
            # Run the custom agent with the provided message and context
            result = await Runner.run(
                starting_agent=custom_agent,
                input=message,
                context=context,
                session=RedisSession(redis_url="redis://localhost:6379", session_id=session_id),
            )
        except InputGuardrailTripwireTriggered as e:
            return {
                "error": str(e),
                "context_summary": context.get_context_summary(),
                "escalation_needed": context.escalation_needed
            }
    
    return {
        "response": result.final_output,
        "context_summary": context.get_context_summary(),
        "escalation_needed": context.escalation_needed
    }

if __name__ == "__main__":
    print("Example of custom context implementation with generic ContextMiddleware")
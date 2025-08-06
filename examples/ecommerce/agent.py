from agents import Agent, RunContextWrapper, Runner, TResponseInputItem, function_tool, input_guardrail, GuardrailFunctionOutput
from pydantic import BaseModel
from ecommerce.context import MyCustomAgentContext
from ecommerce.llm import get_openai_chat_model


@function_tool
async def get_customer_info(wrapper: RunContextWrapper[MyCustomAgentContext]) -> str:
    """Get customer information from context."""
    context = wrapper.context
    
    info = [
        f"Customer Tier: {context.customer_tier}",
        f"User ID: {context.user_id}",
        f"Session ID: {context.session_id}",
        f"Region: {context.region}"
    ]
    
    if context.current_inquiry:
        info.append(f"Current Inquiry: {context.current_inquiry}")
    
    return "\n".join(info)

@function_tool
async def update_customer_region(
    wrapper: RunContextWrapper[MyCustomAgentContext],
    region: str
) -> str:
    """Update the customer's region."""
    context = wrapper.context
    if region not in ["us", "eu", "asia"]:
        raise ValueError("Invalid region. Must be 'us', 'eu', or 'asia'.")
    
    context.update_region(region)
    return f"Customer region updated to: {region}"

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


class EcommerceGuardrail(BaseModel):
    is_ecommerce_related: bool
    reasoning: str

guardrail_agent = Agent(
    name = "Guardrail Check",
    instructions="Check if the question is related to e-commerce. If it is, return True and a reasoning. If not, return False.",
    model=get_openai_chat_model(),
    output_type=EcommerceGuardrail
)


@input_guardrail
async def ecommerce_input_guardrail(
    ctx: RunContextWrapper[MyCustomAgentContext], agent: Agent, input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    
    result = await Runner.run(guardrail_agent, input=input, context=ctx.context)
    print(f"Guardrail check result: {result.final_output}")
    output = GuardrailFunctionOutput(
        output_info=result.final_output, 
        tripwire_triggered=not(result.final_output.is_ecommerce_related),
    )
    print(f"Guardrail output: {output}")
    return output

custom_agent = Agent[MyCustomAgentContext](
    name="CustomerServiceAgent",
    tools=[get_customer_info, add_customer_note, escalate_to_human, update_customer_region],
    instructions="You are a customer service agent. Use the tools to help customers and escalate when needed.",
    model=get_openai_chat_model(),
    input_guardrails=[ecommerce_input_guardrail]
)
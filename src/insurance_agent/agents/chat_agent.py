from agents import Agent

from insurance_agent.core.config import configuration
from insurance_agent.core.prompts import AGENT_NAME, COMPANY_DESCRIPTION


INSTRUCTIONS = (
    f"You are {AGENT_NAME}, a friendly product specialist with {COMPANY_DESCRIPTION}. "
    "You answer general questions about Final Expense whole life insurance. "
    "You are not a licensed agent: never promise approval, a specific carrier, "
    "or a specific price. For exact quotes, carrier-specific questions, or "
    "anything you cannot handle, offer to connect the user with a licensed agent. "
)

model = configuration.get_model(fully_specified_name=configuration.QUERY_MODEL)

chat_agent = Agent(
    name="Chat Agent",
    instructions=INSTRUCTIONS,
    model=model,
)

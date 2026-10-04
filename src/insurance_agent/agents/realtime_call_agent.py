from typing import cast

from agents.realtime import RealtimeAgent
from agents.run_context import RunContextWrapper

from insurance_agent.core.config import configuration
from insurance_agent.core.prompts import AGENT_NAME, COMPANY_DESCRIPTION, SYSTEM_PROMPT
from insurance_agent.core.utils.logger import logger_config
from insurance_agent.context.realtime_agent_context import RealtimeAgentContext
from insurance_agent.tools.websocket_tools import (
    check_websocket_connection_tool,
    disconnect_websocket_tool,
)
from insurance_agent.tools.knowledge_base_tools import search_knowledge_base_tool
from insurance_agent.tools.all_escalate_to_human_tools import escalate_to_human_tool
from insurance_agent.tools.wait_tools import wait_for_user_tool

logger = logger_config(__name__)


def _load_prompt_template() -> str:
    """The admin-editable prompt with {language} resolved; SYSTEM_PROMPT on failure.

    Imported lazily so a dashboard problem can never break call handling.
    """
    try:
        from insurance_agent.admin_dashboard.settings_store import get_settings_store

        return get_settings_store().load().resolved_system_prompt()
    except Exception as e:
        logger.error(
            f"Could not load admin prompt settings, using built-in default: {e}",
            exc_info=True,
        )
        return SYSTEM_PROMPT


async def get_realtime_agent_instructions(
    context: RunContextWrapper[RealtimeAgentContext],
    agent: RealtimeAgent[RealtimeAgentContext],
) -> str:
    """Generate dynamic instructions for the Realtime Agent based on the context.

    Placeholders are resolved with targeted str.replace (never str.format) so
    any other braces in the admin-edited template pass through untouched.
    """
    instructions = _load_prompt_template()
    instructions = instructions.replace("{name}", AGENT_NAME)
    instructions = instructions.replace("{company}", COMPANY_DESCRIPTION)

    user_info = context.context.user_info
    user_name = (user_info.user_name if user_info else None) or "Not provided"
    date_of_birth = (user_info.date_of_birth if user_info else None) or "Not provided"
    state = (user_info.state if user_info else None) or "Not provided"
    instructions = instructions.replace("{user_info.user_name}", user_name)
    instructions = instructions.replace("{user_info.date_of_birth}", date_of_birth)
    instructions = instructions.replace("{user_info.state}", state)

    if not user_info:
        return instructions

    # Define fields to check (Label, Value)
    customer_details = [
        ("Customer Name", user_info.user_name),
        ("Date of Birth", user_info.date_of_birth),
        ("State", user_info.state),
    ]

    # Build the list of lines, filtering out empty values
    info_lines = [f"- {label}: {value}" for label, value in customer_details if value]

    # If all fields were empty, return base instructions
    if not info_lines:
        return instructions

    customer_section = "\n".join(info_lines)

    return f"{instructions}\n\n# Customer Information\n{customer_section}"


model: str = cast(
    str, configuration.get_model(fully_specified_name=configuration.REALTIME_MODEL)
)

realtime_call_agent = RealtimeAgent[RealtimeAgentContext](
    name="Realtime Call Agent",
    instructions=get_realtime_agent_instructions,
    tools=[
        check_websocket_connection_tool,
        disconnect_websocket_tool,
        search_knowledge_base_tool,
        escalate_to_human_tool,
        wait_for_user_tool,
    ],
)

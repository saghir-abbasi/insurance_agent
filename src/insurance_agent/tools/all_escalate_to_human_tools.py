"""Tool the realtime agent calls to transfer the call to a licensed agent (LA).

The agent invokes `escalate_to_human` when a qualified customer is ready for
the licensed agent (end of the first-agent script), or earlier when the
customer asks for a licensed agent / real person or needs an exact quote,
carrier, or approval answer. The tool sends an `escalate_to_human` event over the FastAPI WebSocket back
to the AGI client (callapi.py), which sets the `ESCALATE` and
`ESCALATE_REASON` channel variables so the Asterisk dialplan can transfer
the call. The tool never closes the WebSocket itself: the AGI side quiesces
playback and ends the session once it receives the event.
"""

import re

from agents import function_tool
from fastapi.websockets import WebSocketState

from insurance_agent.context.realtime_agent_context import RealtimeAgentContextWrapper
from insurance_agent.core.config import configuration
from insurance_agent.core.utils.logger import logger_config
from insurance_agent.tools.websocket_tools import close_call, wait_for_playback

logger = logger_config(__name__)


def _sanitize_reason(reason: str | None) -> str:
    """Collapse the reason to a single quote-free line.

    callapi.py forwards the reason into an Asterisk `SET VARIABLE` command,
    where newlines or quotes would corrupt the AGI protocol. It sanitizes
    again on its side, but don't rely on that.
    """
    safe = (reason or "Transfer to licensed agent.").strip()
    safe = re.sub(r"[\r\n\"']+", " ", safe)
    return re.sub(r"\s+", " ", safe).strip()


def _with_customer_name(context: RealtimeAgentContextWrapper, reason: str) -> str:
    """Prefix the summary with the caller's name so the licensed agent sees it first."""
    user_info = context.context.user_info
    name = (user_info.user_name if user_info else None) or ""
    name = _sanitize_reason(name.replace("_", " ")) if name.strip() else "Not provided"
    return f"Customer: {name} | {reason}"


@function_tool(name_override="escalate_to_human", failure_error_function=None)
async def escalate_to_human_tool(
    context: RealtimeAgentContextWrapper,
    reason: str,
) -> str:
    """Transfer the call to a licensed insurance agent.

    Call this when the customer has completed the qualification and product
    explanation and wants to explore coverage, or earlier if the customer
    asks for a licensed agent or a real person, or insists on an exact
    quote, a specific carrier, or an approval decision. Speak the transfer
    line BEFORE calling this tool, and do not end the call yourself
    afterwards - the transfer system takes over from here.

    Args:
        reason: A single line starting with why the call is being transferred,
            followed by the key qualification answers collected (for example,
            "qualified lead: TX 75001, non-smoker, checking, burial, first
            policy, health all no, 2 meds (blood pressure)" or "caller
            requested licensed agent before qualification").

    Returns:
        A short status string describing whether the escalation event was
        sent to the call client.
    """
    websocket = context.context.websocket
    if websocket.client_state != WebSocketState.CONNECTED:
        logger.warning("Escalate tool called but call websocket is not connected.")
        return "Could not escalate: call connection already closed."

    safe_reason = _with_customer_name(context, _sanitize_reason(reason))

    if not configuration.LA_TRANSFER_ENABLED:
        # No licensed agent is connected yet: let the transfer line finish
        # playing, hand over the lead summary, then end the call.
        await wait_for_playback(context)

    try:
        await websocket.send_json(
            {
                "event": "escalate_to_human",
                "reason": safe_reason,
            }
        )
    except Exception as e:
        logger.error(f"Failed to send escalate_to_human event: {e}", exc_info=True)
        return "Could not escalate: failed to send escalation event."

    logger.info(f"Licensed-agent transfer event sent. Reason: {safe_reason}")

    if not configuration.LA_TRANSFER_ENABLED:
        await close_call(context, "transferred to licensed agent (no live agent connected)")
        return "Lead summary handed over and call ended. Do not speak again."

    return (
        "Transfer request sent. The call will be connected to a licensed agent; "
        "do not end the call."
    )


all_escalate_to_human_tools = [escalate_to_human_tool]

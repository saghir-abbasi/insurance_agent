"""No-op tool letting the realtime model end a turn without speaking.

Recommended by the OpenAI Realtime-2 prompting guide: when the latest audio is
silence, background noise, hold music, TV audio, or side conversation, the
model calls this instead of interjecting ("I'm here", "I didn't catch that").
"""

from agents import function_tool


@function_tool(name_override="wait_for_user", failure_error_function=None)
async def wait_for_user_tool() -> str:
    """Call when the latest audio doesn't need a spoken response: silence, background noise, hold music, TV audio, side conversation, or speech not addressed to the assistant. Helps end the turn without a spoken reply."""
    return "No response needed. Stay silent and keep listening for the user."

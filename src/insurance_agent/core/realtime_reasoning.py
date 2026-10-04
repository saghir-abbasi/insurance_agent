"""Injects reasoning effort into realtime session configs.

openai-agents 0.4.2 predates gpt-realtime-2 and has no reasoning field in
``RealtimeSessionModelSettings``, so the field is injected here instead:
``RealtimeSessionCreateRequest`` allows extra fields (``extra="allow"``) and
the SDK serializes them into the ``session.update`` payload unchanged.

Remove this module once openai-agents is upgraded to a version whose realtime
config supports reasoning natively.
"""

from typing import Any

from agents.realtime.openai_realtime import OpenAIRealtimeWebSocketModel

from insurance_agent.core.config import configuration
from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

_original_get_session_config = OpenAIRealtimeWebSocketModel._get_session_config


def _get_session_config_with_reasoning(self: Any, model_settings: Any) -> Any:
    session_config = _original_get_session_config(self, model_settings)
    effort = configuration.REALTIME_REASONING_EFFORT
    if effort != "off":
        session_config.reasoning = {"effort": effort}
    return session_config


def apply_reasoning_effort_patch() -> None:
    """Idempotently patch the realtime model to send reasoning effort."""
    if (
        OpenAIRealtimeWebSocketModel._get_session_config
        is _get_session_config_with_reasoning
    ):
        return
    OpenAIRealtimeWebSocketModel._get_session_config = (  # type: ignore[method-assign]
        _get_session_config_with_reasoning
    )
    logger.info(
        "Realtime reasoning effort patch applied "
        f"(REALTIME_REASONING_EFFORT={configuration.REALTIME_REASONING_EFFORT})"
    )

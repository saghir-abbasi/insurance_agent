from pydantic import BaseModel
from fastapi.websockets import WebSocket
from agents import RunContextWrapper


class UserInfo(BaseModel):
    """Current customer information."""
    user_id: str | None = None
    user_name: str | None = None
    date_of_birth: str | None = None
    state: str | None = None


class RealtimeAgentContext(BaseModel):
    websocket: WebSocket
    """The WebSocket connection for this session."""

    session_id: str
    """Optional session ID for tracking."""

    user_info: UserInfo | None = None
    """Optional user information passed from the connection."""

    class Config:
        arbitrary_types_allowed = True


RealtimeAgentContextWrapper = RunContextWrapper[RealtimeAgentContext]

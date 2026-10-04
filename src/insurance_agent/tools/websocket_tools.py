import websockets
import asyncio
from agents import function_tool

from insurance_agent.context.realtime_agent_context import RealtimeAgentContextWrapper


@function_tool(
    name_override="check_websocket_connection_tool", failure_error_function=None
)
async def check_websocket_connection_tool(context: RealtimeAgentContextWrapper) -> str:
    """Check if the WebSocket connection is still open."""
    websocket = context.context.websocket
    if websocket.state != websockets.State.CLOSED:
        return "WebSocket connection is open."

    return "WebSocket connection is closed."


async def wait_for_playback(context: RealtimeAgentContextWrapper) -> None:
    """Let the agent's last spoken audio finish playing before acting on the call."""
    from insurance_agent.api.v1.routes.realtime import manager

    elapsed_ms = (
        manager.playback_trackers[context.context.session_id]
        .get_state()
        .get("elapsed_ms")
    ) or 0.0
    elapsed_seconds = elapsed_ms / 1000
    print(f"Disconnecting websocket in {elapsed_seconds - 1} seconds")
    await asyncio.sleep(elapsed_seconds - 1)


async def close_call(context: RealtimeAgentContextWrapper, reason: str | None) -> str:
    """Send the disconnect event and close the call WebSocket."""
    websocket = context.context.websocket
    if websocket.state != websockets.State.CLOSED:
        await websocket.send_json(
            {
                "event": "disconnect",
                "reason": reason,
            }
        )
        await websocket.close(reason=reason)
        return "WebSocket connection closed."

    return "WebSocket connection already closed."


@function_tool(name_override="disconnect_websocket_tool", failure_error_function=None)
async def disconnect_websocket_tool(
    context: RealtimeAgentContextWrapper,
    reason: str | None = None,
) -> str:
    """End the Call Session by closing the WebSocket connection."""
    await wait_for_playback(context)
    return await close_call(context, reason)


all_websocket_tools = [check_websocket_connection_tool, disconnect_websocket_tool]

from typing import Any, Literal
import json
import base64
import asyncio

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket

from agents.realtime import (
    RealtimeRunner,
    RealtimeRunConfig,
    RealtimeSessionModelSettings,
    RealtimeTurnDetectionConfig,
    RealtimeSessionEvent,
    RealtimeModelUserInputMessage,
    RealtimeModelInputTextContent,
    RealtimeModelConfig,
    RealtimePlaybackTracker,
)

from insurance_agent.realtime_websocket_manager import RealtimeWebSocketManager
from insurance_agent.agents.realtime_call_agent import (
    realtime_call_agent,
    model as realtime_model,
)
from insurance_agent.context.realtime_agent_context import (
    RealtimeAgentContext,
    UserInfo,
)
from insurance_agent.core.utils.logger import logger_config
from insurance_agent.core.config import EnvironmentEnum, configuration
from insurance_agent.core.realtime_reasoning import apply_reasoning_effort_patch

logger = logger_config(__name__)

apply_reasoning_effort_patch()

router = APIRouter()


def _current_voice() -> str:
    """Voice from the admin settings store; falls back to the .env default.

    Read per call so a dashboard save takes effect on the next call without a
    server restart. A settings problem must never block call handling.
    """
    try:
        from insurance_agent.admin_dashboard.settings_store import get_settings_store

        return get_settings_store().load().voice_id
    except Exception as e:
        logger.error(f"Could not load voice from admin settings: {e}", exc_info=True)
        return configuration.REALTIME_VOICE


AudioFormat = Literal["pcm16", "g711_alaw"]


def _default_audio_format() -> AudioFormat:
    """Asterisk (production) speaks G.711 A-law; local/browser testing uses PCM16."""
    if configuration.ENVIRONMENT == EnvironmentEnum.production:
        return "g711_alaw"
    return "pcm16"


def build_model_settings(
    audio_format: AudioFormat | None = None,
) -> RealtimeSessionModelSettings:
    """Per-call model settings (voice comes from the admin dashboard).

    `audio_format` lets a client pick its codec per call (the browser UI
    always sends PCM16); otherwise the ENVIRONMENT default applies.
    """
    audio_format = audio_format or _default_audio_format()
    return RealtimeSessionModelSettings(
        model_name=realtime_model,
        voice=_current_voice(),
        modalities=["audio"],
        turn_detection=RealtimeTurnDetectionConfig(
            type="server_vad",  # https://platform.openai.com/docs/guides/realtime-vad
            # threshold=0.5,  # Activation threshold (0 to 1). A higher threshold will require louder audio to activate the model, and thus might perform better in noisy environments.
            # prefix_padding_ms=500,  # Amount of audio (in milliseconds) to include before the VAD detected speech.
            silence_duration_ms=100,  # Duration of silence (in milliseconds) to detect speech stop. With shorter values turns will be detected more quickly.
            create_response=True,
            interrupt_response=True,
        ),
        input_audio_transcription={
            "model": configuration.REALTIME_TRANSCRIBE_MODEL,
        },
        input_audio_format=audio_format,
        output_audio_format=audio_format,
        input_audio_noise_reduction={
            "type": "near_field",
        },
    )

INITIAL_CONVERSATION_PROMPT = "Hello"

AUDIO_TRANSCRIPTIONS = {}


async def event_handler(
    websocket: WebSocket,
    event: RealtimeSessionEvent,
    session_id: str | None = None,
):
    """Handles Realtime session events and sends them to the WebSocket."""
    base_event: dict[str, Any] = {
        "event": event.type,
    }

    # Initialize state for this connection if needed
    if session_id not in AUDIO_TRANSCRIPTIONS:
        AUDIO_TRANSCRIPTIONS[session_id] = ""

    if event.type == "audio_interrupted":
        base_event["event"] = "clear"
        await websocket.send_json(base_event)

    elif event.type == "audio":
        audio = base64.b64encode(event.audio.data).decode("utf-8")
        base_event["event"] = "media"
        base_event["media"] = {"payload": audio}
        await websocket.send_json(base_event)

    # Handling Audio Transcription Events
    elif event.type == "raw_model_event":
        if event.data.type == "input_audio_transcription_completed":
            message = {
                "event": "user_transcript",
                "transcript": event.data.transcript,
            }
            await websocket.send_json(message)
        elif event.data.type == "transcript_delta":
            message = {
                "event": "assistant_transcript_delta",
                "transcript": event.data.delta,
            }
            await websocket.send_json(message)
            AUDIO_TRANSCRIPTIONS[session_id] += event.data.delta
        elif event.data.type == "audio_done":
            message = {
                "event": "assistant_transcript",
                "transcript": AUDIO_TRANSCRIPTIONS[session_id],  # Read from dictionary
            }
            await websocket.send_json(message)
            del AUDIO_TRANSCRIPTIONS[session_id]


manager = RealtimeWebSocketManager(event_handler=event_handler)


@router.websocket("/call-session/{session_id}")
async def handle_call_session(
    websocket: WebSocket,
    session_id: str,
    user_id: str | None = None,
    user_name: str | None = None,
    date_of_birth: str | None = None,
    state: str | None = None,
    audio_format: AudioFormat | None = None,
):
    logger.info(f"SERVER ===> Client {session_id} connected")

    # Built per call so admin dashboard changes (voice) apply to new calls.
    model_settings = build_model_settings(audio_format)

    runner = RealtimeRunner(
        starting_agent=realtime_call_agent,
        config=RealtimeRunConfig(
            model_settings=model_settings,
        ),
    )

    context = RealtimeAgentContext(
        websocket=websocket,
        session_id=session_id,
        user_info=UserInfo(
            user_id=user_id,
            user_name=user_name,
            date_of_birth=date_of_birth,
            state=state,
        ),
    )
    await manager.connect(
        websocket,
        session_id,
        runner=runner,
        run_model_config=RealtimeModelConfig(
            initial_model_settings=model_settings,
        ),
        context=context,
        playback_tracker=RealtimePlaybackTracker(),
    )
    try:
        # Send initial message to model to start the conversation
        await manager.active_sessions[session_id].send_message(
            message=RealtimeModelUserInputMessage(
                role="user",
                type="message",
                content=[
                    RealtimeModelInputTextContent(
                        type="input_text",
                        text=INITIAL_CONVERSATION_PROMPT,
                    )
                ],
            )
        )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                data = json.loads(message)

                if data["event"] == "media":
                    audio_bytes = base64.b64decode(data["media"]["payload"])
                    await manager.send_audio(session_id, audio_bytes)

            except asyncio.TimeoutError:
                logger.warning(
                    f"SERVER ===> No message from session {session_id} in 30s. Closing connection."
                )
                await websocket.close()
                break

    except WebSocketDisconnect:
        logger.info(f"SERVER ===> Client {session_id} disconnected")
    except Exception as e:
        logger.error(f"SERVER ===> Unexpected error: {e}")
    finally:
        await manager.disconnect(session_id)

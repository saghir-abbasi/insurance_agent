import asyncio
import inspect
import json
import base64
from typing import Any, Callable, cast
from dataclasses import dataclass, field

from fastapi import WebSocket

from agents import TContext
from agents.realtime import (
    RealtimeRunner,
    RealtimeSession,
    RealtimeModelConfig,
    RealtimeUserInput,
    RealtimeSessionEvent,
    RealtimePlaybackTracker,
    RealtimeAudioFormat,
)

from insurance_agent.core.config import configuration
from insurance_agent.core.utils.logger import logger_config
from insurance_agent.core.utils.types import MaybeAwaitable

logger = logger_config(__name__)


def calculate_audio_length_ms(
    format: RealtimeAudioFormat | None, audio_bytes: bytes
) -> float:
    """
    Calculate audio duration in milliseconds based on format.

    PCM16: 16-bit samples (2 bytes per sample) at 24kHz
    G.711 (A-law/μ-law): 8-bit samples (1 byte per sample) at 8kHz
    """
    if format and isinstance(format, str) and format.startswith("g711"):
        # G.711: 8-bit samples (1 byte per sample) at 8kHz
        sample_rate = 8000
        bytes_per_sample = 1
    else:
        # PCM16: 16-bit samples (2 bytes per sample) at 24kHz
        sample_rate = 24000
        bytes_per_sample = 2

    num_samples = len(audio_bytes) // bytes_per_sample
    duration_seconds = num_samples / sample_rate
    duration_ms = duration_seconds * 1000

    return duration_ms


@dataclass
class RealtimeWebSocketManager:
    """Manages WebSocket connections for Realtime sessions with continuous operation."""

    runner: RealtimeRunner | None = None
    """The RealtimeRunner instance used to manage Realtime sessions."""

    run_model_config: RealtimeModelConfig | None = None
    """Optional model configuration for the Realtime session."""

    active_sessions: dict[str, RealtimeSession] = field(default_factory=dict)
    """Active Realtime sessions keyed by session ID."""

    session_contexts: dict[str, Any] = field(default_factory=dict)
    """Contexts for active Realtime sessions keyed by session ID."""

    websockets: dict[str, WebSocket] = field(default_factory=dict)
    """WebSocket connections keyed by session ID."""

    event_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    """Event processing tasks keyed by session ID."""

    event_handler: (
        Callable[
            [WebSocket, RealtimeSessionEvent, str | None],
            MaybeAwaitable,
        ]
        | None
    ) = None
    """
    Optional event handler for Realtime session events.

    Args:
        websocket (WebSocket): The WebSocket connection.
        event (RealtimeSessionEvent): The Realtime session event.
        session_id (str | None): The session ID associated with the event.
    """

    playback_trackers: dict[str, RealtimePlaybackTracker] = field(default_factory=dict)
    """Playback trackers keyed by session ID."""

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        runner: RealtimeRunner,
        run_model_config: RealtimeModelConfig | None = None,
        context: TContext | None = None,
        playback_tracker: RealtimePlaybackTracker | None = None,
    ):
        """Accepts a WebSocket connection and initializes a Realtime session."""
        await websocket.accept()
        self.websockets[session_id] = websocket
        logger.info(f"WebSocket accepted for session {session_id}")

        if not configuration.OPENAI_API_KEY:
            raise ValueError("OpenAI API key is not configured.")

        try:
            if playback_tracker:
                self.playback_trackers[session_id] = playback_tracker

            self.runner = runner
            if run_model_config:
                run_model_config = RealtimeModelConfig(
                    **run_model_config,  # type: ignore
                    api_key=configuration.OPENAI_API_KEY,
                    playback_tracker=playback_tracker,  # type: ignore
                )
                self.run_model_config = run_model_config

            session_context = await runner.run(
                context=context,
                model_config=run_model_config
                or RealtimeModelConfig(
                    api_key=configuration.OPENAI_API_KEY,
                    playback_tracker=playback_tracker,  # type: ignore
                ),
            )

            session = await session_context.__aenter__()

            self.active_sessions[session_id] = session
            self.session_contexts[session_id] = session_context

            # Start event processing task
            event_task = asyncio.create_task(
                self._process_events(session_id), name=f"event_processor_{session_id}"
            )
            self.event_tasks[session_id] = event_task

        except Exception as e:
            logger.error(f"Error initializing session {session_id}: {e}", exc_info=True)
            raise

    async def disconnect(self, session_id: str):
        """Disconnects a WebSocket and cleans up the Realtime session."""
        logger.info(f"Disconnecting session {session_id}")

        # Cancel event processing task
        if session_id in self.event_tasks:
            task = self.event_tasks[session_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.event_tasks[session_id]

        # Clean up session context
        if session_id in self.session_contexts:
            try:
                await self.session_contexts[session_id].__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error exiting session context: {e}")
            del self.session_contexts[session_id]

        # Remove session
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

        # Close websocket if still open
        if session_id in self.websockets:
            websocket = self.websockets[session_id]
            try:
                if websocket.client_state.name != "DISCONNECTED":
                    await websocket.close()
            except Exception as e:
                logger.error(f"Error closing websocket: {e}")
            del self.websockets[session_id]

        logger.info(f"Session {session_id} fully disconnected")

    async def send_audio(self, session_id: str, audio_bytes: bytes):
        """Sends audio data to the Realtime session."""
        if session_id in self.active_sessions:
            try:
                await self.active_sessions[session_id].send_audio(audio_bytes)
            except Exception as e:
                logger.error(f"Error sending audio to session {session_id}: {e}")
        else:
            logger.warning(f"Attempted to send audio to inactive session {session_id}")

    async def send_message(self, session_id: str, message: RealtimeUserInput):
        """Sends a message to the Realtime session."""
        if session_id in self.active_sessions:
            try:
                await self.active_sessions[session_id].send_message(message)
            except Exception as e:
                logger.error(f"Error sending message to session {session_id}: {e}")
        else:
            logger.warning(
                f"Attempted to send message to inactive session {session_id}"
            )

    async def _process_events(self, session_id: str):
        """Processes events from the Realtime session and sends them to the WebSocket."""
        try:
            session = self.active_sessions.get(session_id)
            websocket = self.websockets.get(session_id)

            if not session or not websocket:
                logger.error(f"Session or websocket not found for {session_id}")
                return

            event_count = 0

            async for event in session:
                event_count += 1

                if event.type == "audio":
                    audio_format: RealtimeAudioFormat = "pcm16"
                    if self.run_model_config:
                        audio_format = cast(
                            RealtimeAudioFormat,
                            self.run_model_config.get("initial_model_settings", {}).get(
                                "output_audio_format", "pcm16"
                            ),
                        )
                    audio_ms = calculate_audio_length_ms(audio_format, event.audio.data)
                    self.playback_trackers[session_id].on_play_ms(
                        item_id=event.item_id,
                        item_content_index=event.content_index,
                        ms=audio_ms,
                    )

                try:
                    if self.event_handler:
                        # Use custom event handler
                        if inspect.iscoroutinefunction(self.event_handler):
                            await self.event_handler(websocket, event, session_id)
                        else:
                            self.event_handler(websocket, event, session_id)
                    else:
                        # Use default serialization
                        event_data = await self._serialize_event(event)
                        await websocket.send_text(json.dumps(event_data))
                except Exception as e:
                    logger.error(
                        f"Error handling event for session {session_id}: {e}",
                        exc_info=True,
                    )
                    continue

            logger.info(
                f"Event processing ended for session {session_id} (processed {event_count} events)"
            )

        except asyncio.CancelledError:
            logger.info(f"Event processing cancelled for session {session_id}")
            raise
        except Exception as e:
            logger.error(
                f"Error in event processing loop for session {session_id}: {e}",
                exc_info=True,
            )

    async def _serialize_event(
        self,
        event: RealtimeSessionEvent,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Serializes a RealtimeSessionEvent to a dictionary."""
        base_event: dict[str, Any] = {
            "type": event.type,
        }

        if event.type == "agent_start":
            base_event["agent"] = event.agent.name
        elif event.type == "agent_end":
            base_event["agent"] = event.agent.name
        elif event.type == "handoff":
            base_event["from"] = event.from_agent.name
            base_event["to"] = event.to_agent.name
        elif event.type == "tool_start":
            base_event["tool"] = event.tool.name
        elif event.type == "tool_end":
            base_event["tool"] = event.tool.name
            base_event["output"] = str(event.output)
        elif event.type == "audio":
            base_event["audio"] = base64.b64encode(event.audio.data).decode("utf-8")
        elif event.type == "audio_interrupted":
            pass
        elif event.type == "audio_end":
            pass
        elif event.type == "history_updated":
            base_event["history"] = [
                item.model_dump(mode="json") for item in event.history
            ]
        elif event.type == "history_added":
            pass
        elif event.type == "guardrail_tripped":
            base_event["guardrail_results"] = [
                {"name": result.guardrail.name} for result in event.guardrail_results
            ]
        elif event.type == "raw_model_event":
            base_event["raw_model_event"] = {
                "type": event.data.type,
            }
        elif event.type == "error":
            base_event["error"] = (
                str(event.error) if hasattr(event, "error") else "Unknown error"
            )
        elif event.type == "input_audio_timeout_triggered":
            base_event["input_audio_timeout_triggered"] = {
                "type": event.type,
                "info": event.info,
            }

        return base_event

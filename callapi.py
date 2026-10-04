#!/var/lib/asterisk/agi-bin/.venv/bin/python

"""
updated on 6-7-2026
Asterisk AGI script for real-time AI voice agent integration.
Handles bidirectional audio streaming with interrupt support and multiple calls.
* transcript are saved now. change base_dir accordingly as needed
* transcripts_agent is activated at the end of the call to refine the transcript and generate a summary. check run_refinement.py for details.
* mock_user_data is now removed. you can integrate your user database in the get_call_arguments function to fetch real user data based on the call info (caller ID, etc.)
* transfer to a licensed agent (escalate_to_human) is implemented by setting AGI variables and returning control to the dialplan, where you can handle the transfer logic based on those variables.
* add to blacklist logic is implemented
* optional 5th dialplan arg: customer's state, used by the agent to confirm the customer's location
"""

import asyncio

# audioop was removed from the stdlib in Python 3.13; install "audioop-lts"
# in the AGI venv to keep this import working (pip install audioop-lts).
import audioop
import base64
import json
import logging
import os
import random
import subprocess
import sys
import threading
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import websockets
from asterisk.agi import AGI  # type: ignore

# MOCK_USERS_DATA = [
#     {
#         "id": 1,
#         "name": "Jamaal_Lone",
#         "date_of_birth":"20_May_1974",
#     },
# ]


# Configuration
@dataclass
class AudioConfig:
    """Audio configuration constants."""

    # EAGI (Asterisk) settings
    eagi_fd: int  # Now dynamic per call
    EAGI_CHUNK_SIZE: int = 640
    EAGI_RATE: int = 8000
    EAGI_WIDTH: int = 2
    EAGI_CHANNELS: int = 1

    # AI Input settings (G.711 A-law at 8kHz)
    AI_INPUT_RATE: int = 8000
    AI_INPUT_FORMAT: str = "g711_alaw"

    # AI Output settings (G.711 A-law at 8kHz)
    AI_OUTPUT_RATE: int = 8000
    AI_OUTPUT_FORMAT: str = "g711_alaw"

    # Playback settings (PCM for Asterisk playback)
    PLAYBACK_RATE: int = 8000
    PLAYBACK_WIDTH: int = 2
    PLAYBACK_CHANNELS: int = 1


@dataclass
class PathConfig:
    """File path configuration - now unique per call."""

    call_id: str
    # base directory for calls voice and transcript saving
    base_dir: str = "/var/lib/asterisk/agi-bin/insurance_agent/calls"

    # These will be set in __post_init__
    call_dir: str = field(init=False)
    INPUT_FILE: str = field(init=False)
    OUTPUT_FILE: str = field(init=False)
    LOG_FILE: str = field(init=False)
    TEMP_DIR: str = field(init=False)
    TRANSCRIPT_FILE: str = field(init=False)

    def __post_init__(self):
        """Initialize call-specific paths."""
        self.call_dir = f"{self.base_dir}/{self.call_id}"
        self.TEMP_DIR = self.call_dir
        self.INPUT_FILE = f"{self.call_dir}/input.wav"
        self.OUTPUT_FILE = f"{self.call_dir}/output.wav"
        self.LOG_FILE = f"{self.call_dir}/debug.log"
        self.TRANSCRIPT_FILE = f"{self.call_dir}/transcript.json"

        # Create call-specific directory
        try:
            Path(self.call_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error creating call directory: {e}", file=sys.stderr)

    def cleanup(self):
        """Clean up call-specific files and directory."""
        pass
        # try:
        #     import shutil

        #     if Path(self.call_dir).exists():
        #         shutil.rmtree(self.call_dir, ignore_errors=True)
        # except Exception as e:
        #     print(f"Error cleaning up call directory: {e}", file=sys.stderr)


class EventType(Enum):
    """WebSocket event types."""

    MEDIA = "media"
    CLEAR = "clear"
    DISCONNECT = "disconnect"
    USER_TRANSCRIPT = "user_transcript"
    ASSISTANT_TRANSCRIPT = "assistant_transcript"
    ASSISTANT_TRANSCRIPT_DELTA = "assistant_transcript_delta"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class AudioTrackManager:
    """Manages audio tracks for interrupt handling"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.current_track_id: str = self._generate_track_id()
        self._lock = threading.Lock()

    def _generate_track_id(self) -> str:
        """Generate a new unique track ID."""
        return uuid.uuid4().hex

    def new_track(self) -> str:
        """Start a new track (used when clear event received)."""
        with self._lock:
            self.current_track_id = self._generate_track_id()
            self.logger.info(
                f"[TrackManager]: ðŸ”„ New track: {self.current_track_id[:8]}"
            )
            return self.current_track_id

    def get_current_track(self) -> str:
        """Get the current track ID."""
        with self._lock:
            return self.current_track_id


class PlaybackManager:
    """
    Manages audio playback WITHOUT QUEUING.
    Plays chunks directly with track-based interrupt support.
    """

    def __init__(
        self,
        agi: AGI,
        config: PathConfig,
        track_manager: AudioTrackManager,
        logger: logging.Logger,
    ):
        self.agi = agi
        self.config = config
        self.track_manager = track_manager
        self.logger = logger
        self.is_running: bool = False
        self._playback_lock = asyncio.Lock()
        self._currently_playing: bool = False

    async def start(self):
        """Start the playback manager."""
        self.is_running = True
        self.logger.info("[PlaybackManager]: Started (queueless mode)")

    async def stop(self):
        """Stop the playback manager gracefully."""
        self.logger.info("[PlaybackManager]: Stopping...")
        self.is_running = False
        self.logger.info("[PlaybackManager]: Stopped")

    async def play_chunk(self, audio_chunk: bytes, track_id: str):
        """
        Play audio chunk directly WITHOUT queueing.
        Checks track validity before playing.
        """
        if not self.is_running:
            return

        # Check if this chunk belongs to the current track
        current_track = self.track_manager.get_current_track()
        if track_id != current_track:
            self.logger.info(
                f"[PlaybackManager]: â­ï¸ Skipping chunk "
                f"(old track {track_id[:8]}, current {current_track[:8]})"
            )
            return

        # Use lock to prevent concurrent playback
        async with self._playback_lock:
            # Double-check track hasn't changed while waiting for lock
            current_track = self.track_manager.get_current_track()
            if track_id != current_track:
                self.logger.info(
                    f"[PlaybackManager]: â­ï¸ Track changed while waiting, skipping"
                )
                return

            await self._play_chunk_internal(audio_chunk, track_id)

    async def _play_chunk_internal(self, chunk: bytes, track_id: str):
        """Internal method to play a chunk."""
        chunk_id = uuid.uuid4().hex[:8]
        temp_file = f"{self.config.TEMP_DIR}/chunk_{chunk_id}.wav"
        file_name_without_ext = str(Path(temp_file).with_suffix(""))

        try:
            # Write audio file as PCM
            with wave.open(temp_file, "wb") as wf:
                wf.setnchannels(AudioConfig.PLAYBACK_CHANNELS)
                wf.setsampwidth(AudioConfig.PLAYBACK_WIDTH)
                wf.setframerate(AudioConfig.PLAYBACK_RATE)
                wf.writeframes(chunk)

            # Final check before playing
            if track_id != self.track_manager.get_current_track():
                self.logger.info(
                    f"[PlaybackManager]: Track changed before play, aborting"
                )
                return

            self._currently_playing = True
            self.logger.debug(f"[PlaybackManager]: ðŸ”Š Playing chunk {chunk_id}")

            # Play in executor to not block event loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self.agi.stream_file(file_name_without_ext)
            )

        except Exception as e:
            self.logger.error(f"[PlaybackManager]: Error playing chunk: {e}")
        finally:
            self._currently_playing = False
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception as e:
                self.logger.debug(f"[PlaybackManager]: Cleanup error: {e}")


class AudioStreamer:
    """Handles streaming audio from Asterisk to the AI backend."""

    def __init__(
        self, audio_config: AudioConfig, path_config: PathConfig, logger: logging.Logger
    ):
        self.audio_config = audio_config
        self.path_config = path_config
        self.logger = logger
        self.is_running: bool = False
        self._fd_registered: bool = False

    async def stream_to_backend(self, ws: websockets.ClientConnection):
        """Stream audio from Asterisk to backend in G.711 A-law format."""
        if ws.state != websockets.protocol.State.OPEN:
            self.logger.error("[AudioStreamer]: WebSocket not open")
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.is_running = True

        def on_data():
            """Callback for reading from EAGI file descriptor."""
            try:
                chunk = os.read(
                    self.audio_config.eagi_fd, self.audio_config.EAGI_CHUNK_SIZE
                )
                if chunk:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                else:
                    self._unregister_fd(loop)
                    loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as e:
                self.logger.error(f"[AudioStreamer]: FD read error: {e}")
                self._unregister_fd(loop)
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Register FD reader
        try:
            loop.add_reader(self.audio_config.eagi_fd, on_data)
            self._fd_registered = True
            self.logger.info(
                f"[AudioStreamer]: Started reading from FD {self.audio_config.eagi_fd}"
            )
        except Exception as e:
            self.logger.error(f"[AudioStreamer]: Failed to register FD: {e}")
            self.is_running = False
            return

        # Stream audio to backend
        try:
            with wave.open(self.path_config.INPUT_FILE, "wb") as wf:
                wf.setnchannels(self.audio_config.EAGI_CHANNELS)
                wf.setsampwidth(self.audio_config.EAGI_WIDTH)
                wf.setframerate(self.audio_config.EAGI_RATE)

                while self.is_running:
                    try:
                        chunk = await asyncio.wait_for(queue.get(), timeout=2.0)
                    except asyncio.TimeoutError:
                        if ws.state != websockets.protocol.State.OPEN:
                            self.logger.info(
                                "[AudioStreamer]: WebSocket closed, stopping"
                            )
                            break
                        continue

                    if chunk is None:
                        break

                    # Write original PCM to file for debugging
                    wf.writeframes(chunk)

                    # Convert PCM (16-bit) to G.711 A-law (8-bit)
                    alaw_chunk = audioop.lin2alaw(chunk, self.audio_config.EAGI_WIDTH)

                    if self.is_running and ws.state == websockets.protocol.State.OPEN:
                        try:
                            payload = base64.b64encode(alaw_chunk).decode("utf-8")
                            message = {
                                "event": "media",
                                "media": {"payload": payload},
                            }
                            await ws.send(json.dumps(message))
                            self.logger.debug(
                                f"[AudioStreamer]: Sent {len(alaw_chunk)} bytes (G.711 A-law)"
                            )
                        except websockets.ConnectionClosed:
                            self.logger.info(
                                "[AudioStreamer]: Connection closed during send"
                            )
                            break
                        except Exception as e:
                            self.logger.error(f"[AudioStreamer]: Send error: {e}")
                            break

        finally:
            self._unregister_fd(loop)
            self.is_running = False
            self.logger.info("[AudioStreamer]: Stopped")

    def _unregister_fd(self, loop: asyncio.AbstractEventLoop):
        """Safely unregister file descriptor reader."""
        if self._fd_registered:
            try:
                loop.remove_reader(self.audio_config.eagi_fd)
                self._fd_registered = False
            except Exception as e:
                self.logger.error(f"[AudioStreamer]: Error unregistering FD: {e}")

    async def stop(self):
        """Stop the audio streamer."""
        self.is_running = False


class AudioReceiver:
    """Handles receiving audio from the AI backend."""

    def __init__(
        self,
        agi: AGI,
        audio_config: AudioConfig,
        path_config: PathConfig,
        playback_manager: PlaybackManager,
        track_manager: AudioTrackManager,
        logger: logging.Logger,
    ):
        self.agi = agi
        self.audio_config = audio_config
        self.path_config = path_config
        self.playback_manager = playback_manager
        self.track_manager = track_manager
        self.logger = logger
        self.is_running: bool = False

    async def receive_from_backend(self, ws: websockets.ClientConnection):
        """Receive audio and events from backend."""
        self.is_running = True

        try:
            with wave.open(self.path_config.OUTPUT_FILE, "wb") as wf:
                wf.setnchannels(AudioConfig.PLAYBACK_CHANNELS)
                wf.setsampwidth(AudioConfig.PLAYBACK_WIDTH)
                wf.setframerate(AudioConfig.PLAYBACK_RATE)

                while self.is_running:
                    try:
                        message = await ws.recv()

                        try:
                            data: dict = json.loads(message)
                        except json.JSONDecodeError as e:
                            self.logger.error(
                                f"[AudioReceiver]: JSON decode error: {e}"
                            )
                            continue

                        event = data.get("event")
                        self.logger.debug(f"[AudioReceiver]: Received event: {event}")

                        if event == EventType.CLEAR.value:
                            await self._handle_clear_event()
                        elif event == EventType.MEDIA.value:
                            await self._handle_media_event(data, wf)
                        elif event in [
                            EventType.USER_TRANSCRIPT.value,
                            EventType.ASSISTANT_TRANSCRIPT.value,
                            EventType.ASSISTANT_TRANSCRIPT_DELTA.value,
                        ]:
                            await self._handle_transcript_event(data)
                        elif event == EventType.ESCALATE_TO_HUMAN.value:
                            await self._handle_escalation_event(data)
                        elif event == EventType.DISCONNECT.value:
                            self.logger.info(
                                "[AudioReceiver]: Disconnect event received"
                            )
                            break

                    except websockets.ConnectionClosed:
                        self.logger.info("[AudioReceiver]: Connection closed by server")
                        break
                    except Exception as e:
                        self.logger.error(f"[AudioReceiver]: Error: {e}")
                        continue

        finally:
            self.is_running = False
            self.logger.info("[AudioReceiver]: Stopped")

    async def _handle_media_event(self, data: dict, wf: wave.Wave_write):
        """Handle incoming media event - convert A-law to PCM and play."""
        try:
            if "media" not in data or "payload" not in data["media"]:
                return

            # Decode base64 to get A-law audio bytes
            alaw_bytes = base64.b64decode(data["media"]["payload"])

            # Convert G.711 A-law (8-bit) to PCM (16-bit) for Asterisk playback
            pcm_audio = audioop.alaw2lin(alaw_bytes, AudioConfig.PLAYBACK_WIDTH)

            # Write PCM to debug file
            wf.writeframes(pcm_audio)

            self.logger.debug(f"[AudioReceiver]: Received {len(pcm_audio)} PCM bytes")

            # Get current track and play directly (no queueing!)
            current_track = self.track_manager.get_current_track()

            # Create task to play chunk (non-blocking)
            asyncio.create_task(
                self.playback_manager.play_chunk(pcm_audio, current_track)
            )

        except Exception as e:
            self.logger.error(f"[AudioReceiver]: Failed to process media: {e}")

    # Event handling for transcripts
    async def _handle_transcript_event(self, event: dict):
        """Handle transcript events"""
        event_type = event.get("event")

        if event_type == EventType.USER_TRANSCRIPT.value:
            transcript: str = event.get("transcript", "")
            if transcript and transcript.strip():
                self.logger.info(f"[AudioReceiver]: ðŸ‘¤ User: {transcript}")
                self._append_transcript_to_file(event)

        elif event_type == EventType.ASSISTANT_TRANSCRIPT.value:
            transcript = event.get("transcript", "")
            if transcript and transcript.strip():
                self.logger.info(f"[AudioReceiver]: ðŸ¤– Assistant: {transcript}")
                self._append_transcript_to_file(event)

    # Event handling for escalations
    async def _handle_escalation_event(self, event: dict):
        """Handle escalation events - set AGI variable and end session so dialplan can transfer."""
        event_type = event.get("event")

        if event_type == EventType.ESCALATE_TO_HUMAN.value:
            reason = event.get("reason", "No reason provided")
            self.logger.info(f"[AudioReceiver]: Escalation event received: {reason}")

            # Sanitize reason (single-line, no quotes) so SET VARIABLE doesn't break
            safe_reason = (
                str(reason).replace('"', "'").replace("\n", " ").replace("\r", " ")
            )

            # Quiesce playback before set_variable: concurrent stream_file and
            # set_variable on the shared AGI stdin/stdout corrupts the protocol.
            await self.playback_manager.stop()
            self.track_manager.new_track()
            async with self.playback_manager._playback_lock:
                pass

            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, lambda: self.agi.set_variable("ESCALATE", "true")
                )
                await loop.run_in_executor(
                    None, lambda: self.agi.set_variable("ESCALATE_REASON", safe_reason)
                )
                self.logger.info(
                    "[AudioReceiver]: AGI vars set (ESCALATE=true) - returning to dialplan"
                )
            except Exception as e:
                self.logger.error(f"[AudioReceiver]: Failed to set AGI variables: {e}")

            # Stop the receiver loop so the session ends and control returns to dialplan
            self.is_running = False

    def _append_transcript_to_file(self, event: dict):
        """Append transcript to file as JSON lines."""
        try:
            with open(self.path_config.TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
                json_line = json.dumps(
                    event,
                    ensure_ascii=False,  # Preserve Unicode characters
                )
                f.write(json_line + "\n")
        except Exception as e:
            self.logger.error(f"[AudioReceiver]: Error writing transcript: {e}")

    async def _handle_clear_event(self):
        """Handle clear event - creates new track to invalidate old chunks."""
        self.logger.info("[AudioReceiver]: ðŸš¨ CLEAR EVENT - User interrupted!")

        # Just create new track - any pending chunks will see old track ID and skip
        self.track_manager.new_track()

        self.logger.info(
            "[AudioReceiver]: âœ… Track changed - old chunks will be skipped"
        )

    async def stop(self):
        """Stop the audio receiver."""
        self.is_running = False


class AICallSession:
    """Main orchestrator for AI call session."""

    def __init__(
        self,
        session_id: str,
        ws_uri: str,
        agi: AGI,
        audio_config: AudioConfig,
        path_config: PathConfig,
        logger: logging.Logger,
        firstname: str = None,
        date_of_birth: str = None,
        phone_number: str = None,
    ):
        self.session_id = session_id
        self.ws_uri = ws_uri
        self.agi = agi
        self.audio_config = audio_config
        self.path_config = path_config
        self.logger = logger
        self.firstname = firstname
        self.date_of_birth = date_of_birth
        self.phone_number = phone_number

        self.track_manager = AudioTrackManager(logger)
        self.playback_manager = PlaybackManager(
            agi, path_config, self.track_manager, logger
        )
        self.audio_streamer = AudioStreamer(audio_config, path_config, logger)
        self.audio_receiver = AudioReceiver(
            agi,
            audio_config,
            path_config,
            self.playback_manager,
            self.track_manager,
            logger,
        )

        self.is_active: bool = False

    async def start(self):
        """Start the AI call session."""
        try:
            with open(self.path_config.LOG_FILE, "w"):
                pass
        except Exception as e:
            self.logger.warning(f"[AICallSession]: Could not clear log file: {e}")

        # uri = f"{self.ws_uri}/{self.session_id}"
        uri = self.ws_uri
        self.logger.info(f"[AICallSession]: Connecting to {uri}")

        self.is_active = True

        try:
            async with websockets.connect(uri, max_queue=None) as ws:
                self.logger.info("[AICallSession]: WebSocket connected")

                await self.playback_manager.start()

                streamer_task = asyncio.create_task(
                    self.audio_streamer.stream_to_backend(ws), name="audio_streamer"
                )
                receiver_task = asyncio.create_task(
                    self.audio_receiver.receive_from_backend(ws), name="audio_receiver"
                )

                try:
                    done, pending = await asyncio.wait(
                        [streamer_task, receiver_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in done:
                        task_name = task.get_name()
                        try:
                            task.result()
                            self.logger.info(
                                f"[AICallSession]: Task completed: {task_name}"
                            )
                        except Exception as e:
                            self.logger.error(
                                f"[AICallSession]: Task error in {task_name}: {e}"
                            )

                    for task in pending:
                        task_name = task.get_name()
                        self.logger.info(
                            f"[AICallSession]: Cancelling task: {task_name}"
                        )
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            self.logger.info(
                                f"[AICallSession]: Task cancelled: {task_name}"
                            )

                finally:
                    self.logger.info(
                        "[AICallSession]: Finalizing session and transcript..."
                    )
                    # 1. Stop all audio tasks
                    await self.audio_receiver.stop()
                    await self.audio_streamer.stop()
                    await self.playback_manager.stop()
                    self.logger.info("Log 1")
                    # 2. Trigger Refinement as a detached background process
                    #    This survives even if the AGI process is killed by Asterisk.
                    raw_file = self.path_config.TRANSCRIPT_FILE
                    destination = self.path_config.call_dir
                    self.logger.info("Log 2")
                    if os.path.exists(raw_file):
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        runner_script = os.path.join(
                            script_dir, "transcript_agent", "run_refinement.py"
                        )
                        try:
                            venv_python = "/var/lib/asterisk/agi-bin/.venv/bin/python"
                            subprocess.Popen(
                                [
                                    venv_python,
                                    runner_script,
                                    raw_file,
                                    destination,
                                    self.session_id,
                                    self.firstname or "",
                                    self.date_of_birth or "",
                                    self.phone_number or "",
                                ],
                                stdout=open(
                                    os.path.join(destination, "refinement.log"), "w"
                                ),
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                            )
                            self.logger.info(
                                f"Refinement spawned. Source: {raw_file} | Dest: {destination}"
                            )
                        except Exception as e:
                            self.logger.error(f"Failed to spawn refinement: {e}")
                    self.logger.info("Log 3")
                    self.is_active = False
                    self.path_config.cleanup()

                    if ws.state == websockets.protocol.State.OPEN:
                        try:
                            await ws.close()
                            self.logger.info("[AICallSession]: WebSocket closed")
                        except Exception as e:
                            self.logger.warning(
                                f"[AICallSession]: Error closing WebSocket: {e}"
                            )

                # ///////////////////////////////////////////////////////////////////

        except websockets.ConnectionClosed as e:
            self.logger.error(f"[AICallSession]: WebSocket connection closed: {e}")
        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"[AICallSession]: WebSocket error: {e}")
        except Exception as e:
            self.logger.error(f"[AICallSession]: Error: {e}")
        finally:
            self.is_active = False
            # Cleanup call-specific files
            self.path_config.cleanup()
            self.logger.info("[AICallSession]: Session ended and cleaned up")


def setup_logger(call_id: str, log_file: str) -> logging.Logger:
    """Configure and return logger instance for this specific call."""
    logger = logging.getLogger(f"AGI-{call_id}")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        f"%(asctime)s [{call_id[:8]}] [%(levelname)s] %(name)s: %(message)s"
    )
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def get_eagi_fd(agi: AGI) -> int:
    """Get the EAGI file descriptor from Asterisk environment."""
    # Try to get from AGI environment variable
    enhanced = agi.env.get("agi_enhanced")
    if enhanced and enhanced != "0.0":
        return 3  # Standard EAGI FD

    # Fallback to FD 3 (standard EAGI)
    return 3


def get_call_arguments(agi: AGI):
    # Read arguments from Asterisk
    # Dialplan: EAGI(callapi.py, CLEAN_UNIQUEID, first_name, dob, BNUM, state)
    try:
        clean_uniqueid = sys.argv[1]
        firstname = sys.argv[2]  # IMPORTANT: keep 'firstname'
        dob = sys.argv[3]
    except IndexError:
        clean_uniqueid = None
        firstname = None
        dob = None

    # BNUM = caller's phone number (passed as 4th arg). Optional/may be absent.
    try:
        bnum = sys.argv[4]
    except IndexError:
        bnum = None

    # Customer's state (passed as 5th arg). Optional; the agent asks if absent.
    try:
        state = sys.argv[5]
    except IndexError:
        state = None

    return clean_uniqueid, firstname, dob, bnum, state


def parse_dob(dob_string):
    # Define possible input formats
    formats = ["%Y-%m-%d", "%d_%b_%Y", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(dob_string, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return "1970-01-01"  # Default or fallback


async def main():
    """Main entry point."""
    # Initialize AGI first to get call info
    agi = AGI()

    clean_uniqueid, firstname, dob, bnum, state = get_call_arguments(agi)
    customer_state = quote((state or "").strip())

    call_id = clean_uniqueid or "0000000"
    user_id = random.randint(1000, 9999)
    user_name = (firstname or "Unknown").replace(" ", "_")
    date_of_birth = parse_dob(dob or "1970-01-01")

    # Caller's phone number comes from the dialplan as BNUM (4th AGI arg).
    # It's used to blacklist on opt-out. When caller ID is withheld the
    # dialplan may pass an empty/placeholder value ("unknown"/"anonymous") ->
    # fall back to a static placeholder number so downstream opt-out still works.
    caller_number = (bnum or "").strip()
    if caller_number.lower() in ("unknown", "anonymous", "0.0"):
        caller_number = ""
    if not caller_number:
        caller_number = f"051-{random.randint(1000000, 9999999)}"

    eagi_fd = get_eagi_fd(agi)

    # Create call-specific configuration
    path_config = PathConfig(call_id=call_id)
    audio_config = AudioConfig(eagi_fd=eagi_fd)

    # Setup logger with call-specific file
    logger = setup_logger(call_id, path_config.LOG_FILE)
    logger.info(
        f"=== Starting call session: {call_id} ===user_id: {user_id}, caller: {user_name}, DOB: {date_of_birth}, phone: {caller_number or 'N/A'} ==="
    )
    logger.info(f"EAGI FD: {eagi_fd}")
    logger.info(f"Call directory: {path_config.call_dir}")

    # fetch a user at random to send to the AI backend
    # random_user = random.choice(MOCK_USERS_DATA)

    # Backend WebSocket. `uv run server` listens on port 8000; switch the
    # active line if the production service runs on a different port/host.
    # for production systemd service on the Asterisk host
    # ws://localhost:8003/api/v1/realtime/call-session/

    ws_uri = (
        "ws://localhost:8002/api/v1/realtime/call-session/"
        f"{call_id}"
        f"?user_id={user_id}"
        f"&user_name={user_name}"
        f"&date_of_birth={date_of_birth}"
    )
    if customer_state:
        ws_uri += f"&state={customer_state}"

    session = AICallSession(
        call_id,
        ws_uri,
        agi,
        audio_config,
        path_config,
        logger,
        firstname=user_name,
        date_of_birth=date_of_birth,
        phone_number=caller_number,
    )

    try:
        await session.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Session error: {e}", exc_info=True)
    finally:
        logger.info(f"=== Call session ended: {call_id} ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

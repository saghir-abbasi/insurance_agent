"""Admin dashboard API (mounted at /api/v1/admin) and the /admin page route.

All API endpoints require the ``X-Admin-Token`` header matching
``ADMIN_API_TOKEN`` from the environment. The page route only serves the static
HTML shell; every data call from it is token-authenticated.

There is no "apply" step beyond saving: OpenAI Realtime sessions read voice
and instructions from the settings store at connect time, so a save takes
effect on the next call automatically.
"""

import secrets
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from insurance_agent.admin_dashboard.openai_voices import (
    SAMPLE_UTTERANCES,
    is_known_voice,
    list_voices,
    synthesize_voice_sample,
)
from insurance_agent.admin_dashboard.settings_store import (
    LANGUAGE_OPTIONS,
    LANGUAGE_PLACEHOLDER,
    AgentSettings,
    get_settings_store,
)
from insurance_agent.core.config import configuration
from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

# Simple in-process rate limit for the TTS voice-test endpoint (spend guard).
_TEST_RATE_LIMIT = 10  # requests
_TEST_RATE_WINDOW_SECS = 60.0
_test_timestamps: deque[float] = deque()


def require_admin_token(x_admin_token: str = Header(default="")) -> None:
    if not configuration.ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Admin dashboard is disabled: set ADMIN_API_TOKEN in the backend .env to enable it.",
        )
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token, configuration.ADMIN_API_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")


router = APIRouter(dependencies=[Depends(require_admin_token)])

page_router = APIRouter()


# tags is required even off-schema: main.py's custom_generate_unique_id reads tags[0]
@page_router.get("/admin", include_in_schema=False, tags=["Admin"])
async def admin_page():
    return FileResponse(_STATIC_DIR / "admin.html", media_type="text/html")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsUpdate(BaseModel):
    voice_id: str
    language: str
    system_prompt: str


@router.get("/settings")
async def get_settings():
    settings = get_settings_store().load()
    return {
        "settings": settings.model_dump(),
        "available_languages": LANGUAGE_OPTIONS,
        "has_language_placeholder": settings.has_language_placeholder(),
        "language_placeholder": LANGUAGE_PLACEHOLDER,
    }


@router.put("/settings")
async def update_settings(update: SettingsUpdate):
    warnings: list[str] = []

    # --- Validate ---
    if not update.system_prompt.strip():
        raise HTTPException(status_code=422, detail="System prompt must not be empty.")
    if update.language not in LANGUAGE_OPTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported language '{update.language}'. Supported: {', '.join(LANGUAGE_OPTIONS)}",
        )
    if not is_known_voice(update.voice_id):
        raise HTTPException(
            status_code=422,
            detail=f"Voice id '{update.voice_id}' is not a supported voice.",
        )
    if LANGUAGE_PLACEHOLDER not in update.system_prompt:
        warnings.append(
            f"The prompt has no {LANGUAGE_PLACEHOLDER} placeholder, so the language "
            "selection has no effect on the prompt."
        )

    # --- Persist (this is the whole apply step; next call reads the store) ---
    old_settings = get_settings_store().load()
    settings = AgentSettings(
        voice_id=update.voice_id,
        language=update.language,
        system_prompt=update.system_prompt,
    )
    get_settings_store().save(settings)
    logger.info(
        "Admin settings saved: "
        f"voice {old_settings.voice_id} -> {settings.voice_id}, "
        f"language {old_settings.language} -> {settings.language}, "
        f"prompt {'changed' if old_settings.system_prompt != settings.system_prompt else 'unchanged'}"
    )
    return {
        "saved": True,
        "applied": True,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------


@router.get("/voices")
async def get_voices():
    return {"voices": list_voices()}


class VoiceTestRequest(BaseModel):
    voice_id: str
    language: str = "English"


@router.post("/voices/test")
async def test_voice(request: VoiceTestRequest):
    if not is_known_voice(request.voice_id):
        raise HTTPException(
            status_code=422,
            detail=f"Voice id '{request.voice_id}' is not a supported voice.",
        )
    if request.language not in SAMPLE_UTTERANCES:
        request.language = "English"

    now = time.monotonic()
    while _test_timestamps and now - _test_timestamps[0] > _TEST_RATE_WINDOW_SECS:
        _test_timestamps.popleft()
    if len(_test_timestamps) >= _TEST_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Voice-test limit reached ({_TEST_RATE_LIMIT}/min). Wait a moment and try again.",
        )
    _test_timestamps.append(now)

    try:
        audio = await synthesize_voice_sample(request.voice_id, request.language)
    except Exception as e:
        logger.error(f"Voice test synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Voice test failed: {e}")
    return Response(content=audio, media_type="audio/mpeg")

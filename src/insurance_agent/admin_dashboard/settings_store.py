"""Persisted admin settings for the voice agent (voice, language, system prompt).

The system prompt is stored as a *template* containing the literal ``{language}``
placeholder, which resolves to a full language instruction (a fixed-language
directive, or the follow-the-caller directive for "Caller Language").
Resolution uses a targeted ``str.replace`` (never ``str.format``) so the
call script's other braces — ``{name}``, ``{company}``,
``{user_info.user_name}``, ``{user_info.date_of_birth}``,
``{user_info.state}``, resolved per call by the realtime agent — pass
through untouched.

The store is a single JSON file written atomically (temp file + rename), seeded
on first load from the hardcoded defaults in ``core/prompts.py`` and
``core/config.py`` so behavior is unchanged until an admin saves.

Unlike the Hume version of this dashboard, there is no remote config to push:
OpenAI Realtime sessions take voice and instructions at connect time, so every
new call simply reads this store. Saving is the whole "apply" step.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from insurance_agent.core.config import configuration
from insurance_agent.core.prompts import SYSTEM_PROMPT
from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

LANGUAGE_PLACEHOLDER = "{language}"

# Languages offered as fixed choices in the dashboard dropdown: the most
# widely spoken languages of the world, alphabetical. The "Caller Language"
# option is prepended separately in LANGUAGE_OPTIONS.
SUPPORTED_LANGUAGES = [
    "Arabic",
    "Bengali",
    "Chinese",
    "English",
    "French",
    "German",
    "Hindi",
    "Indonesian",
    "Italian",
    "Japanese",
    "Korean",
    "Portuguese",
    "Russian",
    "Spanish",
    "Turkish",
    "Urdu",
]

# Special dropdown option: the agent starts in English and follows the caller
# into any supported language instead of being pinned to one.
CALLER_LANGUAGE = "Caller Language"

# Everything offered in the dashboard dropdown.
LANGUAGE_OPTIONS = [CALLER_LANGUAGE, *SUPPORTED_LANGUAGES]

DEFAULT_LANGUAGE = "English"

# Appended to the existing SYSTEM_PROMPT when seeding the store. {language} is
# replaced with a full language instruction (see language_directive_value), so
# the placeholder stands alone inside the tag.
_LANGUAGE_DIRECTIVE = """
<language>
{language}
</language>
"""

# Whitelist-first phrasing: the permitted set and the refusal rule come before
# the switch rule, otherwise the model reads "switch to any other language" as
# the primary instruction and speaks unsupported languages instead of refusing.
_CALLER_LANGUAGE_INSTRUCTION = (
    "Start and speak in English by default. "
    f"The ONLY languages you are permitted to speak are: {', '.join(SUPPORTED_LANGUAGES)}. "
    "Never speak, imitate, or attempt any language outside this list under any circumstances. "
    "If the caller speaks one of the permitted languages, switch and continue the entire conversation in that language. "
    "If the caller speaks a language that is NOT in the permitted list, "
    "do not switch to it and do not answer in some other permitted language; reply in English with: "
    "\"I'm sorry, I don't understand the language you are speaking. I can only continue in English.\" "
    "and carry on in English. If you are not certain which language the caller is speaking, stay in English. "
    "Identify closely related languages carefully: for example, Urdu and Hindi are distinct languages; "
    "reply in the one the caller is actually speaking."
)


def language_directive_value(language: str) -> str:
    """The text substituted for {language}: a complete language instruction."""
    if language == CALLER_LANGUAGE:
        return _CALLER_LANGUAGE_INSTRUCTION
    return (
        f"Converse with the customer exclusively in {language}. "
        f"If the customer speaks another language, politely continue in {language}."
    )


# The current SYSTEM_PROMPT carries its own "# Language" section holding the
# placeholder; the directive is appended only for templates that lack it.
DEFAULT_PROMPT_TEMPLATE = (
    SYSTEM_PROMPT
    if LANGUAGE_PLACEHOLDER in SYSTEM_PROMPT
    else SYSTEM_PROMPT + _LANGUAGE_DIRECTIVE
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = _PROJECT_ROOT / "data" / "agent_settings.json"


class AgentSettings(BaseModel):
    voice_id: str
    language: str = DEFAULT_LANGUAGE
    system_prompt: str  # template; may contain {language}
    updated_at: str | None = None
    updated_by: str = "admin"

    def resolved_system_prompt(self) -> str:
        """Return the prompt with {language} substituted (targeted replace)."""
        return self.system_prompt.replace(
            LANGUAGE_PLACEHOLDER, language_directive_value(self.language)
        )

    def has_language_placeholder(self) -> bool:
        return LANGUAGE_PLACEHOLDER in self.system_prompt


def default_settings() -> AgentSettings:
    return AgentSettings(
        voice_id=configuration.REALTIME_VOICE,
        language=DEFAULT_LANGUAGE,
        system_prompt=DEFAULT_PROMPT_TEMPLATE,
    )


class SettingsStore:
    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH):
        self.path = Path(path)

    def load(self) -> AgentSettings:
        """Load settings, seeding the file from defaults if absent or corrupt.

        A settings file left over from the Hume deployment would parse (extra
        keys are ignored) but carries a Hume voice UUID, so any voice id not
        in the OpenAI realtime set re-seeds the store to defaults.
        """
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                settings = AgentSettings.model_validate(data)
                from insurance_agent.admin_dashboard.openai_voices import (
                    is_known_voice,
                )

                if not is_known_voice(settings.voice_id):
                    logger.warning(
                        f"Settings file {self.path} has unknown voice "
                        f"'{settings.voice_id}' (stale Hume settings?); re-seeding defaults"
                    )
                else:
                    return settings
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(
                    f"Settings file {self.path} is corrupt ({e}); re-seeding defaults"
                )
        settings = default_settings()
        self.save(settings)
        logger.info(f"Seeded agent settings at {self.path}")
        return settings

    def save(self, settings: AgentSettings) -> AgentSettings:
        settings.updated_at = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a crash mid-save must not corrupt the settings file.
        fd, tmp_path = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(settings.model_dump_json(indent=2))
            os.replace(tmp_path, self.path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        return settings


_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store

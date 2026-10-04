from typing import Literal, Optional, Any, Annotated
from enum import Enum

from pydantic import computed_field, BeforeValidator, AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from agents import Model


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class EnvironmentEnum(str, Enum):
    development = "development"
    production = "production"
    testing = "testing"


class Configuration(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Insurance Agent"
    DESCRIPTION: Optional[str] = ""
    ENVIRONMENT: EnvironmentEnum = EnvironmentEnum.production

    VERSION: str = "1.0"
    API_STR: str = "/api/v1"

    DOMAIN_URL: str = "http://localhost:8000"

    @computed_field  # type: ignore[misc]
    @property
    def SERVER_HOST(self) -> str:
        return self.DOMAIN_URL + self.API_STR

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    OPENAI_API_KEY: Optional[str] = None

    ENABLE_TRACING: bool = False

    ADMIN_API_TOKEN: Optional[str] = None
    """Enables the /admin dashboard; admin API returns 503 when unset."""

    REALTIME_VOICE: str = "marin"
    """Default realtime voice, used when no admin settings file exists."""

    LA_TRANSFER_ENABLED: bool = False
    """When False (no licensed agent connected yet), the call ends right after
    the agent speaks the transfer line. Set True once the dialplan routes
    ESCALATE=true calls to a live licensed agent; the line then stays open."""

    TRANSCRIPT_MODEL: str = "gpt-5-nano-2025-08-07"
    """Model used by the post-call transcript refinement agent."""

    REALTIME_MODEL: str = "openai/gpt-realtime-mini"
    QUERY_MODEL: str = "openai/gpt-realtime-mini"

    REALTIME_REASONING_EFFORT: Literal[
        "minimal", "low", "medium", "high", "xhigh", "off"
    ] = "low"
    """Reasoning effort for realtime-2 models; "off" stops sending the field
    (required for non-reasoning models such as gpt-realtime-mini)."""

    REALTIME_TRANSCRIBE_MODEL: Literal[
        "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"
    ] = "gpt-4o-mini-transcribe"

    @classmethod
    def get_model(cls, fully_specified_name: str) -> str | Model:
        """
        Get the model from the fully specified name.

        Args:
            fully_specified_name (str): The fully specified name of the model.

        Returns:
            str | Model: The model object or the model name.
        """
        if "/" in fully_specified_name:
            provider, model = fully_specified_name.split("/", maxsplit=1)
        else:
            provider = ""
            model = fully_specified_name

        match provider:
            case "openai":
                return model
            case _:
                raise ValueError(f"Unsupported embedding provider: {provider}")


configuration = Configuration()  # type: ignore


class TestConfiguration(Configuration):
    pass


test_configuration = TestConfiguration()  # type: ignore

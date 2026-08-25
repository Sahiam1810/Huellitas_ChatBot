from enum import StrEnum
from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ports.chat_model import ModelProvider


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ActiveModelConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ModelProvider
    api_key: SecretStr
    model: str
    timeout_seconds: float
    base_url: AnyHttpUrl | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HUELLITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="Huellitas ChatBot", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    docs_enabled: bool = True
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)

    chat_enabled: bool = False
    chat_provider: ModelProvider = ModelProvider.OPENROUTER
    chat_max_output_tokens: int = Field(default=1024, ge=1, le=32768)

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: AnyHttpUrl = AnyHttpUrl("https://openrouter.ai/api/v1")
    openrouter_model: str | None = "google/gemini-3.5-flash"
    openrouter_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    openai_api_key: SecretStr | None = None
    openai_base_url: AnyHttpUrl = AnyHttpUrl("https://api.openai.com/v1")
    openai_model: str | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = "gemini-3.5-flash"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def validate_active_provider(self) -> "Settings":
        if not self.chat_enabled:
            return self

        api_key, model, _, _ = self._selected_values()
        if api_key is None or not api_key.get_secret_value().strip():
            raise ValueError(f"API key is required for {self.chat_provider.value}")
        if model is None or not model.strip():
            raise ValueError(f"Model is required for {self.chat_provider.value}")
        return self

    def active_model_configuration(self) -> ActiveModelConfiguration | None:
        if not self.chat_enabled:
            return None

        api_key, model, timeout_seconds, base_url = self._selected_values()
        assert api_key is not None
        assert model is not None
        return ActiveModelConfiguration(
            provider=self.chat_provider,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
        )

    def _selected_values(
        self,
    ) -> tuple[SecretStr | None, str | None, float, AnyHttpUrl | None]:
        values = {
            ModelProvider.OPENROUTER: (
                self.openrouter_api_key,
                self.openrouter_model,
                self.openrouter_timeout_seconds,
                self.openrouter_base_url,
            ),
            ModelProvider.OPENAI: (
                self.openai_api_key,
                self.openai_model,
                self.openai_timeout_seconds,
                self.openai_base_url,
            ),
            ModelProvider.GEMINI: (
                self.gemini_api_key,
                self.gemini_model,
                self.gemini_timeout_seconds,
                None,
            ),
        }
        return values[self.chat_provider]


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    return Settings(_env_file=env_file)

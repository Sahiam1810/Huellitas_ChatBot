from enum import StrEnum
from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ports.chat_model import ModelProvider
from app.ports.embedding_model import EmbeddingProvider
from app.ports.vector_store import VectorDistance


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


class ActiveVectorStoreConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: AnyHttpUrl
    api_key: SecretStr | None
    timeout_seconds: float
    startup_max_attempts: int
    startup_retry_delay_seconds: float


class ActiveEmbeddingConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: EmbeddingProvider
    api_key: SecretStr
    base_url: AnyHttpUrl
    model: str
    dimensions: int
    timeout_seconds: float
    max_batch_size: int


class ActiveRagConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    global_knowledge_collection: str
    conversation_memory_collection: str
    dimensions: int
    distance: VectorDistance


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HUELLITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
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

    vector_store_enabled: bool = False
    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:6333")
    qdrant_api_key: SecretStr | None = None
    qdrant_timeout_seconds: float = Field(default=5.0, gt=0, le=300)
    qdrant_startup_max_attempts: int = Field(default=5, ge=1, le=20)
    qdrant_startup_retry_delay_seconds: float = Field(default=1.0, ge=0, le=60)

    embedding_enabled: bool = False
    embedding_provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    embedding_openai_api_key: SecretStr | None = None
    embedding_openai_base_url: AnyHttpUrl = AnyHttpUrl("https://api.openai.com/v1")
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    embedding_max_batch_size: int = Field(default=64, ge=1, le=2048)

    rag_enabled: bool = False
    qdrant_global_knowledge_collection: str = Field(default="knowledge_global", min_length=1)
    qdrant_conversation_memory_collection: str = Field(default="conversation_memory", min_length=1)
    qdrant_vector_distance: VectorDistance = VectorDistance.COSINE

    @model_validator(mode="after")
    def validate_active_provider(self) -> "Settings":
        if self.chat_enabled:
            api_key, model, _, _ = self._selected_values()
            if api_key is None or not api_key.get_secret_value().strip():
                raise ValueError(f"API key is required for {self.chat_provider.value}")
            if model is None or not model.strip():
                raise ValueError(f"Model is required for {self.chat_provider.value}")
        if self.embedding_enabled:
            if (
                self.embedding_openai_api_key is None
                or not self.embedding_openai_api_key.get_secret_value().strip()
            ):
                raise ValueError("API key is required for embeddings")
            if self.embedding_model is None or not self.embedding_model.strip():
                raise ValueError("Model is required for embeddings")
            if self.embedding_dimensions is None:
                raise ValueError("Dimensions are required for embeddings")
        if self.rag_enabled:
            if not self.embedding_enabled:
                raise ValueError("embeddings must be enabled when RAG is enabled")
            if not self.vector_store_enabled:
                raise ValueError("vector store must be enabled when RAG is enabled")
            if (
                self.qdrant_global_knowledge_collection.strip()
                == self.qdrant_conversation_memory_collection.strip()
            ):
                raise ValueError("RAG collection names must be different")
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

    def active_vector_store_configuration(self) -> ActiveVectorStoreConfiguration | None:
        if not self.vector_store_enabled:
            return None

        api_key = self.qdrant_api_key
        if api_key is not None and not api_key.get_secret_value().strip():
            api_key = None
        return ActiveVectorStoreConfiguration(
            url=self.qdrant_url,
            api_key=api_key,
            timeout_seconds=self.qdrant_timeout_seconds,
            startup_max_attempts=self.qdrant_startup_max_attempts,
            startup_retry_delay_seconds=self.qdrant_startup_retry_delay_seconds,
        )

    def active_embedding_configuration(self) -> ActiveEmbeddingConfiguration | None:
        if not self.embedding_enabled:
            return None
        assert self.embedding_openai_api_key is not None
        assert self.embedding_model is not None
        assert self.embedding_dimensions is not None
        return ActiveEmbeddingConfiguration(
            provider=self.embedding_provider,
            api_key=self.embedding_openai_api_key,
            base_url=self.embedding_openai_base_url,
            model=self.embedding_model,
            dimensions=self.embedding_dimensions,
            timeout_seconds=self.embedding_timeout_seconds,
            max_batch_size=self.embedding_max_batch_size,
        )

    def active_rag_configuration(self) -> ActiveRagConfiguration | None:
        if not self.rag_enabled:
            return None
        assert self.embedding_dimensions is not None
        return ActiveRagConfiguration(
            global_knowledge_collection=self.qdrant_global_knowledge_collection.strip(),
            conversation_memory_collection=self.qdrant_conversation_memory_collection.strip(),
            dimensions=self.embedding_dimensions,
            distance=self.qdrant_vector_distance,
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

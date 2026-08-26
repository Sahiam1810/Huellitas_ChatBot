from unittest.mock import Mock

import pytest

from app.adapters.embeddings import embedding_factory
from app.adapters.embeddings.openai import OpenAIEmbeddingModel
from app.bootstrap.settings import Settings


def test_factory_returns_none_when_disabled() -> None:
    assert embedding_factory.create_embedding_model(Settings(_env_file=None)) is None


def test_factory_builds_independent_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(embedding_factory, "AsyncOpenAI", constructor)
    settings = Settings(
        embedding_enabled=True,
        embedding_openai_api_key="embedding-secret",
        embedding_model="embedding-test",
        embedding_dimensions=3,
        _env_file=None,
    )
    result = embedding_factory.create_embedding_model(settings)
    assert isinstance(result, OpenAIEmbeddingModel)
    constructor.assert_called_once_with(
        api_key="embedding-secret",
        base_url="https://api.openai.com/v1",
        timeout=30,
        max_retries=0,
    )

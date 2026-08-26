from openai import AsyncOpenAI

from app.adapters.embeddings.openai import OpenAIEmbeddingModel
from app.bootstrap.settings import Settings
from app.ports.embedding_model import EmbeddingModel


def create_embedding_model(settings: Settings) -> EmbeddingModel | None:
    configuration = settings.active_embedding_configuration()
    if configuration is None:
        return None
    client = AsyncOpenAI(
        api_key=configuration.api_key.get_secret_value(),
        base_url=str(configuration.base_url),
        timeout=configuration.timeout_seconds,
        max_retries=0,
    )
    return OpenAIEmbeddingModel(
        client=client,
        model=configuration.model,
        dimensions=configuration.dimensions,
        max_batch_size=configuration.max_batch_size,
    )

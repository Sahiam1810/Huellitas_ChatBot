from qdrant_client import AsyncQdrantClient

from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.bootstrap.settings import Settings
from app.ports.vector_store import VectorStore


def create_vector_store(settings: Settings) -> VectorStore | None:
    configuration = settings.active_vector_store_configuration()
    if configuration is None:
        return None

    api_key = (
        configuration.api_key.get_secret_value() if configuration.api_key is not None else None
    )
    client = AsyncQdrantClient(
        url=str(configuration.url),
        api_key=api_key,
        timeout=configuration.timeout_seconds,
        prefer_grpc=False,
    )
    return QdrantVectorStore(client)

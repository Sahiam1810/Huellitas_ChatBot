from app.ports.vector_store import VectorStore


class StubVectorStore:
    async def check_health(self) -> None:
        return None

    async def close(self) -> None:
        return None


def test_vector_store_is_a_runtime_checkable_structural_port() -> None:
    assert isinstance(StubVectorStore(), VectorStore)

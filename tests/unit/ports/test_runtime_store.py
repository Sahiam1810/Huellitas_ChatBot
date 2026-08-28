from app.ports.runtime_store import RuntimeStore


class StubRuntimeStore:
    async def check_health(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_runtime_store_accepts_a_neutral_health_and_lifecycle_implementation() -> None:
    assert isinstance(StubRuntimeStore(), RuntimeStore)

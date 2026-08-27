from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.rag_routing import cli
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)

DATASET = "evaluations/datasets/veterinary-routing-v1.jsonl"


@pytest.mark.anyio
async def test_evaluate_offline_runs_without_loading_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_loaded() -> None:
        raise AssertionError("offline evaluation must not load settings")

    monkeypatch.setattr(cli, "load_settings", fail_if_loaded)

    code = await cli.async_main(["evaluate", "--dataset", DATASET, "--output-dir", str(tmp_path)])

    assert code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert len(list(tmp_path.glob("*.md"))) == 1


@pytest.mark.anyio
async def test_live_mode_requires_paid_embedding_consent_before_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_loaded() -> None:
        raise AssertionError("settings must not load before consent")

    monkeypatch.setattr(cli, "load_settings", fail_if_loaded)

    code = await cli.async_main(["evaluate", "--mode", "live-retrieval", "--dataset", DATASET])

    assert code == 1


@pytest.mark.anyio
async def test_live_mode_closes_embedding_and_qdrant_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Embedding:
        dimensions = 3

        def __init__(self) -> None:
            self.closed = 0

        async def embed_query(self, text: str) -> EmbeddingResponse:
            return EmbeddingResponse(
                vectors=(EmbeddingVector((0.1, 0.2, 0.3)),),
                provider=EmbeddingProvider.OPENAI,
                model="embedding-test",
                usage=EmbeddingUsage(input_tokens=2, total_tokens=2),
            )

        async def close(self) -> None:
            self.closed += 1

    class Store:
        def __init__(self) -> None:
            self.closed = 0

        async def search_global(self, query: object) -> tuple[object, ...]:
            return ()

        async def search_conversation(self, query: object) -> tuple[object, ...]:
            return ()

        async def close(self) -> None:
            self.closed += 1

    embedding = Embedding()
    store = Store()
    settings = SimpleNamespace(
        active_rag_configuration=lambda: SimpleNamespace(
            global_limit=4,
            conversation_limit=3,
        ),
        active_embedding_configuration=lambda: SimpleNamespace(
            provider=EmbeddingProvider.OPENAI,
            model="embedding-test",
        ),
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_embedding_model", lambda active: embedding)
    monkeypatch.setattr(cli, "create_vector_store", lambda active: store)

    code = await cli.async_main(
        [
            "evaluate",
            "--mode",
            "live-retrieval",
            "--dataset",
            DATASET,
            "--output-dir",
            str(tmp_path),
            "--allow-paid-embeddings",
        ]
    )

    assert code == 0
    assert embedding.closed == 1
    assert store.closed == 1


@pytest.mark.anyio
async def test_live_mode_closes_embedding_when_qdrant_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Embedding:
        dimensions = 3

        def __init__(self) -> None:
            self.closed = 0

        async def close(self) -> None:
            self.closed += 1

    embedding = Embedding()
    settings = SimpleNamespace(
        active_rag_configuration=lambda: SimpleNamespace(
            global_limit=4,
            conversation_limit=3,
        ),
        active_embedding_configuration=lambda: SimpleNamespace(
            provider=EmbeddingProvider.OPENAI,
            model="embedding-test",
        ),
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_embedding_model", lambda active: embedding)
    monkeypatch.setattr(cli, "create_vector_store", lambda active: None)

    code = await cli.async_main(
        [
            "evaluate",
            "--mode",
            "live-retrieval",
            "--dataset",
            DATASET,
            "--allow-paid-embeddings",
        ]
    )

    assert code == 1
    assert embedding.closed == 1


@pytest.mark.anyio
async def test_tune_offline_produces_a_safe_recommendation(tmp_path: Path) -> None:
    code = await cli.async_main(["tune", "--dataset", DATASET, "--output-dir", str(tmp_path)])

    assert code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.anyio
async def test_cli_returns_configuration_error_for_missing_dataset(tmp_path: Path) -> None:
    code = await cli.async_main(["evaluate", "--dataset", str(tmp_path / "missing.jsonl")])

    assert code == 1

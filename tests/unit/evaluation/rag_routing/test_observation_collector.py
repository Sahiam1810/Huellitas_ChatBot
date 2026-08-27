from pathlib import Path

import pytest

from app.evaluation.rag_routing.dataset_loader import load_dataset
from app.evaluation.rag_routing.observation_collector import OfflineObservationCollector
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch


@pytest.mark.anyio
async def test_offline_collector_maps_serialized_candidates_to_port_matches() -> None:
    dataset = load_dataset(Path("evaluations/datasets/veterinary-routing-v1.jsonl"))

    observations = await OfflineObservationCollector().collect(dataset)

    assert len(observations) == 60
    assert observations[0].case is dataset.cases[0]
    assert observations[0].embedding_input_tokens is None
    assert isinstance(observations[0].global_matches[0], GlobalKnowledgeMatch)
    assert observations[0].global_matches[0].kind is GlobalKnowledgeKind.APPROVED_EXCHANGE
    assert observations[0].global_matches[0].score == 0.99
    assert isinstance(observations[1].conversation_matches[0], ConversationMemoryMatch)
    assert observations[1].conversation_matches[0].answer == "Max está registrado como labrador."

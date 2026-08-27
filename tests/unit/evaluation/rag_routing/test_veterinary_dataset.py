from collections import Counter
from pathlib import Path

from app.evaluation.rag_routing.contracts import DatasetSplit
from app.evaluation.rag_routing.dataset_loader import load_dataset
from app.orchestration.rag_contracts import SemanticRoute
from app.ports.global_knowledge_store import GlobalKnowledgeKind

DATASET_PATH = Path("evaluations/datasets/veterinary-routing-v1.jsonl")


def test_veterinary_dataset_is_balanced_and_partitioned() -> None:
    dataset = load_dataset(DATASET_PATH)

    assert len(dataset.cases) == 60
    assert Counter(case.expected_route for case in dataset.cases) == {
        SemanticRoute.DIRECT: 20,
        SemanticRoute.CONTEXTUAL: 20,
        SemanticRoute.GENERAL: 20,
    }
    assert Counter(case.split for case in dataset.cases) == {
        DatasetSplit.CALIBRATION: 42,
        DatasetSplit.VALIDATION: 18,
    }
    for split in DatasetSplit:
        assert Counter(case.expected_route for case in dataset.cases if case.split is split) == {
            SemanticRoute.DIRECT: 14 if split is DatasetSplit.CALIBRATION else 6,
            SemanticRoute.CONTEXTUAL: 14 if split is DatasetSplit.CALIBRATION else 6,
            SemanticRoute.GENERAL: 14 if split is DatasetSplit.CALIBRATION else 6,
        }


def test_veterinary_dataset_exercises_routing_risks() -> None:
    dataset = load_dataset(DATASET_PATH)
    cases = dataset.cases
    non_direct_scores = [
        candidate.score
        for case in cases
        if case.expected_route is not SemanticRoute.DIRECT
        for candidate in (*case.offline_candidates.global_, *case.offline_candidates.conversation)
    ]

    assert all(not case.id.startswith("real-") for case in cases)
    assert any(case.safety_critical for case in cases)
    assert any(
        not case.allow_direct and score >= 0.95
        for case in cases
        for score in (
            [candidate.score for candidate in case.offline_candidates.global_]
            + [candidate.score for candidate in case.offline_candidates.conversation]
        )
    )
    assert max(non_direct_scores) >= 0.95
    assert any(0.79 <= score <= 0.81 for score in non_direct_scores)
    assert any(
        candidate.kind is GlobalKnowledgeKind.DOCUMENT_CHUNK
        for case in cases
        for candidate in case.offline_candidates.global_
    )
    assert any(
        candidate.kind is GlobalKnowledgeKind.APPROVED_EXCHANGE
        for case in cases
        for candidate in case.offline_candidates.global_
    )
    assert any(case.offline_candidates.conversation for case in cases)
    assert sum(case.baseline_usage is not None for case in cases) == 30

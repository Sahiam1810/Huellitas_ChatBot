import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.evaluation.rag_routing.contracts import (
    DatasetSplit,
    OfflineCandidates,
    RoutingEvaluationCase,
    RoutingObservation,
)
from app.evaluation.rag_routing.evaluator import evaluate_observations
from app.evaluation.rag_routing.reporters import ReportMetadata, write_reports
from app.orchestration.rag_contracts import SemanticRoute
from app.ports.conversation_memory_store import ConversationMemoryMatch


def _evaluation_result() -> object:
    case = RoutingEvaluationCase(
        schema_version=1,
        id="direct-report",
        split=DatasetSplit.VALIDATION,
        category="report",
        safety_critical=False,
        question="Pregunta privada que no debe aparecer",
        conversation_id=UUID("00000000-0000-4000-8000-000000000001"),
        expected_route=SemanticRoute.DIRECT,
        allow_direct=True,
        acceptable_direct_answers=("Respuesta segura.",),
        offline_candidates=OfflineCandidates(),
    )
    observation = RoutingObservation(
        case=case,
        global_matches=(),
        conversation_matches=(
            ConversationMemoryMatch(
                point_id=UUID("10000000-0000-4000-8000-000000000001"),
                score=0.97,
                question="Pregunta anterior",
                answer="Respuesta segura.",
            ),
        ),
    )
    return evaluate_observations((observation,), high_threshold=0.95, medium_threshold=0.80)


def test_write_reports_serializes_safe_machine_and_human_results(tmp_path: Path) -> None:
    metadata = ReportMetadata(
        mode="offline",
        dataset_path="evaluations/datasets/test.jsonl",
        dataset_sha256="abc123",
    )

    paths = write_reports(
        _evaluation_result(),
        metadata,
        output_dir=tmp_path,
        now=datetime(2026, 8, 27, 15, 0, tzinfo=UTC),
    )

    assert paths.json_path.name == "rag-routing-offline-20260827T150000Z.json"
    assert paths.markdown_path.name == "rag-routing-offline-20260827T150000Z.md"
    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["schemaVersion"] == 1
    assert payload["generatedAt"] == "2026-08-27T15:00:00Z"
    assert payload["metadata"] == {
        "mode": "offline",
        "datasetPath": "evaluations/datasets/test.jsonl",
        "datasetSha256": "abc123",
        "embedding": {"provider": None, "model": None},
    }
    assert payload["evaluation"]["metrics"]["routeDistribution"]["direct"] == 1
    assert payload["evaluation"]["metrics"]["directAnswerPrecision"] == 1.0
    assert "Pregunta privada" not in serialized
    assert "Respuesta segura" not in serialized
    assert "vector" not in serialized.casefold()
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "Safety gate: passed" in markdown
    assert "LLM calls avoided: 1" in markdown
    assert not paths.json_path.with_suffix(".json.tmp").exists()
    assert not paths.markdown_path.with_suffix(".md.tmp").exists()

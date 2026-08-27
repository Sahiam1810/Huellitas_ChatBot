import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from app.evaluation.rag_routing.contracts import DatasetSplit
from app.evaluation.rag_routing.dataset_loader import DatasetValidationError, load_dataset
from app.orchestration.rag_contracts import SemanticRoute


def _case(route: str, split: str, suffix: int) -> dict[str, object]:
    direct = route == "direct"
    conversation = []
    if direct:
        conversation = [
            {
                "pointId": f"10000000-0000-4000-8000-{suffix:012d}",
                "score": 0.97,
                "question": "¿Qué edad tiene Luna?",
                "answer": "Luna tiene dos años.",
            }
        ]
    return {
        "schemaVersion": 1,
        "id": f"{route}-{split}-{suffix}",
        "split": split,
        "category": "pet_profile",
        "safetyCritical": False,
        "question": "  ¿Cuántos años tiene Luna?  ",
        "conversationId": f"00000000-0000-4000-8000-{suffix:012d}",
        "expectedRoute": route,
        "allowDirect": direct,
        "acceptableDirectAnswers": ["  Luna tiene dos años.  "] if direct else [],
        "baselineUsage": {"inputTokens": 120, "outputTokens": 25},
        "offlineCandidates": {"global": [], "conversation": conversation},
    }


def _valid_cases() -> list[dict[str, object]]:
    return [
        _case(route, split, index)
        for index, (split, route) in enumerate(
            (
                ("calibration", "direct"),
                ("calibration", "contextual"),
                ("calibration", "general"),
                ("validation", "direct"),
                ("validation", "contextual"),
                ("validation", "general"),
            ),
            start=1,
        )
    ]


def _write_jsonl(path: Path, cases: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )
    return path


def test_load_dataset_parses_strict_versioned_cases(tmp_path: Path) -> None:
    dataset = load_dataset(_write_jsonl(tmp_path / "dataset.jsonl", _valid_cases()))

    first = dataset.cases[0]
    assert len(dataset.cases) == 6
    assert len(dataset.sha256) == 64
    assert first.split is DatasetSplit.CALIBRATION
    assert first.expected_route is SemanticRoute.DIRECT
    assert first.question == "¿Cuántos años tiene Luna?"
    assert first.acceptable_direct_answers == ("Luna tiene dos años.",)
    assert first.baseline_usage is not None
    assert first.baseline_usage.total_tokens == 145
    assert first.conversation_id == UUID("00000000-0000-4000-8000-000000000001")


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda case: case.update(schemaVersion=2), "line 1"),
        (lambda case: case.update(unexpected=True), "line 1"),
        (lambda case: case.update(question="   "), "line 1"),
        (lambda case: case.update(conversationId="invalid"), "line 1"),
        (lambda case: case.update(expectedRoute="disabled"), "line 1"),
        (lambda case: case.update(allowDirect=False), "line 1"),
        (lambda case: case.update(acceptableDirectAnswers=[]), "line 1"),
        (
            lambda case: case["baselineUsage"].update(inputTokens=-1),
            "line 1",
        ),
        (
            lambda case: case["offlineCandidates"]["conversation"][0].update(score=1.1),
            "line 1",
        ),
    ],
)
def test_load_dataset_rejects_invalid_case_fields(
    tmp_path: Path,
    mutation: object,
    expected: str,
) -> None:
    cases = _valid_cases()
    mutation(cases[0])

    with pytest.raises(DatasetValidationError, match=expected):
        load_dataset(_write_jsonl(tmp_path / "invalid.jsonl", cases))


def test_load_dataset_rejects_acceptable_answers_for_non_direct_case(tmp_path: Path) -> None:
    cases = _valid_cases()
    cases[1]["acceptableDirectAnswers"] = ["No debe existir"]

    with pytest.raises(DatasetValidationError, match="line 2"):
        load_dataset(_write_jsonl(tmp_path / "invalid.jsonl", cases))


def test_load_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    cases = _valid_cases()
    cases[1]["id"] = cases[0]["id"]

    with pytest.raises(DatasetValidationError, match="duplicate case id"):
        load_dataset(_write_jsonl(tmp_path / "duplicate.jsonl", cases))


@pytest.mark.parametrize("content", ["", "\n", "{}\n\n"])
def test_load_dataset_rejects_empty_or_blank_lines(tmp_path: Path, content: str) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(DatasetValidationError):
        load_dataset(path)


def test_load_dataset_reports_invalid_json_without_echoing_content(tmp_path: Path) -> None:
    secret_question = "pregunta-que-no-debe-aparecer"
    path = tmp_path / "invalid.jsonl"
    path.write_text(f'{{"question": "{secret_question}"\n', encoding="utf-8")

    with pytest.raises(DatasetValidationError) as error:
        load_dataset(path)

    assert "line 1" in str(error.value)
    assert secret_question not in str(error.value)


def test_load_dataset_requires_all_routes_in_each_split(tmp_path: Path) -> None:
    cases = deepcopy(_valid_cases())
    cases.pop()

    with pytest.raises(DatasetValidationError, match="each split must contain all routes"):
        load_dataset(_write_jsonl(tmp_path / "unbalanced.jsonl", cases))

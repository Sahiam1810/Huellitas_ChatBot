import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.rag_routing.contracts import (
    DatasetSplit,
    RoutingDataset,
    RoutingEvaluationCase,
)
from app.orchestration.rag_contracts import SemanticRoute

_REQUIRED_ROUTES = {
    SemanticRoute.DIRECT,
    SemanticRoute.CONTEXTUAL,
    SemanticRoute.GENERAL,
}


class DatasetValidationError(ValueError):
    """Raised when an evaluation dataset cannot be trusted."""


def load_dataset(path: Path) -> RoutingDataset:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DatasetValidationError(f"cannot read dataset: {path}") from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetValidationError(f"dataset is not valid UTF-8: {path}") from exc

    lines = text.splitlines()
    if not lines:
        raise DatasetValidationError(f"dataset is empty: {path}")

    cases: list[RoutingEvaluationCase] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise DatasetValidationError(f"dataset contains a blank line at line {line_number}")
        cases.append(_parse_line(line, line_number))

    _validate_collection(tuple(cases))
    return RoutingDataset(cases=tuple(cases), sha256=hashlib.sha256(raw).hexdigest())


def _parse_line(line: str, line_number: int) -> RoutingEvaluationCase:
    try:
        payload = json.loads(line)
        return RoutingEvaluationCase.model_validate(payload)
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"invalid JSON at line {line_number}") from exc
    except ValidationError as exc:
        raise DatasetValidationError(f"invalid evaluation case at line {line_number}") from exc


def _validate_collection(cases: tuple[RoutingEvaluationCase, ...]) -> None:
    if not cases:
        raise DatasetValidationError("dataset is empty")

    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise DatasetValidationError("dataset contains a duplicate case id")

    for split in DatasetSplit:
        routes = {case.expected_route for case in cases if case.split is split}
        if routes != _REQUIRED_ROUTES:
            raise DatasetValidationError("each split must contain all routes")

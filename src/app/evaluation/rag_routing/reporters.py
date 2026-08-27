import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation.rag_routing.contracts import (
    EvaluationMetrics,
    EvaluationResult,
    RouteMetrics,
    ThresholdOptimizationResult,
)


@dataclass(frozen=True, slots=True)
class ReportMetadata:
    mode: str
    dataset_path: str
    dataset_sha256: str
    embedding_provider: str | None = None
    embedding_model: str | None = None


@dataclass(frozen=True, slots=True)
class ReportPaths:
    json_path: Path
    markdown_path: Path


def write_reports(
    result: EvaluationResult | ThresholdOptimizationResult,
    metadata: ReportMetadata,
    *,
    output_dir: Path,
    now: datetime,
) -> ReportPaths:
    timestamp = now.astimezone(UTC)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / f"rag-routing-{metadata.mode}-{stamp}"
    paths = ReportPaths(
        json_path=base.with_suffix(".json"),
        markdown_path=base.with_suffix(".md"),
    )
    payload = _report_payload(result, metadata, timestamp)
    markdown = _markdown_report(result, metadata, timestamp)
    _atomic_write(paths.json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(paths.markdown_path, markdown)
    return paths


def _report_payload(
    result: EvaluationResult | ThresholdOptimizationResult,
    metadata: ReportMetadata,
    timestamp: datetime,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "metadata": {
            "mode": metadata.mode,
            "datasetPath": metadata.dataset_path,
            "datasetSha256": metadata.dataset_sha256,
            "embedding": {
                "provider": metadata.embedding_provider,
                "model": metadata.embedding_model,
            },
        },
    }
    if isinstance(result, EvaluationResult):
        payload["resultType"] = "evaluation"
        payload["evaluation"] = _evaluation_payload(result)
    else:
        payload["resultType"] = "optimization"
        payload["optimization"] = {
            "evaluatedPairs": result.evaluated_pairs,
            "recommendation": {
                "status": result.recommendation.status.value,
                "highThreshold": result.recommendation.high_threshold,
                "mediumThreshold": result.recommendation.medium_threshold,
                "reason": result.recommendation.reason,
                "environment": result.recommendation.environment,
            },
            "calibration": (
                _evaluation_payload(result.calibration) if result.calibration is not None else None
            ),
            "validation": (
                _evaluation_payload(result.validation) if result.validation is not None else None
            ),
        }
    return payload


def _evaluation_payload(result: EvaluationResult) -> dict[str, Any]:
    return {
        "highThreshold": result.high_threshold,
        "mediumThreshold": result.medium_threshold,
        "metrics": _metrics_payload(result.metrics),
        "cases": [
            {
                "id": case.case_id,
                "split": case.split.value,
                "expectedRoute": case.expected_route.value,
                "predictedRoute": case.predicted_route.value,
                "topScore": case.top_score,
                "directAnswerCorrect": case.direct_answer_correct,
                "falseDirect": case.false_direct,
                "safetyCritical": case.safety_critical,
            }
            for case in result.cases
        ],
    }


def _metrics_payload(metrics: EvaluationMetrics) -> dict[str, Any]:
    return {
        "totalCases": metrics.total_cases,
        "accuracy": metrics.accuracy,
        "macroF1": metrics.macro_f1,
        "confusionMatrix": metrics.confusion_matrix,
        "perRoute": {
            route: _route_metrics_payload(values) for route, values in metrics.per_route.items()
        },
        "routeDistribution": metrics.route_distribution,
        "falseDirectIds": list(metrics.false_direct_ids),
        "unsafeDirectIds": list(metrics.unsafe_direct_ids),
        "baselineLlmCalls": metrics.baseline_llm_calls,
        "actualLlmCalls": metrics.actual_llm_calls,
        "llmCallsAvoided": metrics.llm_calls_avoided,
        "llmCallAvoidanceRate": metrics.llm_call_avoidance_rate,
        "directAnswerPrecision": metrics.direct_answer_precision,
        "observedTokensAvoided": metrics.observed_tokens_avoided,
        "tokenCoverage": metrics.token_coverage,
    }


def _route_metrics_payload(metrics: RouteMetrics) -> dict[str, float | int]:
    return {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1": metrics.f1,
        "support": metrics.support,
    }


def _markdown_report(
    result: EvaluationResult | ThresholdOptimizationResult,
    metadata: ReportMetadata,
    timestamp: datetime,
) -> str:
    lines = [
        "# RAG routing evaluation",
        "",
        f"- Mode: `{metadata.mode}`",
        f"- Generated: `{timestamp.isoformat(timespec='seconds')}`",
        f"- Dataset SHA-256: `{metadata.dataset_sha256}`",
        "",
    ]
    if isinstance(result, EvaluationResult):
        passed = not result.metrics.false_direct_ids
        lines.extend(_evaluation_markdown("Evaluation", result, passed))
    else:
        passed = result.recommendation.status.value == "recommended"
        lines.extend(
            [
                f"Safety gate: {'passed' if passed else 'blocked'}",
                f"Recommendation: `{result.recommendation.status.value}`",
                f"Evaluated pairs: {result.evaluated_pairs}",
                "",
            ]
        )
        if result.calibration is not None:
            lines.extend(_evaluation_markdown("Calibration", result.calibration, True))
        if result.validation is not None:
            lines.extend(_evaluation_markdown("Validation", result.validation, passed))
    return "\n".join(lines).rstrip() + "\n"


def _evaluation_markdown(
    title: str,
    result: EvaluationResult,
    passed: bool,
) -> list[str]:
    metrics = result.metrics
    false_ids = ", ".join(metrics.false_direct_ids) or "none"
    return [
        f"## {title}",
        "",
        f"Safety gate: {'passed' if passed else 'blocked'}",
        f"Thresholds: high `{result.high_threshold:.2f}`, medium `{result.medium_threshold:.2f}`",
        f"Accuracy: {metrics.accuracy:.4f}",
        f"Macro F1: {metrics.macro_f1:.4f}",
        f"Direct answer precision: {metrics.direct_answer_precision:.4f}",
        f"LLM calls avoided: {metrics.llm_calls_avoided}",
        f"Observed tokens avoided: {metrics.observed_tokens_avoided}",
        f"Token coverage: {metrics.token_coverage:.2%}",
        f"False direct cases: {false_ids}",
        "",
    ]


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)

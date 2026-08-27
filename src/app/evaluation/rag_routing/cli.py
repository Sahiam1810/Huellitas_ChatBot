import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.embeddings.embedding_factory import create_embedding_model
from app.adapters.vector_store.vector_store_factory import create_vector_store
from app.bootstrap.settings import load_settings
from app.evaluation.rag_routing.contracts import (
    EvaluationResult,
    RecommendationStatus,
    RoutingDataset,
    RoutingObservation,
    ThresholdOptimizationResult,
)
from app.evaluation.rag_routing.dataset_loader import (
    DatasetValidationError,
    load_dataset,
)
from app.evaluation.rag_routing.evaluator import evaluate_observations
from app.evaluation.rag_routing.observation_collector import (
    LiveRetrievalError,
    LiveRetrievalObservationCollector,
    OfflineObservationCollector,
)
from app.evaluation.rag_routing.reporters import ReportMetadata, write_reports
from app.evaluation.rag_routing.threshold_optimizer import optimize_thresholds


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit:
        return 1

    if arguments.mode == "live-retrieval" and not arguments.allow_paid_embeddings:
        print("live retrieval requires explicit paid embedding consent", file=sys.stderr)
        return 1

    try:
        dataset = load_dataset(arguments.dataset)
        observations, metadata = await _collect_observations(arguments, dataset)
        result = _run_command(arguments, observations)
        paths = write_reports(
            result,
            metadata,
            output_dir=arguments.output_dir,
            now=datetime.now(UTC),
        )
    except (DatasetValidationError, LiveRetrievalError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"JSON report: {paths.json_path}")
    print(f"Markdown report: {paths.markdown_path}")
    return _result_exit_code(result)


async def _collect_observations(
    arguments: argparse.Namespace,
    dataset: RoutingDataset,
) -> tuple[tuple[RoutingObservation, ...], ReportMetadata]:
    if arguments.mode == "offline":
        observations = await OfflineObservationCollector().collect(dataset)
        return observations, ReportMetadata(
            mode="offline",
            dataset_path=str(arguments.dataset),
            dataset_sha256=dataset.sha256,
        )

    settings = load_settings()
    rag_configuration = settings.active_rag_configuration()
    embedding_configuration = settings.active_embedding_configuration()
    if rag_configuration is None or embedding_configuration is None:
        raise ValueError("live retrieval requires active RAG and embedding configuration")

    embedding_model = create_embedding_model(settings)
    vector_store = create_vector_store(settings)
    if embedding_model is None or vector_store is None:
        raise ValueError("live retrieval infrastructure is not configured")
    if not hasattr(vector_store, "search_global") or not hasattr(
        vector_store, "search_conversation"
    ):
        await embedding_model.close()
        await vector_store.close()
        raise ValueError("vector store does not expose RAG search capabilities")

    try:
        collector = LiveRetrievalObservationCollector(
            embedding_model,
            vector_store,
            vector_store,
            global_limit=rag_configuration.global_limit,
            conversation_limit=rag_configuration.conversation_limit,
        )
        observations = await collector.collect(dataset)
    finally:
        await embedding_model.close()
        await vector_store.close()

    return observations, ReportMetadata(
        mode="live-retrieval",
        dataset_path=str(arguments.dataset),
        dataset_sha256=dataset.sha256,
        embedding_provider=embedding_configuration.provider.value,
        embedding_model=embedding_configuration.model,
    )


def _run_command(
    arguments: argparse.Namespace,
    observations: tuple[RoutingObservation, ...],
) -> EvaluationResult | ThresholdOptimizationResult:
    if arguments.command == "evaluate":
        return evaluate_observations(
            observations,
            high_threshold=arguments.high_threshold,
            medium_threshold=arguments.medium_threshold,
        )
    return optimize_thresholds(observations)


def _result_exit_code(result: EvaluationResult | ThresholdOptimizationResult) -> int:
    if isinstance(result, EvaluationResult):
        return 2 if result.metrics.false_direct_ids else 0
    return 0 if result.recommendation.status is RecommendationStatus.RECOMMENDED else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.rag_routing")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("evaluate", "tune"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dataset", type=Path, required=True)
        subparser.add_argument(
            "--mode",
            choices=("offline", "live-retrieval"),
            default="offline",
        )
        subparser.add_argument(
            "--output-dir",
            type=Path,
            default=Path(".cache/evaluations"),
        )
        subparser.add_argument("--allow-paid-embeddings", action="store_true")
        if command == "evaluate":
            subparser.add_argument("--high-threshold", type=float, default=0.95)
            subparser.add_argument("--medium-threshold", type=float, default=0.80)
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))

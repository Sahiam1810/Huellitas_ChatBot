import logging

from app.bootstrap.settings import LogLevel
from app.observability.tracing import GraphRunCompleted, GraphRunFailed, GraphRunStarted


class SafeLoggingGraphObserver:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("app.graph")

    def started(self, event: GraphRunStarted) -> None:
        self._logger.info(
            "event=graph_run_started correlation_id=%s execution_id=%s",
            event.correlation_id,
            event.execution_id,
        )

    def completed(self, event: GraphRunCompleted) -> None:
        self._logger.info(
            "event=graph_run_completed correlation_id=%s execution_id=%s duration_ms=%s "
            "route=%s fallback=%s module=%s provider=%s model=%s input_tokens=%s "
            "output_tokens=%s tokens_reported=%s rag_status=%s rag_route=%s "
            "global_matches=%s conversation_matches=%s memory_stored=%s "
            "knowledge_published=%s",
            event.correlation_id,
            event.execution_id,
            event.duration_ms,
            event.route.value,
            event.fallback.value,
            event.module,
            event.provider,
            event.model,
            event.input_tokens,
            event.output_tokens,
            event.tokens_reported,
            event.rag_status,
            event.rag_route,
            event.global_matches,
            event.conversation_matches,
            event.memory_stored,
            event.knowledge_published,
        )

    def failed(self, event: GraphRunFailed) -> None:
        self._logger.warning(
            "event=graph_run_failed correlation_id=%s execution_id=%s duration_ms=%s category=%s",
            event.correlation_id,
            event.execution_id,
            event.duration_ms,
            event.category.value,
        )


def configure_logging(level: LogLevel) -> None:
    logging.basicConfig(
        level=level.value,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )

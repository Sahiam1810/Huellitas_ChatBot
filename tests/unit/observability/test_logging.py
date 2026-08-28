import logging
from uuid import UUID

from app.observability.logging import SafeLoggingGraphObserver
from app.observability.tracing import (
    FallbackCategory,
    GraphFailureCategory,
    GraphRoute,
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunStarted,
)

CORRELATION_ID = UUID("11111111-1111-1111-1111-111111111111")
EXECUTION_ID = UUID("22222222-2222-2222-2222-222222222222")


def completed_event() -> GraphRunCompleted:
    return GraphRunCompleted(
        CORRELATION_ID,
        EXECUTION_ID,
        125.0,
        GraphRoute.MODULE,
        FallbackCategory.NONE,
        "appointments",
        "openai",
        "gpt-4o-mini",
        12,
        8,
        True,
        "used",
        "contextual",
        2,
        1,
        True,
        False,
    )


def test_logs_only_allowlisted_graph_run_fields(caplog: object) -> None:
    logger = logging.getLogger("test.graph.observer")
    observer = SafeLoggingGraphObserver(logger)
    with caplog.at_level(logging.INFO, logger=logger.name):  # type: ignore[attr-defined]
        observer.started(GraphRunStarted(CORRELATION_ID, EXECUTION_ID))
        observer.completed(completed_event())
        observer.failed(
            GraphRunFailed(
                CORRELATION_ID,
                EXECUTION_ID,
                30.0,
                GraphFailureCategory.MODEL_TIMEOUT,
            )
        )

    output = caplog.text  # type: ignore[attr-defined]
    assert "event=graph_run_started" in output
    assert "event=graph_run_completed" in output
    assert "event=graph_run_failed" in output
    for expected in (
        str(CORRELATION_ID),
        str(EXECUTION_ID),
        "route=module",
        "fallback=none",
        "module=appointments",
        "provider=openai",
        "model=gpt-4o-mini",
        "input_tokens=12",
        "rag_status=used",
        "category=model_timeout",
    ):
        assert expected in output


def test_observer_never_logs_sensitive_surrounding_values(caplog: object) -> None:
    sentinels = (
        "JWT-SENTINEL",
        "MESSAGE-SENTINEL",
        "RESPONSE-SENTINEL",
        "CONVERSATION-SENTINEL",
        "USER-SENTINEL",
        "PET-SENTINEL",
        "ROLE-SENTINEL",
        "EMAIL-SENTINEL",
        "PROMPT-SENTINEL",
        "RAG-CONTENT-SENTINEL",
        "EXCEPTION-TEXT-SENTINEL",
    )
    surrounding_data = {value: value for value in sentinels}
    logger = logging.getLogger("test.graph.privacy")
    observer = SafeLoggingGraphObserver(logger)
    with caplog.at_level(logging.INFO, logger=logger.name):  # type: ignore[attr-defined]
        observer.completed(completed_event())

    assert surrounding_data
    for sentinel in sentinels:
        assert sentinel not in caplog.text  # type: ignore[attr-defined]
        assert sentinel not in repr(observer)


def test_failure_log_does_not_attach_exception_information() -> None:
    records: list[logging.LogRecord] = []

    class RecordingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("test.graph.failure")
    logger.handlers = [RecordingHandler()]
    logger.propagate = False
    observer = SafeLoggingGraphObserver(logger)

    observer.failed(
        GraphRunFailed(CORRELATION_ID, EXECUTION_ID, 1.0, GraphFailureCategory.UNEXPECTED)
    )

    assert len(records) == 1
    assert records[0].exc_info is None

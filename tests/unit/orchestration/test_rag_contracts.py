from app.orchestration.rag_contracts import RagMessageResult, RagStatus


def test_rag_status_values_are_stable() -> None:
    assert [status.value for status in RagStatus] == [
        "disabled",
        "skipped",
        "empty",
        "used",
        "degraded",
    ]


def test_disabled_rag_result_does_not_claim_retrieval_or_writes() -> None:
    result = RagMessageResult.disabled()

    assert result.status is RagStatus.DISABLED
    assert result.global_matches == 0
    assert result.conversation_matches == 0
    assert result.memory_stored is False
    assert result.knowledge_published is False


def test_skipped_rag_result_does_not_claim_retrieval_or_writes() -> None:
    result = RagMessageResult.skipped()

    assert result.status is RagStatus.SKIPPED
    assert result.global_matches == 0
    assert result.conversation_matches == 0
    assert result.memory_stored is False
    assert result.knowledge_published is False

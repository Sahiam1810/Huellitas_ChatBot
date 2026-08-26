import pytest

from app.knowledge.contracts import CreateKnowledgeDocument
from app.knowledge.document_chunker import DocumentChunker


def test_create_command_normalizes_and_deduplicates_tags() -> None:
    command = CreateKnowledgeDocument(
        external_id="  vaccines  ",
        title="  Vaccines  ",
        content="  Authorized content.  ",
        source="  handbook  ",
        tags=("  dogs ", "vaccines", "dogs"),
        active=True,
    )

    assert command.external_id == "vaccines"
    assert command.content == "Authorized content."
    assert command.tags == ("dogs", "vaccines")


def test_chunker_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="content"):
        DocumentChunker(max_characters=20, overlap_characters=5).split("   ")


def test_chunker_returns_short_content_as_one_normalized_chunk() -> None:
    chunks = DocumentChunker(max_characters=20, overlap_characters=5).split("  short text  ")

    assert chunks == ("short text",)


def test_chunker_prefers_whitespace_and_keeps_bounded_overlap() -> None:
    chunks = DocumentChunker(max_characters=12, overlap_characters=3).split(
        "alpha beta gamma delta"
    )

    assert chunks == ("alpha beta", "eta gamma", "mma delta")
    assert all(chunk and len(chunk) <= 12 for chunk in chunks)


def test_chunker_terminates_for_a_long_token() -> None:
    chunks = DocumentChunker(max_characters=5, overlap_characters=2).split("abcdefghijk")

    assert chunks == ("abcde", "defgh", "ghijk")
    assert all(len(chunk) <= 5 for chunk in chunks)


@pytest.mark.parametrize(
    ("maximum", "overlap"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunker_rejects_invalid_configuration(maximum: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        DocumentChunker(max_characters=maximum, overlap_characters=overlap)

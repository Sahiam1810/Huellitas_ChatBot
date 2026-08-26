from dataclasses import dataclass
from enum import StrEnum


class RagStatus(StrEnum):
    DISABLED = "disabled"
    SKIPPED = "skipped"
    EMPTY = "empty"
    USED = "used"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class RetrievedRagContext:
    status: RagStatus
    query_vector: tuple[float, ...] | None = None
    prompt_context: str | None = None
    global_matches: int = 0
    conversation_matches: int = 0


@dataclass(frozen=True, slots=True)
class RagWriteResult:
    memory_stored: bool = False
    knowledge_published: bool = False
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class RagMessageResult:
    status: RagStatus
    global_matches: int = 0
    conversation_matches: int = 0
    memory_stored: bool = False
    knowledge_published: bool = False

    @classmethod
    def disabled(cls) -> "RagMessageResult":
        return cls(status=RagStatus.DISABLED)

    @classmethod
    def skipped(cls) -> "RagMessageResult":
        return cls(status=RagStatus.SKIPPED)

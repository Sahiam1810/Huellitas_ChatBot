import math
from dataclasses import dataclass
from enum import StrEnum


class RagStatus(StrEnum):
    DISABLED = "disabled"
    SKIPPED = "skipped"
    EMPTY = "empty"
    USED = "used"
    DEGRADED = "degraded"


class SemanticRoute(StrEnum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    GENERAL = "general"
    DISABLED = "disabled"
    SKIPPED = "skipped"
    DEGRADED = "degraded"


def _validate_top_score(value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or not -1 <= value <= 1):
        raise ValueError("top_score must be finite and between -1 and 1")


@dataclass(frozen=True, slots=True)
class RetrievedRagContext:
    status: RagStatus
    query_vector: tuple[float, ...] | None = None
    prompt_context: str | None = None
    global_matches: int = 0
    conversation_matches: int = 0
    route: SemanticRoute = SemanticRoute.DISABLED
    top_score: float | None = None
    direct_answer: str | None = None

    def __post_init__(self) -> None:
        _validate_top_score(self.top_score)
        if self.direct_answer is not None:
            normalized = self.direct_answer.strip()
            if not normalized:
                raise ValueError("direct_answer cannot be blank")
            object.__setattr__(self, "direct_answer", normalized)


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
    route: SemanticRoute = SemanticRoute.DISABLED
    top_score: float | None = None

    def __post_init__(self) -> None:
        _validate_top_score(self.top_score)

    @classmethod
    def disabled(cls) -> "RagMessageResult":
        return cls(status=RagStatus.DISABLED, route=SemanticRoute.DISABLED)

    @classmethod
    def skipped(cls) -> "RagMessageResult":
        return cls(status=RagStatus.SKIPPED, route=SemanticRoute.SKIPPED)

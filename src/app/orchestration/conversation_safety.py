from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ConversationSafetyClassification(StrEnum):
    ALLOWED = "allowed"
    OUT_OF_SCOPE = "out_of_scope"
    PROMPT_INJECTION = "prompt_injection"


@dataclass(frozen=True, slots=True)
class ConversationSafetyDecision:
    classification: ConversationSafetyClassification
    confidence: float
    reason: str

    @property
    def allowed(self) -> bool:
        return self.classification is ConversationSafetyClassification.ALLOWED


class ConversationSafetyGuard(Protocol):
    async def evaluate(self, message: str) -> ConversationSafetyDecision: ...

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestration.intent_router import RoutingDecision
from app.orchestration.message_processor import MessageCommand


@dataclass(frozen=True, slots=True)
class IntentCandidate:
    module_id: str
    intent: str
    score: float
    examples: tuple[str, ...]

    def __post_init__(self) -> None:
        module_id = self.module_id.strip()
        intent = self.intent.strip()
        examples = tuple(example.strip() for example in self.examples if example.strip())
        if not module_id or not intent or not examples:
            raise ValueError("Intent candidate requires module, intent, and examples")
        if not -1 <= self.score <= 1:
            raise ValueError("Intent candidate score must be between minus one and one")
        object.__setattr__(self, "module_id", module_id)
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "examples", examples)


@runtime_checkable
class IntentAdjudicator(Protocol):
    async def adjudicate(
        self,
        command: MessageCommand,
        candidates: tuple[IntentCandidate, ...],
    ) -> RoutingDecision: ...

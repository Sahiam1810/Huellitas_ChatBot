from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest


class RoutingKind(StrEnum):
    MODULE = "module"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


def _normalized(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-blank text")
    return normalized


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    kind: RoutingKind
    intent: str | None = None
    module_id: str | None = None
    reason: str | None = None

    @classmethod
    def module(cls, *, intent: str, module_id: str) -> "RoutingDecision":
        return cls(
            kind=RoutingKind.MODULE,
            intent=_normalized("intent", intent),
            module_id=_normalized("module_id", module_id),
        )

    @classmethod
    def unknown(cls, reason: str) -> "RoutingDecision":
        return cls(kind=RoutingKind.UNKNOWN, reason=_normalized("reason", reason))

    @classmethod
    def ambiguous(cls, reason: str) -> "RoutingDecision":
        return cls(kind=RoutingKind.AMBIGUOUS, reason=_normalized("reason", reason))


@runtime_checkable
class IntentRouter(Protocol):
    async def route(
        self,
        command: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision: ...

import logging

from app.orchestration.intent_router import IntentRouter, RoutingDecision, RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.shared.exceptions import EmbeddingModelError

logger = logging.getLogger(__name__)


class CompositeIntentRouter:
    def __init__(self, primary: IntentRouter, fallback: IntentRouter) -> None:
        self._primary = primary
        self._fallback = fallback

    async def route(
        self,
        command: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        primary_decision = await self._primary.route(command, manifests)
        if primary_decision.kind is not RoutingKind.UNKNOWN:
            return primary_decision
        try:
            return await self._fallback.route(command, manifests)
        except EmbeddingModelError:
            logger.warning("semantic_intent_routing_degraded")
            return primary_decision

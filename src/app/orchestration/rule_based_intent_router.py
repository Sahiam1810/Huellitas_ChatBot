import re
import unicodedata
from dataclasses import dataclass

from app.orchestration.intent_router import RoutingDecision
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest


def normalize_for_routing(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())


@dataclass(frozen=True, slots=True)
class IntentRule:
    module_id: str
    intent: str
    phrases: tuple[str, ...]


class RuleBasedIntentRouter:
    def __init__(self, rules: tuple[IntentRule, ...]) -> None:
        self._rules = rules

    async def route(
        self,
        command: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        available = {manifest.module_id: manifest for manifest in manifests}
        message = normalize_for_routing(command.message)
        matches: list[tuple[int, IntentRule]] = []
        for rule in self._rules:
            manifest = available.get(rule.module_id)
            if manifest is None or rule.intent not in manifest.intents:
                continue
            lengths = [
                len(normalized)
                for phrase in rule.phrases
                if (normalized := normalize_for_routing(phrase)) in message
            ]
            if lengths:
                matches.append((max(lengths), rule))
        if not matches:
            return RoutingDecision.unknown("no deterministic module rule matched")
        best_score = max(score for score, _ in matches)
        winners = [rule for score, rule in matches if score == best_score]
        if len({(rule.module_id, rule.intent) for rule in winners}) != 1:
            return RoutingDecision.ambiguous("multiple deterministic module rules matched")
        selected = winners[0]
        return RoutingDecision.module(intent=selected.intent, module_id=selected.module_id)

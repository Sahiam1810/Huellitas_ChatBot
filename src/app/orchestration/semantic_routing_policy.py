from dataclasses import dataclass

from app.orchestration.rag_contracts import SemanticRoute
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch

_QUESTION_PREFIX = "Question:\n"
_ANSWER_SEPARATOR = "\n\nAnswer:\n"


@dataclass(frozen=True, slots=True)
class SemanticRoutingDecision:
    route: SemanticRoute
    top_score: float | None
    global_matches: tuple[GlobalKnowledgeMatch, ...] = ()
    conversation_matches: tuple[ConversationMemoryMatch, ...] = ()
    direct_answer: str | None = None


class SemanticRoutingPolicy:
    def __init__(self, *, high_threshold: float, medium_threshold: float) -> None:
        if not 0 <= medium_threshold < high_threshold <= 1:
            raise ValueError("semantic thresholds must satisfy 0 <= medium < high <= 1")
        self._high_threshold = high_threshold
        self._medium_threshold = medium_threshold

    def decide(
        self,
        *,
        global_matches: tuple[GlobalKnowledgeMatch, ...],
        conversation_matches: tuple[ConversationMemoryMatch, ...],
        degraded: bool,
        allow_direct: bool,
    ) -> SemanticRoutingDecision:
        scores = tuple(match.score for match in (*global_matches, *conversation_matches))
        top_score = max(scores, default=None)
        accepted_global = tuple(
            match for match in global_matches if match.score >= self._medium_threshold
        )
        accepted_conversation = tuple(
            match for match in conversation_matches if match.score >= self._medium_threshold
        )

        if degraded:
            return SemanticRoutingDecision(
                route=SemanticRoute.DEGRADED,
                top_score=top_score,
                global_matches=accepted_global,
                conversation_matches=accepted_conversation,
            )

        direct_answer = None
        if allow_direct:
            direct_answer = self._best_direct_answer(accepted_global, accepted_conversation)
        if direct_answer is not None:
            return SemanticRoutingDecision(
                route=SemanticRoute.DIRECT,
                top_score=top_score,
                global_matches=accepted_global,
                conversation_matches=accepted_conversation,
                direct_answer=direct_answer,
            )

        route = (
            SemanticRoute.CONTEXTUAL
            if top_score is not None and top_score >= self._medium_threshold
            else SemanticRoute.GENERAL
        )
        return SemanticRoutingDecision(
            route=route,
            top_score=top_score,
            global_matches=accepted_global,
            conversation_matches=accepted_conversation,
        )

    def _best_direct_answer(
        self,
        global_matches: tuple[GlobalKnowledgeMatch, ...],
        conversation_matches: tuple[ConversationMemoryMatch, ...],
    ) -> str | None:
        candidates = [
            (match.score, answer)
            for match in global_matches
            if match.score >= self._high_threshold
            and (answer := self._approved_answer(match)) is not None
        ]
        candidates.extend(
            (match.score, match.answer)
            for match in conversation_matches
            if match.score >= self._high_threshold
        )
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[0])[1]

    @staticmethod
    def _approved_answer(match: GlobalKnowledgeMatch) -> str | None:
        if match.kind is not GlobalKnowledgeKind.APPROVED_EXCHANGE:
            return None
        if not match.content.startswith(_QUESTION_PREFIX):
            return None
        question, separator, answer = match.content[len(_QUESTION_PREFIX) :].partition(
            _ANSWER_SEPARATOR
        )
        normalized_answer = answer.strip()
        if not separator or not question.strip() or not normalized_answer:
            return None
        return normalized_answer

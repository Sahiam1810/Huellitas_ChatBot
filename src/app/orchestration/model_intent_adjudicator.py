import asyncio
import json
import logging
import math
from typing import Any

from app.orchestration.intent_adjudicator import IntentAdjudicator, IntentCandidate
from app.orchestration.intent_router import RoutingDecision
from app.orchestration.message_processor import MessageCommand
from app.ports.chat_model import ChatMessage, ChatModel, ChatRequest, ChatRole
from app.shared.exceptions import ChatModelError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Clasifica la intención operativa del mensaje usando exclusivamente uno de los candidatos.
Distingue solicitar una operación de pedir información: reservar o sacar una consulta es
agendamiento; preguntar qué servicios existen es catálogo; describir síntomas es orientación.
No respondas al usuario ni inventes identificadores. Si ninguno aplica, devuelve null.
Devuelve solamente JSON con moduleId, intent y confidence entre 0 y 1, sin Markdown.
"""


class ModelIntentAdjudicator(IntentAdjudicator):
    def __init__(
        self,
        model: ChatModel,
        *,
        minimum_confidence: float,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> None:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("Intent adjudicator confidence must be between zero and one")
        if max_output_tokens < 1:
            raise ValueError("Intent adjudicator output limit must be positive")
        if timeout_seconds <= 0:
            raise ValueError("Intent adjudicator timeout must be positive")
        self._model = model
        self._minimum_confidence = minimum_confidence
        self._max_output_tokens = max_output_tokens
        self._timeout_seconds = timeout_seconds

    async def adjudicate(
        self,
        command: MessageCommand,
        candidates: tuple[IntentCandidate, ...],
    ) -> RoutingDecision:
        if not candidates:
            return RoutingDecision.unknown("intent adjudication has no candidates")

        payload = {
            "message": command.message,
            "candidates": [
                {
                    "moduleId": candidate.module_id,
                    "intent": candidate.intent,
                    "examples": candidate.examples,
                }
                for candidate in candidates
            ],
        }
        try:
            response = await asyncio.wait_for(
                self._model.generate(
                    ChatRequest(
                        messages=(
                            ChatMessage(ChatRole.SYSTEM, SYSTEM_PROMPT),
                            ChatMessage(
                                ChatRole.USER,
                                json.dumps(payload, ensure_ascii=False),
                            ),
                        ),
                        max_output_tokens=self._max_output_tokens,
                    )
                ),
                timeout=self._timeout_seconds,
            )
            decision = self._parse_decision(response.text, candidates)
        except (ChatModelError, TimeoutError, ValueError, TypeError, KeyError):
            logger.warning(
                "intent_adjudication_degraded provider=%s model=%s",
                self._model.provider.value,
                self._model.model,
            )
            return RoutingDecision.ambiguous(
                "intent adjudication did not produce a safe decision"
            )

        logger.info(
            "intent_adjudication_completed provider=%s model=%s input_tokens=%s "
            "output_tokens=%s selected_module=%s selected_intent=%s",
            response.provider.value,
            response.model,
            response.input_tokens,
            response.output_tokens,
            decision.module_id,
            decision.intent,
        )
        return decision

    def _parse_decision(
        self,
        text: str,
        candidates: tuple[IntentCandidate, ...],
    ) -> RoutingDecision:
        value: Any = json.loads(text)
        if not isinstance(value, dict) or set(value) != {"moduleId", "intent", "confidence"}:
            raise ValueError("Intent adjudication response has an invalid shape")

        module_id = value["moduleId"]
        intent = value["intent"]
        confidence = value["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Intent adjudication confidence is invalid")
        if module_id is None and intent is None:
            return RoutingDecision.unknown("intent adjudicator rejected all candidates")
        if not isinstance(module_id, str) or not isinstance(intent, str):
            raise ValueError("Intent adjudication selection is invalid")
        if confidence < self._minimum_confidence:
            raise ValueError("Intent adjudication confidence is insufficient")

        allowed = {(candidate.module_id, candidate.intent) for candidate in candidates}
        selected = (module_id.strip(), intent.strip())
        if selected not in allowed:
            raise ValueError("Intent adjudication selected an unavailable candidate")
        return RoutingDecision.module(module_id=selected[0], intent=selected[1])

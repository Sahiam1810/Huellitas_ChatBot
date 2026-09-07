import asyncio
import logging
import math
from dataclasses import dataclass

from app.orchestration.intent_router import RoutingDecision
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.ports.embedding_model import EmbeddingModel
from app.shared.exceptions import EmbeddingInvalidResponseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SemanticIntentDefinition:
    module_id: str
    intent: str
    examples: tuple[str, ...]

    def __post_init__(self) -> None:
        module_id = self.module_id.strip()
        intent = self.intent.strip()
        examples = tuple(example.strip() for example in self.examples if example.strip())
        if not module_id or not intent or not examples:
            raise ValueError("Semantic intent definition requires module, intent, and examples")
        object.__setattr__(self, "module_id", module_id)
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "examples", examples)


class SemanticIntentRouter:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        definitions: tuple[SemanticIntentDefinition, ...],
        *,
        minimum_score: float,
        minimum_margin: float,
    ) -> None:
        if not 0 <= minimum_score <= 1:
            raise ValueError("Semantic intent minimum score must be between zero and one")
        if not 0 <= minimum_margin <= 1:
            raise ValueError("Semantic intent minimum margin must be between zero and one")
        self._embedding_model = embedding_model
        self._definitions = definitions
        self._minimum_score = minimum_score
        self._minimum_margin = minimum_margin
        self._example_vectors: tuple[tuple[tuple[float, ...], ...], ...] | None = None
        self._prepare_lock = asyncio.Lock()

    async def route(
        self,
        command: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        available = {
            (manifest.module_id, intent) for manifest in manifests for intent in manifest.intents
        }
        eligible = tuple(
            index
            for index, definition in enumerate(self._definitions)
            if (definition.module_id, definition.intent) in available
        )
        if not eligible:
            return RoutingDecision.unknown("no registered semantic intent is available")

        example_vectors = await self._prepared_example_vectors()
        response = await self._embedding_model.embed_query(command.message)
        if len(response.vectors) != 1:
            raise EmbeddingInvalidResponseError("Semantic query returned an invalid vector count")
        query_vector = response.vectors[0].values
        scores = sorted(
            [
                (
                    max(
                        self._cosine_similarity(query_vector, example_vector)
                        for example_vector in example_vectors[index]
                    ),
                    self._definitions[index],
                )
                for index in eligible
            ],
            key=lambda item: item[0],
        )
        best_score, best = scores[-1]
        if best_score < self._minimum_score:
            logger.info(
                "semantic_intent_unknown module=%s intent=%s top_score=%.6f",
                best.module_id,
                best.intent,
                best_score,
            )
            return RoutingDecision.unknown("semantic intent score is below threshold")
        if len(scores) > 1:
            second_score = scores[-2][0]
            margin = best_score - second_score
            if margin < self._minimum_margin:
                logger.info(
                    "semantic_intent_ambiguous module=%s intent=%s top_score=%.6f margin=%.6f",
                    best.module_id,
                    best.intent,
                    best_score,
                    margin,
                )
                return RoutingDecision.ambiguous("semantic intent margin is insufficient")
        else:
            margin = 1.0
        logger.info(
            "semantic_intent_selected module=%s intent=%s top_score=%.6f margin=%.6f",
            best.module_id,
            best.intent,
            best_score,
            margin,
        )
        return RoutingDecision.module(intent=best.intent, module_id=best.module_id)

    async def _prepared_example_vectors(self) -> tuple[tuple[tuple[float, ...], ...], ...]:
        if self._example_vectors is not None:
            return self._example_vectors
        async with self._prepare_lock:
            if self._example_vectors is not None:
                return self._example_vectors
            examples = tuple(
                example for definition in self._definitions for example in definition.examples
            )
            response = await self._embedding_model.embed_documents(examples)
            if len(response.vectors) != len(examples):
                raise EmbeddingInvalidResponseError(
                    "Semantic intent examples returned an invalid vector count"
                )
            grouped: list[tuple[tuple[float, ...], ...]] = []
            offset = 0
            for definition in self._definitions:
                next_offset = offset + len(definition.examples)
                grouped.append(
                    tuple(vector.values for vector in response.vectors[offset:next_offset])
                )
                offset = next_offset
            self._example_vectors = tuple(grouped)
            return self._example_vectors

    @staticmethod
    def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right) or not left:
            raise EmbeddingInvalidResponseError("Semantic vectors have incompatible dimensions")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            raise EmbeddingInvalidResponseError("Semantic vectors cannot be empty")
        similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
        return max(-1.0, min(1.0, similarity))

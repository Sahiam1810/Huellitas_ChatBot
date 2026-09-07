from uuid import uuid4

import pytest

from app.orchestration.intent_router import RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.semantic_intent_router import (
    SemanticIntentDefinition,
    SemanticIntentRouter,
)
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)


class ControlledEmbeddings:
    dimensions = 2

    def __init__(self, vectors: dict[str, tuple[float, float]]) -> None:
        self._vectors = vectors
        self.document_calls = 0

    async def embed_query(self, text: str) -> EmbeddingResponse:
        return self._response((self._vectors[text],))

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        self.document_calls += 1
        return self._response(tuple(self._vectors[text] for text in texts))

    async def close(self) -> None:
        return None

    @staticmethod
    def _response(vectors: tuple[tuple[float, float], ...]) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=tuple(EmbeddingVector(values=value) for value in vectors),
            provider=EmbeddingProvider.OPENAI,
            model="controlled",
            usage=EmbeddingUsage(input_tokens=1, total_tokens=1),
        )


def command(message: str) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("TelegramGuest",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="semantic-route-1",
    )


def manifest(module_id: str, *intents: str) -> ModuleManifest:
    return ModuleManifest(module_id, "1.0.0", module_id, intents=intents)


@pytest.mark.anyio
async def test_routes_paraphrase_to_registered_semantic_intent() -> None:
    embeddings = ControlledEmbeddings(
        {
            "listar prestaciones de la clinica": (1.0, 0.0),
            "consultar animales propios": (0.0, 1.0),
            "que servicios tienen": (0.98, 0.10),
        }
    )
    router = SemanticIntentRouter(
        embeddings,
        (
            SemanticIntentDefinition(
                "services_catalog",
                "services.list",
                ("listar prestaciones de la clinica",),
            ),
            SemanticIntentDefinition("pet_profile", "pets.list", ("consultar animales propios",)),
        ),
        minimum_score=0.75,
        minimum_margin=0.10,
    )

    decision = await router.route(
        command("que servicios tienen"),
        (
            manifest("services_catalog", "services.list"),
            manifest("pet_profile", "pets.list"),
        ),
    )

    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == "services_catalog"
    assert decision.intent == "services.list"


@pytest.mark.anyio
async def test_returns_unknown_when_best_similarity_is_below_threshold() -> None:
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "listar prestaciones": (1.0, 0.0),
                "saludo casual": (0.4, 0.9165),
            }
        ),
        (SemanticIntentDefinition("services_catalog", "services.list", ("listar prestaciones",)),),
        minimum_score=0.75,
        minimum_margin=0.10,
    )

    decision = await router.route(
        command("saludo casual"),
        (manifest("services_catalog", "services.list"),),
    )

    assert decision.kind is RoutingKind.UNKNOWN


@pytest.mark.anyio
async def test_returns_ambiguous_when_two_intents_have_insufficient_margin() -> None:
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "listar servicios": (1.0, 0.0),
                "buscar un servicio": (0.99, 0.14),
                "atenciones veterinarias": (1.0, 0.04),
            }
        ),
        (
            SemanticIntentDefinition("services_catalog", "services.list", ("listar servicios",)),
            SemanticIntentDefinition(
                "services_catalog", "services.search", ("buscar un servicio",)
            ),
        ),
        minimum_score=0.75,
        minimum_margin=0.05,
    )

    decision = await router.route(
        command("atenciones veterinarias"),
        (manifest("services_catalog", "services.list", "services.search"),),
    )

    assert decision.kind is RoutingKind.AMBIGUOUS


@pytest.mark.anyio
async def test_ignores_semantic_definition_that_is_not_registered() -> None:
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "listar servicios": (1.0, 0.0),
                "consultar mascotas": (0.0, 1.0),
                "que servicios tienen": (1.0, 0.0),
            }
        ),
        (
            SemanticIntentDefinition("services_catalog", "services.list", ("listar servicios",)),
            SemanticIntentDefinition("pet_profile", "pets.list", ("consultar mascotas",)),
        ),
        minimum_score=0.75,
        minimum_margin=0.05,
    )

    decision = await router.route(
        command("que servicios tienen"),
        (manifest("pet_profile", "pets.list"),),
    )

    assert decision.kind is RoutingKind.UNKNOWN


@pytest.mark.anyio
async def test_reuses_prepared_intent_embeddings_between_messages() -> None:
    embeddings = ControlledEmbeddings(
        {
            "listar servicios": (1.0, 0.0),
            "que servicios tienen": (1.0, 0.0),
            "que atenciones ofrecen": (0.99, 0.01),
        }
    )
    router = SemanticIntentRouter(
        embeddings,
        (SemanticIntentDefinition("services_catalog", "services.list", ("listar servicios",)),),
        minimum_score=0.75,
        minimum_margin=0.05,
    )
    manifests = (manifest("services_catalog", "services.list"),)

    await router.route(command("que servicios tienen"), manifests)
    await router.route(command("que atenciones ofrecen"), manifests)

    assert embeddings.document_calls == 1

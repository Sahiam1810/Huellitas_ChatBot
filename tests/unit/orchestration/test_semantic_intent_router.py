import math
from uuid import uuid4

import pytest

from app.orchestration.intent_adjudicator import IntentCandidate
from app.orchestration.intent_router import RoutingDecision, RoutingKind
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


class Adjudicator:
    def __init__(self, decision: RoutingDecision) -> None:
        self._decision = decision
        self.calls = 0
        self.received_candidates: tuple[IntentCandidate, ...] = ()

    async def adjudicate(
        self,
        command: MessageCommand,
        candidates: tuple[IntentCandidate, ...],
    ) -> RoutingDecision:
        self.calls += 1
        self.received_candidates = candidates
        return self._decision


def vector_for_score(score: float) -> tuple[float, float]:
    return (score, math.sqrt(1 - score**2))


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
            SemanticIntentDefinition("appointments", "appointments.book", ("buscar un servicio",)),
        ),
        minimum_score=0.75,
        minimum_margin=0.05,
    )

    decision = await router.route(
        command("atenciones veterinarias"),
        (
            manifest("services_catalog", "services.list"),
            manifest("appointments", "appointments.book"),
        ),
    )

    assert decision.kind is RoutingKind.AMBIGUOUS


@pytest.mark.anyio
async def test_close_intents_in_same_module_select_best_instead_of_general_fallback() -> None:
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "listar prestaciones": (1.0, 0.0),
                "buscar una prestacion": (0.99, 0.14),
                "oferta de la clinica": (1.0, 0.04),
            }
        ),
        (
            SemanticIntentDefinition("services_catalog", "services.list", ("listar prestaciones",)),
            SemanticIntentDefinition(
                "services_catalog", "services.search", ("buscar una prestacion",)
            ),
        ),
        minimum_score=0.75,
        minimum_margin=0.05,
    )

    decision = await router.route(
        command("oferta de la clinica"),
        (manifest("services_catalog", "services.list", "services.search"),),
    )

    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == "services_catalog"
    assert decision.intent == "services.list"


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


@pytest.mark.anyio
async def test_close_cross_module_scores_use_one_adjudication() -> None:
    message = "Quiero sacar una consulta general para mi cachorro"
    adjudicator = Adjudicator(
        RoutingDecision.module(module_id="appointments", intent="appointments.book")
    )
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "pregunta general de salud": vector_for_score(0.640084),
                "reservar consulta veterinaria": vector_for_score(0.586304),
                message: (1.0, 0.0),
            }
        ),
        (
            SemanticIntentDefinition(
                "veterinary_guidance", "guidance.ask", ("pregunta general de salud",)
            ),
            SemanticIntentDefinition(
                "appointments", "appointments.book", ("reservar consulta veterinaria",)
            ),
        ),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )

    decision = await router.route(
        command(message),
        (
            manifest("veterinary_guidance", "guidance.ask"),
            manifest("appointments", "appointments.book"),
        ),
    )

    assert decision == RoutingDecision.module(
        module_id="appointments", intent="appointments.book"
    )
    assert adjudicator.calls == 1
    assert len(adjudicator.received_candidates) == 2


@pytest.mark.anyio
async def test_adjudicator_cannot_select_a_candidate_outside_active_manifests() -> None:
    message = "solicitud ambigua"
    adjudicator = Adjudicator(
        RoutingDecision.module(module_id="invented", intent="invented.execute")
    )
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "orientacion veterinaria": vector_for_score(0.70),
                "reservar cita": vector_for_score(0.65),
                message: (1.0, 0.0),
            }
        ),
        (
            SemanticIntentDefinition(
                "veterinary_guidance", "guidance.ask", ("orientacion veterinaria",)
            ),
            SemanticIntentDefinition(
                "appointments", "appointments.book", ("reservar cita",)
            ),
        ),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )

    decision = await router.route(
        command(message),
        (
            manifest("veterinary_guidance", "guidance.ask"),
            manifest("appointments", "appointments.book"),
        ),
    )

    assert decision.kind is RoutingKind.AMBIGUOUS


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("best_score", "competing_score", "expected_kind"),
    ((0.80, 0.40, RoutingKind.MODULE), (0.40, 0.35, RoutingKind.UNKNOWN)),
)
async def test_clear_or_low_score_match_does_not_use_adjudicator(
    best_score: float,
    competing_score: float,
    expected_kind: RoutingKind,
) -> None:
    message = "consulta controlada"
    adjudicator = Adjudicator(RoutingDecision.ambiguous("must not be called"))
    router = SemanticIntentRouter(
        ControlledEmbeddings(
            {
                "orientacion veterinaria": vector_for_score(best_score),
                "reservar cita": vector_for_score(competing_score),
                message: (1.0, 0.0),
            }
        ),
        (
            SemanticIntentDefinition(
                "veterinary_guidance", "guidance.ask", ("orientacion veterinaria",)
            ),
            SemanticIntentDefinition(
                "appointments", "appointments.book", ("reservar cita",)
            ),
        ),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )

    decision = await router.route(
        command(message),
        (
            manifest("veterinary_guidance", "guidance.ask"),
            manifest("appointments", "appointments.book"),
        ),
    )

    assert decision.kind is expected_kind
    assert adjudicator.calls == 0

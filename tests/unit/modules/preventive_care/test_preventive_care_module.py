from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.preventive_care.graph import PreventiveCareModuleExecutor
from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
from app.modules.preventive_care.routing import PREVENTIVE_CARE_ROUTING_RULES
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.ports.pet_profile_gateway import PetProfile
from app.ports.preventive_knowledge_gateway import PreventiveKnowledgeResult
from app.ports.token_validator import AuthenticatedPrincipal
from app.ports.vaccinations_gateway import VaccinationRecord


def pet() -> PetProfile:
    return PetProfile(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        name="Luna",
        age=3,
        gender="Hembra",
        weight=5.5,
        observations=None,
        species_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        species_name="Perro",
        race_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        race_name="Mestizo",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def vaccination() -> VaccinationRecord:
    return VaccinationRecord(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        client_pet_id=UUID("22222222-2222-2222-2222-222222222222"),
        record_id=UUID("33333333-3333-3333-3333-333333333333"),
        vaccine_name="Rabia",
        dose_number=1,
        application_date=datetime(2026, 1, 15, 10, tzinfo=UTC),
        next_dose_date=datetime(2027, 1, 15, 10, tzinfo=UTC),
        created_at=datetime(2026, 1, 15, 10, 5, tzinfo=UTC),
    )


class PetGateway:
    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        return (pet(),)

    async def close(self) -> None:
        return None


class VaccinationsGatewayMock:
    async def list_owned(self, bearer_token: str) -> tuple[VaccinationRecord, ...]:
        return (vaccination(),)

    async def close(self) -> None:
        return None


class KnowledgeGateway:
    def __init__(self, result: PreventiveKnowledgeResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def retrieve(self, query: str) -> PreventiveKnowledgeResult:
        self.queries.append(query)
        return self.result


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role="Cliente",
            username="samuel",
            email="samuel@example.com",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )


def request(message: str, intent: str) -> ModuleExecutionRequest:
    return ModuleExecutionRequest(
        command=MessageCommand(
            message=message,
            conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
            user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=("Cliente",),
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="preventive-1",
            publish_as_global_knowledge=False,
        ),
        intent=intent,
        manifest=PREVENTIVE_CARE_MANIFEST,
    )


@pytest.mark.anyio
async def test_vaccines_intent_lists_official_records_for_pet() -> None:
    executor = PreventiveCareModuleExecutor(
        PetGateway(),  # type: ignore[arg-type]
        VaccinationsGatewayMock(),  # type: ignore[arg-type]
        "America/Bogota",
    )
    result = await executor.execute(
        request("¿Qué vacunas tiene Luna?", "preventive.vaccines"), context()
    )
    assert "Rabia" in (result.message or "")
    assert "Luna" in (result.message or "")
    assert result.rag.status is RagStatus.SKIPPED


@pytest.mark.anyio
async def test_upcoming_intent_highlights_next_dose() -> None:
    executor = PreventiveCareModuleExecutor(
        PetGateway(),  # type: ignore[arg-type]
        VaccinationsGatewayMock(),  # type: ignore[arg-type]
        "America/Bogota",
    )
    result = await executor.execute(
        request("¿Cuándo le toca la próxima vacuna a Luna?", "preventive.vaccines.upcoming"),
        context(),
    )
    assert "Próximas dosis" in (result.message or "")
    assert "Rabia" in (result.message or "")


@pytest.mark.anyio
async def test_ask_intent_uses_preventive_knowledge_and_disclaimer() -> None:
    executor = PreventiveCareModuleExecutor(
        PetGateway(),  # type: ignore[arg-type]
        VaccinationsGatewayMock(),  # type: ignore[arg-type]
        "America/Bogota",
        knowledge_gateway=KnowledgeGateway(
            PreventiveKnowledgeResult(
                status=RagStatus.USED,
                excerpts=("Desparasita cada 3 meses.",),
                match_count=1,
            )
        ),
    )
    result = await executor.execute(
        request("¿Cada cuánto desparasitar a Luna?", "preventive.ask"), context()
    )
    assert "no un diagnóstico" in (result.message or "")
    assert "Desparasita" in (result.message or "")
    assert result.rag.status is RagStatus.USED
    assert result.rag.route is SemanticRoute.CONTEXTUAL


@pytest.mark.anyio
async def test_preventive_vaccines_routes_deterministically() -> None:
    decision = await RuleBasedIntentRouter(PREVENTIVE_CARE_ROUTING_RULES).route(
        request("historial de vacunas de Luna", "preventive.vaccines").command,
        (PREVENTIVE_CARE_MANIFEST,),
    )
    assert decision.module_id == "preventive_care"
    assert decision.intent == "preventive.vaccines"

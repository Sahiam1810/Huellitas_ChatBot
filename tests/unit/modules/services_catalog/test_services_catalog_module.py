from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.services_catalog.graph import ServicesCatalogModuleExecutor
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.ports.service_knowledge_gateway import ServiceKnowledgeResult
from app.ports.services_catalog_gateway import (
    ServiceCatalogItem,
    ServicesCatalogAuthenticationError,
    ServicesCatalogForbiddenError,
    ServicesCatalogGateway,
    ServicesCatalogUnavailableError,
)
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType


def catalog() -> tuple[ServiceCatalogItem, ...]:
    return (
        ServiceCatalogItem(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            type_service_name="Consulta",
            name="Consulta general",
            duration_minutes=30,
            price=Decimal("55000"),
        ),
        ServiceCatalogItem(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            type_service_name="Consulta",
            name="Consulta especializada",
            duration_minutes=45,
            price=Decimal("85000"),
        ),
    )


class CatalogGateway(ServicesCatalogGateway):
    def __init__(self, result: tuple[ServiceCatalogItem, ...] = catalog()) -> None:
        self.result = result
        self.error: Exception | None = None

    async def list_available(self, bearer_token: str) -> tuple[ServiceCatalogItem, ...]:
        if self.error is not None:
            raise self.error
        return self.result

    async def close(self) -> None:
        return None


class KnowledgeGateway:
    def __init__(self, result: ServiceKnowledgeResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def describe(self, query: str) -> ServiceKnowledgeResult:
        self.queries.append(query)
        return self.result


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="secret-token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role="TelegramGuest",
            username="telegram_guest",
            email="guest@telegram.invalid",
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
            user_id=UUID("10000000-0000-0000-0000-000000000002"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=("TelegramGuest",),
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="services-message-001",
            publish_as_global_knowledge=False,
        ),
        intent=intent,
        manifest=SERVICES_CATALOG_MANIFEST,
    )


@pytest.mark.anyio
async def test_list_returns_official_catalog_values() -> None:
    result = await ServicesCatalogModuleExecutor(CatalogGateway()).execute(
        request("¿Qué servicios ofrecen?", "services.list"), context()
    )

    assert result.module_id == "services_catalog"
    assert result.response_type is MessageResponseType.RETRIEVED
    assert "Consulta general — Consulta — 30 minutos — $55.000 COP" in (result.message or "")
    assert "Consulta especializada — Consulta — 45 minutos — $85.000 COP" in (
        result.message or ""
    )


@pytest.mark.anyio
async def test_detail_with_multiple_matches_requests_a_selection() -> None:
    result = await ServicesCatalogModuleExecutor(CatalogGateway()).execute(
        request("¿Cuánto cuesta una consulta?", "services.detail"), context()
    )

    assert "varios servicios" in (result.message or "").casefold()
    assert "Consulta general" in (result.message or "")
    assert "Consulta especializada" in (result.message or "")


@pytest.mark.anyio
async def test_search_without_match_does_not_invent_a_service() -> None:
    result = await ServicesCatalogModuleExecutor(CatalogGateway()).execute(
        request("¿Tienen radiografía?", "services.search"), context()
    )

    assert "no encontré un servicio activo" in (result.message or "").casefold()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ServicesCatalogAuthenticationError("safe"), "validar tu sesión"),
        (ServicesCatalogForbiddenError("safe"), "autorizar la consulta"),
        (ServicesCatalogUnavailableError("safe"), "sistema veterinario"),
    ],
)
async def test_gateway_errors_are_translated_to_safe_module_messages(
    error: Exception, expected: str
) -> None:
    gateway = CatalogGateway()
    gateway.error = error

    result = await ServicesCatalogModuleExecutor(gateway).execute(
        request("¿Qué servicios ofrecen?", "services.list"), context()
    )

    assert expected in (result.message or "")
    assert "safe" not in (result.message or "")


@pytest.mark.anyio
async def test_single_service_appends_scoped_knowledge_without_replacing_official_data() -> None:
    knowledge = KnowledgeGateway(
        ServiceKnowledgeResult(
            status=RagStatus.USED,
            description="Incluye valoración clínica preventiva.",
            match_count=1,
            top_score=0.91,
        )
    )

    result = await ServicesCatalogModuleExecutor(
        CatalogGateway(), knowledge_gateway=knowledge
    ).execute(request("Cuánto cuesta la consulta general", "services.detail"), context())

    assert "30 minutos" in (result.message or "")
    assert "$55.000 COP" in (result.message or "")
    assert "Información adicional: Incluye valoración clínica preventiva." in (
        result.message or ""
    )
    assert knowledge.queries == ["Consulta general"]
    assert result.rag.status is RagStatus.USED
    assert result.rag.route is SemanticRoute.CONTEXTUAL
    assert result.rag.global_matches == 1
    assert result.rag.top_score == 0.91


@pytest.mark.anyio
async def test_list_does_not_query_optional_service_knowledge() -> None:
    knowledge = KnowledgeGateway(ServiceKnowledgeResult(status=RagStatus.EMPTY))

    result = await ServicesCatalogModuleExecutor(
        CatalogGateway(), knowledge_gateway=knowledge
    ).execute(request("Qué servicios ofrecen", "services.list"), context())

    assert knowledge.queries == []
    assert result.rag.status is RagStatus.DISABLED


@pytest.mark.anyio
async def test_degraded_knowledge_keeps_official_service_response() -> None:
    knowledge = KnowledgeGateway(ServiceKnowledgeResult(status=RagStatus.DEGRADED))

    result = await ServicesCatalogModuleExecutor(
        CatalogGateway(), knowledge_gateway=knowledge
    ).execute(request("Cuánto cuesta la consulta general", "services.detail"), context())

    assert "Consulta general" in (result.message or "")
    assert "$55.000 COP" in (result.message or "")
    assert result.rag.status is RagStatus.DEGRADED
    assert result.rag.route is SemanticRoute.DEGRADED

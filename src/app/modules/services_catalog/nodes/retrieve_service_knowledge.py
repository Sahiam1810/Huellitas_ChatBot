from app.ports.service_knowledge_gateway import (
    ServiceKnowledgeGateway,
    ServiceKnowledgeResult,
)


async def retrieve_service_knowledge(
    gateway: ServiceKnowledgeGateway | None,
    service_name: str,
) -> ServiceKnowledgeResult | None:
    if gateway is None:
        return None
    return await gateway.describe(service_name)

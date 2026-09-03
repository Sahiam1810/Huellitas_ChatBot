from app.orchestration.rag_contracts import RagStatus
from app.ports.preventive_knowledge_gateway import (
    PreventiveKnowledgeGateway,
    PreventiveKnowledgeResult,
)


async def retrieve_preventive_knowledge(
    gateway: PreventiveKnowledgeGateway | None,
    query: str,
) -> PreventiveKnowledgeResult:
    if gateway is None:
        return PreventiveKnowledgeResult(status=RagStatus.DISABLED)
    return await gateway.retrieve(query)

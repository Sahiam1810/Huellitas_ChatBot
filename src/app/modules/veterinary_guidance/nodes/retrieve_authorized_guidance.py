from app.ports.guidance_knowledge_gateway import (
    GuidanceKnowledgeGateway,
    GuidanceKnowledgeResult,
)


async def retrieve_authorized_guidance(
    gateway: GuidanceKnowledgeGateway | None,
    query: str,
) -> GuidanceKnowledgeResult:
    if gateway is None:
        from app.orchestration.rag_contracts import RagStatus

        return GuidanceKnowledgeResult(status=RagStatus.DISABLED)
    return await gateway.retrieve(query)

from app.modules.preventive_care.nodes.prepare_preventive_response import (
    prepare_preventive_ask_response,
)
from app.orchestration.rag_contracts import RagStatus
from app.ports.preventive_knowledge_gateway import PreventiveKnowledgeResult


def test_prepare_preventive_ask_includes_disclaimer_and_context() -> None:
    message = prepare_preventive_ask_response(
        knowledge=PreventiveKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Desparasita cada 3 meses.",),
        ),
        pet_context="Contexto: Luna, perro, 3 años.",
    )
    assert "no un diagnóstico" in message
    assert "Luna" in message
    assert "Desparasita" in message

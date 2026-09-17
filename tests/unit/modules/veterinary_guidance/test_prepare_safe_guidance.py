from app.modules.veterinary_guidance.domain.urgency_signals import UrgencyAssessment
from app.modules.veterinary_guidance.nodes.prepare_safe_guidance import prepare_safe_guidance
from app.orchestration.rag_contracts import RagStatus
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult


def test_prepare_safe_guidance_prioritizes_urgency_over_excerpts() -> None:
    message = prepare_safe_guidance(
        urgency=UrgencyAssessment(True, ("no respira",)),
        knowledge=GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Extracto irrelevante",),
        ),
    )
    assert "atención veterinaria inmediata" in message.lower()


def test_prepare_safe_guidance_includes_disclaimer_and_excerpts() -> None:
    message = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Mantén agua fresca y observa el apetito.",),
        ),
    )
    assert "no un diagnóstico" in message
    assert "agua fresca" in message


def test_prepare_safe_guidance_handles_empty_and_degraded() -> None:
    empty = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(status=RagStatus.EMPTY),
    )
    degraded = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(status=RagStatus.DEGRADED),
    )
    disabled = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(status=RagStatus.DISABLED),
    )
    assert "guía autorizada" in empty.lower()
    assert "asesor" in empty.lower()
    assert "no puedo consultar" in degraded.lower()
    assert "asesor" in degraded.lower()
    assert "guía autorizada" in disabled.lower()
    assert "asesor" in disabled.lower()

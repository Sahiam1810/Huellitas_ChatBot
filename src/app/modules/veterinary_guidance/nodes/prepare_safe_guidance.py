from app.modules.veterinary_guidance.domain.urgency_signals import UrgencyAssessment
from app.orchestration.rag_contracts import RagStatus
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult

DISCLAIMER = "Esto es orientación general, no un diagnóstico ni una receta."
URGENT_MESSAGE = (
    "Hay señales que requieren atención veterinaria inmediata. "
    "Acude a urgencias o contacta a la clínica ahora."
)
_ASESOR_HINT = (
    "Si no te ayuda o prefieres una persona, escribe la palabra asesor."
)
EMPTY_MESSAGE = (
    "No tengo una guía autorizada para ese caso. "
    "Evita medicar por tu cuenta y consulta a un veterinario. "
    f"{_ASESOR_HINT}"
)
DEGRADED_MESSAGE = (
    "Ahora no puedo consultar la guía. Si hay signos graves, busca atención inmediata; "
    "si no, intenta de nuevo en unos minutos. "
    f"{_ASESOR_HINT}"
)
DISABLED_MESSAGE = (
    "Por ahora no puedo consultar la guía autorizada. "
    "Si hay signos graves, busca atención inmediata; si no, consulta a un veterinario. "
    f"{_ASESOR_HINT}"
)
CLOSING = (
    "Si empeora o dura más de lo esperado, agenda una cita o consulta a un veterinario."
)


def prepare_safe_guidance(
    *,
    urgency: UrgencyAssessment,
    knowledge: GuidanceKnowledgeResult,
) -> str:
    if urgency.is_urgent:
        return URGENT_MESSAGE

    if knowledge.status is RagStatus.USED and knowledge.excerpts:
        numbered = "\n".join(
            f"{index}. {excerpt}" for index, excerpt in enumerate(knowledge.excerpts, start=1)
        )
        return f"{DISCLAIMER}\n\n{numbered}\n\n{CLOSING}"

    if knowledge.status is RagStatus.EMPTY:
        return EMPTY_MESSAGE
    if knowledge.status is RagStatus.DEGRADED:
        return DEGRADED_MESSAGE
    return DISABLED_MESSAGE

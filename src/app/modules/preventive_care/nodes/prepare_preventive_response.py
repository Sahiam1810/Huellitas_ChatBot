from app.orchestration.rag_contracts import RagStatus
from app.ports.preventive_knowledge_gateway import PreventiveKnowledgeResult

DISCLAIMER = "Esto es orientación general preventiva, no un diagnóstico ni una receta."
EMPTY_MESSAGE = (
    "No tengo una guía preventiva autorizada para esa consulta. "
    "Consulta a un veterinario para un plan personalizado."
)
DEGRADED_MESSAGE = (
    "Ahora no puedo consultar la guía preventiva. Intenta de nuevo en unos minutos "
    "o consulta directamente con la clínica."
)
DISABLED_MESSAGE = (
    "Por ahora no puedo consultar la guía preventiva autorizada. "
    "Consulta a un veterinario para orientación personalizada. "
    "Si prefieres hablar con una persona, escribe la palabra asesor."
)
CLOSING = "Para un calendario exacto según el historial clínico, agenda una cita de control."


def prepare_preventive_ask_response(
    *,
    knowledge: PreventiveKnowledgeResult,
    pet_context: str | None = None,
) -> str:
    context_block = f"{pet_context}\n\n" if pet_context else ""
    if knowledge.status is RagStatus.USED and knowledge.excerpts:
        numbered = "\n".join(
            f"{index}. {excerpt}" for index, excerpt in enumerate(knowledge.excerpts, start=1)
        )
        return f"{DISCLAIMER}\n\n{context_block}{numbered}\n\n{CLOSING}"
    if knowledge.status is RagStatus.EMPTY:
        return EMPTY_MESSAGE
    if knowledge.status is RagStatus.DEGRADED:
        return DEGRADED_MESSAGE
    return DISABLED_MESSAGE

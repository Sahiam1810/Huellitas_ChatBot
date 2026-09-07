from app.orchestration.semantic_intent_router import SemanticIntentDefinition

APPOINTMENTS_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "appointments",
        "appointments.list",
        (
            "consultar mis citas veterinarias próximas",
            "ver las reservas que tengo programadas",
        ),
    ),
    SemanticIntentDefinition(
        "appointments",
        "appointments.history",
        (
            "consultar el historial de mis citas anteriores",
            "ver atenciones pasadas o canceladas",
        ),
    ),
    SemanticIntentDefinition(
        "appointments",
        "appointments.view",
        (
            "consultar fecha hora y detalles de una cita específica",
            "ver la información completa de mi reserva veterinaria",
        ),
    ),
    SemanticIntentDefinition(
        "appointments",
        "appointments.book",
        (
            "reservar una nueva cita veterinaria para mi mascota",
            "buscar horario y agendar una atención en la clínica",
            "solicitar una consulta veterinaria para mi mascota",
            "quiero llevar a mi perro a una consulta en la clínica",
            "sacar turno para que atiendan a mi animal",
            "reservar una atención veterinaria para mi perro o gato",
        ),
    ),
    SemanticIntentDefinition(
        "appointments",
        "appointments.cancel",
        (
            "anular una cita veterinaria que tengo reservada",
            "cancelar una atención programada para mi mascota",
        ),
    ),
    SemanticIntentDefinition(
        "appointments",
        "appointments.reschedule",
        (
            "cambiar la fecha o la hora de una cita veterinaria",
            "mover una reserva existente a otro horario disponible",
        ),
    ),
)

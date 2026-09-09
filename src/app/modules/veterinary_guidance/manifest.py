from app.orchestration.module_manifest import ModuleManifest

VETERINARY_GUIDANCE_MANIFEST = ModuleManifest(
    module_id="veterinary_guidance",
    version="1.0.0",
    description="Orientación veterinaria general basada en contenido autorizado",
    intents=("guidance.ask", "guidance.urgent", "guidance.appointment_offer"),
    required_permissions=(),
    allowed_tools=("knowledge.guidance.retrieve",),
    response_types=("retrieved",),
    confirmable_actions=("guidance.offer_appointment",),
    guest_accessible=True,
)

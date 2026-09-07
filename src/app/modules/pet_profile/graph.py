from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.pet_profile.nodes.collect_pet_registration import (
    COLLECTION_ACTION,
    CONFIRMATION_ACTION,
    collect_pet_registration,
    registration_cancelled,
    start_pet_registration,
)
from app.modules.pet_profile.nodes.fetch_pet_profile import fetch_owned_profiles
from app.modules.pet_profile.nodes.identify_pet import identify_pet
from app.modules.pet_profile.nodes.prepare_profile_change import prepare_profile_change
from app.modules.pet_profile.nodes.request_confirmation import request_profile_confirmation
from app.modules.pet_profile.nodes.submit_pet_registration import submit_pet_registration
from app.modules.pet_profile.nodes.submit_profile_change import (
    confirmation_choice,
    confirmation_expired,
    submit_profile_change,
)
from app.modules.pet_profile.services.response_formatter import (
    format_pet_detail,
    format_pet_list,
)
from app.modules.pet_profile.state import PetProfileGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import (
    ModuleHandoff,
    ModuleExecutionRequest,
    ModuleResult,
    PendingConfirmation,
)
from app.ports.pet_profile_gateway import (
    PetProfileAuthenticationError,
    PetProfileForbiddenError,
    PetProfileGateway,
    PetProfileGatewayError,
    PetProfileOwnerProfileNotFoundError,
    PetProfileVersionConflictError,
)
from app.shared.enums import MessageResponseType


class PetProfileModuleExecutor:
    def __init__(self, gateway: PetProfileGateway, *, confirmation_ttl_seconds: int = 600) -> None:
        self._gateway = gateway
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        builder = StateGraph(PetProfileGraphState, context_schema=ExecutionContext)
        builder.add_node("execute_pet_profile", self._execute_node)
        builder.add_edge(START, "execute_pet_profile")
        builder.add_edge("execute_pet_profile", END)
        self._graph = builder.compile()

    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult:
        state = await self._graph.ainvoke({"request": request}, context=context)
        return state["result"]

    async def _execute_node(
        self,
        state: PetProfileGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> PetProfileGraphState:
        request = state["request"]
        context = runtime.context
        if context is None:
            return {"result": self._message("No pude verificar tu identidad.")}
        try:
            result = await self._dispatch(request, context)
        except PetProfileOwnerProfileNotFoundError:
            result = self._message(
                "Tu cuenta de Telegram está vinculada, pero todavía no tienes "
                "un perfil de cliente en Huellitas. Completa tu registro como "
                "cliente para poder consultar y registrar mascotas."
            )
        except (PetProfileAuthenticationError, PetProfileForbiddenError):
            result = self._message(
                "No pude autorizar la consulta de tus mascotas. "
                "Vuelve a iniciar sesión o vincula tu cuenta."
            )
        except PetProfileVersionConflictError:
            result = self._message(
                "El perfil cambió desde que lo consultaste. "
                "Pídeme los datos nuevamente antes de actualizarlo."
            )
        except PetProfileGatewayError:
            result = self._message(
                "No pude consultar el sistema veterinario en este momento. "
                "Inténtalo nuevamente más tarde."
            )
        return {"result": result}

    async def _dispatch(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        if request.intent == "pet_profile.confirmation":
            return await self._continue_confirmation(request, context)
        if request.intent == "pet_profile.registration":
            return await self._continue_registration(request, context)
        if request.intent == "pets.register":
            message, pending = start_pet_registration(
                self._confirmation_ttl_seconds,
                request.continuation,
            )
            return self._message(message, pending=pending)

        profiles = await fetch_owned_profiles(self._gateway, context.bearer_token)
        if request.intent == "pets.list":
            return self._message(format_pet_list(profiles))

        pet = identify_pet(profiles, request.command.message, request.command.pet_id)
        if pet is None:
            if not profiles:
                return self._message(format_pet_list(profiles))
            names = ", ".join(profile.name for profile in profiles)
            return self._message(f"Indícame cuál mascota quieres consultar: {names}.")
        if request.intent == "pets.view":
            return self._message(format_pet_detail(pet))
        if request.intent == "pets.update":
            change = await prepare_profile_change(
                self._gateway, context.bearer_token, request.command.message, pet
            )
            if change is None:
                return self._message(
                    "No identifiqué el dato que quieres cambiar. "
                    "Puedes indicar nombre, edad, género, "
                    "peso, observaciones, especie o raza."
                )
            pending = request_profile_confirmation(pet, change, self._confirmation_ttl_seconds)
            summary = "; ".join(change.descriptions)
            return self._message(
                f"Voy a actualizar a {pet.name}: {summary}. ¿Confirmas? Responde sí o no.",
                pending=pending,
            )
        return self._message("No pude identificar la operación de mascotas solicitada.")

    async def _continue_registration(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        pending = request.pending_confirmation
        if pending is None or pending.action not in {COLLECTION_ACTION, CONFIRMATION_ACTION}:
            return self._message("No hay un registro de mascota pendiente.")
        if confirmation_expired(pending):
            return self._message(
                "El registro venció. Solicita registrar la mascota nuevamente."
            )
        if registration_cancelled(request.command.message):
            return self._message("Cancelé el registro; no se creó ninguna mascota.")
        if pending.action == COLLECTION_ACTION:
            message, next_pending = await collect_pet_registration(
                self._gateway,
                context.bearer_token,
                pending,
                request.command.message,
            )
            return self._message(message, pending=next_pending)

        choice = confirmation_choice(request.command.message)
        if choice is False:
            return self._message("Cancelé el registro; no se creó ninguna mascota.")
        if choice is None:
            return self._message(
                "Necesito una confirmación explícita. Responde sí o no.",
                pending=pending,
            )
        created = await submit_pet_registration(
            self._gateway, context.bearer_token, pending
        )
        return self._message(
            f"{created.name} fue registrada correctamente como tu mascota.",
            handoff=(
                ModuleHandoff(target=pending.continuation)
                if pending.continuation is not None
                else None
            ),
        )

    async def _continue_confirmation(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        pending = request.pending_confirmation
        if pending is None or pending.action != "pets.update":
            return self._message("No hay una actualización de mascota pendiente.")
        if confirmation_expired(pending):
            return self._message(
                "La confirmación venció. Solicita nuevamente el cambio para proteger tus datos."
            )
        choice = confirmation_choice(request.command.message)
        if choice is False:
            return self._message("Cancelé la actualización; no se modificó ningún dato.")
        if choice is None:
            return self._message(
                "Necesito una confirmación explícita. "
                "Responde sí para actualizar o no para cancelar.",
                pending=pending,
            )
        updated = await submit_profile_change(self._gateway, context.bearer_token, pending)
        return self._message(f"El perfil de {updated.name} fue actualizado correctamente.")

    @staticmethod
    def _message(
        message: str,
        *,
        pending: PendingConfirmation | None = None,
        handoff: ModuleHandoff | None = None,
    ) -> ModuleResult:
        return ModuleResult(
            module_id="pet_profile",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            pending_confirmation=pending,
            handoff=handoff,
        )

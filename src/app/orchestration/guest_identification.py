import re
from dataclasses import dataclass

from app.orchestration.module_executor import ModuleResult, PendingConfirmation
from app.ports.guest_identity_gateway import (
    GuestClientMatch,
    GuestIdentityConflictError,
    GuestIdentityGateway,
    GuestIdentityGatewayError,
    GuestIdentityLinkConflictError,
    GuestIdentityUnavailableError,
    GuestOwnerRegistration,
)
from app.shared.enums import MessageResponseType

GUEST_IDENTIFICATION_ACTION = "guest_identification"

IDENTIFICATION_PROMPT = (
    "Para continuar, compárteme estos datos en un solo mensaje, cada uno en una línea:\n"
    "Nombre: tu nombre completo\n"
    "Cédula: tu número de identificación\n"
    "Correo: tu correo electrónico\n"
    "Teléfono: tu número de teléfono"
)

# Único code de conflicto que representa una carrera legítima (dos mensajes casi
# simultáneos registrando la misma cédula): se resuelve con un segundo lookup,
# nunca se muestra al usuario. Confirmados en Application.Security.Errors /
# Application.Clients.Errors del backend (veterinarian-backend).
_IDENTIFICATION_CONFLICT_CODE = "Authentication.IdentificationNumberAlreadyExists"
_EMAIL_CONFLICT_CODE = "Authentication.UserAlreadyExists"
_PHONE_CONFLICT_CODE = "Clients.PhoneAlreadyInUse"

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAME_PATTERN = re.compile(r"nombres?\s*[:\-]?\s*([^\n,;]+)", re.IGNORECASE)
_CEDULA_PATTERN = re.compile(
    r"(?:c[eé]dula|identificaci[oó]n|documento|\bcc\b)"
    r"(?:\s+(?:es|numero|n[uú]mero))?\s*[:\-]?\s*([0-9][0-9.\s]{3,15})",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?:tel[eé]fono|celular|whatsapp|\bcel\b|\btel\b)"
    r"(?:\s+(?:es|numero|n[uú]mero))?\s*[:\-]?\s*([0-9][0-9\s\-]{5,15})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GuestIdentificationInput:
    full_name: str
    identification_number: str
    email: str
    phone_number: str


def parse_guest_identification(message: str) -> GuestIdentificationInput | None:
    email_match = _EMAIL_PATTERN.search(message)
    if email_match is None:
        return None
    email = email_match.group(0).strip().casefold()
    remainder = message[: email_match.start()] + message[email_match.end() :]

    name = _labeled_text(_NAME_PATTERN, remainder)
    cedula = _digits_only(_labeled_text(_CEDULA_PATTERN, remainder))
    phone = _digits_only(_labeled_text(_PHONE_PATTERN, remainder))

    if name is None or cedula is None or phone is None:
        fallback_name, fallback_cedula, fallback_phone = _positional_fallback(remainder)
        name = name or fallback_name
        cedula = cedula or fallback_cedula
        phone = phone or fallback_phone

    if not name or not cedula or not phone or not _valid_name(name):
        return None
    if not (5 <= len(cedula) <= 15) or not (7 <= len(phone) <= 15) or cedula == phone:
        return None
    return GuestIdentificationInput(
        full_name=name.strip()[:150],
        identification_number=cedula,
        email=email,
        phone_number=phone,
    )


def _labeled_text(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match is not None else None


def _digits_only(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def _valid_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü'.\-\s]{2,150}", value.strip()))


def _positional_fallback(remainder: str) -> tuple[str | None, str | None, str | None]:
    segments = [segment.strip() for segment in re.split(r"[,;\n]+", remainder) if segment.strip()]
    if len(segments) < 3:
        return None, None, None
    return segments[0], _digits_only(segments[1]), _digits_only(segments[2])


@dataclass(frozen=True, slots=True)
class _IdentificationOutcome:
    message: str
    pending: PendingConfirmation | None


class GuestIdentificationCoordinator:
    """Shared client-identification step for guest-accessible private modules.

    Collects name/cédula/correo/teléfono in one exchange, then resolves the
    person (lookup, register with 409-race handling) and links the Telegram
    guest to it. Never verifies a code: per business decision, identity data
    is accepted as given. See Tickets 1, 2 and 2.5 (veterinarian-backend).
    """

    def __init__(self, gateway: GuestIdentityGateway, *, ttl_seconds: int = 600) -> None:
        self._gateway = gateway
        self._ttl_seconds = ttl_seconds

    async def handle(
        self,
        *,
        module_id: str,
        intent: str,
        message: str,
        bearer_token: str,
        pending: PendingConfirmation | None,
    ) -> ModuleResult:
        if (
            pending is not None
            and pending.action == GUEST_IDENTIFICATION_ACTION
            and pending.module_id == module_id
        ):
            outcome = (
                self._start(module_id, pending.intent)
                if pending.is_expired()
                else await self._advance(pending, bearer_token, message)
            )
        else:
            outcome = self._start(module_id, intent)
        return ModuleResult(
            module_id=module_id,
            message=outcome.message,
            response_type=MessageResponseType.RETRIEVED,
            pending_confirmation=outcome.pending,
        )

    def _start(self, module_id: str, intent: str) -> _IdentificationOutcome:
        pending = PendingConfirmation.create(
            module_id=module_id,
            action=GUEST_IDENTIFICATION_ACTION,
            payload={},
            ttl_seconds=self._ttl_seconds,
            intent=intent,
        )
        return _IdentificationOutcome(IDENTIFICATION_PROMPT, pending)

    async def _advance(
        self, pending: PendingConfirmation, bearer_token: str, message: str
    ) -> _IdentificationOutcome:
        parsed = parse_guest_identification(message)
        if parsed is None:
            return _IdentificationOutcome(
                "No pude leer esos datos correctamente. " + IDENTIFICATION_PROMPT,
                pending,
            )
        try:
            await self._resolve_and_link(parsed, bearer_token)
        except GuestIdentityConflictError as error:
            return _IdentificationOutcome(_conflict_message(error.code), pending)
        except (GuestIdentityLinkConflictError, GuestIdentityUnavailableError):
            return _IdentificationOutcome(
                "No pude completar tu registro en este momento. "
                "Inténtalo nuevamente en unos minutos.",
                pending,
            )
        except GuestIdentityGatewayError:
            return _IdentificationOutcome(
                "No pude completar tu registro en este momento. "
                "Inténtalo nuevamente en unos minutos.",
                pending,
            )
        first_name = parsed.full_name.split()[0]
        return _IdentificationOutcome(
            f"¡Listo, {first_name}! Ya registré tus datos y vinculé tu Telegram con Huellitas. "
            "Escríbeme de nuevo lo que necesitas (por ejemplo, agendar una cita) para continuar.",
            None,
        )

    async def _resolve_and_link(
        self, parsed: GuestIdentificationInput, bearer_token: str
    ) -> GuestClientMatch:
        match = await self._gateway.lookup_by_identification(
            parsed.identification_number, bearer_token
        )
        if match is None:
            try:
                match = await self._gateway.register(
                    GuestOwnerRegistration(
                        full_name=parsed.full_name,
                        email=parsed.email,
                        identification_number=parsed.identification_number,
                        phone_number=parsed.phone_number,
                    ),
                    bearer_token,
                )
            except GuestIdentityConflictError as error:
                if error.code != _IDENTIFICATION_CONFLICT_CODE:
                    raise
                match = await self._gateway.lookup_by_identification(
                    parsed.identification_number, bearer_token
                )
                if match is None:
                    raise GuestIdentityUnavailableError(
                        "Registration reported a conflict but the client could not be found"
                    ) from error
        await self._gateway.link_telegram_account(match.person_id, bearer_token)
        return match


def _conflict_message(code: str) -> str:
    if code == _EMAIL_CONFLICT_CODE:
        detail = "Ese correo ya está registrado con otra cuenta."
    elif code == _PHONE_CONFLICT_CODE:
        detail = "Ese teléfono ya está registrado con otra cuenta."
    else:
        detail = "Alguno de esos datos ya está registrado con otra cuenta."
    return f"{detail} Verifica la información e inténtalo de nuevo.\n\n{IDENTIFICATION_PROMPT}"

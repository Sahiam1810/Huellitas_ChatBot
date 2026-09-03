from app.ports.pet_profile_gateway import (
    PetProfileAuthenticationError,
    PetProfileForbiddenError,
    PetProfileGatewayError,
    PetProfileOwnerProfileNotFoundError,
    PetProfileUnavailableError,
)
from app.ports.vaccinations_gateway import (
    VaccinationsAuthenticationError,
    VaccinationsForbiddenError,
    VaccinationsGatewayError,
    VaccinationsUnavailableError,
)


def safe_preventive_error(error: Exception) -> str:
    if isinstance(error, PetProfileOwnerProfileNotFoundError):
        return "No encontré un perfil de dueño vinculado. Registra o vincula tu cuenta primero."
    if isinstance(
        error,
        (
            PetProfileAuthenticationError,
            VaccinationsAuthenticationError,
        ),
    ):
        return "No pude validar tu sesión. Vuelve a iniciar sesión o vincula tu cuenta."
    if isinstance(
        error,
        (
            PetProfileForbiddenError,
            VaccinationsForbiddenError,
        ),
    ):
        return "No pude autorizar la consulta preventiva."
    if isinstance(
        error,
        (
            PetProfileUnavailableError,
            VaccinationsUnavailableError,
        ),
    ):
        return "No pude consultar el sistema veterinario en este momento. Inténtalo más tarde."
    if isinstance(error, (PetProfileGatewayError, VaccinationsGatewayError)):
        return "No pude completar la consulta preventiva. Inténtalo más tarde."
    raise error

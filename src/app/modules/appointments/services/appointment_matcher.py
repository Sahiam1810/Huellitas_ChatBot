import unicodedata

from app.modules.appointments.contracts import AppointmentSelection
from app.ports.appointments_gateway import AppointmentItem


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def select_appointments(message: str, items: tuple[AppointmentItem, ...]) -> AppointmentSelection:
    query = normalize(message)
    pet_matches = tuple(item for item in items if normalize(item.pet_name) in query)
    service_matches = tuple(item for item in items if normalize(item.service_name) in query)
    if pet_matches and service_matches:
        service_ids = {item.id for item in service_matches}
        intersection = tuple(item for item in pet_matches if item.id in service_ids)
        return AppointmentSelection(intersection or pet_matches)
    return AppointmentSelection(pet_matches or service_matches)

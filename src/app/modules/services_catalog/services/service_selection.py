from collections.abc import Sequence
import re

from app.modules.services_catalog.services.catalog_matcher import normalize_catalog_text
from app.ports.services_catalog_gateway import ServiceCatalogItem

CATALOG_SELECTION_ACTION = "services.select"
SERVICE_OFFER_ACTION = "services.offer_appointment"
CATALOG_SELECTION_INTENT = "services.selecting"
SERVICE_OFFER_INTENT = "services.appointment_offer"

_SELECTION_HINTS = {
    "uno",
    "dos",
    "tres",
    "primero",
    "segundo",
    "tercero",
    "ese",
    "este",
    "aquel",
}


def choose_catalog_service(
    message: str,
    ordered_ids: Sequence[str],
    catalog: tuple[ServiceCatalogItem, ...],
) -> ServiceCatalogItem | None:
    current_by_id = {str(service.id): service for service in catalog}
    advertised = tuple(
        current_by_id[service_id]
        for service_id in ordered_ids
        if service_id in current_by_id
    )
    normalized = normalize_catalog_text(message)
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(ordered_ids):
            return current_by_id.get(ordered_ids[index])
        return None
    matches = tuple(
        service
        for service in advertised
        if normalize_catalog_text(service.name) in normalized
    )
    return matches[0] if len(matches) == 1 else None


def looks_like_catalog_selection_attempt(
    message: str,
    ordered_ids: Sequence[str],
    catalog: tuple[ServiceCatalogItem, ...],
) -> bool:
    """True when the user still seems to be picking from the numbered list."""
    current_by_id = {str(service.id): service for service in catalog}
    advertised = tuple(
        current_by_id[service_id]
        for service_id in ordered_ids
        if service_id in current_by_id
    )
    normalized = normalize_catalog_text(message)
    if not normalized:
        return False
    if normalized.isdigit() or re.search(r"\b\d+\b", normalized) is not None:
        return True
    tokens = set(normalized.split())
    if len(tokens) <= 3 and tokens & _SELECTION_HINTS:
        return True
    return any(
        name and (name in normalized or normalized in name)
        for name in (normalize_catalog_text(service.name) for service in advertised)
    )


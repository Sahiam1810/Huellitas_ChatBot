import re
import unicodedata

from app.ports.services_catalog_gateway import ServiceCatalogItem


def normalize_catalog_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def match_services(
    services: tuple[ServiceCatalogItem, ...], message: str
) -> tuple[ServiceCatalogItem, ...]:
    normalized_message = normalize_catalog_text(message)
    name_matches = tuple(
        service
        for service in services
        if normalize_catalog_text(service.name) in normalized_message
    )
    if name_matches:
        longest_name = max(len(normalize_catalog_text(item.name)) for item in name_matches)
        return tuple(
            item
            for item in name_matches
            if len(normalize_catalog_text(item.name)) == longest_name
        )

    return tuple(
        service
        for service in services
        if normalize_catalog_text(service.type_service_name) in normalized_message
    )

from app.modules.services_catalog.contracts import ServiceCatalogSelection
from app.modules.services_catalog.services.catalog_matcher import match_services
from app.ports.services_catalog_gateway import ServiceCatalogItem


def understand_service_query(
    message: str, services: tuple[ServiceCatalogItem, ...]
) -> ServiceCatalogSelection:
    return ServiceCatalogSelection(services=match_services(services, message))

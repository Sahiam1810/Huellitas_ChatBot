from dataclasses import dataclass

from app.ports.services_catalog_gateway import ServiceCatalogItem


@dataclass(frozen=True, slots=True)
class ServiceCatalogSelection:
    services: tuple[ServiceCatalogItem, ...]

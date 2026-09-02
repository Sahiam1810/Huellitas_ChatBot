from app.modules.services_catalog.contracts import ServiceCatalogSelection
from app.modules.services_catalog.services.response_formatter import (
    format_service_detail,
    format_service_list,
)
from app.ports.services_catalog_gateway import ServiceCatalogItem


def prepare_service_response(
    *,
    intent: str,
    catalog: tuple[ServiceCatalogItem, ...],
    selection: ServiceCatalogSelection,
) -> str:
    if not catalog:
        return "No hay servicios veterinarios activos disponibles en este momento."
    if intent == "services.list":
        return "Estos son los servicios veterinarios disponibles:\n" + format_service_list(catalog)
    if not selection.services:
        return (
            "No encontré un servicio activo que coincida con tu consulta. "
            "Puedes pedirme la lista de servicios disponibles."
        )
    if len(selection.services) > 1:
        return (
            "Encontré varios servicios. Indícame cuál quieres consultar:\n"
            + format_service_list(selection.services)
        )
    return format_service_detail(selection.services[0])

from app.ports.services_catalog_gateway import ServiceCatalogItem, ServicesCatalogGateway


async def fetch_available_services(
    gateway: ServicesCatalogGateway, bearer_token: str
) -> tuple[ServiceCatalogItem, ...]:
    return await gateway.list_available(bearer_token)

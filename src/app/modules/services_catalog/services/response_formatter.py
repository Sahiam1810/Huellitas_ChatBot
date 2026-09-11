from decimal import Decimal

from app.ports.services_catalog_gateway import ServiceCatalogItem


def format_cop(value: Decimal) -> str:
    integral = f"{int(value):,}".replace(",", ".")
    remainder = value % 1
    if not remainder:
        return f"${integral} COP"
    decimals = f"{remainder:.2f}".split(".", maxsplit=1)[1].rstrip("0")
    return f"${integral},{decimals} COP"


def format_service_detail(service: ServiceCatalogItem) -> str:
    return (
        f"{service.name} — {service.type_service_name} — "
        f"{service.duration_minutes} minutos — {format_cop(service.price)}"
    )


def format_service_list(
    services: tuple[ServiceCatalogItem, ...], *, numbered: bool = False
) -> str:
    if numbered:
        return "\n".join(
            f"{index}. {format_service_detail(service)}"
            for index, service in enumerate(services, start=1)
        )
    return "\n".join(f"• {format_service_detail(service)}" for service in services)

from decimal import Decimal
from uuid import UUID

from app.modules.services_catalog.services.catalog_matcher import match_services
from app.modules.services_catalog.services.response_formatter import (
    format_service_detail,
    format_service_list,
)
from app.ports.services_catalog_gateway import ServiceCatalogItem


def service(
    service_id: str,
    name: str,
    category: str,
    duration: int,
    price: str,
) -> ServiceCatalogItem:
    return ServiceCatalogItem(
        id=UUID(service_id),
        type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        type_service_name=category,
        name=name,
        duration_minutes=duration,
        price=Decimal(price),
    )


CATALOG = (
    service("11111111-1111-1111-1111-111111111111", "Consulta general", "Consulta", 30, "55000"),
    service(
        "22222222-2222-2222-2222-222222222222",
        "Consulta especializada",
        "Consulta",
        45,
        "85000",
    ),
    service("33333333-3333-3333-3333-333333333333", "Vacunación", "Prevención", 20, "45000"),
)


def test_match_services_prefers_the_exact_official_name() -> None:
    result = match_services(CATALOG, "¿Cuánto cuesta la consulta general?")

    assert tuple(item.name for item in result) == ("Consulta general",)


def test_match_services_finds_name_or_category_without_accents() -> None:
    by_name = match_services(CATALOG, "¿Tienen vacunacion?")
    by_category = match_services(CATALOG, "Necesito una consulta")

    assert tuple(item.name for item in by_name) == ("Vacunación",)
    assert tuple(item.name for item in by_category) == (
        "Consulta general",
        "Consulta especializada",
    )


def test_match_services_does_not_guess_an_unknown_service() -> None:
    assert match_services(CATALOG, "¿Tienen radiografía?") == ()


def test_formatters_preserve_official_duration_and_price() -> None:
    detail = format_service_detail(CATALOG[0])
    listing = format_service_list(CATALOG[:1])

    assert "Consulta general" in detail
    assert "Consulta" in detail
    assert "30 minutos" in detail
    assert "$55.000 COP" in detail
    assert listing == "• Consulta general — Consulta — 30 minutos — $55.000 COP"

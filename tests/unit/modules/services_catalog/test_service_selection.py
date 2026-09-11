from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.services_catalog.services.service_selection import choose_catalog_service
from app.ports.services_catalog_gateway import ServiceCatalogItem


def service(service_id: str, name: str) -> ServiceCatalogItem:
    return ServiceCatalogItem(
        id=UUID(service_id),
        type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        type_service_name="Procedimiento",
        name=name,
        duration_minutes=30,
        price=Decimal("45000"),
    )


CATALOG = (
    service("11111111-1111-1111-1111-111111111111", "Consulta general"),
    service("22222222-2222-2222-2222-222222222222", "Medicina interna"),
)
ORDERED_IDS = tuple(str(item.id) for item in CATALOG)


@pytest.mark.parametrize(
    "message",
    ("2", "medicina interna", "quiero medicina interna"),
)
def test_choose_catalog_service_accepts_number_name_or_unambiguous_phrase(
    message: str,
) -> None:
    selected = choose_catalog_service(message, ORDERED_IDS, CATALOG)

    assert selected is not None
    assert selected.name == "Medicina interna"


def test_choose_catalog_service_rejects_an_index_outside_the_advertised_list() -> None:
    assert choose_catalog_service("9", ORDERED_IDS, CATALOG) is None


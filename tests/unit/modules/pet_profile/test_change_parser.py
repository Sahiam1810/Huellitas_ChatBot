from datetime import UTC, datetime
from uuid import uuid4

from app.modules.pet_profile.services.change_parser import parse_profile_change
from app.ports.pet_profile_gateway import CatalogItem, PetProfile


def pet() -> PetProfile:
    return PetProfile(
        id=uuid4(),
        name="Luna",
        age=4,
        gender="F",
        weight=12.5,
        observations="Sana",
        species_id=uuid4(),
        species_name="Canino",
        race_id=uuid4(),
        race_name="Mestizo",
        updated_at=datetime(2026, 9, 2, 15, tzinfo=UTC),
    )


def test_parser_can_explicitly_clear_observations() -> None:
    current = pet()

    change = parse_profile_change(
        "Quita las observaciones de Luna",
        current,
        (CatalogItem(current.species_id, "Canino"),),
        (CatalogItem(current.race_id, "Mestizo"),),
    )

    assert change is not None
    assert change.patch.change_observations is True
    assert change.patch.observations is None

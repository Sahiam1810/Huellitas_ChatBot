from datetime import UTC, datetime
from uuid import UUID

from app.modules.preventive_care.domain.pet_matcher import identify_pet
from app.ports.pet_profile_gateway import PetProfile


def profile(*, name: str = "Luna") -> PetProfile:
    return PetProfile(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        name=name,
        age=3,
        gender="Hembra",
        weight=5.5,
        observations=None,
        species_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        species_name="Perro",
        race_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        race_name="Mestizo",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_identify_pet_matches_name_in_message() -> None:
    assert identify_pet((profile(),), "vacunas de Luna", None) is not None


def test_identify_pet_returns_none_when_multiple_without_name() -> None:
    pets = (profile(name="Luna"), profile(name="Max"))
    assert identify_pet(pets, "historial de vacunas", None) is None

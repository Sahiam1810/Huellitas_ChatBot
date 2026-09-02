from uuid import UUID

import pytest

from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.modules.pet_profile.services.registration_formatter import registration_summary
from app.modules.pet_profile.services.registration_parser import advance_registration
from app.ports.pet_profile_gateway import CatalogItem

SPECIES = (CatalogItem(UUID("22222222-2222-2222-2222-222222222222"), "Canino"),)
RACES = (CatalogItem(UUID("33333333-3333-3333-3333-333333333333"), "Mestizo"),)


@pytest.mark.parametrize(
    ("step", "message", "accepted", "next_step"),
    [
        ("name", " Luna ", True, "species"),
        ("age", "4", True, "gender"),
        ("age", "cuatro", False, "age"),
        ("gender", "hembra", True, "weight"),
        ("gender", "desconocido", False, "gender"),
        ("weight", "12,5 kg", True, "observations"),
        ("weight", "mucho", False, "weight"),
        ("observations", "ninguna", True, "confirmation"),
    ],
)
def test_registration_advances_only_with_valid_step_input(
    step: str, message: str, accepted: bool, next_step: str
) -> None:
    draft = PetRegistrationDraft(step=step)

    result = advance_registration(draft, message, SPECIES, RACES)

    assert result.accepted is accepted
    assert result.draft.step == next_step


def test_catalog_steps_require_exact_normalized_matches() -> None:
    species = advance_registration(
        PetRegistrationDraft(step="species"), "caníno", SPECIES, RACES
    )
    race = advance_registration(species.draft, "mestizo", SPECIES, RACES)

    assert species.accepted
    assert species.draft.species_id == SPECIES[0].id
    assert race.accepted
    assert race.draft.race_id == RACES[0].id
    assert race.draft.step == "age"


def test_complete_draft_formats_confirmation_summary() -> None:
    draft = PetRegistrationDraft(
        step="confirmation",
        name="Luna",
        species_id=SPECIES[0].id,
        species_name="Canino",
        race_id=RACES[0].id,
        race_name="Mestizo",
        age=4,
        gender="F",
        weight=12.5,
        observations=None,
    )

    summary = registration_summary(draft)

    assert "Luna" in summary
    assert "Canino" in summary
    assert "Mestizo" in summary
    assert "12.5 kg" in summary
    assert "sin observaciones" in summary.casefold()

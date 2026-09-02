from dataclasses import dataclass
from uuid import UUID

from app.ports.pet_profile_gateway import PetRegistration


@dataclass(frozen=True, slots=True)
class PetRegistrationDraft:
    step: str = "name"
    name: str | None = None
    species_id: UUID | None = None
    species_name: str | None = None
    race_id: UUID | None = None
    race_name: str | None = None
    age: int | None = None
    gender: str | None = None
    weight: float | None = None
    observations: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"step": self.step}
        for field in (
            "name",
            "species_name",
            "race_name",
            "age",
            "gender",
            "weight",
            "observations",
        ):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        if self.species_id is not None:
            payload["species_id"] = str(self.species_id)
        if self.race_id is not None:
            payload["race_id"] = str(self.race_id)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "PetRegistrationDraft":
        return cls(
            step=str(payload.get("step", "name")),
            name=_optional_text(payload.get("name")),
            species_id=_optional_uuid(payload.get("species_id")),
            species_name=_optional_text(payload.get("species_name")),
            race_id=_optional_uuid(payload.get("race_id")),
            race_name=_optional_text(payload.get("race_name")),
            age=int(payload["age"]) if "age" in payload else None,
            gender=_optional_text(payload.get("gender")),
            weight=float(payload["weight"]) if "weight" in payload else None,
            observations=_optional_text(payload.get("observations")),
        )

    def to_registration(self) -> PetRegistration:
        if (
            self.step != "confirmation"
            or self.name is None
            or self.species_id is None
            or self.race_id is None
            or self.age is None
            or self.gender is None
            or self.weight is None
        ):
            raise ValueError("Pet registration draft is incomplete")
        return PetRegistration(
            name=self.name,
            age=self.age,
            gender=self.gender,
            weight=self.weight,
            observations=self.observations,
            species_id=self.species_id,
            race_id=self.race_id,
        )


def _optional_text(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _optional_uuid(value: object | None) -> UUID | None:
    return UUID(str(value)) if value is not None else None

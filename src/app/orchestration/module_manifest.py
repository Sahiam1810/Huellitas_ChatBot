from collections.abc import Iterable
from dataclasses import dataclass


class InvalidModuleManifestError(ValueError):
    """Raised when a module declares an invalid manifest."""


def normalized_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidModuleManifestError(f"{field} must be non-blank text")
    return value.strip()


def normalized_collection(field: str, values: Iterable[object]) -> tuple[str, ...]:
    normalized = tuple(normalized_text(field, value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise InvalidModuleManifestError(f"{field} cannot contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    module_id: str
    version: str
    description: str
    intents: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    response_types: tuple[str, ...] = ()
    confirmable_actions: tuple[str, ...] = ()
    guest_accessible: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.guest_accessible, bool):
            raise InvalidModuleManifestError("guest_accessible must be a boolean")
        for field in ("module_id", "version", "description"):
            object.__setattr__(self, field, normalized_text(field, getattr(self, field)))
        for field in (
            "intents",
            "required_permissions",
            "allowed_tools",
            "response_types",
            "confirmable_actions",
        ):
            object.__setattr__(
                self,
                field,
                normalized_collection(field, getattr(self, field)),
            )

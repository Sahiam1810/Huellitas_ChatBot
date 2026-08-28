from dataclasses import dataclass

from app.orchestration.module_executor import ModuleExecutor
from app.orchestration.module_manifest import ModuleManifest


class DuplicateModuleIdError(ValueError):
    """Raised when a module identifier is already registered."""


class ConflictingModuleIntentError(ValueError):
    """Raised when an intent already belongs to another module."""


class ModuleNotFoundError(LookupError):
    """Raised when a module or intent is not registered."""


@dataclass(frozen=True, slots=True)
class RegisteredModule:
    manifest: ModuleManifest
    executor: ModuleExecutor | None = None


class ModuleRegistry:
    def __init__(self) -> None:
        self._registrations_by_id: dict[str, RegisteredModule] = {}
        self._registrations_by_intent: dict[str, RegisteredModule] = {}

    def register(
        self,
        manifest: ModuleManifest,
        executor: ModuleExecutor | None = None,
    ) -> None:
        if manifest.module_id in self._registrations_by_id:
            raise DuplicateModuleIdError(f"Module id is already registered: {manifest.module_id}")
        for intent in manifest.intents:
            if intent in self._registrations_by_intent:
                raise ConflictingModuleIntentError(f"Module intent is already registered: {intent}")

        registration = RegisteredModule(manifest=manifest, executor=executor)
        self._registrations_by_id[manifest.module_id] = registration
        for intent in manifest.intents:
            self._registrations_by_intent[intent] = registration

    def get(self, module_id: str) -> ModuleManifest:
        return self.get_registration(module_id).manifest

    def get_registration(self, module_id: str) -> RegisteredModule:
        normalized_id = module_id.strip()
        try:
            return self._registrations_by_id[normalized_id]
        except KeyError:
            raise ModuleNotFoundError(f"Module is not registered: {normalized_id}") from None

    def list_manifests(self) -> tuple[ModuleManifest, ...]:
        return tuple(registration.manifest for registration in self.list_registrations())

    def list_registrations(self) -> tuple[RegisteredModule, ...]:
        return tuple(
            sorted(
                self._registrations_by_id.values(),
                key=lambda registration: registration.manifest.module_id,
            )
        )

    def find_by_intent(self, intent: str) -> ModuleManifest:
        normalized_intent = intent.strip()
        try:
            return self._registrations_by_intent[normalized_intent].manifest
        except KeyError:
            raise ModuleNotFoundError(
                f"Module intent is not registered: {normalized_intent}"
            ) from None

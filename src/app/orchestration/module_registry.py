from app.orchestration.module_manifest import ModuleManifest


class DuplicateModuleIdError(ValueError):
    """Raised when a module identifier is already registered."""


class ConflictingModuleIntentError(ValueError):
    """Raised when an intent already belongs to another module."""


class ModuleNotFoundError(LookupError):
    """Raised when a module or intent is not registered."""


class ModuleRegistry:
    def __init__(self) -> None:
        self._manifests_by_id: dict[str, ModuleManifest] = {}
        self._manifests_by_intent: dict[str, ModuleManifest] = {}

    def register(self, manifest: ModuleManifest) -> None:
        if manifest.module_id in self._manifests_by_id:
            raise DuplicateModuleIdError(f"Module id is already registered: {manifest.module_id}")
        for intent in manifest.intents:
            if intent in self._manifests_by_intent:
                raise ConflictingModuleIntentError(f"Module intent is already registered: {intent}")

        self._manifests_by_id[manifest.module_id] = manifest
        for intent in manifest.intents:
            self._manifests_by_intent[intent] = manifest

    def get(self, module_id: str) -> ModuleManifest:
        normalized_id = module_id.strip()
        try:
            return self._manifests_by_id[normalized_id]
        except KeyError:
            raise ModuleNotFoundError(f"Module is not registered: {normalized_id}") from None

    def list_manifests(self) -> tuple[ModuleManifest, ...]:
        return tuple(
            sorted(self._manifests_by_id.values(), key=lambda manifest: manifest.module_id)
        )

    def find_by_intent(self, intent: str) -> ModuleManifest:
        normalized_intent = intent.strip()
        try:
            return self._manifests_by_intent[normalized_intent]
        except KeyError:
            raise ModuleNotFoundError(
                f"Module intent is not registered: {normalized_intent}"
            ) from None

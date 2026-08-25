from dataclasses import FrozenInstanceError

import pytest

from app.orchestration.module_manifest import (
    InvalidModuleManifestError,
    ModuleManifest,
)


def valid_manifest(**changes: object) -> ModuleManifest:
    values: dict[str, object] = {
        "module_id": "services_catalog",
        "version": "1.0.0",
        "description": "Answers questions about veterinary services.",
        "intents": ("services.lookup", "services.pricing"),
        "required_permissions": ("services.read",),
        "allowed_tools": ("services_catalog.lookup",),
        "response_types": ("text",),
        "confirmable_actions": (),
    }
    values.update(changes)
    return ModuleManifest(**values)  # type: ignore[arg-type]


def test_manifest_is_immutable_and_owns_tuple_collections() -> None:
    source_intents = ["services.lookup"]
    manifest = valid_manifest(intents=source_intents)

    source_intents.append("services.pricing")

    assert manifest.intents == ("services.lookup",)
    with pytest.raises(FrozenInstanceError):
        manifest.module_id = "changed"  # type: ignore[misc]


def test_manifest_strips_outer_whitespace_from_text() -> None:
    manifest = valid_manifest(
        module_id=" services_catalog ",
        version=" 1.0.0 ",
        description=" Service information. ",
        intents=(" services.lookup ",),
    )

    assert manifest.module_id == "services_catalog"
    assert manifest.version == "1.0.0"
    assert manifest.description == "Service information."
    assert manifest.intents == ("services.lookup",)


@pytest.mark.parametrize("field", ["module_id", "version", "description"])
def test_manifest_rejects_blank_identity_fields(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: " "})


@pytest.mark.parametrize(
    "field",
    [
        "intents",
        "required_permissions",
        "allowed_tools",
        "response_types",
        "confirmable_actions",
    ],
)
def test_manifest_rejects_blank_collection_values(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: (" ",)})


@pytest.mark.parametrize(
    "field",
    [
        "intents",
        "required_permissions",
        "allowed_tools",
        "response_types",
        "confirmable_actions",
    ],
)
def test_manifest_rejects_duplicate_normalized_values(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: ("duplicate", " duplicate ")})

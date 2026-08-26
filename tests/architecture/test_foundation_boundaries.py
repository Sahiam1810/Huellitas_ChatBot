import ast
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings

FORBIDDEN_FOUNDATION_IMPORTS = {
    "langgraph",
    "openai",
    "qdrant_client",
    "redis",
}
SDK_IMPORTS = {"google", "openai"}
PROVIDER_ADAPTER_ROOTS = (
    Path("src/app/adapters/models"),
    Path("src/app/adapters/embeddings"),
)
VECTOR_STORE_ADAPTERS_ROOT = Path("src/app/adapters/vector_store")


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.parent.relative_to("src").parts)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package) - (node.level - 1)
                base = package[:keep]
                if node.module:
                    base.extend(node.module.split("."))
                names.add(".".join(base))
            elif node.module:
                names.add(node.module)
    return names


def test_foundation_does_not_import_future_integrations() -> None:
    foundation_files = (
        Path("src/app/main.py"),
        Path("src/app/bootstrap/application.py"),
        Path("src/app/bootstrap/lifecycle.py"),
        Path("src/app/bootstrap/settings.py"),
        Path("src/app/api/routers/health.py"),
    )

    imported = set().union(*(imported_roots(path) for path in foundation_files))

    assert imported.isdisjoint(FORBIDDEN_FOUNDATION_IMPORTS)


def test_api_layer_does_not_read_environment_directly() -> None:
    api_files = Path("src/app/api").rglob("*.py")

    imported = set().union(*(imported_roots(path) for path in api_files))

    assert "os" not in imported


def test_provider_sdks_are_isolated_to_provider_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in Path("src/app").rglob("*.py"):
        sdk_imports = imported_roots(path) & SDK_IMPORTS
        if sdk_imports and not any(path.is_relative_to(root) for root in PROVIDER_ADAPTER_ROOTS):
            violations[str(path)] = sorted(sdk_imports)

    assert violations == {}


def test_qdrant_sdk_is_isolated_to_vector_store_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in Path("src/app").rglob("*.py"):
        sdk_imports = imported_roots(path) & {"qdrant_client"}
        if sdk_imports and not path.is_relative_to(VECTOR_STORE_ADAPTERS_ROOT):
            violations[str(path)] = sorted(sdk_imports)

    assert violations == {}


def test_api_exposes_only_approved_foundation_routes() -> None:
    app = create_application(Settings(environment="test", _env_file=None))

    assert set(app.openapi()["paths"]) == {
        "/health/live",
        "/health/ready",
        "/api/v1/info",
        "/api/v1/messages",
    }


def test_api_layer_does_not_import_concrete_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in Path("src/app/api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        adapter_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                adapter_imports.extend(
                    alias.name for alias in node.names if alias.name.startswith("app.adapters")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.adapters")
            ):
                adapter_imports.append(node.module)
        if adapter_imports:
            violations[str(path)] = sorted(adapter_imports)

    assert violations == {}


def test_orchestration_depends_on_ports_not_provider_or_storage_adapters() -> None:
    forbidden_prefixes = ("app.adapters", "openai", "qdrant_client")
    violations: dict[str, list[str]] = {}
    for path in Path("src/app/orchestration").rglob("*.py"):
        forbidden = sorted(
            name for name in imported_names(path) if name.startswith(forbidden_prefixes)
        )
        if forbidden:
            violations[str(path)] = forbidden

    assert violations == {}


def test_provider_secret_is_absent_from_http_metadata() -> None:
    secret = "must-never-be-exposed"
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            chat_provider="openrouter",
            openrouter_api_key=secret,
            _env_file=None,
        )
    )
    client = TestClient(app)

    info_response = client.get("/api/v1/info")
    openapi_document = json.dumps(app.openapi())

    client.close()
    assert info_response.status_code == 200
    assert secret not in info_response.text
    assert secret not in openapi_document


def test_module_registry_is_independent_from_http_and_adapters() -> None:
    registry_files = (
        Path("src/app/orchestration/module_manifest.py"),
        Path("src/app/orchestration/module_registry.py"),
    )
    forbidden_prefixes = ("fastapi", "app.api", "app.adapters")
    violations = {
        str(path): sorted(
            name for name in imported_names(path) if name.startswith(forbidden_prefixes)
        )
        for path in registry_files
    }

    assert {path: names for path, names in violations.items() if names} == {}


def test_veterinary_modules_respect_isolation_boundaries() -> None:
    modules_root = Path("src/app/modules")
    forbidden_prefixes = ("app.api", "app.adapters", "app.bootstrap")
    violations: dict[str, list[str]] = {}

    for path in modules_root.rglob("*.py"):
        module_name = path.relative_to(modules_root).parts[0]
        own_module = f"app.modules.{module_name}"
        forbidden: list[str] = []
        for name in imported_names(path):
            imports_sibling_module = name.startswith("app.modules.") and not (
                name == own_module or name.startswith(f"{own_module}.")
            )
            if (
                name.startswith(forbidden_prefixes)
                or name == "app.modules"
                or imports_sibling_module
            ):
                forbidden.append(name)
        if forbidden:
            violations[str(path)] = sorted(forbidden)

    assert violations == {}

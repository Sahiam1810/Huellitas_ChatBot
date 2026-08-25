import ast
from pathlib import Path

FORBIDDEN_FOUNDATION_IMPORTS = {
    "langgraph",
    "openai",
    "qdrant_client",
    "redis",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


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

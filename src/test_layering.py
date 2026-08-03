"""Enforces the dependency boundary between document ingestion and retrieval.

Ingestion and retrieval must stay independent so that either can be replaced without
touching the other. Reusing the retrieval side on a different corpus should mean writing
a new ingestion layer and a schema, and nothing else.

Both layers may read the schema. Neither may import the other. Storage may import
neither, because it holds the schema and no knowledge of what fills it or reads it.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).parent
APPS = SOURCE.parent / "apps"

LAYERS = ("config", "observability", "storage", "corpus", "retrieval", "agent", "evaluation")

# What each layer is allowed to import. Anything absent from a layer's set is a violation.
ALLOWED = {
    "config": set(),
    "observability": {"config"},
    "storage": {"config", "observability"},
    # Ingestion writes the schema and knows nothing about how anything is searched.
    "corpus": {"config", "observability", "storage"},
    # Retrieval reads the schema and knows nothing about where documents came from.
    "retrieval": {"config", "observability", "storage"},
    # Tools sit on retrieval's contract, never on a source.
    "agent": {"config", "observability", "storage", "retrieval"},
    # Packaging reads the contract files on disk and imports no layer, so it stays
    # measurable against a system it does not depend on.
    "evaluation": set(),
}


def imports_of(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
    return found & set(LAYERS)


def modules() -> list[tuple[str, Path]]:
    """Every non-test module, paired with the layer it belongs to."""
    pairs = []
    for path in SOURCE.rglob("*.py"):
        if path.name.startswith("test_") or "migrations" in path.parts:
            continue
        layer = path.relative_to(SOURCE).parts[0].removesuffix(".py")
        if layer in LAYERS:
            pairs.append((layer, path))
    return pairs


def test_no_layer_imports_something_it_should_not() -> None:
    violations = []
    for layer, path in modules():
        for imported in imports_of(path) - {layer}:
            if imported not in ALLOWED[layer]:
                violations.append(f"{path.relative_to(SOURCE.parent)} imports {imported}")
    assert not violations, "layer boundary broken:\n  " + "\n  ".join(violations)


def test_ingestion_and_retrieval_never_import_each_other() -> None:
    """The boundary that makes the retrieval side reusable on a different corpus."""
    for layer, path in modules():
        if layer == "corpus":
            assert "retrieval" not in imports_of(path), (
                f"{path.name} couples ingestion to retrieval"
            )
        if layer == "retrieval":
            assert "corpus" not in imports_of(path), f"{path.name} couples retrieval to ingestion"


def test_storage_holds_the_schema_and_nothing_above_it() -> None:
    for layer, path in modules():
        if layer == "storage":
            reaching_up = imports_of(path) & {"corpus", "retrieval", "agent"}
            assert not reaching_up, f"{path.name} reaches up into {reaching_up}"


def test_entry_points_are_where_the_layers_meet() -> None:
    """Apps compose the layers, which is why they alone may import across the boundary."""
    composing = [
        path
        for path in APPS.rglob("*.py")
        if not path.name.startswith("test_") and {"corpus", "retrieval"} <= imports_of(path)
    ]
    assert composing, "no entry point joins ingestion to retrieval"

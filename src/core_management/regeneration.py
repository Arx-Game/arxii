"""Django-dependent helpers for ``arx manage squashmigrations arxii`` (ADR-0272).

The Django-free half of the regeneration (topological inlining, constraint
folding, tail templates) lives under ``tools/`` so it stays importable without a
settings module; this module is the bridge that needs the app registry, the
migration writer or a database connection.
"""

from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType

from django.apps import apps
from django.db import migrations
from django.db.migrations.writer import OperationWriter

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
MIGRATIONS_DIR = REPO_ROOT / "src" / "world" / "migrations"


def tools_module(name: str) -> ModuleType:
    """Import a ``tools/`` module by name (``tools/`` is not a package)."""
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    return __import__(name)


def post_partition_addfield_sources() -> tuple[list[str], set[str]]:
    """``AddField`` sources for every column the frozen partition SQL omits.

    Rendered from the live ``Interaction`` model through Django's own writer, so
    the field definition is the model's and never a hand copy (#2982 is what a
    hand copy costs). Returns the operation sources and the imports they need.
    """
    drift = tools_module("check_partition_sql_drift")
    model = apps.get_model("arxii", "Interaction")
    sources: list[str] = []
    imports: set[str] = set()
    for column in sorted(drift.POST_PARTITION_COLUMNS):
        # _meta is Django's public-by-convention model API (same suppression as elsewhere).
        field = model._meta.get_field(column.removesuffix("_id"))  # noqa: SLF001
        operation = migrations.AddField(
            model_name="interaction", name=field.name, field=field.clone()
        )
        text, op_imports = OperationWriter(operation, indentation=0).serialize()
        sources.append(text.strip().rstrip(","))
        imports.update(op_imports)
    return sources, imports

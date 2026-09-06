"""Render the infrastructure tail migrations a regenerated chain needs (ADR-0276).

``makemigrations`` only ever emits ``CreateModel``; the range partition on
``arxii_interaction``, its composite FKs and the five materialized views are raw
SQL that lives in ``.sql`` files shared with ``tools/build_schema.py``. This module
renders three migrations from ``build_schema.SQL_FILES`` so the two schema paths
cannot diverge (#2982 is what divergence costs), in ``build_schema``'s order:
partition rewrite, then the database-only re-add of the columns the frozen
partition SQL omits, then the materialized views.

Template rules (do not "tidy"): each tail inlines its own ``_read_sql`` (migrations
run from ``src/``, where ``tools/`` is not importable), and every ``RunSQL`` keeps a
literal ``_read_sql("<subpackage>", "<file>.sql")`` call inside ``operations``,
because ``tools/check_standalone_sql_wiring.py`` only counts ``.sql`` constants
inside that subtree. Django-free: the one Django-dependent input (the serialized
``AddField`` sources for the partition-columns tail) is rendered by
``core_management.regeneration`` and passed in as strings.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re

APP_LABEL = "arxii"
_MATVIEW_RE = re.compile(
    r"CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)", re.IGNORECASE
)

_BASE_IMPORTS = "from django.db import migrations, models"
_PREAMBLE = f"""from pathlib import Path

from django.conf import settings
{_BASE_IMPORTS}

from world.migrations._generations import replaced_slice

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()

"""
# Imports the preamble already provides; the writer reports them per operation.
_COVERED_IMPORTS = {
    "from django.conf import settings",
    "from django.db import migrations",
    "from django.db import models",
    _BASE_IMPORTS,
}


def read_sql_files(build_schema_path: Path) -> list[str]:
    """``build_schema.SQL_FILES``, parsed without importing (importing pulls in Django)."""
    tree = ast.parse(build_schema_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SQL_FILES" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    message = f"SQL_FILES not found in {build_schema_path}"
    raise ValueError(message)


def matview_name(sql_text: str) -> str:
    match = _MATVIEW_RE.search(sql_text)
    if match is None:
        message = "no CREATE MATERIALIZED VIEW statement found"
        raise ValueError(message)
    return match.group(1)


def tail_names(generation: int, first_number: int) -> tuple[str, str, str]:
    """``(partition_sql, partition_columns, matviews)`` names, numbered from the last chunk."""
    return (
        f"{first_number:04d}_g{generation}_partition_sql",
        f"{first_number + 1:04d}_g{generation}_partition_columns",
        f"{first_number + 2:04d}_g{generation}_matviews",
    )


@dataclass(frozen=True)
class _Header:
    """What every tail shares: predecessor, ``replaced_slice`` position, extra imports."""

    depends_on: str
    replaces: tuple[int, int]  # (index, total) for replaced_slice, see _generations.py
    swappable: bool = False
    extra_imports: frozenset[str] = field(default_factory=frozenset)


def _module(docstring: str, header: _Header, operations: str) -> str:
    deps = f'("{APP_LABEL}", "{header.depends_on}")'
    if header.swappable:
        deps += ", migrations.swappable_dependency(settings.AUTH_USER_MODEL)"
    extra = "".join(
        f"{line}\n" for line in sorted(header.extra_imports) if line not in _COVERED_IMPORTS
    )
    index, total = header.replaces
    return (
        f'"""{docstring}"""\n\n'
        f"{extra}{_PREAMBLE}\n"
        "class Migration(migrations.Migration):\n"
        f"    replaces = replaced_slice({index}, {total})\n"
        f"    dependencies = [{deps}]\n\n"
        f"    operations = [\n{operations}    ]\n"
    )


def render_matviews_tail(
    name: str, depends_on: str, entries: list[tuple[str, str, str]], replaces: tuple[int, int]
) -> str:
    """One ``RunSQL`` per ``(subpackage, filename, view_name)``."""
    ops = "".join(
        "        migrations.RunSQL(\n"
        f'            sql=_read_sql("{sub}", "{fname}"),\n'
        f'            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS {view};",\n'
        "        ),\n"
        for sub, fname, view in entries
    )
    doc = (
        f"{name}: the managed=False materialized views (ADR-0276 tail, rendered from\n"
        "tools/build_schema.py's SQL_FILES by arx manage squashmigrations; do not edit)."
    )
    return _module(doc, _Header(depends_on, replaces), ops)


def render_partition_sql_tail(
    name: str, depends_on: str, entries: list[tuple[str, str]], replaces: tuple[int, int]
) -> str:
    """One ``RunSQL`` per ``(subpackage, forward_filename)``, reverse paired by name."""
    ops = "".join(
        "        migrations.RunSQL(\n"
        f'            sql=_read_sql("{sub}", "{fwd}"),\n'
        f'            reverse_sql=_read_sql("{sub}", "{fwd.replace("_forward", "_reverse")}"),\n'
        "        ),\n"
        for sub, fwd in entries
    )
    doc = (
        f"{name}: the arxii_interaction range partition and composite FKs (ADR-0276 tail,\n"
        "rendered from tools/build_schema.py's SQL_FILES by arx manage squashmigrations;\n"
        "SQL-only so the DDL/DML lint needs no grandfather entry; do not edit)."
    )
    return _module(doc, _Header(depends_on, replaces), ops)


def render_partition_columns_tail(
    name: str,
    depends_on: str,
    addfield_sources: list[str],
    imports: set[str],
    replaces: tuple[int, int],
) -> str:
    """A database-only ``AddField`` per column the frozen partition SQL omits."""
    inner = "".join(f"                {src},\n" for src in addfield_sources)
    ops = (
        "        migrations.SeparateDatabaseAndState(\n"
        "            database_operations=[\n"
        f"{inner}"
        "            ],\n"
        "            state_operations=[],\n"
        "        ),\n"
    )
    doc = (
        f"{name}: database-only re-add of the columns the frozen partition SQL omits\n"
        "(POST_PARTITION_COLUMNS in tools/check_partition_sql_drift.py). Migration state\n"
        "already carries them from CreateModel; the partition rewrite rebuilt the table\n"
        "without them. Rendered from the live Interaction model by arx manage\n"
        "squashmigrations (ADR-0276 tail); do not edit."
    )
    header = _Header(depends_on, replaces, swappable=True, extra_imports=frozenset(imports))
    return _module(doc, header, ops)

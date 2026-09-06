"""Reject Django migrations that mix schema operations with data operations.

PostgreSQL queues a deferred FK trigger event for every row a transaction
writes, and refuses ``ALTER TABLE`` on any table that still has events queued.
Django runs one migration in one transaction, so a ``RunPython`` that touches
rows followed by *any* schema operation on those tables aborts with::

    cannot ALTER TABLE "..." because it has pending trigger events

This is data-dependent: it passes every test and CI run, because a freshly
migrated database has no rows for the data operation to touch, and then fails
on the production converge. Migration 0220_upbringings broke a deploy this way
on 2026-09-04.

The rule is therefore structural, not conditional: a migration is schema-only
or data-only, never both. Where data genuinely has to move, use the
expand/migrate/contract sequence - add the new columns in one migration, copy
in the next, drop in a third - so every ALTER TABLE gets a transaction with an
empty trigger queue. Reverse migrations replay the operations backwards, so a
schema-then-data migration is just as broken running down as data-then-schema
is running up; both are rejected.

See ADR-0237.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# Operations that write rows. RunSQL is counted as data because the linter
# cannot tell DDL from DML inside a SQL string; a RunSQL that really is schema
# work belongs in the allowlist below with that stated.
DATA_OPERATIONS = frozenset({"RunPython", "RunSQL"})

# Migrations that predate this rule AND are already applied in production, so
# they can no longer be restructured - splitting an applied migration would
# re-run its operations against a database that already has them. Nothing may
# be added here: a new migration that needs an entry is a new migration that
# needs splitting instead.
GRANDFATHERED: frozenset[str] = frozenset(
    {
        # Every entry below is already applied to production, so it can no
        # longer be restructured - splitting an applied migration would re-run
        # its operations against a database that already has them. Each one
        # survived for the same reason: the rows its data operation touched were
        # empty or few enough that PostgreSQL's trigger queue happened to be
        # empty at the ALTER TABLE. That is luck, not design, which is why the
        # rule below is structural. NOTHING MAY BE ADDED HERE - a new migration
        # that would need an entry is a new migration that needs splitting.
        "world/migrations/0113_partition_interaction.py",
        "world/migrations/0186_gmlevelcap_max_story_npcs.py",
        "world/migrations/0199_roomprofile_published_at.py",
        "world/migrations/0203_persona_title.py",
        "world/migrations/0207_alter_beat_outcome_alter_beatcompletion_outcome_and_more.py",
        "world/migrations/0208_battle_story_beat_and_more.py",
        "world/migrations/0211_retire_stake_outcome_gm_pick.py",
        "world/migrations/0219_familykind_family_kind_influence.py",
    }
)


def operation_names(tree: ast.Module) -> list[str]:
    """Return the operation call names in a migration's ``operations`` list."""
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "operations" for t in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        names.extend(
            element.func.attr
            for element in node.value.elts
            if isinstance(element, ast.Call) and isinstance(element.func, ast.Attribute)
        )
    return names


def classify_source(source: str) -> tuple[list[str], list[str]]:
    """Split a migration's operations into (data operations, schema operations)."""
    names = operation_names(ast.parse(source))
    data = sorted({name for name in names if name in DATA_OPERATIONS})
    schema = sorted({name for name in names if name not in DATA_OPERATIONS})
    return data, schema


def check_migration(path: Path) -> str | None:
    """Return a failure message when *path* mixes schema and data operations."""
    try:
        data, schema = classify_source(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - a broken migration fails elsewhere
        return f"{path}: could not parse ({exc})"

    if not (data and schema):
        return None

    # Paths outside src/ (a caller passing an absolute path, or a test fixture)
    # are reported as given; only src-relative paths can match the allowlist.
    relative = (
        path.relative_to(SRC_DIR).as_posix() if path.is_relative_to(SRC_DIR) else path.as_posix()
    )
    if relative in GRANDFATHERED:
        return None
    return (
        f"{relative}: mixes data operations ({', '.join(data)}) with schema operations "
        f"({', '.join(schema)}) in one migration, so they share one transaction. "
        "Split them: schema in one migration, data in the next (expand/migrate/contract). "
        "See ADR-0237 and tools/lint_migration_ddl_dml.py."
    )


def main(argv: list[str]) -> int:
    """Check the given migration files, or every migration when none are given."""
    if argv:
        paths = [Path(arg).resolve() for arg in argv]
    else:
        paths = sorted(SRC_DIR.glob("**/migrations/*.py"))

    failures = [
        message
        for path in paths
        if path.name != "__init__.py" and "migrations" in path.parts
        for message in [check_migration(path)]
        if message
    ]
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

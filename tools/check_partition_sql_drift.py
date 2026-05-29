"""Detect drift between the Interaction model and the partition SQL.

`src/world/scenes/sql/partition_interaction_forward.sql` (and its reverse
counterpart) hand-rolls a `CREATE TABLE scenes_interaction (...)` because
PostgreSQL range partitioning isn't expressible through Django's
makemigrations. That SQL is a frozen snapshot — if a developer adds a column
to `Interaction` and doesn't update the SQL, the column gets created by
0001_initial then silently dropped by the partition migration. The break
is invisible until someone collapses the migration chain or otherwise builds
a fresh DB through the new chain.

This hook compares the columns the SQL declares against the columns
`world.scenes.models.Interaction` actually has (plus the FK column names
Django would generate). It fails if any model column is missing from the SQL
or vice versa. Run it via the pre-commit hook of the same name.

It does NOT enforce type or default equivalence — that's a deeper check
that requires resolving Django field types to Postgres column types. The
column-name check catches 95% of the drift incidents in practice
(field-add-without-SQL-update is the dominant failure mode).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

import django
from django.db.models.fields.related import ForeignObjectRel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# Files this hook governs.
FORWARD_SQL = SRC_DIR / "world/scenes/sql/partition_interaction_forward.sql"
REVERSE_SQL = SRC_DIR / "world/scenes/sql/partition_interaction_reverse.sql"


def _setup_django() -> None:
    """Configure Django so we can import models — mirrors check_migrations.py."""
    os.chdir(SRC_DIR)
    sys.path.insert(0, str(SRC_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")
    os.environ.setdefault("SECRET_KEY", "arxii-placeholder-secret-key")
    django.setup()


def _interaction_columns_from_model() -> set[str]:
    """Introspect Interaction and return the set of DB column names."""
    # Deferred import: world.scenes.models requires django.setup() to have run.
    from world.scenes.models import Interaction  # noqa: PLC0415

    columns: set[str] = set()
    # _meta is Django's documented introspection entry point despite the
    # underscore — see https://docs.djangoproject.com/en/5.1/ref/models/meta/.
    for field in Interaction._meta.get_fields():  # noqa: SLF001
        # Skip reverse relations and M2M-from-other-side (no column on this table).
        if isinstance(field, ForeignObjectRel):
            continue
        if field.many_to_many:
            continue
        # field.column is the actual DB column name (handles FK _id suffixing).
        columns.add(field.column)
    return columns


_COLUMN_LINE_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*|\"[a-z_]+\")\s+\S")


def _columns_from_create_table(sql_text: str) -> set[str]:
    """Parse the CREATE TABLE scenes_interaction (...) column names out of SQL."""
    # Find the CREATE TABLE scenes_interaction block.
    match = re.search(
        r"CREATE TABLE scenes_interaction\s*\(([^;]+?)\)(\s+PARTITION BY[^;]*)?;",
        sql_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return set()
    body = match.group(1)
    columns: set[str] = set()
    for raw_line in body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        # Skip table-level constraints (PRIMARY KEY, FOREIGN KEY, CHECK, UNIQUE).
        upper = line.upper()
        if upper.startswith(("PRIMARY KEY", "FOREIGN KEY", "CHECK", "UNIQUE", "CONSTRAINT")):
            continue
        match = _COLUMN_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1).strip('"')
        columns.add(name)
    return columns


def _columns_from_insert(sql_text: str) -> set[str]:
    """Parse the explicit column list from `INSERT INTO scenes_interaction (...)`."""
    match = re.search(
        r"INSERT INTO scenes_interaction\s*\(([^)]+)\)",
        sql_text,
        re.IGNORECASE,
    )
    if not match:
        return set()
    raw = match.group(1)
    return {col.strip().strip('"') for col in raw.split(",") if col.strip()}


def main() -> int:
    _setup_django()
    model_columns = _interaction_columns_from_model()

    issues: list[str] = []

    for sql_path, label in [(FORWARD_SQL, "forward"), (REVERSE_SQL, "reverse")]:
        if not sql_path.exists():
            issues.append(f"{label} SQL missing: {sql_path}")
            continue
        sql_text = sql_path.read_text()
        create_columns = _columns_from_create_table(sql_text)
        insert_columns = _columns_from_insert(sql_text)

        missing_in_create = model_columns - create_columns
        extra_in_create = create_columns - model_columns
        if missing_in_create:
            issues.append(
                f"{label} CREATE TABLE is missing model column(s): {sorted(missing_in_create)}"
            )
        if extra_in_create:
            issues.append(
                f"{label} CREATE TABLE has column(s) that aren't on Interaction: "
                f"{sorted(extra_in_create)}"
            )

        # INSERT column list should match CREATE TABLE exactly (forward SQL only
        # makes sense to check if both are present; reverse has the same shape).
        if insert_columns and insert_columns != create_columns:
            create_only = create_columns - insert_columns
            insert_only = insert_columns - create_columns
            issues.append(
                f"{label} INSERT column list drifted from CREATE TABLE — "
                f"only-in-CREATE: {sorted(create_only)} "
                f"only-in-INSERT: {sorted(insert_only)}"
            )

    if issues:
        sys.stderr.write("Partition SQL has drifted from world.scenes.models.Interaction:\n")
        for issue in issues:
            sys.stderr.write(f"  - {issue}\n")
        sys.stderr.write(
            "\nFix: edit src/world/scenes/sql/partition_interaction_*.sql so the "
            "CREATE TABLE and INSERT INTO column lists match the current model. "
            "Adding a model field to Interaction also requires adding the column "
            "(and any db_index=True index) to both SQL files.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

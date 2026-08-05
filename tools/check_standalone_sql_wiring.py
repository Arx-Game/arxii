"""Enforce that every standalone SQL artifact is wired into BOTH schema paths.

Arx II builds its schema two ways (ADR-0083):

* ``arx manage migrate`` replays the migration chain. This is production's path.
* ``tools/build_schema.py`` builds from model state and applies the raw SQL
  listed in its ``SQL_FILES`` constant. This is CI's, the parity tier's and the
  devcontainer's path.

Raw SQL that Django cannot express - a range partition, a composite FK onto a
partitioned table, a materialized view - has to be wired into BOTH. Wiring it
into only one makes two supported commands produce two different databases, and
the failure is silent: no error, just an object that is simply absent from
whichever path was missed.

``docs/evennia-quirks.md`` has documented the migration -> SQL_FILES direction
for a while. #2906's squash broke the OTHER one: it regenerated the chain with a
plain ``makemigrations``, which only emits ``CreateModel``, and the ``RunSQL``
that partitioned ``arxii_interaction`` was dropped while the SQL file stayed in
``SQL_FILES``. Nobody noticed for two months (#2982). This hook enforces both
directions so neither half can rot again.

``*_reverse.sql`` files are exempt from the SQL_FILES direction: ``build_schema``
is forward-only by construction, so a reverse file legitimately appears in a
migration and nowhere else.

Run via the pre-commit hook of the same name. Deliberately parses
``tools/build_schema.py`` with ``ast`` rather than importing it - importing pulls
in Django and this check must stay fast and database-free.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCHEMA = PROJECT_ROOT / "tools" / "build_schema.py"
MIGRATIONS_DIR = PROJECT_ROOT / "src" / "world" / "migrations"

# Any string literal ending in .sql, anywhere in a migration module's source.
_SQL_LITERAL_RE = re.compile(r"""["']([A-Za-z0-9_./-]+\.sql)["']""")


def sql_files_from_build_schema(source: str) -> list[str]:
    """Return build_schema.py's SQL_FILES list, parsed without importing it."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "SQL_FILES":
                return list(ast.literal_eval(node.value))
    msg = f"could not find a SQL_FILES assignment in {BUILD_SCHEMA}"
    raise SystemExit(msg)


def sql_names_referenced_by_migrations(sources: dict[str, str]) -> dict[str, set[str]]:
    """Map each .sql basename a migration mentions to the modules mentioning it."""
    referenced: dict[str, set[str]] = {}
    for module_name, source in sources.items():
        for match in _SQL_LITERAL_RE.finditer(source):
            name = Path(match.group(1)).name
            referenced.setdefault(name, set()).add(module_name)
    return referenced


def check(build_schema_source: str, migration_sources: dict[str, str]) -> list[str]:
    """Return a list of wiring problems. Empty means both directions hold."""
    sql_files = sql_files_from_build_schema(build_schema_source)
    declared = {Path(rel).name: rel for rel in sql_files}
    referenced = sql_names_referenced_by_migrations(migration_sources)

    problems: list[str] = []

    for name, rel_path in sorted(declared.items()):
        if name not in referenced:
            problems.append(
                f"{rel_path} is in build_schema.SQL_FILES but no migration applies it. "
                f"A schema-from-models database will have this object and a migrated "
                f"database will not. Add a migrations.RunSQL step that reads it."
            )

    for name, modules in sorted(referenced.items()):
        if name.endswith("_reverse.sql"):
            continue
        if name not in declared:
            where = ", ".join(sorted(modules))
            problems.append(
                f"{name} is applied by {where} but is missing from "
                f"build_schema.SQL_FILES. A migrated database will have this object "
                f"and every schema-from-models database (CI, the parity tier, the "
                f"devcontainer) will not. Add it to SQL_FILES."
            )

    return problems


def main() -> int:
    migration_sources = {
        path.name: path.read_text()
        for path in sorted(MIGRATIONS_DIR.glob("*.py"))
        if path.name != "__init__.py"
    }
    problems = check(BUILD_SCHEMA.read_text(), migration_sources)
    if problems:
        sys.stderr.write("Standalone SQL is wired into only one schema path:\n")
        for problem in problems:
            sys.stderr.write(f"  - {problem}\n")
        sys.stderr.write(
            "\nSee 'A new standalone-SQL migration must be mirrored into "
            "tools/build_schema.py' in docs/evennia-quirks.md.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

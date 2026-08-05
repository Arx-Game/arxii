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
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCHEMA = PROJECT_ROOT / "tools" / "build_schema.py"
MIGRATIONS_DIR = PROJECT_ROOT / "src" / "world" / "migrations"


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


def _operations_node(source: str) -> ast.AST | None:
    """Return the AST subtree assigned to Migration.operations, or None.

    Parses with ast rather than scanning raw text so that comments (not part of
    the AST at all) and module-level constants outside the operations list (not
    part of this subtree) cannot masquerade as a wired reference. A module with
    no ``class Migration`` or no ``operations`` assignment yields None rather
    than raising - malformed or unusual modules should contribute no references,
    not crash the check.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    migration_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Migration":
            migration_class = node
            break
    if migration_class is None:
        return None

    for node in ast.walk(migration_class):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == "operations":
                    return node.value
    return None


def sql_names_referenced_by_migrations(sources: dict[str, str]) -> dict[str, set[str]]:
    """Map each .sql basename a migration mentions to the modules mentioning it.

    Only string constants reachable from within ``Migration.operations`` count -
    see ``_operations_node`` for why.
    """
    referenced: dict[str, set[str]] = {}
    for module_name, source in sources.items():
        operations = _operations_node(source)
        if operations is None:
            continue
        for node in ast.walk(operations):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if not node.value.endswith(".sql"):
                continue
            name = Path(node.value).name
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

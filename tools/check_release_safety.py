"""Guard pending migrations against incompatible code still running in production.

Unsafe operations require a reviewed declaration. Contract declarations name the
commit that stopped using the old schema; it must already be in the running
server's recorded revision, not merely in the release being deployed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import re
import subprocess
import sys

import django
from django.db import connection
from django.db.migrations import operations
from django.db.migrations.executor import MigrationExecutor
from django.db.models import NOT_PROVIDED

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = re.compile(r"^# release-safety: (expand|contract) ([0-9a-f]{40})$", re.MULTILINE)

# These operations cannot make an existing query or write incompatible.
SAFE = (
    operations.CreateModel,
    operations.AddIndex,
    operations.RemoveIndex,
    operations.AlterModelOptions,
    operations.AlterModelManagers,
)


def unsafe_operations(migration):
    """Describe operations needing an explicit release compatibility review."""
    return _unsafe_database_operations(migration.operations)


def _unsafe_database_operations(items):
    result = []
    for op in items:
        if type(op) is operations.AddField:
            if op.field.null or op.field.db_default is not NOT_PROVIDED:
                continue
        elif type(op) in SAFE:
            continue
        elif type(op) is operations.SeparateDatabaseAndState:
            result.extend(_unsafe_database_operations(op.database_operations))
            continue
        result.append(type(op).__name__)
    return result


def check_migration(migration, source, running_revision, is_ancestor):
    """Return an explanation when a pending migration is unsafe to apply."""
    unsafe = unsafe_operations(migration)
    if not unsafe:
        return None
    match = DECLARATION.search(source)
    if not match:
        return f"{migration.app_label}.{migration.name}: review required for {', '.join(unsafe)}"
    phase, commit = match.groups()
    if phase == "expand" and any(
        name in {"RemoveField", "DeleteModel", "RenameField", "RenameModel"} for name in unsafe
    ):
        return f"{migration.app_label}.{migration.name}: destructive operations cannot be expand"
    if not is_ancestor(commit, running_revision):
        return (
            f"{migration.app_label}.{migration.name}: reviewed compatibility commit "
            f"{commit} is not in the running server revision"
        )
    return None


def main():
    """Check the actual pending migration plan against the running revision."""
    args = sys.argv[1:]
    if len(args) != 1 or not re.fullmatch(r"[0-9a-f]{40}", args[0]):
        print("Expected the 40-character running server revision.", file=sys.stderr)
        return 1

    django.setup()
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())

    def is_ancestor(commit, revision):
        result = subprocess.run(  # noqa: S603
            ["git", "merge-base", "--is-ancestor", commit, revision],  # noqa: S607
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        return result.returncode == 0

    failures = []
    for migration, backwards in plan:
        if backwards:
            failures.append(f"{migration.app_label}.{migration.name}: reverse migration refused")
            continue
        module = importlib.import_module(migration.__module__)
        try:
            source = Path(module.__file__).read_text(encoding="utf-8")
        except (OSError, TypeError):
            failures.append(f"{migration.app_label}.{migration.name}: cannot read source")
            continue
        problem = check_migration(migration, source, sys.argv[1], is_ancestor)
        if problem:
            failures.append(problem)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print("Migration blocked: review compatibility with the running server.", file=sys.stderr)
        return 1
    print("Pending migrations have passed the running-server compatibility gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

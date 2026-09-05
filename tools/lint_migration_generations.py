"""No migration may reuse a name from, or depend on a name in, an earlier generation.

Why (ADR-0272): production records every applied migration name forever. A new
file whose name is already recorded is silently treated as applied and skipped; a
file that depends on a replaced name is remapped by Django's loader onto whichever
replacing file it meets first and passes every other check. Both surface only
after production has recorded the older row, so they are caught at commit instead.

Run via the pre-commit hook of the same name. ``ast``-level: no Django, no database.
There is no ``# noqa`` for this check; a collision has no legitimate form.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
MIGRATIONS_DIR = SRC_DIR / "world" / "migrations"
APP_LABEL = "arxii"
_MIGRATION_FILE = re.compile(r"^\d{4}_.+\.py$")
_MODULE_REF = re.compile(r"world\.migrations\.(\d{4}_[A-Za-z0-9_]+)")


def _generations(migrations_dir: Path) -> dict[int, list[str]]:
    """``GENERATIONS`` from ``_generations.py``, or empty when there is no such module."""
    path = migrations_dir / "_generations.py"
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "GENERATIONS" and value is not None:
            return {int(k): list(v) for k, v in ast.literal_eval(value).items()}
    return {}


def _arxii_dependencies(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "dependencies" for t in node.targets):
            continue
        elts = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else []
        for elt in elts:
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 2):  # noqa: PLR2004 - (app, name)
                continue
            app, name = elt.elts
            if (
                isinstance(app, ast.Constant)
                and app.value == APP_LABEL
                and isinstance(name, ast.Constant)
            ):
                names.append(str(name.value))
    return names


def check_module_references(src_dir: Path, owner: dict[str, int]) -> list[str]:
    """Code outside the migrations package that names a replaced migration module.

    A test that imports ``world.migrations.0207_...`` to exercise its RunPython
    has no subject once a regeneration drops that file; it fails at import and
    takes its whole test module with it (shard-6 on PR #3662).
    """
    failures: list[str] = []
    for path in sorted(src_dir.rglob("*.py")):
        if MIGRATIONS_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        stale = [n for n in sorted(set(_MODULE_REF.findall(text))) if n in owner]
        failures.extend(
            f"{path}: references world.migrations.{name}, a generation-{owner[name]} "
            "module that no longer exists. A dropped RunPython has no test subject; "
            "delete the test or move the logic it exercises out of the migration."
            for name in stale
        )
    return failures


def check_migrations(
    migrations_dir: Path = MIGRATIONS_DIR, src_dir: Path | None = None
) -> list[str]:
    """Failure messages for every migration whose name or dependency belongs to the past,
    and for any module outside the package that still names a replaced migration."""
    generations = _generations(migrations_dir)
    if not generations:
        return []
    owner: dict[str, int] = {name: gen for gen, names in generations.items() for name in names}
    failures: list[str] = []
    if src_dir is None and migrations_dir == MIGRATIONS_DIR:
        src_dir = SRC_DIR
    if src_dir is not None:
        failures.extend(check_module_references(src_dir, owner))
    for path in sorted(migrations_dir.iterdir()):
        if not _MIGRATION_FILE.match(path.name):
            continue
        if path.stem in owner:
            failures.append(
                f"{path}: name {path.stem!r} already belongs to generation {owner[path.stem]}; "
                "production has it recorded and would skip this file. Rename it (ADR-0272)."
            )
        stale = [d for d in _arxii_dependencies(path.read_text(encoding="utf-8")) if d in owner]
        failures.extend(
            f"{path}: depends on {dep!r}, a generation-{owner[dep]} name that no longer "
            "exists on disk (a straggler from before a regeneration). Regenerate on the "
            "tip of main (ADR-0272)."
            for dep in stale
        )
    return failures


def main() -> int:
    failures = check_migrations()
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Reject a CHECK constraint that pairs a column added in the same migration with an old one.

``AddField(null=True)`` gives every existing row a NULL. A CHECK constraint on that
column alone can never fail: SQL treats a NULL check as satisfied. But a CHECK that
ties the new column to a column that already existed - "both null or both set" -
is violated by every existing row that has the old column set, and PostgreSQL
validates the whole table at ``ADD CONSTRAINT``::

    IntegrityError: check constraint "pose_submission_interaction_timestamp_pair"
    of relation "arxii_posesubmission" is violated by some row

This is data-dependent: it passes every test and CI run, because a freshly
migrated database has no rows, and then fails on the production converge.
``0149_partitioned_metadata_integrity`` broke the deploy this way on 2026-09-24;
production got past it only after the offending row was changed by hand.

The rule is structural: a column added nullable and a constraint that pairs it
with an existing column never share a migration. Use expand/migrate/contract -
add the column in one migration, backfill it in a data migration, add the
constraint in a third - so the constraint meets rows that already satisfy it.
A column added with a default (``preserve_default=False``) is populated on
every row and is not flagged; neither is a check that references only columns
added in the same migration, since those are all NULL together.

See ADR-0237 and tools/lint_migration_ddl_dml.py for the sibling rule.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# Migrations that predate this rule AND are already applied in production, so
# they can no longer be restructured. NOTHING MAY BE ADDED HERE - a new migration
# that would need an entry is a new migration that needs splitting.
GRANDFATHERED: frozenset[str] = frozenset(
    {
        # Applied to production 2026-09-24 after the deploy it broke; the row it
        # rejected was fixed by hand. The founding case for this linter.
        "world/migrations/0149_partitioned_metadata_integrity.py",
    }
)

Finding = tuple[str, str, str]


def _operations(tree: ast.Module) -> list[ast.Call]:
    """Return the operation calls in a migration's ``operations`` list."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "operations" for t in node.targets):
            continue
        if isinstance(node.value, ast.List):
            return [e for e in node.value.elts if isinstance(e, ast.Call)]
    return []


def _operation_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _kwargs(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _string(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _nullable_without_default(field: ast.expr | None) -> bool:
    """True for a field declared ``null=True`` with no ``default`` to fill old rows."""
    if not isinstance(field, ast.Call):
        return False
    kwargs = _kwargs(field)
    return _is_true(kwargs.get("null")) and "default" not in kwargs


def _referenced_fields(constraint: ast.expr) -> set[str]:
    """Field names a constraint expression reads: ``Q(a__isnull=...)`` keys and ``F("a")``."""
    fields: set[str] = set()
    for node in ast.walk(constraint):
        if not isinstance(node, ast.Call):
            continue
        name = _operation_name(node)
        if name == "Q":
            fields.update(kw.arg.split("__", 1)[0] for kw in node.keywords if kw.arg)
        elif name == "F" and node.args:
            target = _string(node.args[0])
            if target:
                fields.add(target.split("__", 1)[0])
    return fields


def check_source(source: str) -> list[Finding]:
    """Return (model, new nullable column, old columns it is paired with) per offence."""
    operations = _operations(ast.parse(source))

    new_nullable: set[tuple[str, str]] = set()
    for call in operations:
        if _operation_name(call) != "AddField":
            continue
        kwargs = _kwargs(call)
        model = _string(kwargs.get("model_name"))
        name = _string(kwargs.get("name"))
        if model and name and _nullable_without_default(kwargs.get("field")):
            new_nullable.add((model, name))

    findings: list[Finding] = []
    for call in operations:
        if _operation_name(call) != "AddConstraint":
            continue
        kwargs = _kwargs(call)
        model = _string(kwargs.get("model_name"))
        constraint = kwargs.get("constraint")
        if not model or not isinstance(constraint, ast.Call):
            continue
        if _operation_name(constraint) != "CheckConstraint":
            continue
        referenced = _referenced_fields(constraint)
        new_here = {name for m, name in new_nullable if m == model}
        old = referenced - new_here
        if not old:
            continue
        findings.extend(
            (model, name, ", ".join(sorted(old))) for name in sorted(referenced & new_here)
        )
    return findings


def check_migration(path: Path) -> str | None:
    """Return a failure message when *path* pairs a new nullable column with an old one."""
    try:
        findings = check_source(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - a broken migration fails elsewhere
        return f"{path}: could not parse ({exc})"
    if not findings:
        return None

    relative = (
        path.relative_to(SRC_DIR).as_posix() if path.is_relative_to(SRC_DIR) else path.as_posix()
    )
    if relative in GRANDFATHERED:
        return None
    detail = "; ".join(f"{model}.{field} paired with {old}" for model, field, old in findings)
    return (
        f"{relative}: adds a nullable column and, in the same migration, a CHECK constraint "
        f"that pairs it with a column that already exists ({detail}). Every existing row "
        "with the old column set has a NULL in the new one, so ADD CONSTRAINT fails with "
        "'check constraint ... is violated by some row' on the production converge, not "
        "in CI, which migrates an empty database (0149, 2026-09-24). Use "
        "expand/migrate/contract: add the column in one migration, backfill it in a data "
        "migration, add the constraint in a third. "
        "See tools/lint_migration_constraint_on_new_column.py."
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

"""Django-dependent helpers for ``arx manage squashmigrations arxii`` (ADR-0272).

The Django-free half of the regeneration (topological inlining, constraint
folding, tail templates) lives under ``tools/`` so it stays importable without a
settings module; this module is the bridge that needs the app registry, the
migration writer or a database connection.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import shutil
import subprocess
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


# ---------------------------------------------------------------------------
# Repository state and the outgoing generation
# ---------------------------------------------------------------------------

LINT_LIST_FILES = [
    TOOLS_DIR / "lint_migration_ddl_dml.py",
    TOOLS_DIR / "check_migration_seed_data.py",
]
_MIGRATION_FILE = re.compile(r"^\d{4}_.+\.py$")
_ROW_CREATION = re.compile(r"\.(get_or_create|update_or_create|bulk_create|create)\(")
_READ_SQL_CALL = re.compile(r'_read_sql\("[^"]+",\s*"([^"]+)"\)')
RUN_PYTHON = "RunPython"
RUN_SQL = "RunSQL"
_NON_SCHEMA_OPS = {RUN_PYTHON, RUN_SQL, "SeparateDatabaseAndState"}


def migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(p for p in migrations_dir.iterdir() if _MIGRATION_FILE.match(p.name))


def snapshot_names(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    return [p.stem for p in migration_files(migrations_dir)]


def _git(*args: str, repo_root: Path = REPO_ROOT) -> str:
    git = shutil.which("git") or "git"
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [git, "-C", str(repo_root), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def git_main_base(repo_root: Path = REPO_ROOT) -> str:
    """The tip of ``origin/main`` this branch sits on: the last commit on main whose
    files are the outgoing generation. Recorded as ``COMMITS[n]`` for the guard's
    recovery message; the branch's own HEAD would be rewritten by the sync rebase
    and its sha would dangle."""
    return _git("merge-base", "HEAD", "origin/main", repo_root=repo_root)


def git_is_clean(repo_root: Path = REPO_ROOT) -> bool:
    return _git("status", "--porcelain", repo_root=repo_root) == ""


def in_main_checkout(repo_root: Path = REPO_ROOT) -> bool:
    """True for the primary checkout, False for a linked worktree."""
    git_dir = Path(repo_root, _git("rev-parse", "--git-dir", repo_root=repo_root)).resolve()
    common = Path(repo_root, _git("rev-parse", "--git-common-dir", repo_root=repo_root)).resolve()
    return git_dir == common


def _first_doc_line(source: str) -> str:
    doc = ast.get_docstring(ast.parse(source)) or ""
    return doc.splitlines()[0] if doc else "(no docstring)"


def _non_schema_operations(source: str) -> list[str]:
    return [
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _NON_SCHEMA_OPS
    ]


def _runpython_disposition(source: str) -> str:
    kind = "discard" if ".delete(" in source else "restructure"
    if _ROW_CREATION.search(source):
        kind += " (allowlisted row creation; see tools/check_migration_seed_data.py)"
    return f"dropped: {kind}; production applied it, a fresh database has no rows"


def _runsql_disposition(source: str, sql_basenames: set[str]) -> str:
    referenced = set(_READ_SQL_CALL.findall(source))
    missing = sorted(
        name
        for name in referenced
        if name not in sql_basenames and not name.endswith("_reverse.sql")
    )
    if missing:
        return f"NOT in SQL_FILES: {missing}"
    return "carried forward (rendered tail from SQL_FILES)"


def drop_report(sources: dict[str, str], sql_files: list[str]) -> str:
    """Markdown table: every non-schema operation of the outgoing generation and its fate.

    ``RunPython`` is always dropped (ADR-0237 restructures and discards on alpha data:
    production applied them, a fresh database has no rows). ``RunSQL`` from
    ``build_schema.SQL_FILES`` is carried forward as a rendered tail; any other
    ``RunSQL`` is flagged, because nothing will re-create what it built.
    """
    lines = [
        "| migration | operation | disposition | first docstring line |",
        "|---|---|---|---|",
    ]
    sql_basenames = {Path(f).name for f in sql_files}
    for name in sorted(sources):
        source = sources[name]
        for op in _non_schema_operations(source):
            if op == RUN_PYTHON:
                disposition = _runpython_disposition(source)
            elif op == RUN_SQL:
                disposition = _runsql_disposition(source, sql_basenames)
            else:
                disposition = "re-rendered from the live model (partition_columns tail)"
            lines.append(f"| `{name}` | {op} | {disposition} | {_first_doc_line(source)} |")
    return "\n".join(lines) + "\n"


def deferred_verdict(baseline: int | None, measured: int, accepted: int | None) -> str | None:
    """Why a regeneration may not proceed on its cycle-breaking AddField count, or None.

    A rise over the previous generation's count means a new FK cycle entered the
    schema; the PR must name it, and the rerun passes ``--accept-deferred`` with
    the exact measured count so the acknowledgement is explicit and checked.
    """
    if accepted is not None:
        if accepted != measured:
            return (
                f"--accept-deferred {accepted} does not match the measured "
                f"{measured}; pass the measured count once you have named the cycle"
            )
        return None
    if baseline is not None and measured > baseline:
        return (
            f"deferred cycle-breaking AddFields rose from {baseline} to {measured}: a new FK "
            "cycle entered the schema. Name it in the PR, then rerun with "
            f"--accept-deferred {measured} (spec #3656, Design 1 step 5)."
        )
    return None


def prune_lint_lists(files: list[Path], existing_names: set[str]) -> dict[str, list[str]]:
    """Drop ``"world/migrations/<name>.py",`` lines whose migration no longer exists.

    The two filename-keyed lint lists say "nothing may be added"; removing an entry
    for a deleted file honours that, it does not loosen it.
    """
    removed: dict[str, list[str]] = {}
    pattern = re.compile(r'^\s*"world/migrations/([^"/]+)\.py",\n', re.MULTILINE)
    for path in files:
        text = path.read_text(encoding="utf-8")
        gone: list[str] = []

        def _keep_or_drop(match: re.Match[str], gone: list[str] = gone) -> str:
            if match.group(1) in existing_names:
                return match.group(0)
            gone.append(f"world/migrations/{match.group(1)}.py")
            return ""

        new_text = pattern.sub(_keep_or_drop, text)
        if gone:
            path.write_text(new_text, encoding="utf-8")
            removed[str(path)] = gone
    return removed

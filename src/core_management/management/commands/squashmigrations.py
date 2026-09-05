"""``squashmigrations``, replaced (ADR-0272).

Django's command concatenates a range and runs ``MigrationOptimizer``. That
optimizer never reorders ``CreateModel`` and is blocked by every index/constraint
operation in between, so on this schema it cannot reach the FK-deferral floor
(measured 2026-09-05: 531 s, 3% fewer operations, output that does not compile).
This command regenerates instead: snapshot the outgoing generation, delete it,
``makemigrations`` a fresh initial from model state, inline FKs topologically and
fold constraints (``tools/optimize_initial_migration.py``), chunk, render the
infrastructure tails (``tools/migration_tails.py``), stamp ``replaces``, prune the
filename-keyed lint lists, and write the drop report. Django's ``replaces``
semantics are kept end to end; nothing here touches a database's schema.

Wins resolution over Django's and django-linear-migrations' commands because
``core_management`` is first in INSTALLED_APPS (pinned by
``core_management.tests.test_command_resolution``). Takes the app label only:
there is one chain, and a partial squash is the shape that produces cycle bugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from core_management.migration_generations import (
    APP_LABEL,
    GENERATIONS_PATH,
    GenerationsData,
    load_generations,
    write_generations,
)
from core_management.regeneration import (
    LINT_LIST_FILES,
    MIGRATIONS_DIR,
    REPO_ROOT,
    TOOLS_DIR,
    drop_report,
    git_head,
    git_is_clean,
    in_main_checkout,
    migration_files,
    post_partition_addfield_sources,
    prune_lint_lists,
    snapshot_names,
    tools_module,
)

REPORT_PATH = REPO_ROOT / "regeneration-report.md"


@dataclass(frozen=True)
class RegenerationOutcome:
    """Everything the drop report needs, gathered once the files are written."""

    new_gen: int
    old_gen: int
    outgoing: dict[str, str]
    head: str
    stats: dict[str, Any]
    sql_files: list[str]
    removed: dict[str, list[str]]


# Generation 1 was inlined by hand for #2906; ADR-0195 records its cycle floor.
GENERATION_1_DEFERRED_BASELINE = 34
DEFAULT_CHUNKS = 100
CHUNK_SIZES_KEY = "chunk_sizes"  # the one inliner stat that is a list, kept out of prose


class Command(BaseCommand):
    help = (
        "Regenerate the arxii migration chain to its floor and hand every database across "
        "with replaces. Replaces Django's squashmigrations (ADR-0272)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("app_label")
        parser.add_argument("migration_range", nargs="*", help="refused: there is one chain")
        parser.add_argument("--chunks", type=int, default=DEFAULT_CHUNKS)
        parser.add_argument(
            "--check", action="store_true", help="preflight and report only; write nothing"
        )
        parser.add_argument("--allow-main-checkout", action="store_true")

    def handle(self, *_args: Any, **options: Any) -> None:
        if options["app_label"] != APP_LABEL or options["migration_range"]:
            message = (
                f"This command regenerates the whole {APP_LABEL!r} chain and takes no range: "
                f"`arx manage squashmigrations {APP_LABEL}` (ADR-0272)."
            )
            raise CommandError(message)
        inliner = tools_module("optimize_initial_migration")
        tails = tools_module("migration_tails")

        data = load_generations()
        new_gen = data.current + 1
        self._preflight(new_gen, allow_main=options["allow_main_checkout"])
        baseline = self._deferred_baseline(data)
        outgoing = {p.stem: p.read_text(encoding="utf-8") for p in migration_files()}
        if options["check"]:
            self.stdout.write(
                f"preflight ok: would regenerate generation {new_gen}, replacing "
                f"{len(outgoing)} files; deferred-FK baseline {baseline}"
            )
            return

        head = git_head()
        for path in migration_files():
            path.unlink()

        # A fresh initial from model state, through our makemigrations override.
        call_command("makemigrations", APP_LABEL, verbosity=0)
        initial = MIGRATIONS_DIR / "0001_initial.py"
        if not initial.exists():
            message = "makemigrations did not produce 0001_initial.py"
            raise CommandError(message)
        source = initial.read_text(encoding="utf-8")

        files, stats = inliner.rewrite_chunks(source, options["chunks"], generation=new_gen)
        self._print_stats(stats)
        deferred = int(stats["deferred_addfield_cycle"])
        if baseline is not None and deferred > baseline:
            message = (
                f"deferred cycle-breaking AddFields rose from {baseline} to {deferred}; a new "
                "FK cycle entered the schema. Name it in the PR, then rerun with the count "
                "explained (spec #3656, Design 1 step 5). Nothing was written; restore with git."
            )
            raise CommandError(message)
        initial.unlink()
        for name, content in files:
            (MIGRATIONS_DIR / f"{name}.py").write_text(content, encoding="utf-8")

        last_name = self._write_tails(tails, new_gen, files[-1][0])
        (MIGRATIONS_DIR / "max_migration.txt").write_text(last_name + "\n", encoding="utf-8")
        write_generations(
            GenerationsData(
                current=new_gen,
                generations={**data.generations, data.current: sorted(outgoing)},
                commits={**data.commits, data.current: head},
                deferred={**data.deferred, data.current: baseline or 0, new_gen: deferred},
            )
        )
        removed = prune_lint_lists(LINT_LIST_FILES, existing_names=set(snapshot_names()))

        outcome = RegenerationOutcome(
            new_gen=new_gen,
            old_gen=data.current,
            outgoing=outgoing,
            head=head,
            stats=stats,
            sql_files=tails.read_sql_files(TOOLS_DIR / "build_schema.py"),
            removed=removed,
        )
        report = self._report(outcome)
        REPORT_PATH.write_text(report, encoding="utf-8")
        self.stdout.write(report)
        self._house_style()
        self.stdout.write(
            self.style.SUCCESS(
                f"generation {new_gen} written: {len(files)} chunks + 3 tails, tip {last_name}; "
                f"report at {REPORT_PATH}"
            )
        )

    # -- steps -----------------------------------------------------------------

    def _preflight(self, new_gen: int, *, allow_main: bool) -> None:
        if in_main_checkout() and not allow_main:
            message = "run this from a worktree, not the main checkout (--allow-main-checkout)"
            raise CommandError(message)
        if not git_is_clean():
            message = "git tree is not clean; commit or discard first"
            raise CommandError(message)
        if any(f"_g{new_gen}_" in p.stem for p in migration_files()):
            message = (
                f"generation {new_gen} files already exist. A rerun starts from a fresh "
                "worktree on the tip of main plus the tooling commits (ADR-0272)."
            )
            raise CommandError(message)
        if not GENERATIONS_PATH.exists():
            message = f"{GENERATIONS_PATH} is missing; see core_management.migration_generations"
            raise CommandError(message)
        try:
            call_command("makemigrations", APP_LABEL, check=True, dry_run=True, verbosity=0)
        except SystemExit as exc:
            message = "models have changes with no migration; run makemigrations first"
            raise CommandError(message) from exc
        tip = (MIGRATIONS_DIR / "max_migration.txt").read_text(encoding="utf-8").strip()
        recorded = {
            name
            for app, name in MigrationRecorder(connection).applied_migrations()
            if app == APP_LABEL
        }
        if tip not in recorded:
            message = (
                f"the connected database has not recorded {tip!r}; run `arx manage migrate` "
                "first so the snapshot describes a database state that exists"
            )
            raise CommandError(message)

    @staticmethod
    def _deferred_baseline(data: GenerationsData) -> int | None:
        if data.current in data.deferred:
            return data.deferred[data.current]
        return GENERATION_1_DEFERRED_BASELINE if data.current == 1 else None

    def _write_tails(self, tails: Any, new_gen: int, last_chunk: str) -> str:
        sql_files = tails.read_sql_files(TOOLS_DIR / "build_schema.py")
        partition_entries = [
            (Path(f).parts[1], Path(f).name) for f in sql_files if f.endswith("_forward.sql")
        ]
        matview_entries = [
            (
                Path(f).parts[1],
                Path(f).name,
                tails.matview_name((REPO_ROOT / "src" / f).read_text(encoding="utf-8")),
            )
            for f in sql_files
            if not f.endswith("_forward.sql")
        ]
        addfields, imports = post_partition_addfield_sources()
        number = int(last_chunk[:4]) + 1
        p_sql, p_cols, m_views = tails.tail_names(new_gen, number)
        rendered = {
            p_sql: tails.render_partition_sql_tail(p_sql, last_chunk, partition_entries),
            p_cols: tails.render_partition_columns_tail(p_cols, p_sql, addfields, imports),
            m_views: tails.render_matviews_tail(m_views, p_cols, matview_entries),
        }
        for name, content in rendered.items():
            (MIGRATIONS_DIR / f"{name}.py").write_text(content, encoding="utf-8")
        return m_views

    @staticmethod
    def _report(outcome: RegenerationOutcome) -> str:
        lines = [
            f"# Regeneration report: generation {outcome.new_gen} replaces generation "
            f"{outcome.old_gen} ({len(outcome.outgoing)} files, commit {outcome.head})",
            "",
            "## Inliner stats",
            "",
            *(f"- {k}: {v}" for k, v in outcome.stats.items() if k != CHUNK_SIZES_KEY),
            "",
            "## Non-schema operations of the outgoing generation",
            "",
            drop_report(outcome.outgoing, outcome.sql_files).rstrip("\n"),
        ]
        if outcome.removed:
            lines += ["", "## Lint-list entries removed", ""]
            lines += [f"- `{f}`: {', '.join(names)}" for f, names in outcome.removed.items()]
        return "\n".join(lines) + "\n"

    def _print_stats(self, stats: dict[str, Any]) -> None:
        for key, value in stats.items():
            if key != CHUNK_SIZES_KEY:
                self.stdout.write(f"{key}: {value}")

    @staticmethod
    def _house_style() -> None:
        uv = shutil.which("uv") or "uv"
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [uv, "run", "ruff", "format", str(MIGRATIONS_DIR)], cwd=REPO_ROOT, check=True
        )
        subprocess.run(  # noqa: S603
            [uv, "run", "ruff", "check", "--fix", str(MIGRATIONS_DIR)], cwd=REPO_ROOT, check=False
        )

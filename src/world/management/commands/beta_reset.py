"""Guarded beta-reset management command (#3055 PR 2).

Wipes every play-provenance row in the world back to a pristine, CG/authoring-only
baseline. Management command only — this is deliberately never surfaced in the Django
admin. Thin wrapper: all logic lives in ``world.beta_reset.services``.

**Operational assumption:** the server must be QUIESCED (no concurrent writers) before
running this. No cache-flush machinery is built here or in the service — a running
server with players connected would leave stale SharedMemoryModel instances in memory
even though their rows were deleted.

**Before running with ``--execute``, the operator must have:**

1. Run a real backup restore-verify (``infra/scripts/restore-rehearsal.sh`` or
   equivalent) within the last 24 hours, and pass its timestamp via
   ``--backup-verified-at``. This command does NOT run or verify a backup itself.
2. Quiesced the server (stopped accepting new connections / actions).
3. Read the dry-run output (the default, with no ``--execute``) and confirmed the
   per-model counts look right.

Run as: ``arx manage beta_reset`` (dry-run, default, always safe) or
``arx manage beta_reset --execute --confirm "wipe the alpha world"
--backup-verified-at 2026-08-08T12:00:00+00:00`` (the real thing — also gated by the
hardcoded ``BETA_RESET_ENABLED`` constant and the one-way ``ReleaseLatch`` DB row; see
``world.beta_reset.services`` for the full guard design).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from world.beta_reset.exceptions import BetaResetError
from world.beta_reset.services import CONFIRMATION_PHRASE, wipe_pristine_world


class Command(BaseCommand):
    help = (
        "Guarded beta-reset wipe (#3055 PR 2). Defaults to a dry-run that only counts "
        "rows. Requires the server to be quiesced and a recently-verified backup before "
        "--execute. See world/beta_reset/services.py for the full guard design."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Actually perform the wipe. Without this flag, always a safe dry-run.",
        )
        parser.add_argument(
            "--confirm",
            default=None,
            help=f'Required with --execute. Must be exactly: "{CONFIRMATION_PHRASE}"',
        )
        parser.add_argument(
            "--backup-verified-at",
            default=None,
            metavar="ISO_TIMESTAMP",
            help=(
                "Required with --execute. ISO-8601 timestamp of when you last ran a "
                "backup restore-verify (infra/scripts/restore-rehearsal.sh). Must be "
                "within the freshness window (see services.BACKUP_FRESHNESS_WINDOW)."
            ),
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        execute: bool = options["execute"]
        confirm: str | None = options["confirm"]
        backup_verified_at_raw: str | None = options["backup_verified_at"]

        backup_verified_at: datetime | None = None
        if backup_verified_at_raw:
            try:
                backup_verified_at = datetime.fromisoformat(backup_verified_at_raw)
            except ValueError as exc:
                msg = f"--backup-verified-at is not a valid ISO-8601 timestamp: {exc}"
                raise CommandError(msg) from exc

        try:
            report = wipe_pristine_world(
                execute=execute,
                confirm=confirm,
                backup_verified_at=backup_verified_at,
            )
        except BetaResetError as exc:
            raise CommandError(exc.user_message) from exc

        verb = "Deleted" if report.executed else "Would delete"
        for count in report.counts:
            if count.would_delete:
                self.stdout.write(f"  {verb} {count.would_delete} {count.label} row(s).")
        summary = self.style.WARNING if report.executed else self.style.NOTICE
        self.stdout.write(
            summary(f"{verb} {report.total} row(s) total across {len(report.counts)} model(s).")
        )
        if not report.executed:
            self.stdout.write(
                "Dry run only — nothing was touched. Re-run with --execute --confirm "
                f'"{CONFIRMATION_PHRASE}" --backup-verified-at <ISO timestamp> to perform '
                "the wipe."
            )

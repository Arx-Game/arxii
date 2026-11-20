"""Guarded beta-reset management command (#3055 PR 2 and PR 3).

Runs the cutover policy steps (roster characters, reserved original characters and any
``--carry-over`` characters are released and progress-reset), then wipes every
play-provenance row in the world back to a pristine, CG/authoring-only baseline.
Management command only — this is deliberately never surfaced in the Django admin. Thin
wrapper: the logic lives in ``world.beta_reset.cutover`` and ``world.beta_reset.services``.

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

from world.beta_reset.cutover import CutoverReport, run_beta_cutover
from world.beta_reset.exceptions import BetaResetError
from world.beta_reset.services import CONFIRMATION_PHRASE


class Command(BaseCommand):
    help = (
        "Guarded beta cutover (#3055). Defaults to a dry-run that lists what each policy "
        "step would do and counts the rows the wipe would delete. Requires the server to be "
        "quiesced and a recently-verified backup before --execute. See "
        "world/beta_reset/services.py for the full guard design."
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

        parser.add_argument(
            "--carry-over",
            action="append",
            type=int,
            default=[],
            metavar="CHARACTER_SHEET_ID",
            help=(
                "Carry a tester's alpha character into early access with its progress "
                "zeroed. Repeat for each character. A roster character or an original "
                "character with a recorded author is already covered and needs no flag."
            ),
        )

        parser.add_argument(
            "--allow-incomplete-ledger",
            action="store_true",
            default=False,
            help=(
                "Proceed past kept characters whose provenance ledger is incomplete. By "
                "default --execute refuses and names them; the dry-run lists them."
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
            report = run_beta_cutover(
                execute=execute,
                confirm=confirm,
                backup_verified_at=backup_verified_at,
                carry_over_sheet_ids=options["carry_over"],
                allow_incomplete_ledger=options["allow_incomplete_ledger"],
            )
        except BetaResetError as exc:
            raise CommandError(exc.user_message) from exc

        self._write_report(report)

    def _write_report(self, report: CutoverReport) -> None:
        verb = "Deleted" if report.wipe.executed else "Would delete"
        action = "Did" if report.executed else "Would"
        self.stdout.write(f"{action} run {len(report.plan.steps)} cutover policy step(s):")
        for step in report.plan.steps:
            self.stdout.write(f"  {step.describe()}")
        if report.plan.carry_over_already_covered:
            names = ", ".join(report.plan.carry_over_already_covered)
            self.stdout.write(f"  Already covered by policy, no --carry-over needed: {names}")
        findings = report.plan.ledger_findings()
        if findings:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(findings)} kept character(s) have an incomplete provenance ledger: "
                    + ", ".join(findings)
                    + ". --execute refuses these unless --allow-incomplete-ledger is given."
                )
            )
        self.stdout.write(
            f"{report.undecided_models} character-linked table(s) are awaiting a ruling "
            "(world.beta_reset.classification.UNDECIDED_AWAITING_RULING) and are left "
            "untouched by this command."
        )
        if not report.executed:
            self.stdout.write(
                "The wipe counts below are computed BEFORE the policy steps run, so rows the "
                "steps remove from kept characters (play-time techniques, gifts, distinctions, "
                "trait changes) are counted here too. A real run reports what the wipe itself "
                "deleted after the steps."
            )
        for count in report.wipe.counts:
            if count.would_delete:
                self.stdout.write(f"  {verb} {count.would_delete} {count.label} row(s).")
        summary = self.style.WARNING if report.executed else self.style.NOTICE
        self.stdout.write(
            summary(
                f"{verb} {report.wipe.total} row(s) total across {len(report.wipe.counts)} "
                "model(s)."
            )
        )
        if not report.executed:
            self.stdout.write(
                "Dry run only — nothing was touched. Re-run with --execute --confirm "
                f'"{CONFIRMATION_PHRASE}" --backup-verified-at <ISO timestamp> to perform '
                "the cutover."
            )

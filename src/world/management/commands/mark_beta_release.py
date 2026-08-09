"""Write the one-way beta-reset ReleaseLatch row (#3055 PR 2).

Separate, tiny command from ``beta_reset`` itself — this is the operator's way to arm
the belt-and-suspenders DB-side guard once early access has actually shipped. There is
no corresponding "unmark" command; ``world.beta_reset.services.mark_released`` refuses
to write a second row once one exists.

Run as: ``arx manage mark_beta_release --released-by <staff username> [--note "..."]``.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from evennia.accounts.models import AccountDB

from world.beta_reset.exceptions import BetaResetError
from world.beta_reset.services import mark_released


class Command(BaseCommand):
    help = (
        "Write the one-way ReleaseLatch row that permanently blocks the beta_reset "
        "command from ever running again. No 'unmark' path exists."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--released-by",
            required=True,
            metavar="USERNAME",
            help="Username of the staff account recorded as having flipped the latch.",
        )
        parser.add_argument(
            "--note",
            default="",
            help="Optional free-text context (e.g. cutover ticket link).",
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        username: str = options["released_by"]
        note: str = options["note"]

        try:
            account = AccountDB.objects.get(username=username)
        except AccountDB.DoesNotExist as exc:
            msg = f"No account found with username '{username}'."
            raise CommandError(msg) from exc

        try:
            latch = mark_released(released_by=account, note=note)
        except BetaResetError as exc:
            raise CommandError(exc.user_message) from exc

        self.stdout.write(
            self.style.WARNING(
                f"ReleaseLatch written (released_at={latch.released_at.isoformat()}, "
                f"released_by={username}). The beta_reset command can never run again."
            )
        )

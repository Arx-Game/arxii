"""Telnet pointer for the staff-contact surfaces (#2288) — web-first, pointer-only."""

from typing import ClassVar

from commands.command import Command

_SUBVERB_STATUS = "status"


class CmdPetition(Command):
    """
    Reach staff about an emergency, or check your petition's status.

    Usage:
        petition
        petition status

    Filing happens on the website (Profile menu > Petition Staff) — the
    form walks you through the emergency categories and attaches the
    scene or character it is about. This command is a pointer plus a
    read-only status check, not a filing surface. For non-emergencies
    use the website's feedback form instead.
    """

    key = "petition"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:
        """Point to the web form; show the caller's own open petition, if any."""
        from world.player_submissions.constants import SubmissionStatus  # noqa: PLC0415
        from world.player_submissions.models import Petition  # noqa: PLC0415

        raw = (self.args or "").strip().lower()
        if raw and raw != _SUBVERB_STATUS:
            self.caller.msg("Unknown petition command. Try: petition status.")
            return

        # Scoped to the caller's own account — no id-based lookup exists here.
        open_petition = Petition.objects.filter(
            account=self.account, status=SubmissionStatus.OPEN
        ).first()
        if open_petition is None:
            self.caller.msg(
                "You have no open petition. Emergencies are filed on the website: "
                "Profile menu > Petition Staff (Emergency)."
            )
            return
        self.caller.msg(
            f"Your open petition ({open_petition.get_category_display()}) is awaiting staff. "
            "Details and staff notes are on the website under Petition Staff."
        )

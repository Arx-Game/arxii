"""Staff/GM telnet surface for the captivity system (#1500).

``demandransom`` raises a crowdfundable ransom for a held captive: it creates a
RANSOM Project standing in the captive's cell that anyone may ``project/donate``
toward, freeing them the instant it's funded. Thin over
``world.captivity.ransom_project.demand_ransom_project`` — the same service the
web GM endpoint calls. Staff-only for now (``perm(Admin)``); opening it to a GM
permission is a later one-lock change, mirroring ``gemit``.
"""

from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage:\n"
    "  demandransom <captive>            — demand the default ransom\n"
    "  demandransom <captive> = <amount> — demand <amount> coppers"
)


class CmdDemandRansom(ArxCommand):
    """Demand a crowdfundable ransom for a held captive (staff).

    Creates a RANSOM project in the captive's cell; anyone may then
    ``project/donate`` toward it, and the captive is freed the instant it is
    fully funded.

    Usage:
      demandransom <captive>
      demandransom <captive> = <amount>
    """

    key = "demandransom"
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        try:
            self._run()
        except CommandError as exc:
            self.msg(str(exc))

    def _run(self) -> None:
        from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
        from world.captivity.exceptions import CaptivityError  # noqa: PLC0415
        from world.captivity.models import Captivity  # noqa: PLC0415
        from world.captivity.ransom_project import demand_ransom_project  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_USAGE)
        if "=" in raw:
            name, amount_part = (part.strip() for part in raw.split("=", 1))
            if not amount_part.isdigit():
                msg = "The amount must be a number of coppers."
                raise CommandError(msg)
            amount: int | None = int(amount_part)
        else:
            name, amount = raw, None
        if not name:
            raise CommandError(_USAGE)

        target = self.caller.search(name, global_search=True)
        if target is None:
            return  # search() already messaged the caller.

        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = "That is not a character."
            raise CommandError(msg)
        captivity = Captivity.objects.filter(captive=sheet, status=CaptivityStatus.HELD).first()
        if captivity is None:
            msg = "That character is not being held captive."
            raise CommandError(msg)

        try:
            project = demand_ransom_project(captivity, amount=amount)
        except CaptivityError as exc:
            raise CommandError(exc.user_message) from exc

        self.msg(
            f"Ransom demanded for {target.key}: project #{project.pk}, "
            f"{project.threshold_target} progress ({project.threshold_target * 100} coppers) "
            "to free them. Anyone may `project/donate` toward it."
        )

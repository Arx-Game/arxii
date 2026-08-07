"""Telnet `train` command (#2739) — dispatches TrainTechniqueAction.

Modeled on CmdTravel (commands/travel.py): overrides func() directly rather
than the base ArxCommand._execute() single-action-dispatch recipe, since bare
`train` needs a meter-listing read path with no action dispatch, and
resolving the technique name to a technique_id needs custom logic before
dispatch. No business logic lives here — meter listing is a plain read, and
the session itself is entirely `TrainTechniqueAction`'s.
"""

from __future__ import annotations

from actions.definitions.technique_training import TrainTechniqueAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdTrain(ArxCommand):
    """Invest AP in a technique training session, or list your meters.

    Usage:
      train                    - list your in-progress technique meters
      train <technique>        - train, investing the default AP
      train <technique>=<ap>   - train, investing a specific amount of AP
    """

    key = "train"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._list_meters()
            return

        try:
            self._do_train(raw)
        except CommandError as err:
            self.msg(str(err))

    def _list_meters(self) -> None:
        from world.magic.models import TechniqueProgress  # noqa: PLC0415

        sheet = self.caller.sheet_data
        meters = TechniqueProgress.objects.filter(character_sheet=sheet).select_related(
            "technique",
            "teacher_tenure",
        )
        if not meters:
            self.msg("You aren't training any techniques.")
            return

        lines = ["Your in-progress technique meters:"]
        for meter in meters:
            tenure = meter.teacher_tenure
            teacher_character = tenure.character if tenure is not None else None
            teacher_name = teacher_character.key if teacher_character is not None else "-"
            lines.append(
                f"  {meter.technique.name}: {meter.points_accumulated}/"
                f"{meter.total_required} (teacher: {teacher_name})"
            )
        self.msg("\n".join(lines))

    def _do_train(self, raw: str) -> None:
        from world.magic.models import Technique  # noqa: PLC0415

        name_part, _sep, ap_part = raw.partition("=")
        name = name_part.strip()
        if not name:
            msg = "Usage: train <technique>[=<ap>]."
            raise CommandError(msg)

        ap_to_invest = None
        ap_part = ap_part.strip()
        if ap_part:
            try:
                ap_to_invest = int(ap_part)
            except ValueError:
                msg = f"'{ap_part}' is not a valid AP amount."
                raise CommandError(msg) from None

        technique = Technique.objects.filter(name__iexact=name).first()
        if technique is None:
            msg = f"There is no technique called '{name}'."
            raise CommandError(msg)

        kwargs = {"technique_id": technique.pk}
        if ap_to_invest is not None:
            kwargs["ap_to_invest"] = ap_to_invest

        result = TrainTechniqueAction().run(self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

"""Extracting Primum (#5125): the ``extract`` command.

Thin over ``HarvestPrimumAction`` (``actions/definitions/primum.py``), the same seam the web
Extract buttons dispatch. ``extract fire`` takes from the lair she stands in; ``extract fire
from elemental`` takes from a slain foe. Bare ``extract`` lists what she can extract here.
The field-food ``harvest`` command (``commands/agriculture.py``) is a different command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from actions.types import ActionResult
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef, DispatchResult

_FROM_WORD = "from"


class CmdExtract(DispatchCommand):
    """Extract Primum from a lair or from a slain creature.

    Usage:
        extract                       (list what you can extract here)
        extract <substance>           (for example: extract fire, in a lair)
        extract <substance> from <foe>  (for example: extract fire from elemental)

    You are offered only the Primum you perceive. A slain creature can be extracted once,
    by one person; a lair gives up what it holds. Every attempt costs action points and
    fatigue, whatever you roll.
    """

    key = "extract"
    locks = "cmd:all()"

    def func(self) -> None:
        """Bare ``extract`` lists; anything else dispatches."""
        if not (self.args or "").strip():
            self._list_offers()
            return
        super().func()

    def _report_dispatch_result(self, result: DispatchResult) -> None:
        """The harvest answer, then what the source holds now, as the web answer shows it."""
        super()._report_dispatch_result(result)
        detail = result.detail
        if isinstance(detail, ActionResult) and detail.success and detail.data:
            remaining = detail.data.get("remaining_line", "")
            if remaining:
                self.msg(remaining)

    def _list_offers(self) -> None:
        from world.magic.services.harvest import check_line, harvest_offers  # noqa: PLC0415

        offers = harvest_offers(self.caller)
        if not offers:
            self.msg("There is nothing here for you to extract.")
            return
        for offer in offers:
            step = f" ({offer.step_name})" if offer.step_name else ""
            if offer.opponent_id is None:
                self.msg(f"You can extract {offer.substance_name} Primum{step} here.")
            else:
                self.msg(
                    f"You can extract {offer.substance_name} Primum{step} "
                    f"from {offer.opponent_name}."
                )
            if offer.check_name:
                self.msg(f"  {check_line(offer)}")
        if offers[0].ap_cost:
            self.msg(f"Each attempt costs {offers[0].ap_cost} AP, whatever you roll.")

    def _split(self) -> tuple[str, str]:
        """The substance and the foe's name ("" when none) typed after the verb."""
        words = self.args.split()
        for position, word in enumerate(words):
            if 0 < position < len(words) - 1 and word.lower() == _FROM_WORD:
                return " ".join(words[:position]), " ".join(words[position + 1 :])
        return " ".join(words), ""

    def _foe_id(self, name: str) -> int:
        """The slain foe in the room whose name is ``name`` (a foe still on offer wins)."""
        from world.combat.constants import OpponentStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415
        from world.magic.services.harvest import harvest_offers  # noqa: PLC0415

        wanted = name.lower()
        for offer in harvest_offers(self.caller):
            if offer.opponent_id is not None and offer.opponent_name.lower() == wanted:
                return offer.opponent_id
        slain = CombatOpponent.objects.filter(
            encounter__room=self.caller.location, status=OpponentStatus.DEFEATED
        ).order_by("pk")
        for foe in slain:
            if foe.name.lower() == wanted:
                return foe.pk
        for foe in slain:
            if foe.name.lower().startswith(wanted) or wanted in foe.name.lower().split():
                return foe.pk
        msg = f"You see no slain {name} here."
        raise CommandError(msg)

    def resolve_action_ref(self) -> ActionRef:
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="harvest_primum")

    def resolve_action_args(self) -> dict[str, Any]:
        substance, foe_name = self._split()
        kwargs: dict[str, Any] = {"substance": substance}
        if foe_name:
            kwargs["opponent_id"] = self._foe_id(foe_name)
        return kwargs

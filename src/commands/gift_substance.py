"""Calling up a gift's substance with no technique (#5018) — the ``callup`` command.

Thin over ``CallUpSubstanceAction`` (``actions/definitions/gift_substance.py``), the same
seam the web "Call up shadow" buttons dispatch. Bare ``callup`` lists her gifts with what
each would cost here; ``callup <substance>`` calls it up; ``callup/confirm <substance>``
goes ahead past the soulfray warning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand

if TYPE_CHECKING:
    from actions.types import ActionRef


_CONFIRM_SWITCH = "confirm"


class CmdCallUp(DispatchCommand):
    """Call up your gift's substance around you, with no technique.

    Usage:
        callup                      (list your gifts and what each costs here)
        callup <substance>          (for example: callup shadow)
        callup/confirm <substance>  (go ahead past the soulfray warning)

    The room changes for everyone while you stay. In a fight it is an immediate act,
    once a round, and not your action for the round.
    """

    key = "callup"
    switch_options = (_CONFIRM_SWITCH,)
    locks = "cmd:all()"

    def func(self) -> None:
        """Bare ``callup`` lists; anything else dispatches."""
        if not (self.args or "").strip():
            self._list_offers()
            return
        super().func()

    def _list_offers(self) -> None:
        from world.magic.services.substance import call_up_offers  # noqa: PLC0415

        offers = call_up_offers(self.caller)
        if not offers:
            self.msg("You hold no gift whose substance you can call up.")
            return
        for offer in offers:
            self.msg(f"Your gift: {offer.plan.label} ({offer.cost_line} here)")

    def resolve_action_ref(self) -> ActionRef:
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="call_up_substance")

    def resolve_action_args(self) -> dict[str, Any]:
        return {
            "substance": self.args.strip(),
            "confirm_soulfray_risk": _CONFIRM_SWITCH in (self.switches or []),
        }

"""Gift/technique/thread-weaving acquisition telnet command — ``learn`` (#2116).

A single namespaced command routes three verbs through the shared
``dispatch_player_action`` seam — the same REGISTRY path the web uses — reaching
the three Actions in ``actions/definitions/gift_acquisition.py``. Bare ``learn``/
``learn status`` shows a hub: open ``GiftUnlock`` rows (XP cost + purchased/missing
status) and open teaching offers (pitch/cost/teacher) for both techniques and
thread-weaving. Mirrors ``CmdSanctum``'s namespaced-subverb shape. No business
logic lives here — all behavior lives in the three Actions and the services they wrap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

_STATUS_SUBVERB = "status"
_GIFT_SUBVERB = "gift"

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    _GIFT_SUBVERB: "purchase_gift_unlock",
    "technique": "accept_technique_offer",
    "thread": "accept_thread_weaving_offer",
}


def _require_positive_int(value: str, name: str) -> int:
    """Return *value* as a positive int, or raise CommandError."""
    if not value or not value.isdigit() or int(value) <= 0:
        msg = f"Usage: learn {name} <id>."
        raise CommandError(msg)
    return int(value)


class CmdLearn(DispatchCommand):
    """Spend XP to unlock gifts and accept teaching offers.

    Usage:
        learn                    — show the learning hub (open unlocks + offers)
        learn status             — (same)
        learn gift <id>          — purchase a GiftUnlock (id = GiftUnlock pk)
        learn technique <id>     — accept a TechniqueTeachingOffer (id = offer pk)
        learn thread <id>        — accept a ThreadWeavingTeachingOffer (id = offer pk)
    """

    key = "learn"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``learn``/``learn status`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _STATUS_SUBVERB:
            self._show_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown learn action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's single positional id into the Action's kwarg."""
        target_id = _require_positive_int(self._rest, self._subverb)
        if self._subverb == _GIFT_SUBVERB:
            return {"gift_unlock_id": target_id}
        return {"offer_id": target_id}

    # -- status hub --------------------------------------------------------

    def _show_hub(self) -> None:
        """List open GiftUnlocks (XP cost + status) and open teaching offers."""
        lines = ["|wLearn actions|n: gift <id>, technique <id>, thread <id>"]

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        lines.extend(self._gift_unlock_lines(sheet))
        lines.extend(self._technique_offer_lines())
        lines.extend(self._thread_offer_lines())

        self.msg("\n".join(lines))

    def _gift_unlock_lines(self, sheet: Any) -> list[str]:
        """Lines for every authored GiftUnlock: XP cost + purchased/missing status."""
        from world.magic.models import CharacterGiftUnlock, GiftUnlock  # noqa: PLC0415
        from world.magic.services.gift_acquisition import (  # noqa: PLC0415
            compute_gift_unlock_xp_cost,
        )

        unlocks = list(GiftUnlock.objects.select_related("gift").order_by("gift__name"))
        if not unlocks:
            return ["", "No gift unlocks are authored."]

        purchased_ids: set[int] = set()
        if sheet is not None:
            purchased_ids = set(
                CharacterGiftUnlock.objects.filter(character=sheet).values_list(
                    "unlock_id", flat=True
                )
            )

        lines = ["", "Gift unlocks:"]
        for unlock in unlocks:
            if sheet is not None:
                cost = compute_gift_unlock_xp_cost(unlock, sheet)
                status = "purchased" if unlock.pk in purchased_ids else "not purchased"
            else:
                cost = unlock.xp_cost
                status = "not purchased"
            lines.append(f"  [gift {unlock.pk}] {unlock.gift.name}: {cost} XP ({status})")
        return lines

    def _technique_offer_lines(self) -> list[str]:
        """Lines for every open TechniqueTeachingOffer: pitch/cost/teacher."""
        from world.magic.models import TechniqueTeachingOffer  # noqa: PLC0415

        offers = list(
            TechniqueTeachingOffer.objects.select_related("technique", "teacher").order_by("-pk")
        )
        if not offers:
            return ["", "No open technique-teaching offers."]

        lines = ["", "Technique-teaching offers:"]
        lines.extend(
            f"  [technique {offer.pk}] {offer.technique.name} — "
            f"{offer.learn_ap_cost} AP, taught by {offer.teacher.display_name}: "
            f"{offer.pitch}"
            for offer in offers
        )
        return lines

    def _thread_offer_lines(self) -> list[str]:
        """Lines for every open ThreadWeavingTeachingOffer: pitch/cost/teacher."""
        from world.magic.models import ThreadWeavingTeachingOffer  # noqa: PLC0415

        offers = list(
            ThreadWeavingTeachingOffer.objects.select_related("unlock", "teacher").order_by("-pk")
        )
        if not offers:
            return ["", "No open thread-weaving teaching offers."]

        lines = ["", "Thread-weaving teaching offers:"]
        lines.extend(
            f"  [thread {offer.pk}] {offer.unlock} — "
            f"taught by {offer.teacher.display_name}: {offer.pitch}"
            for offer in offers
        )
        return lines

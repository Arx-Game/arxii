"""Offer handler for the GM summon consent gate (#3071).

Telnet ``accept summon`` / ``decline summon`` route here via
``commands/offer_registry.py``. Web reaches the same target-side actions
(``AcceptGMSummonAction``/``DeclineGMSummonAction``) through the generic
REGISTRY action-dispatch endpoint — this handler is the telnet face only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.gm.models import GMSummonOffer


class GMSummonPendingHandler:
    """Offer handler for a pending GM summon (#3071).

    A GM invites a player to their scene room via ``SummonPlayerAction``; this
    handler routes ``accept summon`` / ``decline summon`` to the target-side
    response actions (``actions/definitions/gm_summon_offers.py``).
    """

    keyword = "summon"
    label = "GM Summon"

    def pending_for(self, sheet: Any) -> GMSummonOffer | None:
        from world.gm.models import GMSummonOffer  # noqa: PLC0415

        return GMSummonOffer.objects.filter(target_sheet=sheet).select_related("scene").first()

    def describe(self, offer: GMSummonOffer) -> str:
        gm_name = offer.gm_display_name or "A GM"
        scene_title = offer.scene.name if offer.scene else "their scene"
        return f"{gm_name} has invited you to join {scene_title}."

    def accept(self, offer: GMSummonOffer, caller: Any, args: str) -> str:  # noqa: ARG002
        from actions.definitions.gm_summon_offers import AcceptGMSummonAction  # noqa: PLC0415

        result = AcceptGMSummonAction().run(actor=caller)
        return result.message

    def decline(self, offer: GMSummonOffer, caller: Any) -> str:  # noqa: ARG002
        from actions.definitions.gm_summon_offers import DeclineGMSummonAction  # noqa: PLC0415

        result = DeclineGMSummonAction().run(actor=caller)
        return result.message

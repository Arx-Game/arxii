"""Telnet ``accept makeover`` / ``decline makeover`` (#4187).

Rides the generic offer registry (``commands.offer_registry``), the same way the
precapture consent request does, so the existing ``accept`` / ``decline`` commands
reach a pending makeover ask with no new command. Registered from
``world.items.apps.ready``.
"""

from __future__ import annotations

from typing import Any

from world.items.exceptions import ItemError
from world.items.makeover_models import MakeoverConsentRequest
from world.items.services.makeover_requests import (
    describe_offer,
    pending_makeover_requests_for,
    respond_to_makeover_request,
)


class MakeoverOfferHandler:
    """Answer the oldest live makeover ask addressed to the caller's character."""

    keyword = "makeover"
    label = "makeover offer"

    def pending_for(self, sheet: Any) -> MakeoverConsentRequest | None:
        rows = pending_makeover_requests_for(sheet)
        # Newest first from the service; the oldest open ask is answered first.
        return rows[-1] if rows else None

    def describe(self, offer: MakeoverConsentRequest) -> str:
        return describe_offer(offer)

    def accept(self, offer: MakeoverConsentRequest, caller: Any, args: str) -> str:  # noqa: ARG002
        try:
            respond_to_makeover_request(offer, accept=True)
        except ItemError as exc:
            return exc.user_message
        # PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #4187)
        return f"You let {offer.stylist_persona.name} restyle you."

    def decline(self, offer: MakeoverConsentRequest, caller: Any) -> str:  # noqa: ARG002
        try:
            respond_to_makeover_request(offer, accept=False)
        except ItemError as exc:
            return exc.user_message
        # PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #4187)
        return "You decline."

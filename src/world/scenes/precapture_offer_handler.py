"""Telnet offer handler for pre-scene capture consent (#3069 sub-item 4).

Registers with ``commands.offer_registry`` (the same generic ``accept <keyword>`` /
``decline <keyword>`` routing ``SoulfrayPendingHandler``, ``CrossingOfferHandler``,
``OrgInviteHandler`` etc. already use) so telnet gets consent for free — no new
telnet command needed, just this handler plus the registration call in
``world/scenes/apps.py``.
"""

from __future__ import annotations

from typing import Any

from world.scenes.action_constants import ActionRequestStatus
from world.scenes.models import PrecaptureConsentRequest
from world.scenes.precapture_services import (
    precapture_candidates_for,
    respond_to_precapture_consent,
)


class PrecaptureConsentOfferHandler:
    """Handles `accept precapture` / `decline precapture` for pending capture asks."""

    keyword = "precapture"
    label = "pre-scene capture consent"

    def pending_for(self, sheet: Any) -> PrecaptureConsentRequest | None:
        """Return the oldest pending precapture consent request for the sheet's account."""
        character = sheet.character
        if character is None:
            return None
        account = character.active_account
        if account is None:
            return None
        return (
            PrecaptureConsentRequest.objects.filter(
                account=account, status=ActionRequestStatus.PENDING
            )
            .select_related("scene", "scene__location")
            .order_by("requested_at")
            .first()
        )

    def describe(self, offer: PrecaptureConsentRequest) -> str:
        count = precapture_candidates_for(offer).count()
        room = offer.scene.location.db_key if offer.scene.location is not None else "somewhere"
        plural = "s" if count != 1 else ""
        return (
            f"a scene at {room} would like to fold in {count} of your recent unattached "
            f"pose{plural} from before it started"
        )

    def accept(self, offer: PrecaptureConsentRequest, caller: Any, args: str) -> str:  # noqa: ARG002
        count = respond_to_precapture_consent(offer, accept=True)
        plural = "s" if count != 1 else ""
        return f"You allow {count} of your recent pose{plural} to be folded into that scene."

    def decline(self, offer: PrecaptureConsentRequest, caller: Any) -> str:  # noqa: ARG002
        respond_to_precapture_consent(offer, accept=False)
        return "You decline; your recent poses stay out of that scene."

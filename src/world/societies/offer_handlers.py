"""Offer handlers for the societies app (#1511)."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from world.scenes.services import active_persona_for_sheet
from world.societies.membership_services import (
    decline_invitation,
    join_organization,
)
from world.societies.models import OrganizationMembershipOffer


class OrgInviteHandler:
    """Handles `accept org` / `decline org` for pending invitations."""

    keyword = "org"
    label = "organization invitation"

    def pending_for(self, sheet: Any) -> OrganizationMembershipOffer | None:
        """Return the first pending invitation for the sheet's active persona."""
        try:
            persona = active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None

        return (
            OrganizationMembershipOffer.objects.filter(
                to_persona=persona,
                kind=OrganizationMembershipOffer.Kind.INVITE,
                status=OrganizationMembershipOffer.Status.PENDING,
            )
            .select_related("organization")
            .first()
        )

    def describe(self, offer: OrganizationMembershipOffer) -> str:
        """Human-readable line shown in `accept` / `decline` listings."""
        return f"invitation to join {offer.organization.name} from {offer.from_persona.name}"

    def accept(
        self,
        offer: OrganizationMembershipOffer,
        caller: Any,
        _args: str,
    ) -> str:
        """Accept the invitation by creating the membership directly."""
        sheet = caller.sheet_data if hasattr(caller, "sheet_data") else None
        if sheet is None:
            return "You need a character sheet for that."
        try:
            persona = active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return "You have no character identity."

        join_organization(offer.organization, persona)
        return f"You join {offer.organization.name}."

    def decline(
        self,
        offer: OrganizationMembershipOffer,
        caller: Any,
    ) -> str:
        """Decline the invitation."""
        sheet = caller.sheet_data if hasattr(caller, "sheet_data") else None
        if sheet is None:
            return "You need a character sheet for that."
        try:
            persona = active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return "You have no character identity."

        decline_invitation(offer, persona)
        return f"You decline the invitation to join {offer.organization.name}."

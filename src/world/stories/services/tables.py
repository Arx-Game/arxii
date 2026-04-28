"""Service functions for Story.primary_table assignment and GM offer lifecycle."""

from __future__ import annotations

import contextlib

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.gm.constants import GMTableStatus
from world.gm.models import GMProfile, GMTable
from world.stories.constants import StoryGMOfferStatus, StoryScope
from world.stories.exceptions import StoryGMOfferError
from world.stories.models import Story, StoryGMOffer

# Notification kind constants for _send_offer_notification — internal identifiers only.
_KIND_CREATED = "created"
_KIND_ACCEPTED = "accepted"
_KIND_DECLINED = "declined"


@transaction.atomic
def assign_story_to_table(*, story: Story, table: GMTable) -> Story:
    """Assign a story to a GM's table. Sets primary_table; clears any prior assignment.

    Service trusts pre-validated inputs — permission gating happens in the
    serializer/view layer per canonical pattern.
    """
    story.primary_table = table
    story.save(update_fields=["primary_table", "updated_at"])
    return story


@transaction.atomic
def detach_story_from_table(*, story: Story) -> Story:
    """Clear the primary_table; story enters 'seeking GM' state.

    Story history and participations are preserved. The story becomes orphaned
    (no active oversight) until a GM accepts it via the Wave 3 offer flow.
    """
    story.primary_table = None
    story.save(update_fields=["primary_table", "updated_at"])
    return story


# ---------------------------------------------------------------------------
# Wave 3 — StoryGMOffer lifecycle services
# ---------------------------------------------------------------------------


def offer_story_to_gm(
    *,
    story: Story,
    offered_to: GMProfile,
    offered_by_account: AccountDB,
    message: str = "",
) -> StoryGMOffer:
    """Player offers a personal CHARACTER-scope story to a specific GM.

    Pre-conditions (validated by caller; service performs defensive checks):
    - story.scope == CHARACTER
    - story.primary_table is None (must withdraw from current GM first)

    A DB-level partial unique constraint prevents duplicate PENDING offers
    for the same (story, GM) pair; IntegrityError will surface if violated.

    On success: creates StoryGMOffer with status=PENDING; sends a
    NarrativeMessage to the GM so they see the offer in their feed.
    """
    if story.scope != StoryScope.CHARACTER:
        msg = "Only CHARACTER-scope stories support GM offers."
        raise StoryGMOfferError(msg)
    if story.primary_table_id is not None:
        msg = "Withdraw from the current GM's table before offering this story to another GM."
        raise StoryGMOfferError(msg)

    with transaction.atomic():
        offer = StoryGMOffer.objects.create(
            story=story,
            offered_to=offered_to,
            offered_by_account=offered_by_account,
            message=message,
        )
        _send_offer_notification(offer, kind=_KIND_CREATED)
    return offer


def accept_story_offer(*, offer: StoryGMOffer, response_note: str = "") -> StoryGMOffer:
    """GM accepts the offer; story is assigned to the GM's first ACTIVE table.

    Raises StoryGMOfferError if the offer is not PENDING or the GM has no
    ACTIVE table to receive the story.
    """
    if offer.status != StoryGMOfferStatus.PENDING:
        msg = "Offer is no longer pending and cannot be accepted."
        raise StoryGMOfferError(msg)
    table = offer.offered_to.tables.filter(status=GMTableStatus.ACTIVE).first()
    if table is None:
        msg = "The receiving GM has no active table to assign the story to."
        raise StoryGMOfferError(msg)
    with transaction.atomic():
        offer.status = StoryGMOfferStatus.ACCEPTED
        offer.response_note = response_note
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "response_note", "responded_at", "updated_at"])
        offer.story.primary_table = table
        offer.story.save(update_fields=["primary_table", "updated_at"])
        _send_offer_notification(offer, kind=_KIND_ACCEPTED)
    return offer


def decline_story_offer(*, offer: StoryGMOffer, response_note: str = "") -> StoryGMOffer:
    """GM declines the offer; story stays detached (primary_table unchanged)."""
    if offer.status != StoryGMOfferStatus.PENDING:
        msg = "Offer is no longer pending and cannot be declined."
        raise StoryGMOfferError(msg)
    with transaction.atomic():
        offer.status = StoryGMOfferStatus.DECLINED
        offer.response_note = response_note
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "response_note", "responded_at", "updated_at"])
        _send_offer_notification(offer, kind=_KIND_DECLINED)
    return offer


def withdraw_story_offer(*, offer: StoryGMOffer) -> StoryGMOffer:
    """Player rescinds a pending offer."""
    if offer.status != StoryGMOfferStatus.PENDING:
        msg = "Offer is no longer pending and cannot be withdrawn."
        raise StoryGMOfferError(msg)
    with transaction.atomic():
        offer.status = StoryGMOfferStatus.WITHDRAWN
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at", "updated_at"])
    return offer


def _send_offer_notification(offer: StoryGMOffer, *, kind: str) -> None:
    """Send a NarrativeMessage about a StoryGMOffer state change.

    kind:
        "created"  — sent to the GM who received the offer (offer.offered_to)
        "accepted" — sent to the player who made the offer (story.character_sheet)
        "declined" — sent to the player who made the offer (story.character_sheet)

    Recipient CharacterSheet resolution:
        KIND_CREATED: walk GMProfile -> account -> primary character -> CharacterSheet via
        get_notification_target_for_gm(). If the GM has no resolvable CharacterSheet,
        the notification is skipped — the GM offer inbox query surfaces offers without push.
        KIND_ACCEPTED/DECLINED: use story.character_sheet (the player's character).

    If no character_sheet is resolvable the notification is skipped gracefully.
    """
    # Lazy import to avoid circular dependency at module load time.
    from world.gm.services import get_notification_target_for_gm  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    story = offer.story

    if kind == _KIND_CREATED:
        # Notify the GM being approached, not the player who offered.
        character_sheet = get_notification_target_for_gm(offer.offered_to)
        if character_sheet is None:
            # GM has no resolvable character sheet — skip notification gracefully.
            # The GM offer inbox query (Wave 5 frontend) surfaces the offer regardless.
            return
        body = (
            f"A player has offered you their story '{story.title}'. "
            f"Visit your GM offer inbox to accept or decline."
        )
        sender = offer.offered_by_account
    elif kind in (_KIND_ACCEPTED, _KIND_DECLINED):
        # Notify the player who made the offer (the story's character's account).
        character_sheet = story.character_sheet
        if character_sheet is None:
            # TODO(wave-7): fallback notification path when story.character_sheet is None
            return
        verb = "accepted" if kind == _KIND_ACCEPTED else "declined"
        body = f"Your story offer for '{story.title}' has been {verb} by the GM."
        sender = None
    else:
        return  # Unknown kind — ignore.

    with contextlib.suppress(Exception):  # notification is best-effort; don't block the offer
        send_narrative_message(
            recipients=[character_sheet],
            body=body,
            category=NarrativeCategory.SYSTEM,
            sender_account=sender,
            related_story=story,
        )

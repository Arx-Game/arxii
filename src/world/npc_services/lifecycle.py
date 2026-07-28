"""Ladder lifecycle — standing promotion, demotion, roster graduation (#2827 phase 5).

Tiers are layers on one identity (the sheet-spine); these services add and
retire layers, never delete the spine. A standing NPC is the persona's body
placed in the room; demotion melts them back into a background placement;
graduation moves the sheet's shelf entry onto a claimable roster with every
accumulated relationship, secret, and grudge intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Count, QuerySet

from world.npc_services.functionaries import place_functionary
from world.npc_services.models import Functionary

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.npc_services.models import NPCRole
    from world.scenes.models import Persona

# PLACEHOLDER calibration: attachments (active asset claims) before an NPC
# surfaces as a standing-tier candidate for staff review.
STANDING_CANDIDATE_MIN_ATTACHMENTS = 2


class LifecycleError(Exception):
    """A ladder transition could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@transaction.atomic
def promote_to_standing(persona: Persona, room: RoomProfile):
    """Give the persona a body in the room (tier 3 — ADR-0070 class 2).

    The background placement retires (the visible body supersedes the
    room-appearance line; the staffing refill may later hire a fresh
    nobody into the vacated slot — she runs the place now, someone else
    pours). Returns the placed character object.
    """
    character = persona.character_sheet.character
    if character is None:
        msg = "That persona has no body to place."
        raise LifecycleError(msg, user_message=msg)
    character.home = room.objectdb
    character.location = room.objectdb
    character.save()
    Functionary.objects.filter(persona=persona, is_active=True).update(is_active=False)
    return character


@transaction.atomic
def demote_to_instantiated(persona: Persona, *, role: NPCRole, room: RoomProfile) -> Functionary:
    """Retire the body; melt back into a background placement (tier 1).

    The identity keeps everything — this is layer retirement, not deletion.
    """
    character = persona.character_sheet.character
    if character is not None:
        character.location = None
        character.save()
    functionary = place_functionary(role=role, room=room, name_override=persona.name)
    functionary.persona = persona
    functionary.save(update_fields=["persona"])
    return functionary


def standing_candidates(
    *, min_attachments: int = STANDING_CANDIDATE_MIN_ATTACHMENTS
) -> QuerySet[Persona]:
    """NPC personas prominent enough for staff to consider giving a body.

    Earned prominence = active asset claims on the persona. A review
    queue, never automatic — promotion stays a staff/GM decision.
    """
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    return (
        Persona.objects.filter(
            functionary_placements__isnull=False,
            asset_ownerships__status=AssetStatus.ACTIVE,
        )
        .annotate(attachment_count=Count("asset_ownerships", distinct=True))
        .filter(attachment_count__gte=min_attachments)
        .distinct()
    )


@transaction.atomic
def graduate_to_roster(sheet, *, allow_applications_roster: bool = True):
    """The rostering door (tier 5): move the NPC's shelf entry to a claimable
    roster. History rides along — the persona IS the continuity.

    Staff-gated by the caller. Returns the RosterEntry.
    """
    from world.roster.models import Roster, RosterEntry  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    target, _ = Roster.objects.get_or_create(
        roster_type=RosterType.AVAILABLE,
        defaults={
            "name": "Available",
            "is_active": True,
            "is_public": True,
            "allow_applications": allow_applications_roster,
        },
    )
    entry = RosterEntry.objects.filter(character_sheet=sheet).first()
    if entry is None:
        return RosterEntry.objects.create(character_sheet=sheet, roster=target)
    entry.previous_roster = entry.roster
    entry.roster = target
    entry.save(update_fields=["previous_roster", "roster"])
    return entry

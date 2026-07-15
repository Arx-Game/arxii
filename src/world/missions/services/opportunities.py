"""Opportunities discovery service — the three-group query (#2044).

Groups:
  - here: BOARD givers in the character's current room — list their postings.
  - nearby: all givers (BOARD + trigger) in the character's current area.
    BOARD givers list postings; trigger givers show only a generic
    'something stirs here' flavor line (previewing their pool would
    spoil the draw + need side-effect surgery).
  - your organizations: MISSION offers on NPCRoles whose faction_affiliation
    is an org the character's persona belongs to, capped per org.

No accept-from-panel — discovery points you AT the world; acceptance stays
at the giver/board (the tab is the map, not the door).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from django.db.models import Q

from world.missions.constants import GiverKind
from world.missions.models import MissionGiver
from world.missions.services.boards import postings_for_giver
from world.missions.services.visibility import template_visible_to
from world.scenes.services import MissingPrimaryPersonaError, persona_for_character

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character


@dataclass(frozen=True, slots=True)
class OpportunityRow:
    """One discovery row — name, summary, pointer, source flavor."""

    name: str
    summary: str
    pointer: str
    source_flavor: str


@dataclass(frozen=True, slots=True)
class OpportunitiesResult:
    """The three discovery groups."""

    here: list[OpportunityRow] = field(default_factory=list)
    nearby: list[OpportunityRow] = field(default_factory=list)
    your_organizations: list[OpportunityRow] = field(default_factory=list)


def opportunities_for_character(character: ObjectDB) -> OpportunitiesResult:
    """Build the three-group opportunities view for ``character``.

    Viewer-scoped: every row is filtered through ``template_visible_to``
    for this character. No RESTRICTED templates are ever exposed.
    """
    room = character.location
    here_rows = _here_postings(character, room)
    nearby_rows = _nearby_givers(character, room)
    org_rows = _org_offers(character)
    return OpportunitiesResult(
        here=here_rows,
        nearby=nearby_rows,
        your_organizations=org_rows,
    )


def _here_postings(character: ObjectDB, room: ObjectDB | None) -> list[OpportunityRow]:
    """Boards in the current room — list their eligible postings.

    A BOARD giver's ``target`` is the examinable board object itself (an
    Object typeclass; ``clean()`` forbids Room), never the room — a board is
    physically located IN a room via ``target.db_location``, not equal to it
    (#2121; matches the ``target=obj`` lookup ``_maybe_render_board_postings``
    uses when a player examines the board directly).
    """
    if room is None:
        return []
    boards = MissionGiver.objects.filter(
        target__db_location=room, giver_kind=GiverKind.BOARD, is_active=True
    ).prefetch_related("templates")  # noqa: PREFETCH_STRING
    rows: list[OpportunityRow] = []
    for board in boards:
        rows.extend(
            OpportunityRow(
                name=posting.name,
                summary=posting.summary,
                pointer="Examine the board in this room; mission take by number.",
                source_flavor=f"Notice Board — {board.name}",
            )
            for posting in postings_for_giver(board, character)
        )
    return rows


def _nearby_givers(character: ObjectDB, room: ObjectDB | None) -> list[OpportunityRow]:
    """All givers in the current area.

    BOARD givers list postings (same as 'here' but may include boards in
    other rooms of the area). Trigger givers show only a generic flavor
    line — never their pool.
    """
    if room is None:
        return []
    from world.areas.services import get_room_profile  # noqa: PLC0415

    try:
        profile = get_room_profile(room)
    except Exception:  # noqa: BLE001 — room without a profile: no area
        return []
    if profile.area_id is None:
        return []
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    area_room_ids = set(
        RoomProfile.objects.filter(area_id=profile.area_id).values_list("objectdb_id", flat=True)
    )
    # BOARD givers' target is the board object, physically located IN a room
    # (target.db_location) — never the room itself. ROOM_TRIGGER givers' target
    # IS the room. Matches ``_here_postings``' fix (#2121).
    givers = MissionGiver.objects.filter(
        Q(giver_kind=GiverKind.BOARD, target__db_location_id__in=area_room_ids)
        | (~Q(giver_kind=GiverKind.BOARD) & Q(target_id__in=area_room_ids)),
        is_active=True,
    ).prefetch_related("templates")  # noqa: PREFETCH_STRING
    try:
        persona = persona_for_character(cast("Character", character))
    except MissingPrimaryPersonaError:
        persona = None

    rows: list[OpportunityRow] = []
    for giver in givers:
        if giver.giver_kind == GiverKind.BOARD:
            rows.extend(
                OpportunityRow(
                    name=posting.name,
                    summary=posting.summary,
                    pointer=f"At: {giver.target.db_key if giver.target else '?'}",
                    source_flavor=f"Notice Board — {giver.name}",
                )
                for posting in postings_for_giver(giver, character)
            )
        else:
            # Trigger giver — flavor only, never the pool
            has_eligible = any(
                t.is_active and template_visible_to(t, character, persona=persona)
                for t in giver.templates.all()
            )
            if has_eligible:
                rows.append(
                    OpportunityRow(
                        name="Something stirs here",
                        summary="",
                        pointer=f"At: {giver.target.db_key if giver.target else '?'}",
                        source_flavor=giver.name,
                    )
                )
    return rows


def _org_offers(character: ObjectDB) -> list[OpportunityRow]:
    """MISSION offers on NPCRoles whose org the character belongs to."""
    try:
        persona = persona_for_character(cast("Character", character))
    except MissingPrimaryPersonaError:
        return []
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import NPCServiceOffer  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    org_ids = set(
        OrganizationMembership.objects.filter(
            persona=persona, left_at__isnull=True, exiled_at__isnull=True
        ).values_list("organization_id", flat=True)
    )
    if not org_ids:
        return []
    offers = NPCServiceOffer.objects.filter(
        role__faction_affiliation_id__in=org_ids,
        kind=OfferKind.MISSION,
        is_active=True,
    ).select_related("role", "role__faction_affiliation")
    rows: list[OpportunityRow] = []
    for offer in offers:
        org_name = offer.role.faction_affiliation.name if offer.role.faction_affiliation else ""
        rows.append(
            OpportunityRow(
                name=offer.label,
                summary="",
                pointer=f"Seek out {offer.role.name}" + (f" ({org_name})" if org_name else ""),
                source_flavor="Your organization has work",
            )
        )
    return rows


__all__ = (
    "OpportunitiesResult",
    "OpportunityRow",
    "opportunities_for_character",
)

"""Per-audience reads of one side of a tie (#3957). Writes live in services.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.relationships.constants import KNOWN_AWARENESS, LabelAwareness, TieAudience
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipLabel,
)
from world.relationships.types import DepthBreakdown, TieStreamItem

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def tie_audience(
    side: CharacterRelationship, viewer_sheet: CharacterSheet | None, is_staff: bool
) -> str:
    if is_staff:
        return TieAudience.STAFF
    if viewer_sheet is None:
        return TieAudience.THIRD_PARTY
    if viewer_sheet.pk == side.source_id:
        return TieAudience.OWNER
    if side.target_id is not None and viewer_sheet.pk == side.target_id:
        return TieAudience.OTHER_SIDE
    return TieAudience.THIRD_PARTY


def third_party_can_see(side: CharacterRelationship) -> bool:
    """A tie with no Public unended label is absent for everyone but the two parties."""
    return side.labels.filter(ended_at__isnull=True, awareness=LabelAwareness.PUBLIC).exists()


def visible_labels(side: CharacterRelationship, audience: str) -> list[RelationshipLabel]:
    """Owner and staff: all (ended ones too, as former). Other side: known. Third party: public."""
    qs = side.labels.select_related("type", "type__counterpart").order_by("since")
    if audience in (TieAudience.OWNER, TieAudience.STAFF):
        return list(qs)
    if audience == TieAudience.OTHER_SIDE:
        return list(qs.filter(awareness__in=KNOWN_AWARENESS))
    return list(qs.filter(awareness=LabelAwareness.PUBLIC))


def depth_breakdown(side: CharacterRelationship, audience: str) -> DepthBreakdown | None:
    if audience == TieAudience.THIRD_PARTY:
        return None
    other = side.reverse
    owner_or_staff = audience in (TieAudience.OWNER, TieAudience.STAFF)
    return DepthBreakdown(
        tier=side.tier,
        scenes=side.scene_depth,
        invested=side.invested_depth,
        their_added_depth=other.depth if other is not None else 0,
        affection=side.affection if owner_or_staff else None,
        conflict=side.conflict if owner_or_staff else None,
    )


def tie_stream(
    side: CharacterRelationship, viewer_sheet: CharacterSheet | None, is_staff: bool
) -> list[TieStreamItem]:
    """Entries by either side about the other (visibility-filtered) + scenes both posed in."""
    from world.journals.models import JournalEntry  # noqa: PLC0415
    from world.journals.services import visible_entries_q  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    if side.target_id is None:
        return []
    a, b = side.source_id, side.target_id
    entries = (
        JournalEntry.objects.filter(visible_entries_q(viewer_sheet=viewer_sheet, is_staff=is_staff))
        .filter(Q(author_id=a, about_id=b) | Q(author_id=b, about_id=a), parent__isnull=True)
        .select_related("author__character")
        .order_by("-created_at")
    )
    capstone_by_entry = {
        c.journal_entry_id: c.tier_claimed
        for c in RelationshipCapstone.objects.filter(
            journal_entry__in=entries, relationship__source_id__in=(a, b)
        )
    }
    items: list[TieStreamItem] = [
        TieStreamItem(
            kind="entry",
            id=e.pk,
            title=e.title,
            author_id=e.author_id,
            author_name=e.author.character.db_key,
            body=e.body,
            is_public=e.is_public,
            capstone_tier=capstone_by_entry.get(e.pk),
            created_at=e.created_at.isoformat(),
            ic_timestamp=e.ic_timestamp.isoformat() if e.ic_timestamp else None,
        )
        for e in entries
    ]
    scenes = (
        Scene.objects.filter(interactions__persona__character_sheet_id=a)
        .filter(interactions__persona__character_sheet_id=b)
        .distinct()
        .order_by("-date_started")
    )
    items.extend(
        TieStreamItem(
            kind="scene",
            id=s.pk,
            title=s.name,
            author_id=None,
            author_name="",
            body="",
            is_public=True,
            capstone_tier=None,
            created_at=s.date_started.isoformat(),
            ic_timestamp=None,
        )
        for s in scenes
    )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items

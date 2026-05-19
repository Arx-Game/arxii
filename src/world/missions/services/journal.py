"""Journal read service (Phase 5a) — ``journal_for(character)``.

Returns a tuple of :class:`~world.missions.types.JournalEntry` rows,
one per :class:`MissionParticipant` the character owns. The entry shape
is deliberately a frozen dataclass (NOT a dict per CLAUDE.md) so callers
get explicit types when walking the journal.

The query intentionally does not prefetch ``MissionDeedRecord`` —
``SharedMemoryModel`` + the ``Prefetch(to_attr=...)`` rule mean any
per-request data pinned onto identity-mapped rows would leak across
requests. Deeds are read fresh per call (small N — one journal row per
participated mission, deeds bounded by node count).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.models import MissionDeedRecord, MissionParticipant
from world.missions.types import JournalDeed, JournalEntry

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _deeds_for(instance_id: int, character: ObjectDB) -> tuple[JournalDeed, ...]:
    """Per-instance deed slice for ``character`` as ordered ``JournalDeed`` rows.

    Filtering by ``actor=character`` keeps the journal honest: a sharee
    sees only their own deeds, not the holder's. ``applied_at`` is the
    deterministic order — deeds are written in resolve order.
    """
    deed_rows = (
        MissionDeedRecord.objects.filter(instance_id=instance_id, actor=character)
        .select_related("node", "outcome")
        .order_by("applied_at", "pk")
    )
    return tuple(
        JournalDeed(
            node_key=row.node.key,
            option_id=row.option_id,
            outcome_name=row.outcome.name if row.outcome_id else None,
            applied_at=row.applied_at,
        )
        for row in deed_rows
    )


def journal_for(character: ObjectDB) -> list[JournalEntry]:
    """Return one :class:`JournalEntry` per mission this character is in.

    Deterministically ordered by ``instance_id`` ascending (stable across
    runs, easy to diff in tests). Each entry carries the participant's own
    deeds — design §10 "moral/narrative consequence follows the actor".
    """
    participations = (
        MissionParticipant.objects.filter(character=character)
        .select_related(
            "instance",
            "instance__template",
            "instance__current_node",
        )
        .order_by("instance_id", "pk")
    )
    entries: list[JournalEntry] = []
    for part in participations:
        instance = part.instance
        current = instance.current_node
        entries.append(
            JournalEntry(
                instance_id=instance.pk,
                template_name=instance.template.name,
                status=instance.status,
                current_node_key=current.key if current is not None else None,
                is_contract_holder=part.is_contract_holder,
                deeds=_deeds_for(instance.pk, character),
            )
        )
    return entries

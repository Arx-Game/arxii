"""Journal read service (Phase 5a) — ``journal_for(character)``.

Returns a list of :class:`~world.missions.types.JournalEntry` rows, one
per :class:`MissionParticipant` the character owns. The entry shape is a
frozen dataclass (NOT a dict per CLAUDE.md) so callers get explicit types
when walking the journal.

Query discipline (CLAUDE.md "No Queries in Loops"): this function issues
exactly two queries regardless of how many missions the character has
joined — one for the participation rows (with related instance / template
/ current_node selected), one for *all* deeds across those instances
filtered to ``actor=character``. Deeds are then grouped in Python keyed
by ``instance_id`` and stitched onto the journal entries.

We deliberately do NOT prefetch deeds onto the participation/instance
rows via ``Prefetch(to_attr=...)``: ``MissionInstance`` and
``MissionParticipant`` are ``SharedMemoryModel`` rows held in the
identity map, and attaching a per-request, per-actor deed slice as an
attribute on them would leak across requests (see
``feedback_prefetch_to_attr_leaks`` in project memory). A bare Python
dict scoped to this call has no such leak and avoids the N+1.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from world.missions.models import MissionDeedRecord, MissionParticipant
from world.missions.types import JournalDeed, JournalEntry

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def journal_for(character: ObjectDB) -> list[JournalEntry]:
    """Return one :class:`JournalEntry` per mission this character is in.

    Deterministically ordered by ``instance_id`` ascending (stable across
    runs, easy to diff in tests). Each entry carries the participant's own
    deeds — design §10 "moral/narrative consequence follows the actor".

    Issues exactly two queries (participations + deeds) regardless of N.
    """
    participations = list(
        MissionParticipant.objects.filter(character=character)
        .select_related(
            "instance",
            "instance__template",
            "instance__current_node",
        )
        .order_by("instance_id", "pk")
    )
    if not participations:
        return []

    instance_ids = [p.instance_id for p in participations]
    deed_rows = list(
        MissionDeedRecord.objects.filter(
            instance_id__in=instance_ids,
            actor=character,
        )
        .select_related("node", "outcome")
        .order_by("instance_id", "applied_at", "pk")
    )

    deeds_by_instance: dict[int, list[JournalDeed]] = defaultdict(list)
    for row in deed_rows:
        deeds_by_instance[row.instance_id].append(
            JournalDeed(
                node_key=row.node.key,
                option_id=row.option_id,
                outcome_name=row.outcome.name if row.outcome_id else None,
                applied_at=row.applied_at,
            )
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
                deeds=tuple(deeds_by_instance.get(instance.pk, ())),
            )
        )
    return entries

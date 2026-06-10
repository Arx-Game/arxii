"""Journal read service (Phase 5a + #885 compass) — ``journal_for(character)``.

Returns a list of :class:`~world.missions.types.JournalEntry` rows, one
per :class:`MissionParticipant` the character owns. The entry shape is a
frozen dataclass (NOT a dict per CLAUDE.md) so callers get explicit types
when walking the journal.

Query discipline (CLAUDE.md "No Queries in Loops"): this function issues
a CONSTANT number of queries regardless of how many missions the character
has joined — participations (with related instance / template /
current_node / anchor room selected), all deeds across those instances
filtered to ``actor=character``, plus three bulk prefetches for the #885
compass (current nodes' authored locations, their options, and the
options' override locations). Everything is then stitched in Python keyed
by ``instance_id`` / ``node_id``.

We deliberately do NOT prefetch deeds onto the participation/instance
rows via ``Prefetch(to_attr=...)``: ``MissionInstance`` and
``MissionParticipant`` are ``SharedMemoryModel`` rows held in the
identity map, and attaching a per-request, per-actor deed slice as an
attribute on them would leak across requests (see
``feedback_prefetch_to_attr_leaks`` in project memory). A bare Python
dict scoped to this call has no such leak and avoids the N+1.

Compass disclosure rule (#885, see :class:`JournalEntry`): node-level
locations are always shown; a per-option override room is shown only when
the option is UNGATED (empty visibility rule). Computed over prefetched
data — never a per-option predicate evaluation here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from world.missions.constants import MissionStatus, NodeLocationMode
from world.missions.models import MissionDeedRecord, MissionOption, MissionParticipant
from world.missions.types import JournalDeed, JournalEntry

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionInstance, MissionNode


def journal_for(character: ObjectDB) -> list[JournalEntry]:
    """Return one :class:`JournalEntry` per mission this character is in.

    Deterministically ordered by ``instance_id`` ascending (stable across
    runs, easy to diff in tests). Each entry carries the participant's own
    deeds — design §10 "moral/narrative consequence follows the actor" —
    plus the #885 compass fields (where the current beat can happen).

    Issues a constant number of queries regardless of N (see module
    docstring).
    """
    participations = list(
        MissionParticipant.objects.filter(character=character)
        .select_related(
            "instance",
            "instance__template",
            "instance__current_node",
            "instance__anchor_room__objectdb",
        )
        .prefetch_related("instance__current_node__locations__objectdb")  # noqa: PREFETCH_STRING
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

    # Bulk-fetch current nodes' options (+ override locations) for the
    # compass — one pass for every active entry, no per-entry queries.
    current_node_ids = [
        p.instance.current_node_id for p in participations if p.instance.current_node_id
    ]
    options_by_node: dict[int, list[MissionOption]] = defaultdict(list)
    if current_node_ids:
        option_rows = MissionOption.objects.filter(node_id__in=current_node_ids).prefetch_related(
            "locations__objectdb"  # noqa: PREFETCH_STRING
        )
        for option in option_rows:
            options_by_node[option.node_id].append(option)

    entries: list[JournalEntry] = []
    for part in participations:
        instance = part.instance
        current = instance.current_node
        compass_rooms, compass_anywhere = _compass_for(
            instance, current, options_by_node.get(current.pk, []) if current else []
        )
        entries.append(
            JournalEntry(
                instance_id=instance.pk,
                template_name=instance.template.name,
                status=instance.status,
                current_node_key=current.key if current is not None else None,
                is_contract_holder=part.is_contract_holder,
                deeds=tuple(deeds_by_instance.get(instance.pk, ())),
                summary=instance.template.summary,
                epilogue=(
                    instance.template.epilogue if instance.status == MissionStatus.COMPLETE else ""
                ),
                current_node_flavor=current.flavor_text if current is not None else "",
                compass_rooms=compass_rooms,
                compass_anywhere=compass_anywhere,
            )
        )
    return entries


def _node_default_compass(instance: MissionInstance, node: MissionNode) -> tuple[list[str], bool]:
    """Room names + anywhere-flag for a node's own location default."""
    if node.location_mode == NodeLocationMode.ANYWHERE:
        return [], True
    if node.location_mode == NodeLocationMode.ANCHOR:
        if instance.anchor_room_id is not None:
            return [instance.anchor_room.objectdb.db_key], False
        return [], False
    # NodeLocationMode.ROOMS
    return [room.objectdb.db_key for room in node.locations.all()], False


def _compass_for(
    instance: MissionInstance,
    node: MissionNode | None,
    options: list[MissionOption],
) -> tuple[tuple[str, ...], bool]:
    """Resolve the publicly-knowable places for ``instance``'s current beat.

    Mirrors the location-conjunct resolution in
    ``resolution.option_is_locally_live`` but collects room display names
    instead of testing membership, and applies the disclosure rule: an
    option's override rooms appear only when the option is ungated (empty
    ``visibility_rule``). Pure Python over prefetched rows.
    """
    if node is None:
        return (), False

    names: list[str] = []
    anywhere = False
    inherits_node_default = not options

    for option in options:
        override = list(option.locations.all())
        if not override:
            inherits_node_default = True
        elif not option.visibility_rule:  # ungated → publicly knowable
            names.extend(room.objectdb.db_key for room in override)
        # gated override rooms are never leaked by the journal

    if inherits_node_default:
        default_names, anywhere = _node_default_compass(instance, node)
        names.extend(default_names)

    deduped = tuple(dict.fromkeys(names))
    return deduped, anywhere

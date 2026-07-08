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

from django.db.models import Count

from world.missions.constants import MissionStatus, NodeLocationMode
from world.missions.models import MissionDeedRecord, MissionOption, MissionParticipant
from world.missions.types import JournalDeed, JournalEntry, JournalInvite, JournalSummons

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
    deeds_by_instance = _deeds_by_instance(instance_ids, character)
    options_by_node = _options_by_node(participations)
    pending_invites = _pending_invites_for(character)
    pending_summons = _pending_summons_for(character)
    participant_counts = _participant_counts(instance_ids)

    return [
        _journal_entry_for(
            part,
            deeds_by_instance,
            options_by_node,
            pending_invites,
            pending_summons,
            participant_counts,
        )
        for part in participations
    ]


def _pending_invites_for(character: ObjectDB) -> tuple[JournalInvite, ...]:
    """PENDING MissionInvites addressed to this character's primary persona (#2049).

    One query for the whole journal (not per-entry); threaded into every entry
    since invites are persona-scoped, not instance-scoped. Mirrors the telnet
    ``_append_pending_invites`` query (commands/missions.py:117).
    """
    from world.missions.models import MissionInvite  # noqa: PLC0415

    persona = getattr(character.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
    if persona is None:
        return ()
    rows = (
        MissionInvite.objects.filter(
            target_persona=persona, response=MissionInvite.Response.PENDING
        )
        .select_related("instance__template")
        .order_by("invited_at")
    )
    return tuple(
        JournalInvite(
            invite_id=row.pk, instance_id=row.instance_id, template_name=row.instance.template.name
        )
        for row in rows
    )


def _pending_summons_for(character: ObjectDB) -> tuple[JournalSummons, ...]:
    """PENDING OfferSummons directed at this character's primary persona (#2050).

    One query for the whole journal (not per-entry); threaded into every entry
    since summonses are persona-scoped, not instance-scoped. Mirrors the telnet
    ``_append_pending_summonses`` query (commands/missions.py).
    """
    from world.npc_services.constants import SummonsStatus  # noqa: PLC0415
    from world.npc_services.models import OfferSummons  # noqa: PLC0415

    persona = getattr(character.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
    if persona is None:
        return ()
    rows = (
        OfferSummons.objects.filter(target_persona=persona, status=SummonsStatus.PENDING)
        .select_related("offer__role")
        .order_by("created_at")
    )
    return tuple(
        JournalSummons(
            summons_id=row.pk,
            role_name=row.offer.role.name,
            message=row.message,
            expires_at=row.expires_at.isoformat() if row.expires_at else None,
        )
        for row in rows
    )


def _participant_counts(instance_ids: list[int]) -> dict[int, int]:
    """Bulk count participants per instance (one query for the whole journal, #2049).

    Drives the frontend's solo-vs-group card routing — mirrors the telnet
    ``_is_group_beat`` check (participants.count() > 1).
    """
    if not instance_ids:
        return {}
    rows = (
        MissionParticipant.objects.filter(instance_id__in=instance_ids)
        .values("instance_id")
        .annotate(count=Count("pk"))
    )
    return {row["instance_id"]: row["count"] for row in rows}


def _deeds_by_instance(
    instance_ids: list[int],
    character: ObjectDB,
) -> dict[int, list[JournalDeed]]:
    """Bucket the character's own deeds across *instance_ids* by instance id."""
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
    return deeds_by_instance


def _options_by_node(
    participations: list[MissionParticipant],
) -> dict[int, list[MissionOption]]:
    """Bulk-fetch current nodes' options (+ override locations) for the compass.

    One pass for every active entry, no per-entry queries.
    """
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
    return options_by_node


def _journal_entry_for(  # noqa: PLR0913
    part: MissionParticipant,
    deeds_by_instance: dict[int, list[JournalDeed]],
    options_by_node: dict[int, list[MissionOption]],
    pending_invites: tuple[JournalInvite, ...],
    pending_summons: tuple[JournalSummons, ...],
    participant_counts: dict[int, int],
) -> JournalEntry:
    """Build a single :class:`JournalEntry` from a participation row."""
    instance = part.instance
    current = instance.current_node
    compass_rooms, compass_anywhere = _compass_for(
        instance, current, options_by_node.get(current.pk, []) if current else []
    )
    return JournalEntry(
        instance_id=instance.pk,
        template_name=instance.template.name,
        status=instance.status,
        current_node_key=current.key if current is not None else None,
        is_contract_holder=part.is_contract_holder,
        deeds=tuple(deeds_by_instance.get(instance.pk, ())),
        summary=instance.template.summary,
        epilogue=(instance.template.epilogue if instance.status == MissionStatus.COMPLETE else ""),
        current_node_flavor=current.flavor_text if current is not None else "",
        compass_rooms=compass_rooms,
        compass_anywhere=compass_anywhere,
        pending_invites=pending_invites,
        pending_summons=pending_summons,
        participant_count=participant_counts.get(instance.pk, 1),
    )


def _node_default_compass(instance: MissionInstance, node: MissionNode) -> tuple[list[str], bool]:
    """Room names + anywhere-flag for a node's own location default."""
    if node.location_mode == NodeLocationMode.ANYWHERE:
        return [], True
    if node.location_mode == NodeLocationMode.INSTANCE:
        if instance.spawned_room_id is not None:
            return [instance.spawned_room.objectdb.db_key], False
        return [], False
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

"""Derive/install/resync the Trigger graph that delivers ambient entry lines.

Ambient entry lines never deliver from a live query: room entry fires
pre-derived Triggers whose ``TriggerDefinition`` carries a line group's
compiled condition filter and whose Flow step freezes the group's
``line_ids`` (#2471 v2 — see ``ambient_content.deliver_ambient_group``).
Historically that graph was derived only by ``core_management.grid_import``,
which made the world-builder canvas's ambient authoring verbs inert: a
canvas-added line's pk was in no frozen group, and a condition add/remove
left the line gated by its OLD compiled filter — with the only recompile
path a full re-import, forbidden against a populated database (ADR-0238).

``ensure_ambient_group_trigger``/``ensure_ambient_trigger`` moved here from
``grid_import`` (#3477 fix round 2) so one implementation serves both the
import and ``resync_room_ambient_triggers`` — the canvas actions' post-write
call that re-derives one room's ambient graph in place. Group/definition
names are deterministic from ``(scope, scope_key, filter digest)``, so a
resync of unchanged content lands on the import's own rows; only genuinely
changed groups mint new definitions, and stale Trigger rows on the room are
removed (the definitions themselves follow the import's report-never-delete
deferral and are left orphaned, not deleted).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area

AMBIENT_TRIGGER_PREFIX = "moved_ambient_"
SCOPE_ROOM = "room"
SCOPE_AREA = "area"


def room_scope_key(profile: RoomProfile) -> str:
    """The room's stable trigger-name key: its fixture key, or a pk fallback.

    A canvas-dug STORY/PLAYER room has no fixture key yet; ``pk<objectdb_id>``
    keeps its derived names unique and stable. A later promotion changes the
    scope key, minting fresh definitions — the old ones go stale and their
    Trigger rows are swept by the next resync, same as any changed group.
    """
    return profile.fixture_key or f"pk{profile.objectdb_id}"


def area_scope_key(area: Area) -> str:
    """The area's stable trigger-name key: its slug (the import's key), or a pk fallback."""
    return area.slug or f"pk{area.pk}"


def ensure_ambient_trigger(room_objectdb: ObjectDB, trigger_def: object) -> None:
    """Idempotently install one derived TriggerDefinition on one room (#2471 v2).

    The definition's compiled filter is copied onto the new Trigger row's
    additional_filter_condition — required because flows.emit._trigger_should_fire
    (the live MOVED-dispatch path) only ever consults
    Trigger.additional_filter_condition, never TriggerDefinition
    .base_filter_condition. duel_wiring's trigger always has an empty
    base_filter_condition (unconditional per-room fire) so it never needed this
    copy; the ambient case's compiled SPECIES/RESONANCE/etc filter does. Mirrors
    the same copy-on-install step in
    world.conditions.services._install_reactive_side_effects.
    """
    from flows.models import Trigger  # noqa: PLC0415

    trigger, created = Trigger.objects.get_or_create(
        obj=room_objectdb,
        trigger_definition=trigger_def,
        defaults={"additional_filter_condition": trigger_def.base_filter_condition},
    )
    if created:
        handler = room_objectdb.trigger_handler
        if handler is not None:
            handler.on_trigger_added(trigger)


def ensure_ambient_group_trigger(
    scope: str,
    scope_key: str,
    compiled_filter: dict | None,
    line_ids: list[int],
    reports: list[str],
) -> object:
    """Idempotently create (or refresh) the derived TriggerDefinition for one condition
    group (#2471 v2). Name is deterministic from (scope, scope_key, filter digest), so
    re-imports of unchanged content resolve to the same row (get_or_create by name);
    changed content (new lines added to the same condition, or a changed filter under an
    unlikely digest collision) refreshes the existing row's filter/parameters in place.
    A condition group whose compiled filter actually changes gets a new digest, so a new
    FlowDefinition/TriggerDefinition row-set is created rather than migrating the old
    one in place; the old (now-orphaned) rows are never deleted or deactivated — same
    report-never-delete deferral as grid_import's other sidecar types, not a bug.

    ``TriggerDefinition`` carries ``CreditedContent`` (#3017): a row whose
    ``written_by`` a staff admin has set is never overwritten here even when its
    ``base_filter_condition`` would otherwise be refreshed (the digest-collision
    branch above) - the row is left untouched and the conflict is appended to
    ``reports``, same freeze the fixture loader and the weather seed apply
    to their own credited rows. ``FlowDefinition`` (also ``CreditedContent``) is
    only ever created-or-fetched-unchanged in this function (``get_or_create``
    with no field updates on the existing-row path), so it needs no guard.
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.consts import FlowActionChoices  # noqa: PLC0415
    from flows.factories import FlowStepDefinitionFactory  # noqa: PLC0415
    from flows.models import FlowDefinition  # noqa: PLC0415
    from flows.models.triggers import TriggerDefinition  # noqa: PLC0415

    digest = hashlib.sha1(  # noqa: S324 (content-addressing, not security)
        json.dumps(compiled_filter, sort_keys=True).encode()
    ).hexdigest()[:12]
    name = f"{AMBIENT_TRIGGER_PREFIX}{scope}_{scope_key}_{digest}"

    flow, _ = FlowDefinition.objects.get_or_create(name=name)
    step_parameters = {"payload": "@payload", "line_ids": sorted(line_ids)}
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.narrative.ambient_content.deliver_ambient_group",
            parameters=step_parameters,
        )
    else:
        step = flow.steps.first()
        if step.parameters != step_parameters:
            step.parameters = step_parameters
            step.save(update_fields=["parameters"])

    trigger_def, created = TriggerDefinition.objects.get_or_create(
        name=name,
        defaults={
            "event_name": EventName.MOVED,
            "flow_definition": flow,
            "base_filter_condition": compiled_filter,
        },
    )
    if not created and trigger_def.base_filter_condition != compiled_filter:
        if trigger_def.written_by_id is not None:
            reports.append(
                f"TriggerDefinition [{trigger_def.name}] is credited (written_by is set) "
                "and differs from the grid pipeline's value. Row left untouched (#3017)."
            )
        else:
            trigger_def.base_filter_condition = compiled_filter
            trigger_def.save(update_fields=["base_filter_condition"])
    return trigger_def


def _grouped_line_ids(lines: list) -> dict[str, tuple[dict | None, list[int]]]:
    """Group lines by compiled-filter JSON: ``{json: (compiled, [line pks])}``."""
    from world.narrative.ambient_content import compile_line_filter  # noqa: PLC0415

    groups: dict[str, tuple[dict | None, list[int]]] = {}
    for line in lines:
        compiled = compile_line_filter(line)
        key = json.dumps(compiled, sort_keys=True)
        if key not in groups:
            groups[key] = (compiled, [])
        groups[key][1].append(line.pk)
    return groups


def resync_room_ambient_triggers(
    profile: RoomProfile, reports: list[str] | None = None
) -> list[str]:
    """Re-derive one room's ambient Trigger graph after a canvas mutation (#3477).

    Recomputes the room's own room-scoped condition groups AND which of its
    area's area-scoped groups the room should carry (the import's per-group
    most-specific-wins rule: an area group is suppressed on a room whose own
    groups include an identical compiled filter), ensures a Trigger per
    desired group, and deletes stale ambient Triggers on the room (notifying
    the trigger handler). Called by the staff ambient authoring actions after
    every successful line/condition write — without it their rows are frozen
    out of delivery until a re-import that ADR-0238 forbids on a populated
    database. Runs one ensure per group; authoring-time cost, not a hot path.
    """
    from flows.models import Trigger  # noqa: PLC0415
    from world.locations.constants import LocationParentType  # noqa: PLC0415
    from world.narrative.models import AmbientEmoteLine  # noqa: PLC0415

    if reports is None:
        reports = []

    room_lines = list(
        AmbientEmoteLine.objects.filter(
            parent_type=LocationParentType.ROOM, room_profile=profile, is_active=True
        )
    )
    room_groups = _grouped_line_ids(room_lines)
    desired_def_pks: list[int] = []
    for compiled, line_ids in room_groups.values():
        trigger_def = ensure_ambient_group_trigger(
            SCOPE_ROOM, room_scope_key(profile), compiled, line_ids, reports
        )
        ensure_ambient_trigger(profile.objectdb, trigger_def)
        desired_def_pks.append(trigger_def.pk)

    if profile.area_id:
        area_lines = list(
            AmbientEmoteLine.objects.filter(
                parent_type=LocationParentType.AREA, area_id=profile.area_id, is_active=True
            ).select_related("area")
        )
        for key, (compiled, line_ids) in _grouped_line_ids(area_lines).items():
            if key in room_groups:
                continue
            trigger_def = ensure_ambient_group_trigger(
                SCOPE_AREA, area_scope_key(profile.area), compiled, line_ids, reports
            )
            ensure_ambient_trigger(profile.objectdb, trigger_def)
            desired_def_pks.append(trigger_def.pk)

    stale = Trigger.objects.filter(
        obj=profile.objectdb,
        trigger_definition__name__startswith=AMBIENT_TRIGGER_PREFIX,
    ).exclude(trigger_definition_id__in=desired_def_pks)
    handler = profile.objectdb.trigger_handler
    for trigger in stale:
        trigger_pk = trigger.pk
        trigger.delete()
        if handler is not None:
            handler.on_trigger_removed(trigger_pk)
    return reports


def resync_area_ambient_triggers(area: Area, reports: list[str] | None = None) -> list[str]:
    """Re-derive every room in an area after an AREA-scoped ambient mutation (#3477).

    Bounded by the area's own room count and only runs on an authoring write
    against an area-scoped line — never on room entry or any other hot path.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if reports is None:
        reports = []
    for profile in RoomProfile.objects.filter(area=area).select_related("area", "objectdb"):
        resync_room_ambient_triggers(profile, reports)
    return reports

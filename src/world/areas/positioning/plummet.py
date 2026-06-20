"""FELL consumer — begin a plummet when an entity enters a CHASM (#1228).

#1018 opened the seam: ``maybe_emit_fall`` emits ``EventName.FELL``
(``FallEvent(faller, position)``) when an entity enters a CHASM position. This
module is the consumer.

A room-owned system trigger (the escalation pattern, ``source_condition=None``)
dispatches the FELL event to ``begin_plummet_handler`` via a CALL_SERVICE_FUNCTION
flow step. ``begin_plummet`` then:

1. starts (or extends) an AFK-safe DANGER ``SceneRound`` with the faller and any
   other present characters enrolled (``auto_start_or_extend_danger_round``);
2. applies the seeded "Plummeting" :class:`ConditionTemplate` to the faller; and
3. instantiates the seeded "Catch the Faller" :class:`ChallengeInstance` bound to
   the faller via ``target_object`` (so Task 7's catch action can find "the catch
   challenge for this faller").

``begin_plummet`` is idempotent: it no-ops when the faller already carries the
Plummeting condition, so a re-entry / re-emit never doubles the round, the
condition, or the catch challenge.

Task 6 makes the plummet descend each round; Task 7 resolves the catch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from world.areas.positioning.constants import (
    CATCH_THE_FALLER_NAME,
    FALL_DAMAGE_TYPE_NAME,
    PLUMMETING_CONDITION_NAME,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.conditions.models import ConditionInstance


def _faller_is_plummeting(faller: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """True if *faller* already carries an active Plummeting condition."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return False
    return get_active_conditions(faller, condition=template).exists()


def _create_catch_challenge_for(faller: ObjectDB, position: Position) -> None:  # noqa: OBJECTDB_PARAM
    """Instantiate the seeded "Catch the Faller" challenge bound to *faller*.

    The instance binds to the faller through ``target_object`` (the object
    embodying the challenge in the world) so Task 7's catch action can locate
    "the catch challenge for this faller". Idempotent: skips if an active catch
    instance already targets the faller.
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    template = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
    location = faller.location or position.room
    ChallengeInstance.objects.get_or_create(
        template=template,
        target_object=faller,
        is_active=True,
        defaults={"location": location, "is_revealed": True},
    )


def begin_plummet(faller: ObjectDB, position: Position) -> None:  # noqa: OBJECTDB_PARAM
    """Begin a plummet for *faller* who has entered CHASM *position*.

    Starts an AFK-safe DANGER scene round (enrolling present characters), applies
    the seeded Plummeting condition, and instantiates the catch challenge bound to
    the faller. Idempotent — no-op if the faller is already plummeting.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.scenes.round_services import (  # noqa: PLC0415
        auto_start_or_extend_danger_round,
    )

    if _faller_is_plummeting(faller):
        return

    sheet = faller.sheet_data
    auto_start_or_extend_danger_round(sheet)
    apply_condition(faller, ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME))
    _create_catch_challenge_for(faller, position)


def begin_plummet_handler(*, payload: object) -> None:
    """Flow-callable subscriber for ``EventName.FELL``.

    The seeded ``fall_to_plummet`` TriggerDefinition dispatches here via a
    CALL_SERVICE_FUNCTION step with the live :class:`FallEvent` payload. Reads
    ``payload.faller`` / ``payload.position`` and begins the plummet.
    """
    begin_plummet(payload.faller, payload.position)


def _plummeting_instance(target: ObjectDB) -> ConditionInstance | None:  # noqa: OBJECTDB_PARAM
    """Return *target*'s active Plummeting :class:`ConditionInstance`, or None."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_condition_instance  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return None
    return get_condition_instance(target, template)


def _apply_fall_impact(target: ObjectDB, instance: ConditionInstance) -> None:  # noqa: OBJECTDB_PARAM
    """Apply depth-scaled fall damage through the survivability pipeline, then end.

    Damage scales with the Plummeting instance's accumulated ``severity`` (one per
    level descended) times the configured ``FALL_IMPACT_PER_LEVEL`` magnitude, and
    routes through ``process_damage_consequences`` (wound/death/knockout pools;
    null pools on the fall type fall back to the configured default). Removes the
    Plummeting condition and clears the catch challenge afterwards.
    """
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
    damage = instance.severity * settings.FALL_IMPACT_PER_LEVEL
    fall_type = DamageType.objects.filter(name=FALL_DAMAGE_TYPE_NAME).first()
    process_damage_consequences(sheet, damage, fall_type)
    end_plummet(target, caught=False)


def end_plummet(faller: ObjectDB, *, caught: bool = False) -> None:  # noqa: ARG001, OBJECTDB_PARAM
    """End a plummet: remove the Plummeting condition and clear the catch challenge.

    ``caught=True`` is the Task-7 bystander-catch path (no impact); Task 6 calls it
    with ``caught=False`` after applying impact. Either way the faller stops
    plummeting and the bound "Catch the Faller" challenge is deactivated.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415
    from world.mechanics.models import ChallengeInstance  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        template = None
    if template is not None:
        remove_condition(faller, template)
    ChallengeInstance.objects.filter(
        template__name=CATCH_THE_FALLER_NAME,
        target_object=faller,
        is_active=True,
    ).update(is_active=False)


def advance_plummet(targets: Iterable[ObjectDB]) -> None:  # noqa: OBJECTDB_PARAM
    """Walk each plummeting target one elevation level down; impact at the floor.

    For every target carrying the Plummeting condition: move down one
    ``elevation_anchor`` level and accumulate the depth (severity += 1). The round
    the target lands on solid ground (the new position's ``elevation_anchor`` is
    None) fall impact fires through ``_apply_fall_impact``. A target already on the
    floor while still carrying the condition (safety) impacts immediately.

    AFK-safe by construction: empty/None targets are skipped, so a faller with no
    round participants driving the tick never descends.
    """
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        position_of,
    )

    for target in targets:
        if target is None:
            continue
        instance = _plummeting_instance(target)
        if instance is None:
            continue
        cur = position_of(target)
        below = cur.elevation_anchor if cur is not None else None
        if below is None:
            # Already on the floor with the condition still on — impact now.
            _apply_fall_impact(target, instance)
            continue
        force_move_to_position(target, below)
        instance.severity += 1
        instance.save(update_fields=["severity"])
        if below.elevation_anchor is None:
            # Landed on solid ground this round — impact fires now.
            _apply_fall_impact(target, instance)


FALL_TRIGGER_NAME = "fall_to_plummet"


def install_fall_triggers(room: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Idempotently install the FELL → plummet trigger on *room*.

    Mirrors ``install_escalation_room_triggers``: a system-installed
    ``Trigger`` (``source_condition=None``) bound to the seeded
    ``fall_to_plummet`` TriggerDefinition. No-ops when the definition is absent
    (content not wired in this deployment) or *room* is None.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    if room is None:
        return
    trigger_def = TriggerDefinition.objects.filter(name=FALL_TRIGGER_NAME).first()
    if trigger_def is None:
        return
    trigger, created = Trigger.objects.get_or_create(obj=room, trigger_definition=trigger_def)
    if created:
        handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is not None:
            handler.on_trigger_added(trigger)

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
    from world.mechanics.types import AvailableAction, ChallengeResolutionResult


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


def end_plummet(faller: ObjectDB, *, caught: bool = False) -> None:  # noqa: OBJECTDB_PARAM
    """End a plummet: remove the Plummeting condition and clear the catch challenge.

    ``caught`` selects which terminal narration the room sees:

    - ``caught=True`` — a bystander caught the faller (Task 7). A relieved
      safe-landing line is narrated; no impact has been applied.
    - ``caught=False`` — the faller hit the floor (Task 6). A grim impact line is
      narrated *after* ``_apply_fall_impact`` has already run the damage
      consequences.

    Either way the faller stops plummeting and the bound "Catch the Faller"
    challenge is deactivated.
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
    _narrate_plummet_end(faller, caught=caught)


def _narrate_plummet_end(faller: ObjectDB, *, caught: bool) -> None:  # noqa: OBJECTDB_PARAM
    """Narrate the terminal plummet outcome to the room (caught vs impact).

    Best-effort: a faller with no location (detached) narrates nothing. The
    ``caught`` distinction is observable — a relieved catch reads differently from
    a grim impact, so the parameter drives real room output rather than sitting
    inert.
    """
    location = faller.location
    if location is None:
        return
    name = faller.key
    if caught:
        message = f"{name} is caught, halting the plummet, and set down safely."
    else:
        message = f"{name} slams into the ground."
    location.msg_contents(message)


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


def _safe_position_for(catcher: ObjectDB) -> Position | None:  # noqa: OBJECTDB_PARAM
    """The catcher's position if it is a safe (non-CHASM) resting place, else None."""
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415
    from world.areas.positioning.services import position_of  # noqa: PLC0415

    pos = position_of(catcher)
    if pos is None or pos.kind == PositionKind.CHASM:
        return None
    return pos


def resolve_catch(
    faller: ObjectDB,  # noqa: OBJECTDB_PARAM
    catcher: ObjectDB,  # noqa: OBJECTDB_PARAM
    resolution_result: ChallengeResolutionResult,
) -> None:
    """Map a graded catch resolution onto the faller's plummet.

    Translates the ``ChallengeResolutionResult`` from ``resolve_challenge`` into a
    plummet effect:

    - **clean catch** (a SUCCESS check outcome, or any DESTROY resolution): end the
      plummet with no impact (``end_plummet(caught=True)``) and place the faller at
      the catcher's safe non-CHASM position;
    - **partial** (a neutral / zero-success outcome that did not destroy the
      challenge): soften the fall — decrement the accumulated Plummeting
      ``severity`` (floored at 0) — but let the descent continue;
    - **failure** (a negative outcome): no-op; the plummet continues.

    The catch challenge is bound to the faller, so the faller — not the catcher — is
    the entity whose plummet state changes.
    """
    from world.mechanics.constants import ResolutionType  # noqa: PLC0415

    check_result = resolution_result.check_result
    success_level = check_result.success_level if check_result is not None else 0
    is_clean_catch = (
        resolution_result.resolution_type == ResolutionType.DESTROY or success_level > 0
    )

    if is_clean_catch:
        from world.areas.positioning.services import force_move_to_position  # noqa: PLC0415

        end_plummet(faller, caught=True)
        safe = _safe_position_for(catcher)
        if safe is not None:
            force_move_to_position(faller, safe)
        return

    if success_level == 0:
        # Partial — soften the descent without ending it.
        instance = _plummeting_instance(faller)
        if instance is not None and instance.severity > 0:
            instance.severity -= 1
            instance.save(update_fields=["severity"])
        return

    # Failure (success_level < 0) — the plummet continues untouched.


def dispatch_catch(
    catcher: ObjectDB,  # noqa: OBJECTDB_PARAM
    faller: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    approach: str,
) -> ChallengeResolutionResult | None:
    """Resolve *catcher*'s catch attempt against *faller* and apply the outcome.

    Reuses the existing machinery rather than adding a new dispatch surface:

    1. ``get_available_actions`` surfaces only the catch approaches the catcher's
       capabilities qualify for (pure data-gating — a catcher with no catch
       capability gets nothing, so this raises ``LookupError``);
    2. ``resolve_challenge`` resolves the chosen approach against the faller's bound
       catch challenge — the same synchronous immediate-challenge path a DANGER
       round drives through ``_dispatch_immediate_challenge``;
    3. ``resolve_catch`` translates the graded outcome onto the plummet.

    *approach* names the catch capability (e.g. ``"telekinesis"``); the matching
    available action is selected by its capability name.

    Returns the ``ChallengeResolutionResult``, or None if the faller carries no
    active catch challenge.
    """
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415
    from world.mechanics.services import get_available_actions  # noqa: PLC0415

    location = catcher.location
    available = get_available_actions(catcher, location)
    catch_actions = [
        action
        for action in available
        if action.challenge_name == CATCH_THE_FALLER_NAME
        and action.resolved_challenge_instance is not None
        and action.resolved_challenge_instance.target_object_id == faller.id
    ]
    if not catch_actions:
        raise LookupError(_ERR_NO_CATCH_APPROACH)

    chosen = _select_catch_action(catch_actions, approach)

    result = resolve_challenge(
        catcher,
        chosen.resolved_challenge_instance,  # type: ignore[arg-type] — filtered non-None above
        chosen.resolved_challenge_approach,  # type: ignore[arg-type] — set whenever instance is
        chosen.capability_source,
    )
    resolve_catch(faller, catcher, result)
    return result


_ERR_NO_CATCH_APPROACH = "No catch approach is available to this catcher for this faller."


def _select_catch_action(catch_actions: list[AvailableAction], approach: str) -> AvailableAction:
    """Pick the catch AvailableAction matching *approach* (capability name)."""
    for action in catch_actions:
        source = action.capability_source
        if source is not None and source.capability_name == approach:
            return action
    # Fall back to the first available catch action when the name does not match
    # (e.g. condition-sourced sources carry an empty capability_name).
    return catch_actions[0]


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

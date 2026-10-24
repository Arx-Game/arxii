"""Resolving a technique's targets and their prerequisites."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import ActionTargetType
from world.combat.constants import OpponentStatus
from world.combat.models import (
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
)
from world.conditions.constants import Allegiance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique


def _resolve_condition_target(
    kind: str,
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> ObjectDB | None:
    """Resolve a ConditionTargetKind value to a concrete ObjectDB.

    Returns None when the named target is absent or ineligible (e.g. opponent
    already DEFEATED).
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if kind == ConditionTargetKind.SELF:
        return caster_od
    if kind == ConditionTargetKind.ALLY:
        ally = action.focused_ally_target
        return ally.character_sheet.character if ally is not None else None
    if kind == ConditionTargetKind.ENEMY:
        opp = action.focused_opponent_target
        if opp is not None:
            opp.refresh_from_db()
        active = opp is not None and opp.status != OpponentStatus.DEFEATED
        return opp.objectdb if active else None
    return None


def _resolve_enemy_condition_targets(
    all_opponents: list[CombatOpponent],
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> list[ObjectDB]:
    """Resolve the ENEMY condition target list for ``_apply_conditions``.

    AREA / FILTERED_GROUP techniques expand ENEMY to ALL active (non-DEFEATED)
    opponents in ``_resolved_opponent_targets()``; when there are no join-table
    opponents, fall back to the single focused target.
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if all_opponents:
        enemy_objectdbs: list[ObjectDB] = []
        for opp in all_opponents:
            opp.refresh_from_db()
            if opp.status != OpponentStatus.DEFEATED and opp.objectdb is not None:
                enemy_objectdbs.append(opp.objectdb)
        return enemy_objectdbs
    # No join-table opponents — fall back to the single focused target
    target = _resolve_condition_target(ConditionTargetKind.ENEMY, action, caster_od)
    return [target] if target is not None else []


def _build_affected_targets(
    participant: CombatParticipant,  # noqa: ARG001 - reserved for future signature additions
    action: CombatRoundAction,
) -> list[ObjectDB]:
    """Return the dedup'd ObjectDB list for use_technique's targets parameter.

    Resolution rules:
    - opponent target → opp.objectdb (always present after CombatOpponent refactor;
      None-guarded for pathological state)
    - ally target → ally.character_sheet.character
    - both null → empty list
    """
    targets: list = []
    seen: set[int] = set()
    if action.focused_opponent_target_id:
        opp = action.focused_opponent_target
        od = opp.objectdb
        if od is not None and od.pk not in seen:
            targets.append(od)
            seen.add(od.pk)
    if action.focused_ally_target_id:
        ally_od = action.focused_ally_target.character_sheet.character
        if ally_od.pk not in seen:
            targets.append(ally_od)
            seen.add(ally_od.pk)
    return targets


def _resolve_primary_target_sheet(action: CombatRoundAction) -> CharacterSheet | None:
    """Resolve the cast's primary target's ``CharacterSheet`` for situational perks (#2536).

    Mirrors ``_build_affected_targets``'s ordering (opponent target takes
    precedence over ally target when a technique somehow declares both — the
    dispatcher never actually does this, but the ordering is kept consistent).
    Only a PC/sheet-backed target can populate a ``CharacterSheet``:

    - ``focused_ally_target`` → ``CombatParticipant.character_sheet`` (always
      a real ``CharacterSheet`` — every ``CombatParticipant`` is a PC).
    - ``focused_opponent_target`` → a ``CombatOpponent`` is NPC-only and has
      no ``CharacterSheet`` FK of its own, UNLESS it is a "story NPC" linked
      to a persistent ``scenes.Persona`` (``CombatOpponent.persona``, see
      ``world/combat/escalation.py``'s ``opponent.persona.character_sheet``
      for the same resolution pattern) — that gives a real ``CharacterSheet``
      target-keyed situations can read. A bare (non-persona) NPC opponent
      correctly resolves to ``None``: target-keyed situations (
      ``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
      ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) simply
      never hold against it, same as any other targetless cast.

    For a multi-target/AoE cast only this single primary target is resolved
    — per-target perk evaluation for AoE is a legitimate slice-2+
    refinement (see ``vow_situational_power_term``'s docstring).
    """
    if action.focused_opponent_target_id:
        opponent = action.focused_opponent_target
        if opponent.persona_id is not None:
            return opponent.persona.character_sheet
        return None
    if action.focused_ally_target_id:
        return action.focused_ally_target.character_sheet
    return None


def _check_combat_target_prerequisites(
    technique: Technique, caster_od: ObjectDB, targets: list[ObjectDB]
) -> None:
    """Enforce technique.target_prerequisites against combat's explicit target list.

    SINGLE is the only target_type that hard-blocks here: its target list
    (from _build_affected_targets) is the real, complete target set for the
    cast, so a failure hard-blocks the cast — mirroring the non-combat
    SINGLE hard-block in validate_cast_target.

    For target_type=SELF, the caster IS the target — but the real cast dispatcher
    (``_target_spec_for_technique_action`` in ``actions/player_interface.py``) never
    supplies an explicit opponent/ally target for a SELF technique, so
    ``_build_affected_targets`` returns [] (see
    ``test_affected_emitted_for_self_targeted_buff``). Check the caster directly in
    that case rather than relying on targets being populated — mirrors Task 5's
    non-combat SELF fix in ``world/magic/services/targeting.py``.

    AREA/FILTERED_GROUP get NO pre-flight check at all: ``targets`` here is built
    from ``action.focused_opponent_target``, a single FK that for an AoE dispatch
    holds only the arbitrary "first" opponent from a client-supplied
    ``focused_opponent_target_ids`` list (see
    ``RoundContext._resolve_focused_targets``) — not a real single target, and not
    the full AoE set. Hard-blocking the whole cast because THAT one arbitrary
    opponent fails a prerequisite would wrongly kill a cast where other opponents
    in the same AoE set legitimately pass. Defer entirely to
    ``_filter_by_target_prerequisites``'s silent per-opponent filter downstream
    (``_resolved_opponent_targets``, #1793 second-pass fix).
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.services.targeting import InvalidCastTarget  # noqa: PLC0415
    from world.mechanics.services import prerequisites_met  # noqa: PLC0415

    prereqs = technique.cached_target_prerequisites
    if not prereqs:
        return

    if technique.target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
        return

    msg = "Target does not meet this technique's targeting requirement."

    if technique.target_type == ActionTargetType.SELF:
        if not prerequisites_met(prereqs, caster_od, caster_od):
            raise InvalidCastTarget(msg)
        return

    for target_od in targets:
        if not prerequisites_met(prereqs, caster_od, target_od):
            raise InvalidCastTarget(msg)


def opponents_in_reach(
    attacker: ObjectDB, technique: Technique, opponents: list[CombatOpponent]
) -> list[CombatOpponent]:
    """Keep the opponents ``technique_can_reach`` allows from the attacker's live position.

    The one reach filter for an area cast (#4607): the resolver uses it to drop targets
    that moved out of reach, and ``_resolve_pc_action`` uses it to decide a cast fizzles.
    An opponent with no game object stays, and so does everyone when either side is
    unplaced (``technique_can_reach`` is lenient).
    """
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    return [
        opp
        for opp in opponents
        if opp.objectdb is None or technique_can_reach(attacker, technique, opp.objectdb)
    ]


def _filter_by_target_prerequisites(
    caster_od: ObjectDB, technique: Technique, opponents: list[CombatOpponent]
) -> list[CombatOpponent]:
    """Silently drop opponents that fail technique.target_prerequisites.

    AREA/FILTERED_GROUP only: these are enumerated independently of
    _build_affected_targets/_check_combat_target_prerequisites (which skips
    AREA/FILTERED_GROUP entirely, deferring to this filter, #1793 second-pass
    fix), so a target_prerequisites-gated technique would otherwise land on every
    opponent regardless of eligibility. Mirrors resolve_targets' silent
    AREA/FILTERED_GROUP filter (world/magic/services/targeting.py) rather than
    raising: an AoE cast skips ineligible targets, it does not block (ADR-0045).
    """
    from world.mechanics.services import prerequisites_met  # noqa: PLC0415

    prereqs = technique.cached_target_prerequisites
    if not prereqs:
        return opponents
    eligible = []
    for opp in opponents:
        target_od = opp.objectdb
        if target_od is None:
            continue  # can't evaluate a Property-based prerequisite without an ObjectDB
        if prerequisites_met(prereqs, caster_od, target_od):
            eligible.append(opp)
    return eligible


def aoe_opponent_candidates(
    participant: CombatParticipant, action: CombatRoundAction, technique: Technique
) -> list[CombatOpponent]:
    """Opponents an AREA or FILTERED_GROUP technique would act on, before the reach filter.

    - AREA: every non-DEFEATED opponent in the encounter (one query), minus any whose
      effective allegiance is ALLY_OF_CASTER (a summon or charmed NPC; Decision 4, #4091).
    - FILTERED_GROUP: the opponents stored in ``CombatRoundActionTarget``, falling back
      to the single ``focused_opponent_target`` when no join rows exist.

    Both then run through the silent target_prerequisites filter (#1793). Any other
    target type returns an empty list.
    """
    caster_od = participant.character_sheet.character
    if technique.target_type == ActionTargetType.AREA:
        from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

        opponents = list(
            CombatOpponent.objects.filter(encounter=participant.encounter)
            .exclude(status=OpponentStatus.DEFEATED)
            .order_by("pk")
        )
        allegiances = effective_allegiances(opponents)
        opponents = [o for o in opponents if allegiances[o.pk] != Allegiance.ALLY_OF_CASTER]
        return _filter_by_target_prerequisites(caster_od, technique, opponents)
    if technique.target_type == ActionTargetType.FILTERED_GROUP:
        join_opponents = list(
            CombatRoundActionTarget.objects.filter(action=action, opponent__isnull=False)
            .select_related("opponent")
            .order_by("pk")
        )
        if join_opponents:
            opponents = [row.opponent for row in join_opponents]
        else:
            primary = action.focused_opponent_target
            opponents = [primary] if primary is not None else []
        return _filter_by_target_prerequisites(caster_od, technique, opponents)
    return []


def _unreachable_single_target(
    participant: CombatParticipant, action: CombatRoundAction, technique: Technique
) -> bool:
    """True when the declared opponent or ally target is out of the technique's reach now."""
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    attacker = participant.character_sheet.character
    target_od = None
    if action.focused_opponent_target is not None:
        target_od = action.focused_opponent_target.objectdb
    elif action.focused_ally_target is not None and action.focused_ally_target != participant:
        target_od = action.focused_ally_target.character_sheet.character
    return target_od is not None and not technique_can_reach(attacker, technique, target_od)


def finds_no_one_in_reach(
    participant: CombatParticipant, action: CombatRoundAction, technique: Technique
) -> bool:
    """True when the cast's declared target(s) are all out of reach at resolution (#4607).

    Positions change between declaration and the PC's slot (NPCs move in theirs), so
    the declare-time reach gate is re-checked live. A single opponent or ally target
    fizzles when out of reach. An AREA / FILTERED_GROUP cast fizzles only when it had
    opponents to act on and none of them is still in reach. Unplaced combatants and
    self-targeted casts never fizzle.
    """
    if technique.target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
        candidates = aoe_opponent_candidates(participant, action, technique)
        return bool(candidates) and not opponents_in_reach(
            participant.character_sheet.character, technique, candidates
        )
    return _unreachable_single_target(participant, action, technique)

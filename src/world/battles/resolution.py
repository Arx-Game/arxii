"""Battle round resolution engine.

Iterates all unresolved BattleActionDeclarations for a round, casts each
declaration's technique once via ``resolve_battle_technique``, then routes
the result:

- ``success_level > 0`` → STRIKE: attrite the target unit + award VP to the
  participant's side; SUPPORT: award SUPPORT_VP.
- ``success_level <= 0`` → debit PC health then call
  ``process_damage_consequences`` (non-progressive, SQLite-safe).

The ``BattleRoundResult`` dataclass carries per-side VP totals, routed/
destroyed unit lists, and a casualty list for the caller to display or log.

This module also provides ``BattleTechniqueResolver`` and
``resolve_battle_technique``, which cast a declaration's ``technique`` through
the real magic envelope (``use_technique``). Routing through ``use_technique``
(rather than a generic shared check) means the check is sourced from the
player's actual technique (``technique.action_template.check_type``),
anima/Soulfray/mishap apply normally, and Audere/Audere Majora escalation
fires automatically (it's wired inside ``use_technique`` itself, Step 8c — no
separate call site is needed here). ``resolve_battle_round`` calls
``resolve_battle_technique`` per declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_POSTURE_CHECK_MODIFIER,
    BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER,
    BATTLE_POSTURE_VP_MULTIPLIER,
    ROUTED_MORALE_THRESHOLD,
    ROUTED_STRENGTH_THRESHOLD,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    UNIT_QUALITY_STRIKE_MODIFIER,
    BattleActionKind,
    BattleUnitStatus,
)
from world.battles.models import BattleParticipant, BattleRound
from world.checks.services import perform_check
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from world.battles.models import Battle, BattleActionDeclaration, BattlePlace, BattleSide
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance
    from world.magic.models import Technique
    from world.magic.types.power_ledger import PowerLedger


def _is_isolated(participant: BattleParticipant) -> bool:
    """True when no other ACTIVE participant on the same side shares this participant's place.

    A participant with no ``place`` assigned (front-agnostic) is never counted as
    isolated — isolation is specifically about being alone at a front, not merely
    unassigned.
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415

    if participant.place_id is None:
        return False
    return (
        not BattleParticipant.objects.filter(
            battle_id=participant.battle_id,
            side_id=participant.side_id,
            place_id=participant.place_id,
            status=BattleParticipantStatus.ACTIVE,
        )
        .exclude(pk=participant.pk)
        .exists()
    )


def _has_unimpaired_mobility(character_sheet: CharacterSheet) -> bool:
    """True when the character's MOVEMENT capability is currently unimpaired.

    Resolved the same way ``can_act`` resolves AWARENESS — via
    ``get_effective_capability_value`` — rather than the room-based positioning-graph
    ``blocks_flight``/``elevation_anchor`` fields, which don't apply to location-less
    battles (see the #1733 spec's anti-reinvention ledger).
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    movement = CapabilityType.objects.filter(name=FoundationalCapability.MOVEMENT).first()
    if movement is None:
        return False
    return get_effective_capability_value(character_sheet, movement) > 0


def _composition_affinity_modifier(technique: Technique, composition: str) -> int:
    """Flat STRIKE-check modifier from an authored technique-vs-composition row (#1711).

    Returns 0 when no TechniqueCompositionAffinity row matches — most techniques
    have no authored affinity, and that's the expected common case.
    """
    from world.battles.models import TechniqueCompositionAffinity  # noqa: PLC0415

    row = TechniqueCompositionAffinity.objects.filter(
        technique=technique, composition=composition
    ).first()
    return row.modifier if row is not None else 0


def _terrain_effect_modifier(place: BattlePlace | None, composition: str) -> int:
    """Flat attacker-facing STRIKE modifier from an authored terrain-vs-composition
    row (#1711). Returns 0 when the unit has no place, or no row matches.
    """
    from world.battles.models import TerrainCompositionEffect  # noqa: PLC0415

    if place is None:
        return 0
    row = TerrainCompositionEffect.objects.filter(
        terrain_type=place.terrain_type, composition=composition
    ).first()
    return row.modifier if row is not None else 0


def _quality_modifier(quality: str) -> int:
    """Flat attacker-facing STRIKE modifier from the unit's quality tier (#1711)."""
    return UNIT_QUALITY_STRIKE_MODIFIER.get(quality, 0)


def commander_bonus_for_side_at_place(side: BattleSide, place: BattlePlace | None) -> int:
    """Max Battle Command modifier-walk bonus across commanded units on ``side`` at
    ``place`` (#1711). Max, not sum — multiple commanders present don't stack.
    Returns 0 when ``place`` is None or no ACTIVE unit on this side/place has a
    commander set.
    """
    from world.battles.factories import ensure_battle_command_modifier_target  # noqa: PLC0415
    from world.battles.models import BattleUnit  # noqa: PLC0415
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    if place is None:
        return 0
    commander_ids = (
        BattleUnit.objects.filter(
            side=side, place=place, status=BattleUnitStatus.ACTIVE, commander__isnull=False
        )
        .values_list("commander_id", flat=True)
        .distinct()
    )
    if not commander_ids:
        return 0
    target = ensure_battle_command_modifier_target()
    sheets = CharacterSheet.objects.filter(pk__in=commander_ids)
    return max(get_modifier_total(sheet, target) for sheet in sheets)


def select_surrounded_terminal_pool(
    *, battle: Battle, participant: BattleParticipant
) -> ConsequencePool | None:
    """Route the Surrounded terminal resolution to the enemy or PvP-safe pool (#1733).

    Death is permitted by default (``surrounded_terminal_enemy`` — the isolating side is
    normally an abstract, non-PC ``BattleUnit``) UNLESS the opposing ``BattleSide`` has an
    active PC participant at the same ``place`` — an actual PC opponent present means
    ADR-0023 (PvP non-lethal) applies, so ``surrounded_terminal_pvp`` (no death row at
    all) is used instead. This replaces ``select_abandonment_pool``'s ``ObjectDB``
    source-character routing, which doesn't apply here (see Task 2).

    Returns ``None`` on a seeding gap (the named pool doesn't exist) rather than raising
    — matches the "never crash the round, hold the victim" convention the sibling
    ``_resolve_terminal_bleed_out`` already follows (final-review finding: this runs
    inside ``resolve_battle_round``'s ``@transaction.atomic``, so raising here would
    abort the GM's entire round resolution, not just this one victim's outcome).
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.vitals.constants import (  # noqa: PLC0415
        POOL_SURROUNDED_TERMINAL_ENEMY,
        POOL_SURROUNDED_TERMINAL_PVP,
    )

    opposing_pc_present = (
        BattleParticipant.objects.filter(
            battle_id=battle.pk,
            place_id=participant.place_id,
            status=BattleParticipantStatus.ACTIVE,
        )
        .exclude(side_id=participant.side_id)
        .filter(character_sheet__character__db_account__isnull=False)
        .exists()
    )
    pool_name = (
        POOL_SURROUNDED_TERMINAL_PVP if opposing_pc_present else POOL_SURROUNDED_TERMINAL_ENEMY
    )
    return ConsequencePool.objects.filter(name=pool_name).first()


def resolve_surrounded_terminal(
    *, character_sheet: CharacterSheet, instance: ConditionInstance, battle: Battle
) -> bool:
    """Resolve a terminal-stage Surrounded instance through the routed, guarded pool.

    Finds the character's ``BattleParticipant`` for ``battle`` to route via
    ``select_surrounded_terminal_pool``, checks ``has_death_deferred`` explicitly (the
    part of ``death_is_permitted`` that's still relevant — a deferred-death condition
    protects the victim regardless of who/what surrounded them), then dispatches through
    the shared ``_resolve_peril_via_pool`` core (Task 2).

    A missing ``BattleParticipant`` (shouldn't happen — the caller always has one) or a
    missing terminal pool (seeding gap) holds the victim rather than crashing.
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.conditions.services import has_death_deferred  # noqa: PLC0415
    from world.vitals.services import _resolve_peril_via_pool  # noqa: PLC0415

    participant = BattleParticipant.objects.filter(
        battle=battle,
        character_sheet=character_sheet,
        status=BattleParticipantStatus.ACTIVE,
    ).first()
    if participant is None:
        return False

    pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
    if pool is None:
        return False
    death_permitted = not has_death_deferred(character_sheet.character)

    died = _resolve_peril_via_pool(character_sheet, instance, pool, death_permitted=death_permitted)
    if died:
        participant.status = BattleParticipantStatus.INCAPACITATED
        participant.save(update_fields=["status"])
    return died


@dataclass
class BattleTechniqueResolution:
    """Adapts ``use_technique``'s resolve_fn contract — exposes ``.check_result``
    for ``_resolve_check_result`` (``world/magic/services/techniques.py``)."""

    check_result: CheckResult


@dataclass
class BattleTechniqueResolver:
    """``resolve_fn`` passed to ``use_technique``: rolls the declared technique's
    own check, folding in the full battle modifier stack (composition affinity,
    terrain, unit quality, commander bonus, posture — #1711). Battle has no
    damage-profile/condition application of its own — that stays in
    ``resolve_battle_round``'s STRIKE/SUPPORT/failure routing.
    """

    character: ObjectDB
    technique: Technique
    declaration: BattleActionDeclaration

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002 — battle doesn't scale effects off cast power
        ledger: PowerLedger,  # noqa: ARG002 — battle doesn't use the power ledger
        extra_modifiers: int = 0,
    ) -> BattleTechniqueResolution:
        check_type = self.technique.action_template.check_type
        total_modifiers = extra_modifiers + self._battle_modifier_stack()
        check_result = perform_check(self.character, check_type, extra_modifiers=total_modifiers)
        return BattleTechniqueResolution(check_result=check_result)

    def _battle_modifier_stack(self) -> int:
        """Sum every #1711 modifier source relevant to this declaration."""
        participant = self.declaration.participant
        unit = self.declaration.target_unit

        composition = (
            _composition_affinity_modifier(self.technique, unit.composition)
            if unit is not None
            else 0
        )
        terrain = _terrain_effect_modifier(unit.place, unit.composition) if unit is not None else 0
        quality = _quality_modifier(unit.quality) if unit is not None else 0
        commander = commander_bonus_for_side_at_place(participant.side, participant.place)
        posture = BATTLE_POSTURE_CHECK_MODIFIER.get(participant.side.posture, 0)

        return composition + terrain + quality + commander + posture


def resolve_battle_technique(*, declaration: BattleActionDeclaration) -> CheckResult | None:
    """Cast ``declaration.technique`` through the real magic envelope.

    Routes through ``use_technique`` so anima cost, Soulfray accumulation, and —
    critically — the Audere/Audere Majora escalation hook (Step 8c, fires
    unconditionally inside ``use_technique`` for every caller) all apply exactly
    as they would for any other cast. ``confirm_soulfray_risk=True`` because a
    batch round resolve cannot pause mid-batch for one participant's consent
    prompt — same reasoning ``resolve_accepted_cast`` uses for its consent-accept
    path.

    Args:
        declaration: A ``BattleActionDeclaration`` with ``technique`` set.

    Returns:
        The resolved ``CheckResult``, or ``None`` if the cast was interrupted
        before resolution (e.g. a reactive PRE_CAST cancellation) — the caller
        treats ``None`` as success_level 0 (failure).
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    character = declaration.participant.character_sheet.character
    technique = declaration.technique
    resolver = BattleTechniqueResolver(
        character=character, technique=technique, declaration=declaration
    )

    result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        # lethal defaults True (unlike combat's lethal=encounter.is_lethal) — battles
        # have no non-lethal encounter concept; this only bounds the CASTER's own
        # anima-overburn/Soulfray severity, not PvP damage (ADR-0023 is unaffected).
    )
    if not result.confirmed or result.resolution_result is None:
        # PRE_CAST cancellation (rare, e.g. a reactive scar) — no anima was spent,
        # but the caller still counts this as a failure (success_level 0) for
        # simplicity; the round-scale batch resolve has no cheaper alternative.
        return None
    return result.resolution_result.check_result


@dataclass
class BattleRoundResult:
    """Summary of a resolved battle round."""

    # VP awarded per BattleSide pk → total awarded this round.
    vp_awarded: dict[int, int] = field(default_factory=dict)
    # Units whose strength reached 0 and were DESTROYED this round.
    units_destroyed: list[int] = field(default_factory=list)
    # Units whose strength fell below the ROUTED threshold (but not 0).
    units_routed: list[int] = field(default_factory=list)
    # Participant pks who took damage this round.
    casualties: list[int] = field(default_factory=list)


def _compute_unit_status(strength: int, morale: int) -> str:
    """Derive BattleUnitStatus from both resources — status is always a view, never
    written independently of them (#1712). Mirrors the relationship strength alone
    used to have with status before morale existed: DESTROYED requires strength==0
    (physical destruction, morale collapse alone never kills a unit); ROUTED can be
    triggered by either resource crossing its own threshold (a unit can break either
    from being ground down or from its will collapsing).

    A future Mindless/Fearless-style unit property (#1794, "Battle units:
    Property/Capability holding") would skip the morale branch for immune units —
    no such gate exists yet; this issue ships morale uniformly across all units.
    """
    if strength == 0:
        return BattleUnitStatus.DESTROYED
    if strength <= ROUTED_STRENGTH_THRESHOLD or morale <= ROUTED_MORALE_THRESHOLD:
        return BattleUnitStatus.ROUTED
    return BattleUnitStatus.ACTIVE


def _scope_target_units(
    declaration: BattleActionDeclaration, *, include_routed: bool = False
) -> list:
    """Active (optionally also ROUTED) BattleUnits affected by *declaration*, per its
    scope (#1710). ``include_routed=True`` (RALLY, #1712) also includes ROUTED units
    — RALLY's whole purpose is reaching units that have already broken; DESTROYED
    units are never included (gone, not rallyable)."""
    from world.battles.constants import BattleActionScope, BattleUnitStatus  # noqa: PLC0415
    from world.battles.models import BattleUnit  # noqa: PLC0415

    statuses = (
        (BattleUnitStatus.ACTIVE, BattleUnitStatus.ROUTED)
        if include_routed
        else (BattleUnitStatus.ACTIVE,)
    )
    if declaration.scope == BattleActionScope.SIDE and declaration.target_side_id:
        return list(
            BattleUnit.objects.filter(side_id=declaration.target_side_id, status__in=statuses)
        )
    if declaration.scope == BattleActionScope.PLACE and declaration.target_place_id:
        return list(
            BattleUnit.objects.filter(place_id=declaration.target_place_id, status__in=statuses)
        )
    return [declaration.target_unit] if declaration.target_unit is not None else []


def _scope_target_participants(declaration: BattleActionDeclaration) -> list:
    """Active BattleParticipants affected by *declaration*, per its scope (#1710)."""
    from world.battles.constants import BattleActionScope, BattleParticipantStatus  # noqa: PLC0415

    if declaration.scope == BattleActionScope.SIDE and declaration.target_side_id:
        return list(
            BattleParticipant.objects.filter(
                side_id=declaration.target_side_id, status=BattleParticipantStatus.ACTIVE
            )
        )
    if declaration.scope == BattleActionScope.PLACE and declaration.target_place_id:
        return list(
            BattleParticipant.objects.filter(
                place_id=declaration.target_place_id, status=BattleParticipantStatus.ACTIVE
            )
        )
    return [declaration.target_ally] if declaration.target_ally is not None else []


def _resolve_strike_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
    place_defense_bonus: dict[int, int] | None = None,
) -> None:
    """Apply STRIKE success: attrite the unit(s), award VP to the participant's side,
    scaled by the side's posture (#1711).

    Fans out across every active unit at the declaration's scope target
    (SIDE/PLACE, #1710) — each unit takes the same per-level attrition; VP is
    awarded once per declaration regardless of scope breadth. Units on the
    declaring participant's own side are excluded — SIDE/PLACE scope fans out
    across a shared bucket that isn't itself side-aware, so STRIKE must never
    attrite the caster's own units (friendly fire). status is derived jointly
    from strength and morale (#1712) — a unit already broken on morale can flip
    to ROUTED from a hit too small to cross the strength threshold alone.

    Reads ``place_defense_bonus`` (#1712, populated by any REPEL declared this
    round at the unit's place) and subtracts it from the computed attrition
    before applying, floored at 0.
    """
    units = _scope_target_units(declaration)
    units = [u for u in units if u.side_id != declaration.participant.side_id]
    if not units:
        return

    defense_bonus_by_place = place_defense_bonus or {}
    attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
    for unit in units:
        bonus = defense_bonus_by_place.get(unit.place_id, 0)
        net_attrition = max(0, attrition - bonus)
        unit.strength = max(0, unit.strength - net_attrition)
        unit.status = _compute_unit_status(unit.strength, unit.morale)
        if unit.status == BattleUnitStatus.DESTROYED:
            result.units_destroyed.append(unit.pk)
        elif unit.status == BattleUnitStatus.ROUTED:
            result.units_routed.append(unit.pk)
        unit.save(update_fields=["strength", "status"])

    side = declaration.participant.side
    base_vp = success_level * STRIKE_VP_PER_LEVEL
    vp_gain = round(base_vp * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])

    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_support_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
) -> None:
    """Apply SUPPORT success: award SUPPORT_VP to the participant's side, scaled by
    the side's posture (#1711)."""
    side = declaration.participant.side
    vp_gain = round(SUPPORT_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_rout_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply ROUT success: damage the target unit(s)' morale, award VP (#1712).

    Mirrors STRIKE's own-side exclusion and scope fan-out, but moves ``morale``
    instead of ``strength`` — ROUT breaks a unit's will to fight without grinding
    it down physically. Scales with success_level exactly like STRIKE's attrition.
    Only reaches ACTIVE enemy units (default ``_scope_target_units`` filter) —
    a unit that's already ROUTED has nothing further for ROUT to accomplish.
    """
    from world.battles.constants import ROUT_MORALE_PER_LEVEL, ROUT_VP_PER_LEVEL  # noqa: PLC0415

    units = _scope_target_units(declaration)
    units = [u for u in units if u.side_id != declaration.participant.side_id]
    if not units:
        return

    morale_damage = success_level * ROUT_MORALE_PER_LEVEL
    for unit in units:
        unit.morale = max(0, unit.morale - morale_damage)
        unit.status = _compute_unit_status(unit.strength, unit.morale)
        if unit.status == BattleUnitStatus.DESTROYED:
            result.units_destroyed.append(unit.pk)
        elif unit.status == BattleUnitStatus.ROUTED:
            result.units_routed.append(unit.pk)
        unit.save(update_fields=["morale", "status"])

    side = declaration.participant.side
    base_vp = success_level * ROUT_VP_PER_LEVEL
    vp_gain = round(base_vp * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_rally_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply RALLY success: restore the target unit(s)' morale, award flat VP (#1712).

    Fans out across the declarant's own side only (mirrors RESCUE's own-side
    filter), including ROUTED units (``include_routed=True`` — RALLY's whole
    point). A unit whose status reads ROUTED purely from low ``strength`` stays
    ROUTED even after a full morale restore — RALLY only recovers units that
    broke from morale collapse, not ones ground down by attrition.
    """
    from world.battles.constants import (  # noqa: PLC0415
        MAX_MORALE,
        RALLY_MORALE_PER_LEVEL,
        RALLY_VP,
    )

    units = _scope_target_units(declaration, include_routed=True)
    units = [u for u in units if u.side_id == declaration.participant.side_id]
    if not units:
        return

    morale_gain = success_level * RALLY_MORALE_PER_LEVEL
    for unit in units:
        unit.morale = min(MAX_MORALE, unit.morale + morale_gain)
        unit.status = _compute_unit_status(unit.strength, unit.morale)
        unit.save(update_fields=["morale", "status"])

    side = declaration.participant.side
    vp_gain = round(RALLY_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_repel_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    place_defense_bonus: dict[int, int],
) -> None:
    """Apply REPEL success: raise the defense bonus at the target place for this
    round, award flat VP (#1712). Requires scope=PLACE (enforced at declare time
    by PlaceScopeRequiredError) — ``target_place`` is always set here.

    ``resolve_battle_round`` resolves REPEL declarations before STRIKE so the
    bonus is populated in time to reduce STRIKE's attrition against units at
    this place in the same round.
    """
    from world.battles.constants import REPEL_DEFENSE_BONUS, REPEL_VP  # noqa: PLC0415

    place = declaration.target_place
    place_defense_bonus[place.pk] = place_defense_bonus.get(place.pk, 0) + REPEL_DEFENSE_BONUS

    side = declaration.participant.side
    vp_gain = round(REPEL_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_hold_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
) -> None:
    """Apply HOLD success: capture or sustain control of the target place, award VP
    (#1712). Requires scope=PLACE (enforced at declare time) — ``target_place`` is
    always set here. Capturing (place uncontrolled or held by the enemy) awards
    HOLD_CAPTURE_VP and flips control; sustaining (already held by the declarant's
    side) awards the smaller HOLD_SUSTAIN_VP with no state change, so repeatedly
    holding a front doesn't runaway-farm the capture bonus.
    """
    from world.battles.constants import HOLD_CAPTURE_VP, HOLD_SUSTAIN_VP  # noqa: PLC0415

    place = declaration.target_place
    side = declaration.participant.side

    if place.controlled_by_id != side.pk:
        place.controlled_by = side
        place.save(update_fields=["controlled_by"])
        vp_gain = round(HOLD_CAPTURE_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    else:
        vp_gain = round(HOLD_SUSTAIN_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))

    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_rescue_success(declaration: BattleActionDeclaration) -> None:
    """Apply RESCUE success: clear Surrounded from the ally/allies at scope (#1733, #1710).

    Fans out across every active participant at the declaration's scope target
    (SIDE/PLACE) instead of a single ally when scope != UNIT. No VP awarded —
    rescue trades round economy for saving allies, not battlefield progress.
    No-op for a target that isn't (or is no longer) Surrounded. Participants on
    an enemy side are excluded — a PLACE-scope target bucket may hold both
    sides' participants (a shared front), and RESCUE must never clear Surrounded
    from an enemy (that would help the enemy, not the caster's side).
    """
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions, remove_condition  # noqa: PLC0415

    targets = _scope_target_participants(declaration)
    targets = [t for t in targets if t.side_id == declaration.participant.side_id]
    if not targets:
        return

    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    if template is None:
        return

    for target in targets:
        character = target.character_sheet.character
        if get_active_conditions(character, condition=template).exists():
            remove_condition(character, template)


def _maybe_apply_surrounded(declaration: BattleActionDeclaration) -> bool:
    """Roll the surrounded_entry pool for an isolated declaration failure (#1733).

    Isolation and mobility are objective, code-computed signals fed as extra_modifiers
    into the entry check — the pool's authored rows decide the actual odds (never a
    hardcoded gate; see Decision 3 of the #1733 spec). No-op when the pool/condition
    content isn't seeded (degrades gracefully, same convention as the abandonment pools).

    Returns True iff Surrounded was newly applied this call — the caller propagates
    this so ``resolve_battle_round`` can exclude a participant from this same round's
    escalation tick (final-review finding: a participant always declared to reach this
    failure branch, so without the exclusion a freshly-Surrounded participant would
    immediately roll their first escalation check in the very round they entered,
    rather than getting one round before their peril first escalates).
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.battles.constants import (  # noqa: PLC0415
        SURROUNDED_ENTRY_ISOLATED_MODIFIER,
        SURROUNDED_ENTRY_MOBILITY_MODIFIER,
    )
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        resolve_pool_consequences,
        select_consequence,
    )
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionStage, ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.vitals.constants import POOL_SURROUNDED_ENTRY  # noqa: PLC0415

    participant = declaration.participant
    if not _is_isolated(participant):
        return False

    pool = ConsequencePool.objects.filter(name=POOL_SURROUNDED_ENTRY).first()
    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    entry_stage = (
        ConditionStage.objects.filter(condition=template, stage_order=1).first()
        if template is not None
        else None
    )
    if pool is None or template is None or entry_stage is None:
        return False

    extra_modifiers = SURROUNDED_ENTRY_ISOLATED_MODIFIER
    if _has_unimpaired_mobility(participant.character_sheet):
        extra_modifiers += SURROUNDED_ENTRY_MOBILITY_MODIFIER

    character = participant.character_sheet.character
    candidates = resolve_pool_consequences(pool)
    pending = select_consequence(
        character,
        entry_stage.resist_check_type,
        entry_stage.resist_difficulty,
        candidates,
        extra_modifiers=extra_modifiers,
    )
    if pending.selected_consequence.label == "surrounded":  # noqa: STRING_LITERAL
        # No `stage` kwarg on apply_condition — the has_progression=True template
        # auto-initializes current_stage to stage_order=1 (== entry_stage) via
        # _build_bulk_context (world/conditions/services.py:483).
        apply_condition(target=character, condition=template)
        return True
    return False


def _resolve_failure(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> bool:
    """Apply check failure: debit PC health, route through damage consequences, and
    roll the surrounded_entry pool if the participant is isolated (#1733).

    Damage is non-progressive (damage_type=None, source_character=None) so
    the SQLite fast tier can handle it without DISTINCT ON queries.

    Returns True iff Surrounded was newly applied this call (propagated from
    ``_maybe_apply_surrounded`` — see its docstring for why the caller needs this).
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = declaration.participant.character_sheet
    try:
        vitals = sheet.vitals
    except CharacterVitals.DoesNotExist:
        result.casualties.append(declaration.participant.pk)
        return False

    posture_delta = BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER.get(
        declaration.participant.side.posture, 0
    )
    dmg = BASE_FAILURE_DAMAGE + abs(success_level) + posture_delta
    vitals.health -= dmg
    vitals.save(update_fields=["health"])

    process_damage_consequences(
        character_sheet=sheet,
        damage_dealt=dmg,
        damage_type=None,
        source_character=None,
    )
    newly_surrounded = _maybe_apply_surrounded(declaration)
    result.casualties.append(declaration.participant.pk)
    return newly_surrounded


def _advance_surrounded_participants(
    battle: Battle,
    declared_participant_ids: set[int],
    newly_surrounded_participant_ids: set[int],
) -> None:
    """Tick every ACTIVE Surrounded participant's peril once for this round (#1733).

    A participant advances if they declared this round, OR ``battle.afk_peril_override``
    is True (the narrow, explicit ADR-0004 exception — see ADR-0074). Otherwise their
    peril holds unchanged this round — mirroring the intent of the room-based #1480
    own-peril skip without depending on SceneRound (Decision 1 of the #1733 spec).

    ``newly_surrounded_participant_ids`` are always excluded regardless of the above —
    a participant only reaches this tier by declaring (isolated + failed), so without
    this exclusion a freshly-Surrounded participant would immediately roll their first
    escalation check in the very round they entered Surrounded, rather than getting one
    round before their peril first escalates (final-review finding).
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415
    from world.vitals.services import advance_surrounded  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    if template is None:
        return  # seeding gap — nothing to advance

    participants = BattleParticipant.objects.filter(
        battle=battle, status=BattleParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")

    for participant in participants:
        if participant.pk in newly_surrounded_participant_ids:
            continue
        if not (battle.afk_peril_override or participant.pk in declared_participant_ids):
            continue
        sheet = participant.character_sheet
        if not get_active_conditions(sheet.character, condition=template).exists():
            continue
        advance_surrounded(sheet, battle=battle)


def _dispatch_success_handler(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
    place_defense_bonus: dict[int, int],
) -> None:
    """Route a successful declaration to its action-kind-specific resolver (#1712).

    Extracted from ``resolve_battle_round`` to keep that function's own branching
    within the McCabe complexity budget — this is purely a dispatch table, kept
    separate from round-level orchestration (declaration ordering, failure
    handling, Surrounded advancement).
    """
    if declaration.action_kind == BattleActionKind.STRIKE:
        _resolve_strike_success(declaration, result, success_level, place_defense_bonus)
    elif declaration.action_kind == BattleActionKind.RESCUE:
        _resolve_rescue_success(declaration)
    elif declaration.action_kind == BattleActionKind.ROUT:
        _resolve_rout_success(declaration, result, success_level)
    elif declaration.action_kind == BattleActionKind.RALLY:
        _resolve_rally_success(declaration, result, success_level)
    elif declaration.action_kind == BattleActionKind.REPEL:
        _resolve_repel_success(declaration, result, place_defense_bonus)
    elif declaration.action_kind == BattleActionKind.HOLD:
        _resolve_hold_success(declaration, result)
    elif declaration.action_kind == BattleActionKind.SUPPORT:
        _resolve_support_success(declaration, result)
    else:
        _resolve_support_success(declaration, result)


@transaction.atomic
def resolve_battle_round(*, battle_round: BattleRound) -> BattleRoundResult:
    """Resolve all unresolved declarations for ``battle_round``.

    For each unresolved declaration, casts its declared technique through
    ``resolve_battle_technique`` (the real magic envelope) and routes
    success / failure to the appropriate sub-handlers. Before marking the
    round complete, ticks every ACTIVE Surrounded participant's peril once
    via ``_advance_surrounded_participants`` (#1733) — gated by declaration
    this round or ``battle.afk_peril_override``. Sets
    ``battle_round.status = COMPLETED`` at the end.

    Args:
        battle_round: The ``BattleRound`` in DECLARING or RESOLVING status.

    Returns:
        A ``BattleRoundResult`` summarising what happened this round.
    """
    result = BattleRoundResult()

    declarations = list(
        battle_round.declarations.filter(resolved=False).select_related(
            "participant__character_sheet",
            "participant__side",
            "target_unit",
            "target_place",
            "target_side",
            "technique__action_template",
        )
    )
    # REPEL must resolve before every other action kind this round (#1712) — its
    # success populates place_defense_bonus in time for STRIKE to read it below.
    # A stable sort preserves every other kind's relative (declaration) order.
    declarations.sort(key=lambda d: 0 if d.action_kind == BattleActionKind.REPEL else 1)

    place_defense_bonus: dict[int, int] = {}
    newly_surrounded_participant_ids: set[int] = set()
    for declaration in declarations:
        check_result = resolve_battle_technique(declaration=declaration)
        sl = check_result.success_level if check_result is not None else 0

        if sl > 0:
            _dispatch_success_handler(declaration, result, sl, place_defense_bonus)
        elif _resolve_failure(declaration, result, sl):
            newly_surrounded_participant_ids.add(declaration.participant_id)

        declaration.resolved = True
        declaration.success_level = sl
        declaration.save(update_fields=["resolved", "success_level"])

    declared_participant_ids = {d.participant_id for d in declarations}
    _advance_surrounded_participants(
        battle_round.battle, declared_participant_ids, newly_surrounded_participant_ids
    )

    battle_round.status = RoundStatus.COMPLETED
    battle_round.completed_at = timezone.now()
    battle_round.save(update_fields=["status", "completed_at"])

    return result

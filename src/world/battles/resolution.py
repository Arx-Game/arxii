"""Battle round resolution engine.

Iterates all unresolved BattleActionDeclarations for a round, casts each
declaration's technique once via ``resolve_battle_technique``, then routes
the result:

- ``success_level > 0`` → STRIKE: attrite the target unit + award VP to the
  participant's side; SUPPORT: award SUPPORT_VP.
- ``success_level <= 0`` → debit PC health then call
  ``process_damage_consequences`` (non-progressive, SQLite-safe).

The ``BattleRoundResult`` dataclass carries per-side VP totals, routed/
destroyed unit lists, a casualty list, and (#1841) a per-unit swarm-body-loss
map for the caller to display or log.

This module also provides ``BattleTechniqueResolver`` and
``resolve_battle_technique``, which cast a declaration's ``technique`` through
the real magic envelope (``use_technique``). Routing through ``use_technique``
(rather than a generic shared check) means the check is sourced from
``resolve_cast_check_type`` — the caster's provisioned personal magic check
when they have one, falling back to the technique's
``action_template.check_type`` only for an unprovisioned caster (ADR-0096) —
anima/Soulfray/mishap apply normally, and Audere/Audere Majora escalation
fires automatically (it's wired inside ``use_technique`` itself, Step 8c — no
separate call site is needed here). ``resolve_battle_round`` calls
``resolve_battle_technique`` per declaration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
import math
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_POSTURE_CHECK_MODIFIER,
    BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER,
    BATTLE_POSTURE_VP_MULTIPLIER,
    MOVE_COST_DIFFICULTY_PER_POINT,
    ROUTED_MORALE_THRESHOLD,
    ROUTED_STRENGTH_THRESHOLD,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    UNIT_QUALITY_STRIKE_MODIFIER,
    BattleActionKind,
    BattleActionScope,
    BattleUnitStatus,
    swarm_strike_modifier,
)
from world.battles.exceptions import BattleError
from world.battles.models import BattleParticipant, BattleRound
from world.checks.services import perform_check
from world.scenes.constants import RoundStatus

# BREACH_INTEGRITY_PER_LEVEL/FORTIFY_INTEGRITY_PER_LEVEL/BREACH_VP_PER_LEVEL/FORTIFY_VP
# are imported lazily inside _resolve_breach_success/_resolve_fortify_success below,
# matching how ROUT_MORALE_PER_LEVEL/RALLY_MORALE_PER_LEVEL etc. are imported lazily
# inside _resolve_rout_success/_resolve_rally_success rather than at module level.

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from world.battles.models import (
        Battle,
        BattleActionDeclaration,
        BattlePlace,
        BattleSide,
        BattleUnit,
    )
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance
    from world.covenants.perks.context import SituationContext
    from world.magic.models import Technique
    from world.magic.types.power_ledger import PowerLedger
    from world.mechanics.types import HasCapabilities, HasProperties
    from world.weather.models import WeatherType


def _is_isolated(participant: BattleParticipant) -> bool:
    """True when no other ACTIVE participant on the same side shares this participant's place.

    A participant with no ``place`` assigned (front-agnostic) is never counted as
    isolated — isolation is specifically about being alone at a front, not merely
    unassigned. Reads battle.state_cache (#1846) instead of
    BattleParticipant.objects.filter().
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415

    if participant.place_id is None:
        return False
    others = participant.battle.state_cache.participants_on_place(
        participant.place_id, statuses=(BattleParticipantStatus.ACTIVE,)
    )
    return not any(p.side_id == participant.side_id and p.pk != participant.pk for p in others)


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

    movement = next(
        (
            c
            for c in CapabilityType.objects.cached_all()
            if c.name == FoundationalCapability.MOVEMENT
        ),
        None,
    )
    if movement is None:
        return False
    return get_effective_capability_value(character_sheet, movement) > 0


def _property_affinity_modifier(technique: Technique, holder: HasProperties) -> int:
    """Sum every TechniquePropertyAffinity row matching one of holder's properties (#1794).

    Returns 0 when no row matches — most techniques have no authored affinity,
    and that's the expected common case. Reads from cached_all() (#1846) — the
    whole table is small and admin-authored, so it's loaded once per process
    and filtered in Python rather than re-queried per declaration.
    """
    from world.battles.models import TechniquePropertyAffinity  # noqa: PLC0415

    rows = [
        r for r in TechniquePropertyAffinity.objects.cached_all() if r.technique_id == technique.pk
    ]
    return sum(row.modifier for row in rows if holder.has_property(row.property))


def _terrain_property_modifier(place: BattlePlace | None, holder: HasProperties) -> int:
    """Sum every TerrainPropertyEffect row matching one of holder's properties (#1794).

    Returns 0 when the unit has no place, or no row matches. Reads from
    cached_all() (#1846) — see _property_affinity_modifier for why.
    """
    from world.battles.models import TerrainPropertyEffect  # noqa: PLC0415

    if place is None:
        return 0
    rows = [
        r
        for r in TerrainPropertyEffect.objects.cached_all()
        if r.terrain_type == place.terrain_type
    ]
    return sum(row.modifier for row in rows if holder.has_property(row.property))


def effective_weather(place: BattlePlace | None) -> WeatherType | None:
    """Two-tier weather resolution (#1715): local place override -> battle
    override -> ambient (via Battle.region) -> None.

    Returns None when place is None (the unit has no place assigned) as well
    as when no tier resolves to a value.
    """
    from world.weather.services import get_effective_weather  # noqa: PLC0415

    if place is None:
        return None
    if place.weather_override is not None:
        return place.weather_override
    battle = place.battle
    if battle.weather_override is not None:
        return battle.weather_override
    if battle.region is not None:
        state = get_effective_weather(battle.region)
        return state.weather_type if state is not None else None
    return None


def _weather_property_modifier(place: BattlePlace | None, holder: HasProperties) -> int:
    """Sum every WeatherTypePropertyEffect row matching one of holder's properties (#1715).

    Returns 0 when there's no effective weather at place, or no row matches.
    Reads from cached_all() (#1846) — see _property_affinity_modifier for why.
    """
    from world.battles.models import WeatherTypePropertyEffect  # noqa: PLC0415

    weather_type = effective_weather(place)
    if weather_type is None:
        return 0
    rows = [
        r
        for r in WeatherTypePropertyEffect.objects.cached_all()
        if r.weather_type_id == weather_type.pk
    ]
    return sum(row.modifier for row in rows if holder.has_property(row.property))


def _weather_capability_modifier(place: BattlePlace | None, holder: HasCapabilities) -> int:
    """Sum every WeatherTypeCapabilityChallenge row where holder's capability magnitude
    is strictly below the authored threshold (#1715) — the first absence/threshold-based
    battle modifier in the codebase (everything else is presence- or >=-threshold based).

    Returns 0 when there's no effective weather at place, or no row applies.
    Reads from cached_all() (#1846) — see _property_affinity_modifier for why.
    """
    from world.battles.models import WeatherTypeCapabilityChallenge  # noqa: PLC0415

    weather_type = effective_weather(place)
    if weather_type is None:
        return 0
    rows = [
        r
        for r in WeatherTypeCapabilityChallenge.objects.cached_all()
        if r.weather_type_id == weather_type.pk
    ]
    return sum(
        row.modifier for row in rows if holder.effective_capability(row.capability) < row.threshold
    )


def _quality_modifier(quality: str) -> int:
    """Flat attacker-facing STRIKE modifier from the unit's quality tier (#1711)."""
    return UNIT_QUALITY_STRIKE_MODIFIER.get(quality, 0)


def commander_bonus_for_side_at_place(side: BattleSide, place: BattlePlace | None) -> int:
    """Max Battle Command modifier-walk bonus across commanded units on ``side`` at
    ``place`` (#1711). Max, not sum — multiple commanders present don't stack.
    Returns 0 when ``place`` is None or no ACTIVE unit on this side/place has a
    commander set. Reads battle.state_cache (#1846) instead of two separate
    queries (BattleUnit.objects.filter() + CharacterSheet.objects.filter()) —
    unit.commander is already a resolved FK on each cached unit.
    """
    from world.battles.factories import ensure_battle_command_modifier_target  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    if place is None:
        return 0
    units = side.battle.state_cache.units_on_place(place.pk, statuses=(BattleUnitStatus.ACTIVE,))
    commanders = {
        u.military_unit.commander
        for u in units
        if u.side_id == side.pk and u.military_unit.commander_id is not None
    }
    if not commanders:
        return 0
    target = ensure_battle_command_modifier_target()
    return max(get_modifier_total(sheet, target) for sheet in commanders)


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

    others = (
        battle.state_cache.participants_on_place(
            participant.place_id, statuses=(BattleParticipantStatus.ACTIVE,)
        )
        if participant.place_id is not None
        else []
    )
    opposing_pc_present = any(
        p.side_id != participant.side_id and p.character_sheet.character.db_account is not None
        for p in others
    )
    pool_name = (
        POOL_SURROUNDED_TERMINAL_PVP if opposing_pc_present else POOL_SURROUNDED_TERMINAL_ENEMY
    )
    return next((p for p in ConsequencePool.objects.cached_all() if p.name == pool_name), None)


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


def _battle_situation_ctx(character: ObjectDB, action_kind: str) -> SituationContext | None:
    """``SituationContext`` for a warfare-roll check/cast (#2536 slice 3 Battle wiring).

    ``None`` when ``character`` has no ``CharacterSheet`` — mirrors the guard
    ``world.missions.services._situation.mission_situation_ctx`` and
    ``checks.services._situational_perk_check_bonus`` apply to themselves, so a
    caster without a sheet stays byte-identical to the pre-#2536 default (no
    bonus, no penalty). ``holder``/``subject`` are both the caster's own sheet —
    a warfare roll has no distinct target sheet (``target=None``) and no
    combat/mission ``resolution`` object of its own (``resolution=None``); only
    ``battle_action_kind`` is populated, for ``battle_action_kind`` scope
    matching (``perks.services.perk_scope_matches``).
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (ObjectDoesNotExist, AttributeError):
        return None
    return SituationContext(
        holder=sheet,
        subject=sheet,
        target=None,
        resolution=None,
        battle_action_kind=action_kind,
    )


@dataclass
class BattleTechniqueResolution:
    """Adapts ``use_technique``'s resolve_fn contract — exposes ``.check_result``
    for ``_resolve_check_result`` (``world/magic/services/techniques.py``)."""

    check_result: CheckResult


@dataclass
class BattleTechniqueResolver:
    """``resolve_fn`` passed to ``use_technique``: rolls the declared technique's
    own check, folding in the full battle modifier stack (Property affinity,
    terrain, weather property/capability, unit quality, swarm-count band bonus,
    commander bonus, posture — #1711/#1794/#1715/#1841). Battle has no
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
        from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415

        check_type = resolve_cast_check_type(self.character, self.technique.action_template)
        total_modifiers = extra_modifiers + self._battle_modifier_stack()
        situation_ctx = _battle_situation_ctx(self.character, self.declaration.action_kind)
        check_result = perform_check(
            self.character,
            check_type,
            extra_modifiers=total_modifiers,
            situation_ctx=situation_ctx,
        )
        return BattleTechniqueResolution(check_result=check_result)

    def _battle_modifier_stack(self) -> int:
        """Sum every modifier source relevant to this declaration (#1711/#1794/#1715/#1841)."""
        participant = self.declaration.participant
        unit = self.declaration.target_unit

        property_affinity = (
            _property_affinity_modifier(self.technique, unit) if unit is not None else 0
        )
        terrain = _terrain_property_modifier(unit.place, unit) if unit is not None else 0
        weather_property = _weather_property_modifier(unit.place, unit) if unit is not None else 0
        weather_capability = (
            _weather_capability_modifier(unit.place, unit) if unit is not None else 0
        )
        quality = _quality_modifier(unit.quality) if unit is not None else 0
        swarm_modifier = swarm_strike_modifier(unit.individual_count) if unit is not None else 0
        commander = commander_bonus_for_side_at_place(participant.side, participant.place)
        posture = BATTLE_POSTURE_CHECK_MODIFIER.get(participant.side.posture, 0)
        move_cost = (
            -self.declaration.target_place.movement_cost * MOVE_COST_DIFFICULTY_PER_POINT
            if self.declaration.action_kind == BattleActionKind.MOVE
            and self.declaration.target_place is not None
            else 0
        )

        return (
            property_affinity
            + terrain
            + weather_property
            + weather_capability
            + quality
            + swarm_modifier
            + commander
            + posture
            + move_cost
        )


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
        situation_ctx=_battle_situation_ctx(character, declaration.action_kind),
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
    # BattleUnit pk -> swarm-style individual_count bodies lost this round (#1841).
    # Only swarm-style units (individual_count not None) ever appear here — a
    # non-swarm unit that takes STRIKE/ROUT attrition is never added, even with an
    # entry of 0 (mirrors units_destroyed/units_routed only appending on a real
    # status flip, not every attrited unit).
    unit_losses: dict[int, int] = field(default_factory=dict)


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
    units are never included (gone, not rallyable). Reads battle.state_cache (#1846)
    instead of BattleUnit.objects.filter()."""
    from world.battles.constants import BattleActionScope, BattleUnitStatus  # noqa: PLC0415

    statuses = (
        (BattleUnitStatus.ACTIVE, BattleUnitStatus.ROUTED)
        if include_routed
        else (BattleUnitStatus.ACTIVE,)
    )
    battle = declaration.battle_round.battle
    if declaration.scope == BattleActionScope.SIDE and declaration.target_side_id:
        return battle.state_cache.units_on_side(declaration.target_side_id, statuses=statuses)
    if declaration.scope == BattleActionScope.PLACE and declaration.target_place_id:
        return battle.state_cache.units_on_place(declaration.target_place_id, statuses=statuses)
    return [declaration.target_unit] if declaration.target_unit is not None else []


def _scope_target_participants(declaration: BattleActionDeclaration) -> list:
    """Active BattleParticipants affected by *declaration*, per its scope (#1710).
    Reads battle.state_cache (#1846) instead of BattleParticipant.objects.filter()."""
    from world.battles.constants import BattleActionScope, BattleParticipantStatus  # noqa: PLC0415

    statuses = (BattleParticipantStatus.ACTIVE,)
    battle = declaration.battle_round.battle
    if declaration.scope == BattleActionScope.SIDE and declaration.target_side_id:
        return battle.state_cache.participants_on_side(
            declaration.target_side_id, statuses=statuses
        )
    if declaration.scope == BattleActionScope.PLACE and declaration.target_place_id:
        return battle.state_cache.participants_on_place(
            declaration.target_place_id, statuses=statuses
        )
    return [declaration.target_ally] if declaration.target_ally is not None else []


def _apply_swarm_losses(unit: BattleUnit, attrition: int) -> int:
    """Bodies a swarm-style unit loses proportional to this round's attrition (#1841).

    Returns 0 untouched for a non-swarm unit (``individual_count`` is None) or
    non-positive ``attrition`` — no save happens in either case. Otherwise loses
    ``ceil(individual_count * attrition / 100)`` bodies (strength/morale are both
    0-100 scales, so ``attrition`` reads directly as a percentage), floored at 0,
    and persists the new ``individual_count``. Ceil-rounding means any nonzero
    attrition against a swarm always costs at least one body.
    """
    if unit.military_unit.individual_count is None or attrition <= 0:
        return 0
    lost = min(
        unit.military_unit.individual_count,
        math.ceil(unit.military_unit.individual_count * attrition / 100),
    )
    unit.military_unit.individual_count = max(0, unit.military_unit.individual_count - lost)
    unit.military_unit.save(update_fields=["individual_count"])
    return lost


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
    before applying, floored at 0. That net attrition also drives
    ``_apply_swarm_losses`` (#1841) — a swarm-style target loses bodies
    proportional to the same net attrition strength took this round.
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
        unit.military_unit.strength = max(0, unit.military_unit.strength - net_attrition)
        unit.status = _compute_unit_status(unit.military_unit.strength, unit.military_unit.morale)
        if unit.status == BattleUnitStatus.DESTROYED:
            result.units_destroyed.append(unit.pk)
        elif unit.status == BattleUnitStatus.ROUTED:
            result.units_routed.append(unit.pk)
        unit.save(update_fields=["status"])
        unit.military_unit.save(update_fields=["strength"])

        bodies_lost = _apply_swarm_losses(unit, net_attrition)
        if bodies_lost:
            result.unit_losses[unit.pk] = result.unit_losses.get(unit.pk, 0) + bodies_lost

        if unit.status == BattleUnitStatus.DESTROYED:
            from world.battles.services import eject_vehicle_occupants  # noqa: PLC0415

            # is_structural=False only (#1714): a living mount's own BattleUnit
            # destroyed IS the mount going down, so occupants eject immediately.
            # A structural vehicle's (ship/airship) unit represents crew/guns —
            # it can be destroyed/routed (fought to a standstill) without the
            # hull sinking, exactly as a land Fortification's defenders routing
            # doesn't auto-breach the wall. Structural vehicles only eject
            # occupants via a hull Fortification breach (see BREACH handling),
            # never from this unit-destruction path. This asymmetry is
            # intentional, not a gap. Reads battle.state_cache (#1846) instead
            # of BattleVehicle.objects.filter().
            vehicle = unit.battle.state_cache.vehicle_for_unit(unit.pk)
            if vehicle is not None and not vehicle.is_structural:
                eject_vehicle_occupants(vehicle=vehicle)

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

    A swarm-style unit also loses bodies proportional to the *actual* morale
    lost this round (#1841) — the morale floor at 0 can make that less than
    ``morale_damage``, so ``_apply_swarm_losses`` is fed the real delta, not the
    raw computed damage.
    """
    from world.battles.constants import ROUT_MORALE_PER_LEVEL, ROUT_VP_PER_LEVEL  # noqa: PLC0415

    units = _scope_target_units(declaration)
    units = [u for u in units if u.side_id != declaration.participant.side_id]
    if not units:
        return

    morale_damage = success_level * ROUT_MORALE_PER_LEVEL
    for unit in units:
        previous_morale = unit.military_unit.morale
        unit.military_unit.morale = max(0, unit.military_unit.morale - morale_damage)
        actual_morale_loss = previous_morale - unit.military_unit.morale
        unit.status = _compute_unit_status(unit.military_unit.strength, unit.military_unit.morale)
        if unit.status == BattleUnitStatus.DESTROYED:
            result.units_destroyed.append(unit.pk)
        elif unit.status == BattleUnitStatus.ROUTED:
            result.units_routed.append(unit.pk)
        unit.save(update_fields=["status"])
        unit.military_unit.save(update_fields=["morale"])

        bodies_lost = _apply_swarm_losses(unit, actual_morale_loss)
        if bodies_lost:
            result.unit_losses[unit.pk] = result.unit_losses.get(unit.pk, 0) + bodies_lost

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
        unit.military_unit.morale = min(MAX_MORALE, unit.military_unit.morale + morale_gain)
        unit.status = _compute_unit_status(unit.military_unit.strength, unit.military_unit.morale)
        unit.save(update_fields=["status"])
        unit.military_unit.save(update_fields=["morale"])

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


def _resolve_reposition_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,  # noqa: ARG001 — no VP awarded for movement
    success_level: int,  # noqa: ARG001 — movement is capability-bounded, not margin-scaled
) -> None:
    """Apply REPOSITION success: move the target vehicle's place by up to its
    SPEED capability magnitude toward the declared delta (#1714).

    Distance moved this round is bounded by min(requested distance, SPEED
    capability value). success_level scaling is intentionally NOT applied here —
    unlike STRIKE/BREACH, movement is capability-bounded, not check-margin-scaled;
    success_level only determines whether the move happens at all (the check
    already gates that via resolve_battle_technique).
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    place = declaration.target_place
    vehicle = place.vehicle_or_none
    if vehicle is None:
        return
    dx = declaration.reposition_dx or 0
    dy = declaration.reposition_dy or 0
    requested_distance = (dx * dx + dy * dy) ** Decimal("0.5") if (dx or dy) else Decimal(0)
    if requested_distance == 0:
        return

    speed_capability = next(
        (
            c
            for c in CapabilityType.objects.cached_all()
            if c.name == "speed"  # noqa: STRING_LITERAL
        ),
        None,
    )
    max_distance = Decimal(
        vehicle.unit.effective_capability(speed_capability) if speed_capability else 0
    )
    if requested_distance > max_distance:
        scale = max_distance / requested_distance
        dx *= scale
        dy *= scale

    place.x += dx
    place.y += dy
    place.save(update_fields=["x", "y"])


def _withdraw_move_mover(
    participant: BattleParticipant, mover: BattleParticipant | BattleUnit
) -> None:
    """Withdraw ``mover`` from the battle (#2007) — target_place=None branch of
    ``_resolve_move_success``, split out to keep that function under the
    PLR0915 statement budget. UNIT scope only (validated at declare time by
    ``declare_battle_action``): a commander PLACE-scope order can never withdraw
    a unit, only move it between fronts.
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415

    old_place_id = mover.place_id
    mover.place = None
    mover.status = BattleParticipantStatus.WITHDRAWN
    mover.transit_x = None
    mover.transit_y = None
    mover.transit_target_place = None
    mover.save(update_fields=["place", "status", "transit_x", "transit_y", "transit_target_place"])
    participant.battle.state_cache.move_participant_place(mover, old_place_id=old_place_id)


def _advance_move_mover(
    participant: BattleParticipant,
    mover: BattleParticipant | BattleUnit,
    target: BattlePlace,
    *,
    is_self_move: bool,
) -> None:
    """Advance ``mover`` toward ``target`` by up to its effective MOVEMENT capability
    magnitude (#2007) — the target_place-set branch of ``_resolve_move_success``,
    split out to keep that function under the PLR0915 statement budget.

    Distance moved this round is bounded by min(distance to target, effective
    MOVEMENT capability), mirroring REPOSITION's SPEED-bounded movement
    (``_resolve_reposition_success``). Arrival (remaining distance <=
    max_distance) flips ``.place`` to ``target`` and clears transit state;
    otherwise the new intermediate position persists on transit_x/transit_y
    and the mover must redeclare MOVE next round to keep progressing — same
    redeclare-per-round precedent REPOSITION already established.
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    if mover.transit_x is not None and mover.transit_y is not None:
        current_x, current_y = mover.transit_x, mover.transit_y
    elif mover.place is not None:
        current_x, current_y = mover.place.x, mover.place.y
    else:
        current_x, current_y = Decimal(0), Decimal(0)

    dx = target.x - current_x
    dy = target.y - current_y
    distance = (dx * dx + dy * dy) ** Decimal("0.5")

    capability_type = next(
        (
            c
            for c in CapabilityType.objects.cached_all()
            if c.name == FoundationalCapability.MOVEMENT
        ),
        None,
    )
    if capability_type is None:
        max_distance = Decimal(0)
    elif is_self_move:
        max_distance = Decimal(
            get_effective_capability_value(participant.character_sheet, capability_type)
        )
    else:
        max_distance = Decimal(mover.effective_capability(capability_type))

    if distance <= max_distance:
        old_place_id = mover.place_id
        mover.place = target
        mover.transit_x = None
        mover.transit_y = None
        mover.transit_target_place = None
        mover.save(update_fields=["place", "transit_x", "transit_y", "transit_target_place"])
        if is_self_move:
            participant.battle.state_cache.move_participant_place(mover, old_place_id=old_place_id)
        else:
            participant.battle.state_cache.move_unit_place(mover, old_place_id=old_place_id)
        return

    if distance > 0:
        scale = max_distance / distance
        current_x += dx * scale
        current_y += dy * scale
    mover.transit_x = current_x
    mover.transit_y = current_y
    mover.transit_target_place = target
    mover.save(update_fields=["transit_x", "transit_y", "transit_target_place"])


def _resolve_move_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,  # noqa: ARG001 — no VP awarded for movement
    success_level: int,  # noqa: ARG001 — movement is capability-bounded, not margin-scaled
) -> None:
    """Apply MOVE success: advance the mover toward target_place by up to its
    effective MOVEMENT capability magnitude, or withdraw it from the battle (#2007).

    The mover is the declaring participant (scope=UNIT, self-move) or the
    commander-ordered declaration.target_unit (scope=PLACE) — never both.
    target_place=None means withdrawal (UNIT scope only, validated at declare
    time by declare_battle_action) — see ``_withdraw_move_mover``. Otherwise
    the mover advances toward target_place — see ``_advance_move_mover``.
    """
    participant = declaration.participant
    is_self_move = declaration.scope == BattleActionScope.UNIT
    mover = participant if is_self_move else declaration.target_unit
    if mover is None:
        return

    if declaration.target_place is None:
        _withdraw_move_mover(participant, mover)
        return

    _advance_move_mover(participant, mover, declaration.target_place, is_self_move=is_self_move)


def _resolve_breach_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply BREACH success: attrite the target Fortification's integrity, award VP
    (#1713). Ownership is enforced at declare time (FortificationOwnershipMismatchError)
    — this handler trusts target_fortification is set and legally targeted.
    """
    from world.battles.constants import (  # noqa: PLC0415
        BREACH_INTEGRITY_PER_LEVEL,
        BREACH_VP_PER_LEVEL,
        FortificationKind,
    )

    fort = declaration.target_fortification
    if fort is None:
        return

    damage = success_level * BREACH_INTEGRITY_PER_LEVEL
    fort.integrity = max(0, fort.integrity - damage)
    if fort.integrity == 0:
        fort.breached = True
    fort.save(update_fields=["integrity", "breached"])

    if fort.breached and fort.kind == FortificationKind.HULL:
        from world.battles.services import eject_vehicle_occupants  # noqa: PLC0415

        # Reads battle.state_cache (#1846) instead of BattleVehicle.objects.filter().
        vehicle = fort.place.battle.state_cache.vehicle_at_place(fort.place_id)
        if vehicle is not None:
            eject_vehicle_occupants(vehicle=vehicle)

    side = declaration.participant.side
    base_vp = success_level * BREACH_VP_PER_LEVEL
    vp_gain = round(base_vp * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_fortify_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply FORTIFY success: restore the target Fortification's integrity (capped at
    max_integrity), award flat VP (#1713). Ownership is enforced at declare time.
    """
    from world.battles.constants import FORTIFY_INTEGRITY_PER_LEVEL, FORTIFY_VP  # noqa: PLC0415

    fort = declaration.target_fortification
    if fort is None:
        return

    restore = success_level * FORTIFY_INTEGRITY_PER_LEVEL
    fort.integrity = min(fort.max_integrity, fort.integrity + restore)
    fort.save(update_fields=["integrity"])

    side = declaration.participant.side
    vp_gain = round(FORTIFY_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_environment_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
    round_number: int,
) -> None:
    """Apply SET_ENVIRONMENT success: set the cast weather at the declared scope,
    award flat VP (#1715).

    BATTLE scope writes Battle.weather_override (the battle-wide default);
    PLACE scope writes a local exception on the target BattlePlace that beats
    the battle-wide value there only (see resolution.effective_weather).
    Duration scales with success_level so a stronger cast holds longer — see
    SET_ENVIRONMENT_BASE_ROUNDS's docstring for the >= 2 round guarantee.
    """
    from world.battles.constants import (  # noqa: PLC0415
        SET_ENVIRONMENT_BASE_ROUNDS,
        SET_ENVIRONMENT_VP,
        BattleActionScope,
    )

    weather_type = declaration.technique.target_weather_type
    expires_round = round_number + SET_ENVIRONMENT_BASE_ROUNDS + success_level

    if declaration.scope == BattleActionScope.BATTLE:
        battle = declaration.battle_round.battle
        battle.weather_override = weather_type
        battle.weather_override_expires_round = expires_round
        battle.save(update_fields=["weather_override", "weather_override_expires_round"])
    else:
        place = declaration.target_place
        place.weather_override = weather_type
        place.weather_override_expires_round = expires_round
        place.save(update_fields=["weather_override", "weather_override_expires_round"])

    side = declaration.participant.side
    vp_gain = round(SET_ENVIRONMENT_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(side.posture, 1.0))
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

    try:
        template = ConditionTemplate.get_by_name(SURROUNDED_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
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

    pool = next(
        (p for p in ConsequencePool.objects.cached_all() if p.name == POOL_SURROUNDED_ENTRY),
        None,
    )
    try:
        template = ConditionTemplate.get_by_name(SURROUNDED_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        template = None
    entry_stage = (
        next(
            (
                s
                for s in ConditionStage.objects.cached_all()
                if s.condition_id == template.pk and s.stage_order == 1
            ),
            None,
        )
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

    try:
        template = ConditionTemplate.get_by_name(SURROUNDED_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
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
    round_number: int,
) -> None:
    """Route a successful declaration to its action-kind-specific resolver (#1712/#1715).

    Extracted from ``resolve_battle_round`` to keep that function's own branching
    within the McCabe complexity budget — this is purely a dispatch table, kept
    separate from round-level orchestration (declaration ordering, failure
    handling, Surrounded advancement). A dict-of-closures (rather than an
    if/elif chain) keeps this function's own complexity flat as action kinds
    are added — each handler takes a different subset of the shared locals, so
    the dict maps to zero-arg closures rather than the handlers directly.
    """
    handlers: dict[str, Callable[[], None]] = {
        BattleActionKind.STRIKE: lambda: _resolve_strike_success(
            declaration, result, success_level, place_defense_bonus
        ),
        BattleActionKind.RESCUE: lambda: _resolve_rescue_success(declaration),
        BattleActionKind.ROUT: lambda: _resolve_rout_success(declaration, result, success_level),
        BattleActionKind.RALLY: lambda: _resolve_rally_success(declaration, result, success_level),
        BattleActionKind.REPEL: lambda: _resolve_repel_success(
            declaration, result, place_defense_bonus
        ),
        BattleActionKind.HOLD: lambda: _resolve_hold_success(declaration, result),
        BattleActionKind.SET_ENVIRONMENT: lambda: _resolve_environment_success(
            declaration, result, success_level, round_number
        ),
        BattleActionKind.SUPPORT: lambda: _resolve_support_success(declaration, result),
        BattleActionKind.BREACH: lambda: _resolve_breach_success(
            declaration, result, success_level
        ),
        BattleActionKind.FORTIFY: lambda: _resolve_fortify_success(
            declaration, result, success_level
        ),
        BattleActionKind.REPOSITION: lambda: _resolve_reposition_success(
            declaration, result, success_level
        ),
        BattleActionKind.MOVE: lambda: _resolve_move_success(declaration, result, success_level),
    }
    handler = handlers.get(
        declaration.action_kind, lambda: _resolve_support_success(declaration, result)
    )
    handler()


def _block_if_participant_mid_audere_majora_crossing(battle: Battle) -> None:
    """Hard, unconditional block (#1899): a round must never resolve while an
    active participant is mid-Audere-Majora-crossing, regardless of
    ``battle.is_paused`` — that flag is a separate, softer disconnect-pause
    concern. Extracted (mirrors ``world.combat.services``'s sibling helper)
    so the caller-side query cost is independently testable.
    """
    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.magic.audere_majora import (  # noqa: PLC0415
        any_character_mid_audere_majora_crossing,
    )

    active_sheets = [
        p.character_sheet
        for p in battle.participants.filter(status=BattleParticipantStatus.ACTIVE).select_related(
            "character_sheet"
        )
    ]
    if any_character_mid_audere_majora_crossing(active_sheets):
        # Shares the exact user-facing string with the combat-side hard block
        # (actions/errors.py's ActionDispatchError.PARTICIPANT_MID_CROSSING) —
        # one message, two error types (BattleError vs ActionDispatchError)
        # because the battles/combat exception hierarchies are independent.
        raise BattleError(
            user_message=ActionDispatchError(
                ActionDispatchError.PARTICIPANT_MID_CROSSING
            ).user_message
        )


def _process_companion_orders(battle_round: BattleRound) -> list:
    """Create BattleActionDeclarations for ordered companion vehicles (#1921).

    For each companion vehicle with an ATTACK_TARGET order this round, creates
    a declaration with the player as participant and the companion vehicle's
    unit as the target. HOLD orders are skipped (no declaration created).
    DEFEND_ALLY is handled via the damage-interception path, not here.
    """
    from world.battles.constants import BattleActionKind  # noqa: PLC0415
    from world.battles.models import BattleActionDeclaration  # noqa: PLC0415
    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415
    from world.companions.models import CompanionDeployment, CompanionOrder  # noqa: PLC0415

    orders = list(
        CompanionOrder.objects.filter(
            battle=battle_round.battle,
            round_number=battle_round.round_number,
        ).select_related("companion", "ability", "ability__technique", "target_unit")
    )
    if not orders:
        return []

    declarations = []
    for order in orders:
        if order.order_kind == CompanionOrderKind.HOLD:
            continue

        try:
            CompanionDeployment.objects.select_related(
                "vehicle__unit",
            ).get(companion=order.companion, battle=battle_round.battle)
        except CompanionDeployment.DoesNotExist:
            continue

        if order.order_kind == CompanionOrderKind.ATTACK_TARGET:
            technique = (
                order.ability.technique if order.ability and order.ability.technique else None
            )
            if technique is None or order.target_unit is None:
                continue

            # Find the participant (the ordering player)
            participant = battle_round.battle.participants.filter(
                character_sheet=order.companion.owner,
            ).first()
            if participant is None:
                continue

            decl = BattleActionDeclaration.objects.create(
                battle_round=battle_round,
                participant=participant,
                technique=technique,
                action_kind=BattleActionKind.STRIKE,
                target_unit=order.target_unit,
            )
            declarations.append(decl)

    return declarations


@transaction.atomic
def resolve_battle_round(*, battle_round: BattleRound) -> BattleRoundResult:
    """Resolve all unresolved declarations for ``battle_round``.

    Before any declaration resolves, clears any battle- or place-level
    weather override whose ``weather_override_expires_round`` has passed
    (round-boundary weather expiry, #1715). For each unresolved declaration,
    casts its declared technique through ``resolve_battle_technique`` (the
    real magic envelope) and routes success / failure to the appropriate
    sub-handlers. Before marking the round complete, ticks every ACTIVE
    Surrounded participant's peril once via
    ``_advance_surrounded_participants`` (#1733) — gated by declaration
    this round or ``battle.afk_peril_override``. Sets
    ``battle_round.status = COMPLETED`` at the end, then pings connected
    participants via ``notify_battle_state_changed`` (#2009), deferred via
    ``transaction.on_commit`` so it fires only once this transaction commits.

    Args:
        battle_round: The ``BattleRound`` in DECLARING or RESOLVING status.

    Returns:
        A ``BattleRoundResult`` summarising what happened this round.
    """
    _block_if_participant_mid_audere_majora_crossing(battle_round.battle)

    result = BattleRoundResult()

    declarations = list(
        battle_round.declarations.filter(resolved=False).select_related(
            "participant__character_sheet__character",
            "participant__character_sheet",
            "participant__side",
            "participant__place",
            "participant__transit_target_place",
            "target_unit",
            "target_unit__place",
            "target_unit__transit_target_place",
            "target_place",
            "target_side",
            "target_fortification",
            "technique__action_template",
            "technique__target_weather_type",
        )
    )
    # Round-boundary weather expiry (#1715) — clear before any declaration
    # resolves, including this round's own SET_ENVIRONMENT casts (a fresh cast's
    # expires_round is always round_number + at least 2, so it can never be
    # cleared by this same check in the round it's cast).
    battle = battle_round.battle
    if (
        battle.weather_override_expires_round is not None
        and battle.weather_override_expires_round < battle_round.round_number
    ):
        battle.weather_override = None
        battle.weather_override_expires_round = None
        battle.save(update_fields=["weather_override", "weather_override_expires_round"])

    for place in battle.places.filter(weather_override_expires_round__lt=battle_round.round_number):
        place.weather_override = None
        place.weather_override_expires_round = None
        place.save(update_fields=["weather_override", "weather_override_expires_round"])

    # REPEL and SET_ENVIRONMENT must resolve before every other action kind this
    # round (#1712/#1715) — REPEL's success populates place_defense_bonus, and
    # SET_ENVIRONMENT's success sets weather, both in time for STRIKE to read
    # them below. A stable sort preserves every other kind's relative order.
    place_defense_bonus: dict[int, int] = {}
    newly_surrounded_participant_ids: set[int] = set()

    # --- Companion order processing (#1921) ---
    # Create BattleActionDeclarations for ordered companion vehicles before
    # the main iteration so they resolve alongside player declarations.
    _companion_decls = _process_companion_orders(battle_round)
    declarations.extend(_companion_decls)
    declarations.sort(
        key=lambda d: 0
        if d.action_kind in (BattleActionKind.REPEL, BattleActionKind.SET_ENVIRONMENT)
        else 1
    )

    for declaration in declarations:
        check_result = resolve_battle_technique(declaration=declaration)
        sl = check_result.success_level if check_result is not None else 0

        if sl > 0:
            _dispatch_success_handler(
                declaration, result, sl, place_defense_bonus, battle_round.round_number
            )
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

    from world.battles.services import notify_battle_state_changed  # noqa: PLC0415

    transaction.on_commit(lambda: notify_battle_state_changed(battle))

    return result

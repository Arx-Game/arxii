"""Service functions for the battles system.

All public functions are the only permitted entry points for battle state
mutations. Callers (actions, commands, views) must not write to battle models
directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from web.webclient.message_types import BattleStatePayload
from world.battles.beat_wiring import activate_stakes_for_battle, resolve_battle_beats
from world.battles.conclusion_hooks import run_battle_conclusion_hooks
from world.battles.constants import (
    BASE_INTEGRITY,
    DECISIVE_MARGIN,
    DEFAULT_MORALE,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    FORTIFICATION_LEVEL_INTEGRITY_BONUS,
    LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD,
    VEHICLE_HAZARD_BASE_DAMAGE,
    VEHICLE_HAZARD_UNIT_STRENGTH_PENALTY,
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.exceptions import (
    BattleConcludedError,
    CannotStrikeOwnSideError,
    CharacterDoesNotKnowTechniqueError,
    FortificationAlreadyBreachedError,
    FortificationOwnershipMismatchError,
    FortificationTargetRequiredError,
    InsufficientCommandTierError,
    InvalidEnvironmentScopeError,
    InvalidMoveScopeError,
    MissingEnvironmentTargetError,
    MissingScopeTargetError,
    MoveOrderRequiresTargetUnitError,
    NoCommandHierarchyError,
    NotAChampionError,
    NotVehicleCommanderError,
    PlaceAlreadyDuelingError,
    PlaceScopeRequiredError,
    PlacesDoNotOverlapError,
    RoundNotOpenError,
    TechniqueNotBattleReadyError,
)
from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
    BattleVehicle,
    Fortification,
)
from world.combat.constants import OpponentTier, RiskLevel
from world.conditions.models import CapabilityType
from world.mechanics.models import Property
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.buildings.models import Building
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.conditions.models import DamageType
    from world.covenants.models import Covenant
    from world.magic.models import Technique
    from world.stories.models import Story


# ---------------------------------------------------------------------------
# Setup services
# ---------------------------------------------------------------------------


@transaction.atomic
def create_battle(
    *,
    name: str,
    campaign_story: Story | None = None,
    round_limit: int = DEFAULT_ROUND_LIMIT,
    risk_level: str = RiskLevel.LOW,
) -> Battle:
    """Create a new Battle (and its backing Scene).

    Args:
        name: Human-readable name for the battle.
        campaign_story: Optional parent Story this battle belongs to.
        round_limit: Maximum number of rounds before auto-conclusion.
        risk_level: Stakes level for companion death-gating (#1873).

    Returns:
        The newly created ``Battle`` instance.
    """
    battle = Battle(
        name=name,
        campaign_story=campaign_story,
        round_limit=round_limit,
        risk_level=risk_level,
    )
    battle.save()  # Battle.save() auto-creates the backing Scene
    return battle


@transaction.atomic
def add_side(
    *,
    battle: Battle,
    role: str,
    victory_threshold: int = DEFAULT_VICTORY_THRESHOLD,
    covenant: Covenant | None = None,
) -> BattleSide:
    """Add a side (attacker or defender) to a battle.

    Args:
        battle: The ``Battle`` to add the side to.
        role: A ``BattleSideRole`` value.
        victory_threshold: VP total required for this side to win.
        covenant: Optional War Covenant fielding this side (#1710).

    Returns:
        The newly created ``BattleSide``.
    """
    return BattleSide.objects.create(
        battle=battle,
        role=role,
        victory_threshold=victory_threshold,
        covenant=covenant,
    )


@transaction.atomic
def add_place(  # noqa: PLR0913 - each param is a distinct place attribute
    *,
    battle: Battle,
    name: str,
    terrain_type: str = TerrainType.OPEN,
    movement_cost: int = 1,
    x: Decimal = Decimal(0),
    y: Decimal = Decimal(0),
    footprint_radius: Decimal = Decimal(1),
) -> BattlePlace:
    """Add a named front/zone to a battle.

    Args:
        battle: The ``Battle`` to add the place to.
        name: Human-readable name for the front (e.g. "The Main Gates").
        terrain_type: A ``TerrainType`` value (#1711). Defaults to OPEN.
        movement_cost: Authored cost for a future reposition/movement action —
            not yet filed as an issue; #1712 explicitly did not build this
            (#1711). Defaults to 1.
        x: Position on the battle's internal battle-map coordinate plane (#1714).
            Defaults to 0.
        y: See ``x``. Defaults to 0.
        footprint_radius: How much of the battle-map grid this place occupies
            (#1714). Defaults to 1.

    Returns:
        The newly created ``BattlePlace``.
    """
    return BattlePlace.objects.create(
        battle=battle,
        name=name,
        terrain_type=terrain_type,
        movement_cost=movement_cost,
        x=x,
        y=y,
        footprint_radius=footprint_radius,
    )


@transaction.atomic
def add_unit(  # noqa: PLR0913 - each param is a distinct unit attribute
    *,
    battle: Battle,
    side: BattleSide,
    name: str,
    descriptor: str = "",
    quality: str = UnitQuality.TRAINED,
    commander: CharacterSheet | None = None,
    summoned_by: CharacterSheet | None = None,
    strength: int = 100,
    morale: int = DEFAULT_MORALE,
    place: BattlePlace | None = None,
    properties: Iterable[Property] = (),
    capability_values: Iterable[tuple[CapabilityType, int]] = (),
    individual_count: int | None = None,
) -> BattleUnit:
    """Add an abstract typed unit to a battle side.

    Creates a MilitaryUnit (persistent source of truth) and a BattleUnit
    (thin join referencing it). All identity and stats live on MilitaryUnit.

    Args:
        battle: The owning ``Battle``.
        side: The ``BattleSide`` this unit belongs to.
        name: Display name for this unit (e.g. "Cavalry").
        descriptor: Optional flavor tag (e.g. "zombies-on-nightmares"); narrative only.
        quality: A ``UnitQuality`` value (#1711). Defaults to TRAINED.
        commander: Optional commanding ``CharacterSheet`` (#1711).
        summoned_by: Optional summoning ``CharacterSheet``, set by the military-summon
            bridge (#1711).
        strength: Starting strength value (default 100).
        morale: Starting morale value (default DEFAULT_MORALE, #1712).
        place: Optional ``BattlePlace`` this unit is stationed at.
        properties: Property tags to attach (#1794) — presence-only.
        capability_values: (CapabilityType, magnitude) pairs to attach (#1794) —
            each becomes a MilitaryUnitCapability row.
        individual_count: Optional population data point (#1794); mirrors
            CombatOpponent.swarm_count's naming. Drives banded STRIKE bonuses and
            proportional STRIKE/ROUT body loss (#1841) — see
            world.battles.constants.swarm_strike_modifier and
            world.battles.resolution._apply_swarm_losses.

    Returns:
        The newly created ``BattleUnit``.
    """
    from world.military.models import MilitaryUnit, MilitaryUnitCapability  # noqa: PLC0415

    # Apply war-funding bonuses if the side has a covenant (#1890).
    if side.covenant_id is not None:
        from world.battles.war_funding_services import (  # noqa: PLC0415
            _apply_quality_steps,
            get_war_funding_bonus,
        )

        bonus = get_war_funding_bonus(side.covenant)
        quality = _apply_quality_steps(quality, bonus.quality_steps)
        strength += bonus.strength_bonus
        morale += bonus.morale_bonus

    # Apply provisioning penalty if the side's covenant has a shortfall (#2375).
    if side.covenant_id is not None:
        covenant = side.covenant
        if covenant.provisioning_ratio is not None and covenant.provisioning_ratio < 1.0:
            from world.agriculture.services import get_food_config  # noqa: PLC0415

            config = get_food_config()
            shortfall = 1.0 - covenant.provisioning_ratio
            morale = max(1, morale - round(shortfall * config.max_provisioning_morale_penalty))
            strength = max(
                1,
                strength - round(shortfall * config.max_provisioning_strength_penalty),
            )

    mu = MilitaryUnit.objects.create(
        name=name,
        descriptor=descriptor,
        quality=quality,
        commander=commander,
        summoned_by=summoned_by,
        strength=strength,
        morale=morale,
        individual_count=individual_count,
    )
    mu.properties.set(properties)
    MilitaryUnitCapability.objects.bulk_create(
        MilitaryUnitCapability(unit=mu, capability=capability, value=value)
        for capability, value in capability_values
    )
    return BattleUnit.objects.create(
        battle=battle,
        side=side,
        status=BattleUnitStatus.ACTIVE,
        place=place,
        military_unit=mu,
    )


@transaction.atomic
def create_fortification(
    *,
    place: BattlePlace,
    defending_side: BattleSide,
    kind: str = FortificationKind.WALL,
    building: Building | None = None,
    max_integrity: int | None = None,
) -> Fortification:
    """Create a Fortification at *place*, snapshotting its integrity ceiling (#1713).

    max_integrity is computed once, at creation, from BASE_INTEGRITY[kind] plus
    building.fortification_level * FORTIFICATION_LEVEL_INTEGRITY_BONUS if a
    persistent building is provided — mirroring how Building itself snapshots
    target_size/target_grandeur once from its founding Project. A Fortification
    with no building (building=None) is an ad-hoc structure with no persistent
    investment behind it; max_integrity is just BASE_INTEGRITY[kind].

    Args:
        place: The BattlePlace this structure defends.
        defending_side: The BattleSide this structure protects (gates BREACH/
            FORTIFY ownership — see declare_battle_action).
        kind: A FortificationKind value. Defaults to WALL.
        building: Optional persistent Building this structure's integrity
            ceiling derives from.
        max_integrity: Optional explicit integrity ceiling, bypassing the
            BASE_INTEGRITY[kind]/building computation entirely — used when
            staging a blueprint's authored BlueprintFortification.max_integrity
            (#2010) onto a live Fortification.

    Returns:
        The newly created Fortification, with integrity == max_integrity.
    """
    if max_integrity is None:
        level = building.fortification_level if building is not None else 0
        max_integrity = BASE_INTEGRITY[kind] + level * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        # Apply city-defense preparation bonus if the battle has a region (#1892).
        # The bonus comes from a completed CITY_DEFENSE project graded at its
        # deadline; see world.battles.city_defense_services.
        if place.battle.region_id is not None:
            from world.battles.city_defense_services import (  # noqa: PLC0415
                get_city_defense_integrity_bonus,
            )

            max_integrity += get_city_defense_integrity_bonus(place.battle.region)
    return Fortification.objects.create(
        place=place,
        defending_side=defending_side,
        building=building,
        kind=kind,
        integrity=max_integrity,
        max_integrity=max_integrity,
    )


@transaction.atomic
def create_battle_vehicle(
    *,
    battle: Battle,
    side: BattleSide,
    place_name: str,
    vehicle_kind: str = VehicleKind.SHIP,
    is_structural: bool = True,
) -> BattleVehicle:
    """Create a vessel/mount: a paired BattleUnit + BattlePlace, plus a hull
    Fortification if structural (#1714).

    The unit's own `place` is left None (see BattleVehicle's docstring) —
    other units/participants embed by setting their own `place` FK to
    `vehicle.place`, not by any relation on `vehicle.unit`.

    Args:
        battle: The Battle this vehicle belongs to.
        side: The BattleSide crewing/defending this vehicle.
        place_name: Display name for the vehicle's BattlePlace (e.g. "The Wave Cutter").
        vehicle_kind: A VehicleKind value. Defaults to SHIP.
        is_structural: Whether destruction goes through hull-Fortification breach
            (True, ship/airship) or BattleUnitStatus.DESTROYED (False, dragon/kraken).

    Returns:
        The newly created BattleVehicle.
    """
    from world.military.models import MilitaryUnit  # noqa: PLC0415

    mu = MilitaryUnit.objects.create(name=place_name)
    unit = BattleUnit.objects.create(
        battle=battle,
        side=side,
        military_unit=mu,
    )
    default_terrain = (
        TerrainType.AERIAL
        if vehicle_kind in (VehicleKind.AIRSHIP, VehicleKind.DRAGON)
        else TerrainType.WATER
    )
    place = BattlePlace.objects.create(
        battle=battle,
        name=place_name,
        terrain_type=default_terrain,
    )
    vehicle = BattleVehicle.objects.create(
        unit=unit,
        place=place,
        vehicle_kind=vehicle_kind,
        is_structural=is_structural,
    )
    if is_structural:
        create_fortification(
            place=place,
            defending_side=side,
            kind=FortificationKind.HULL,
        )
    return vehicle


def places_overlap(place_a: BattlePlace, place_b: BattlePlace) -> bool:
    """Whether two BattlePlaces' footprints intersect on the battle map (#1714).

    Distance between centers < sum of radii. Same place always overlaps itself
    (distance 0).
    """
    dx = place_a.x - place_b.x
    dy = place_a.y - place_b.y
    distance_squared = dx * dx + dy * dy
    radius_sum = place_a.footprint_radius + place_b.footprint_radius
    return distance_squared < radius_sum * radius_sum


@transaction.atomic
def eject_vehicle_occupants(*, vehicle: BattleVehicle) -> None:
    """Eject every unit/participant embedded on *vehicle*'s place, applying the
    environmental hazard consequence (#1714). Called when a structural vehicle's
    hull Fortification breaches, or a living-mount vehicle's unit is DESTROYED.

    Does not delete or touch vehicle.place itself — the place row persists as
    the wreck/carcass; only occupants' place FKs are cleared.
    """
    from world.conditions.factories import (  # noqa: PLC0415
        ensure_drowning_damage_type,
        ensure_falling_damage_type,
    )

    aerial = vehicle.vehicle_kind in (VehicleKind.AIRSHIP, VehicleKind.DRAGON)
    damage_type = ensure_falling_damage_type() if aerial else ensure_drowning_damage_type()
    hazard_property_name = "flying" if aerial else "aquatic"

    battle = vehicle.unit.battle
    old_place_id = vehicle.place_id

    for unit in battle.state_cache.units_on_place(old_place_id):
        unit.place = None
        unit.save(update_fields=["place"])
        battle.state_cache.move_unit_place(unit, old_place_id=old_place_id)
        _apply_environmental_hazard_to_unit(unit, hazard_property_name)

    for participant in battle.state_cache.participants_on_place(old_place_id):
        participant.place = None
        participant.save(update_fields=["place"])
        battle.state_cache.move_participant_place(participant, old_place_id=old_place_id)
        _apply_environmental_hazard_to_participant(participant, damage_type)


def _apply_environmental_hazard_to_unit(unit: BattleUnit, hazard_property_name: str) -> None:
    """Flat strength penalty for an abstract BattleUnit lacking the relevant
    presence-only Property (#1714). No per-unit resistance granularity — mirrors
    how Property is presence-only for units everywhere else."""
    from world.battles.resolution import _compute_unit_status  # noqa: PLC0415

    if unit.military_unit.properties.filter(name=hazard_property_name).exists():
        return
    unit.military_unit.strength = max(
        0, unit.military_unit.strength - VEHICLE_HAZARD_UNIT_STRENGTH_PENALTY
    )
    unit.status = _compute_unit_status(unit.military_unit.strength, unit.military_unit.morale)
    unit.save(update_fields=["status"])
    unit.military_unit.save(update_fields=["strength"])


def _apply_environmental_hazard_to_participant(
    participant: BattleParticipant, damage_type: DamageType
) -> None:
    """Real PC drowning/falling damage: resistance -> debit vitals -> consequences,
    mirroring world.battles.resolution._resolve_failure's battles-native pattern,
    extended with resolve_damage_type_resistance for a typed hazard (#1714, ADR-0073)."""
    from world.conditions.services import resolve_damage_type_resistance  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = participant.character_sheet
    try:
        vitals = sheet.vitals
    except CharacterVitals.DoesNotExist:
        return

    effective = resolve_damage_type_resistance(
        sheet.character, VEHICLE_HAZARD_BASE_DAMAGE, damage_type
    )
    if effective <= 0:
        return
    vitals.health -= effective
    vitals.save(update_fields=["health"])
    process_damage_consequences(
        character_sheet=sheet,
        damage_dealt=effective,
        damage_type=damage_type,
    )


def set_battle_side_posture(*, side: BattleSide, posture: str) -> BattleSide:
    """Set a battle side's tactical posture (#1711).

    Args:
        side: The ``BattleSide`` to update.
        posture: A ``BattlePosture`` value.

    Returns:
        The updated ``BattleSide``.
    """
    side.posture = posture
    side.save(update_fields=["posture"])
    return side


def assign_unit_commander(*, unit: BattleUnit, commander: CharacterSheet | None) -> BattleUnit:
    """Assign (or clear, with ``commander=None``) a unit's commander (#1711).

    Args:
        unit: The ``BattleUnit`` to update.
        commander: The commanding ``CharacterSheet``, or ``None`` to clear.

    Returns:
        The updated ``BattleUnit``.
    """
    unit.military_unit.commander = commander
    unit.military_unit.save(update_fields=["commander"])
    return unit


@transaction.atomic
def enlist_participant(
    *,
    battle: Battle,
    character_sheet: CharacterSheet,
    side: BattleSide,
    place: BattlePlace | None = None,
) -> BattleParticipant:
    """Enlist a player character in a battle on one side.

    Args:
        battle: The ``Battle`` to enlist the character in.
        character_sheet: The character's ``CharacterSheet``.
        side: The ``BattleSide`` the character fights for.
        place: Optional ``BattlePlace`` the character is stationed at.

    Returns:
        The newly created ``BattleParticipant``.
    """
    return BattleParticipant.objects.create(
        battle=battle,
        character_sheet=character_sheet,
        side=side,
        place=place,
        status=BattleParticipantStatus.ACTIVE,
    )


def notify_battle_state_changed(battle: Battle) -> None:
    """Slim BATTLE_STATE ping -> connected participants; clients refetch the REST aggregate.

    Battles are location-less by default (their backing scene has no
    ``location``) unless a GM staged this one from their own room (#2010,
    ``stage_battle(location=...)``) -- either way, no scene/room broadcast
    path is guaranteed to reach every connected participant, so this is the
    dedicated seam. Called after round transitions (begin_battle_round,
    resolve_battle_round) and on conclusion (conclude_battle) -- always deferred
    via ``transaction.on_commit`` at each call site, so it runs post-commit and a
    client that refetches on receipt always sees committed state.
    """
    current = battle.current_round
    payload = asdict(
        BattleStatePayload(
            battle_id=battle.pk,
            round_number=current.round_number if current else None,
        )
    )
    # A fresh, bounded query rather than BattleStateCache (participants_on_side/
    # participants_on_place): the cache indexes rows by side/place, not "every
    # participant", and neither cached row carries the character_sheet__character
    # join this ping needs -- reading through it would still cost a
    # per-participant query. One bounded query here, not a refetch of cached state.
    for participant in battle.participants.select_related("character_sheet__character"):
        character = participant.character_sheet.character
        if character is None or not character.has_account:
            continue
        character.msg(battle_state=((), payload))


@transaction.atomic
def begin_battle_round(*, battle: Battle) -> BattleRound:
    """Close any open round and open a new DECLARING round.

    Args:
        battle: The ``Battle`` to advance to the next round.

    Raises:
        BattleConcludedError: If the battle has already concluded.

    Returns:
        The newly created ``BattleRound`` in DECLARING status.
    """
    if battle.is_concluded:
        raise BattleConcludedError

    prior = battle.current_round
    if prior is not None:
        prior.status = RoundStatus.COMPLETED
        prior.completed_at = timezone.now()
        prior.save(update_fields=["status", "completed_at"])
        next_number = prior.round_number + 1
    else:
        last = battle.rounds.order_by("-round_number").first()
        if last is None:
            next_number = 1
            activate_stakes_for_battle(battle)
        else:
            next_number = last.round_number + 1

    new_round = BattleRound.objects.create(
        battle=battle,
        round_number=next_number,
        status=RoundStatus.DECLARING,
        round_started_at=timezone.now(),
    )
    transaction.on_commit(lambda: notify_battle_state_changed(battle))
    return new_round


# ---------------------------------------------------------------------------
# Declaration service (Task 6)
# ---------------------------------------------------------------------------


def _validate_action_kind_scope(
    *,
    action_kind: str,
    scope: str,
) -> None:
    """Validate scope requirements keyed on ``action_kind``.

    REPEL/HOLD/REPOSITION require PLACE scope; MOVE requires UNIT or PLACE.
    """
    if (
        action_kind in (BattleActionKind.REPEL, BattleActionKind.HOLD, BattleActionKind.REPOSITION)
        and scope != BattleActionScope.PLACE
    ):
        raise PlaceScopeRequiredError
    if action_kind == BattleActionKind.MOVE and scope not in (
        BattleActionScope.UNIT,
        BattleActionScope.PLACE,
    ):
        raise InvalidMoveScopeError


def _validate_command_and_environment(
    *,
    participant: BattleParticipant,
    action_kind: str,
    technique: Technique,
    scope: str,
    target_place: BattlePlace | None,
) -> None:
    """Dispatch SET_ENVIRONMENT, REPOSITION vehicle, and command-scope validation."""
    if action_kind == BattleActionKind.SET_ENVIRONMENT:
        _validate_environment_action(scope=scope, technique=technique)
    if action_kind == BattleActionKind.REPOSITION:
        _validate_vehicle_command(participant=participant, target_place=target_place)
    elif scope in (BattleActionScope.PLACE, BattleActionScope.SIDE, BattleActionScope.BATTLE):
        _validate_command_scope(participant=participant, scope=scope)


def _validate_action_targets(  # noqa: PLR0913
    *,
    participant: BattleParticipant,
    action_kind: str,
    scope: str,
    target_unit: BattleUnit | None,
    target_side: BattleSide | None,
    target_fortification: Fortification | None,
) -> None:
    """Validate target-specific rules: MOVE target-unit, STRIKE/ROUT own-side,
    BREACH/FORTIFY fortification, and UNIT-scope place overlap.
    """
    if (
        action_kind == BattleActionKind.MOVE
        and scope == BattleActionScope.PLACE
        and target_unit is None
    ):
        raise MoveOrderRequiresTargetUnitError

    if (
        action_kind in (BattleActionKind.STRIKE, BattleActionKind.ROUT)
        and scope == BattleActionScope.SIDE
        and target_side is not None
        and target_side.pk == participant.side_id
    ):
        raise CannotStrikeOwnSideError

    if (
        scope == BattleActionScope.UNIT
        and target_unit is not None
        and participant.place_id is not None
    ):
        _validate_unit_place_overlap(participant=participant, target_unit=target_unit)

    if action_kind in (BattleActionKind.BREACH, BattleActionKind.FORTIFY):
        _validate_fortification_target(
            participant=participant,
            action_kind=action_kind,
            target_fortification=target_fortification,
        )
        _validate_fortification_place_overlap(
            participant=participant,
            action_kind=action_kind,
            target_fortification=target_fortification,
        )


def declare_battle_action(  # noqa: PLR0913 - many declaration facets + checks
    *,
    participant: BattleParticipant,
    action_kind: str,
    technique: Technique,
    target_unit: BattleUnit | None = None,
    target_ally: BattleParticipant | None = None,
    scope: str = BattleActionScope.UNIT,
    target_place: BattlePlace | None = None,
    target_side: BattleSide | None = None,
    target_fortification: Fortification | None = None,
    reposition_dx: Decimal | None = None,
    reposition_dy: Decimal | None = None,
) -> BattleActionDeclaration:
    """Record or update the participant's action declaration for the current round.

    Uses ``update_or_create`` so a second call in the same round replaces the
    first (participants may redeclare until the round closes).

    Args:
        participant: The ``BattleParticipant`` declaring the action.
        action_kind: A ``BattleActionKind`` value.
        technique: The ``Technique`` being cast. Must be known by the participant's
            character and have an ``action_template`` (castable).
        target_unit: The ``BattleUnit`` being struck (STRIKE only).
        target_ally: The ``BattleParticipant`` being supported (SUPPORT) or rescued
            (RESCUE).
        scope: A ``BattleActionScope`` value (#1710). PLACE/SIDE require the
            participant to hold a matching engaged command_tier on the side's
            covenant.
        target_place: The ``BattlePlace`` affected (scope=PLACE).
        target_side: The ``BattleSide`` affected (scope=SIDE).
        target_fortification: The ``Fortification`` being BREACHed/FORTIFYed (#1713).
        reposition_dx: Requested x-axis delta for a REPOSITION declaration (#1714).
        reposition_dy: Requested y-axis delta for a REPOSITION declaration (#1714).

    Raises:
        RoundNotOpenError: If the battle has no DECLARING round.
        CharacterDoesNotKnowTechniqueError: If the participant's character doesn't
            know ``technique``.
        TechniqueNotBattleReadyError: If ``technique`` has no ``action_template``.
        NoCommandHierarchyError: If scope is PLACE/SIDE and the participant's
            side has no covenant.
        InsufficientCommandTierError: If scope is PLACE/SIDE and the
            participant lacks the required engaged command_tier.
        MissingScopeTargetError: If scope is PLACE and ``target_place`` is
            None, or scope is SIDE and ``target_side`` is None.
        CannotStrikeOwnSideError: If ``action_kind`` is STRIKE or ROUT, scope is SIDE,
            and ``target_side`` is the participant's own side.
        PlaceScopeRequiredError: If action_kind is REPEL, HOLD, or REPOSITION and
            scope is not PLACE.
        FortificationTargetRequiredError: If action_kind is BREACH/FORTIFY and
            target_fortification is None.
        FortificationAlreadyBreachedError: If target_fortification.breached is True.
        FortificationOwnershipMismatchError: If BREACH targets your own side's
            fortification, or FORTIFY targets the enemy's.
        InvalidEnvironmentScopeError: If action_kind is SET_ENVIRONMENT and scope is
            not BATTLE or PLACE.
        MissingEnvironmentTargetError: If action_kind is SET_ENVIRONMENT and
            technique.target_weather_type is None.
        NotVehicleCommanderError: If action_kind is REPOSITION and the participant
            is not the target vehicle's BattleUnit.commander.
        InvalidMoveScopeError: If action_kind is MOVE and scope is not UNIT or
            PLACE.
        MoveOrderRequiresTargetUnitError: If action_kind is MOVE, scope is PLACE,
            and target_unit is None.

    Returns:
        The created or updated ``BattleActionDeclaration``.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    battle_round = participant.battle.current_round
    if battle_round is None or battle_round.status != RoundStatus.DECLARING:
        raise RoundNotOpenError

    knows_technique = CharacterTechnique.objects.filter(
        character_id=participant.character_sheet_id,
        technique=technique,
    ).exists()
    if not knows_technique:
        raise CharacterDoesNotKnowTechniqueError

    if not technique.action_template_id:
        raise TechniqueNotBattleReadyError

    _validate_action_kind_scope(action_kind=action_kind, scope=scope)

    _validate_command_and_environment(
        participant=participant,
        action_kind=action_kind,
        technique=technique,
        scope=scope,
        target_place=target_place,
    )

    _validate_scope_target(scope=scope, target_place=target_place, target_side=target_side)

    _validate_action_targets(
        participant=participant,
        action_kind=action_kind,
        scope=scope,
        target_unit=target_unit,
        target_side=target_side,
        target_fortification=target_fortification,
    )

    declaration, _ = BattleActionDeclaration.objects.update_or_create(
        battle_round=battle_round,
        participant=participant,
        defaults={
            "action_kind": action_kind,
            "technique": technique,
            "target_unit": target_unit,
            "target_ally": target_ally,
            "scope": scope,
            "target_place": target_place,
            "target_side": target_side,
            "target_fortification": target_fortification,
            "reposition_dx": reposition_dx,
            "reposition_dy": reposition_dy,
            "resolved": False,
        },
    )
    return declaration


def _validate_environment_action(*, scope: str, technique: Technique) -> None:
    """Validate a SET_ENVIRONMENT declaration's scope and weather target."""
    if scope not in (BattleActionScope.BATTLE, BattleActionScope.PLACE):
        raise InvalidEnvironmentScopeError
    if technique.target_weather_type_id is None:
        raise MissingEnvironmentTargetError


def _validate_scope_target(
    *,
    scope: str,
    target_place: BattlePlace | None,
    target_side: BattleSide | None,
) -> None:
    """Raise ``MissingScopeTargetError`` when a scope's required target is absent."""
    if scope == BattleActionScope.PLACE and target_place is None:
        raise MissingScopeTargetError
    if scope == BattleActionScope.SIDE and target_side is None:
        raise MissingScopeTargetError


def _validate_unit_place_overlap(
    *, participant: BattleParticipant, target_unit: BattleUnit
) -> None:
    """Raise ``PlacesDoNotOverlapError`` when a UNIT target is out of range.

    A vehicle's own BattleUnit never has place set (see BattleVehicle's
    docstring) — resolve its paired vehicle's place so a STRIKE against the
    vehicle's own unit is gated the same as a BREACH against its hull.
    """
    target_unit_place = target_unit.place
    if target_unit_place is None and target_unit.vehicle_or_none is not None:
        target_unit_place = target_unit.vehicle.place
    if (
        target_unit_place is not None
        and target_unit_place.pk != participant.place_id
        and not places_overlap(target_unit_place, participant.place)
    ):
        raise PlacesDoNotOverlapError


def _validate_fortification_place_overlap(
    *,
    participant: BattleParticipant,
    action_kind: str,
    target_fortification: Fortification | None,
) -> None:
    """Raise ``PlacesDoNotOverlapError`` when a BREACH target is out of range."""
    if (
        action_kind == BattleActionKind.BREACH
        and target_fortification is not None
        and target_fortification.place.vehicle_or_none is not None
        and participant.place_id is not None
        and target_fortification.place_id != participant.place_id
        and not places_overlap(target_fortification.place, participant.place)
    ):
        raise PlacesDoNotOverlapError


def _validate_command_scope(*, participant: BattleParticipant, scope: str) -> None:
    """Raise unless *participant* holds the command tier *scope* requires.

    PLACE requires an engaged CharacterCovenantRole with command_tier in
    (SUBORDINATE, SUPREME) on the side's covenant; SIDE and BATTLE (#1715, the
    widest scope) require SUPREME. A side with no covenant has no command
    hierarchy at all.
    """
    from world.covenants.constants import CommandTier  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    covenant = participant.side.covenant
    if covenant is None:
        raise NoCommandHierarchyError

    required_tiers = (
        [CommandTier.SUPREME]
        if scope in (BattleActionScope.SIDE, BattleActionScope.BATTLE)
        else [CommandTier.SUBORDINATE, CommandTier.SUPREME]
    )
    has_tier = CharacterCovenantRole.objects.filter(
        character_sheet=participant.character_sheet,
        covenant=covenant,
        covenant_role__command_tier__in=required_tiers,
        engaged=True,
        left_at__isnull=True,
    ).exists()
    if not has_tier:
        raise InsufficientCommandTierError


def _validate_vehicle_command(
    *, participant: BattleParticipant, target_place: BattlePlace | None
) -> None:
    """Raise unless *participant* is the target vehicle's declared commander (#1714).

    Deliberately bypasses _validate_command_scope's covenant command_tier check —
    a ship with no covenant backing (a pirate crew, an ad-hoc vessel) must still
    be commandable and movable.
    """
    if target_place is None:
        raise MissingScopeTargetError
    vehicle = target_place.vehicle_or_none
    if vehicle is None or vehicle.unit.military_unit.commander_id != participant.character_sheet_id:
        raise NotVehicleCommanderError


def _validate_fortification_target(
    *,
    participant: BattleParticipant,
    action_kind: str,
    target_fortification: Fortification | None,
) -> None:
    """Raise unless *target_fortification* is a valid BREACH/FORTIFY target (#1713).

    BREACH must target the enemy's structure; FORTIFY must target your own.
    Either way the target must be set and not already breached.
    """
    if target_fortification is None:
        raise FortificationTargetRequiredError
    if target_fortification.breached:
        raise FortificationAlreadyBreachedError
    is_own_structure = target_fortification.defending_side_id == participant.side_id
    if action_kind == BattleActionKind.BREACH and is_own_structure:
        raise FortificationOwnershipMismatchError
    if action_kind == BattleActionKind.FORTIFY and not is_own_structure:
        raise FortificationOwnershipMismatchError


# ---------------------------------------------------------------------------
# Conclusion services (Task 7)
# ---------------------------------------------------------------------------


def check_victory(*, battle: Battle) -> BattleOutcome | None:
    """Check whether any side has reached its victory threshold.

    Returns the graded outcome for that side, or ``None`` if no side has won.
    A side is decisive if its ``victory_points`` exceeds its threshold by
    ``DECISIVE_MARGIN``; otherwise marginal.

    Args:
        battle: The ``Battle`` to evaluate.

    Returns:
        A ``BattleOutcome`` value if a side has won, or ``None``.
    """
    for side in battle.sides.all():
        if side.victory_points >= side.victory_threshold:
            margin = side.victory_points - side.victory_threshold
            decisive = margin >= DECISIVE_MARGIN
            if side.role == BattleSideRole.ATTACKER:
                return (
                    BattleOutcome.ATTACKER_DECISIVE if decisive else BattleOutcome.ATTACKER_MARGINAL
                )
            return BattleOutcome.DEFENDER_DECISIVE if decisive else BattleOutcome.DEFENDER_MARGINAL
    return None


@transaction.atomic
def conclude_battle(*, battle: Battle, outcome: str) -> Battle:
    """Set the battle's outcome, end the backing scene, and resolve any linked
    story beat's stakes contract.

    Resolves every UNSATISFIED OUTCOME_TIER beat linked to the battle's scene
    via resolve_battle_beats (#1785) — classifying battle.outcome through
    BattleOutcomeMapping and completing the beat through the same
    record_outcome_tier_completion seam combat/missions already use. Idempotent:
    if the battle is already concluded, returns it unchanged (resolve_battle_beats
    does not re-fire). After beat resolution, runs every hook registered via
    register_battle_conclusion_hook (#1832) — e.g. ships' apply_ship_battle_outcome.
    Pings connected participants via notify_battle_state_changed (#2009) last,
    after every other side effect, deferred via transaction.on_commit so it
    fires only once this transaction has actually committed.

    Args:
        battle: The ``Battle`` to conclude.
        outcome: A ``BattleOutcome`` value.

    Returns:
        The updated ``Battle`` instance.
    """
    if battle.is_concluded:
        return battle

    battle.outcome = outcome
    battle.concluded_at = timezone.now()
    battle.save(update_fields=["outcome", "concluded_at"])

    # End the backing scene.
    scene = battle.scene
    scene.is_active = False
    scene.date_finished = timezone.now()
    scene.save(update_fields=["is_active", "date_finished"])

    # scene.is_active=False above doesn't bust the room's in-memory
    # _active_scene_cache (mirrors finish_scene_full's identical step,
    # world/scenes/scene_admin_services.py) — without this, a stale cache
    # entry keeps pointing room-scoped lookups at the just-concluded battle's
    # scene until something else happens to invalidate it (#2010 review).
    if scene.location is not None:
        from world.scenes.interaction_services import (  # noqa: PLC0415
            invalidate_active_scene_cache,
        )

        invalidate_active_scene_cache(scene.location)

    resolve_battle_beats(battle)
    run_battle_conclusion_hooks(battle)
    transaction.on_commit(lambda: notify_battle_state_changed(battle))

    return battle


def maybe_pause_battle_for_disconnect(character_sheet: CharacterSheet) -> None:
    """Pause the character's live Battle on disconnect, unless it's large-scale
    and the character isn't mid-Audere-Majora-crossing (#1899)."""
    from world.magic.audere_majora import is_mid_audere_majora_crossing  # noqa: PLC0415

    participant = BattleParticipant.objects.filter(
        character_sheet=character_sheet,
        status=BattleParticipantStatus.ACTIVE,
        battle__concluded_at__isnull=True,
    ).first()
    if participant is None:
        return
    battle = participant.battle
    participant_count = BattleParticipant.objects.filter(
        battle=battle, status=BattleParticipantStatus.ACTIVE
    ).count()
    is_large_scale = participant_count >= LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD
    if is_large_scale and not is_mid_audere_majora_crossing(character_sheet):
        return
    battle.is_paused = True
    battle.save(update_fields=["is_paused"])


def maybe_conclude_on_timer(*, battle: Battle) -> BattleOutcome | None:
    """Conclude the battle when the round limit is exhausted.

    Called after each round completes. Fires only when there is no active
    round and the number of completed rounds is ≥ ``battle.round_limit``.

    Timeout rule: defender wins if defender VP ≥ threshold; otherwise attacker.

    Args:
        battle: The ``Battle`` to check.

    Returns:
        The ``BattleOutcome`` applied, or ``None`` if the timer hasn't expired.
    """
    if battle.is_concluded:
        return None
    if battle.current_round is not None:
        return None

    completed_count = battle.rounds.filter(status=RoundStatus.COMPLETED).count()
    if completed_count < battle.round_limit:
        return None

    # Timeout: defender wins by default; check if attacker meets threshold instead.
    outcome: str | None = check_victory(battle=battle)
    if outcome is None:
        # Neither side met threshold — defender holds (timeout = defender marginal win).
        try:
            defender_side = battle.sides.get(role=BattleSideRole.DEFENDER)
            margin = defender_side.victory_points - defender_side.victory_threshold
            if margin >= DECISIVE_MARGIN:
                outcome = BattleOutcome.DEFENDER_DECISIVE
            else:
                outcome = BattleOutcome.DEFENDER_MARGINAL
        except BattleSide.DoesNotExist:
            outcome = BattleOutcome.DEFENDER_MARGINAL

    conclude_battle(battle=battle, outcome=outcome)
    return outcome


# ---------------------------------------------------------------------------
# Champion duel services (#1710)
# ---------------------------------------------------------------------------


@transaction.atomic
def open_champion_duel(
    *,
    battle_place: BattlePlace,
    challenger_participant: BattleParticipant,
    opponent_kwargs: dict,
    tier: str = OpponentTier.BOSS,
) -> CombatEncounter:
    """Bind *battle_place* to a new lethal PC-vs-boss duel (#1710).

    Reuses ``create_lethal_duel`` (world.combat.duels) unmodified — a Champion
    duel against an enemy boss is an ordinary lethal PC-vs-significant-NPC
    duel. Installs the champion-duel-outcome Trigger on the encounter's room
    so ``apply_champion_duel_outcome`` fires when the duel completes.

    Args:
        battle_place: The front the duel is bound to. Must have no existing
            ``combat_encounter``.
        challenger_participant: The Champion's ``BattleParticipant``. Must
            hold an engaged ``is_champion_role`` ``CovenantRole`` for the
            side's covenant.
        opponent_kwargs: Forwarded to ``add_opponent`` via
            ``create_lethal_duel`` (name, max_health, threat_pool, ...).
        tier: Opponent tier; forwarded to ``create_lethal_duel`` (defaults to
            BOSS — a Champion duel is definitionally against a significant
            enemy, not a mook).

    Raises:
        NotAChampionError: If the challenger has no engaged Champion role for
            the side's covenant.
        NoCommandHierarchyError: If the challenger's side has no covenant.
        PlaceAlreadyDuelingError: If ``battle_place.combat_encounter`` is
            already set.

    Returns:
        The newly created ``CombatEncounter``.
    """
    from world.battles.duel_wiring import install_champion_duel_trigger  # noqa: PLC0415
    from world.combat.duels import create_lethal_duel  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    if battle_place.combat_encounter_id is not None:
        raise PlaceAlreadyDuelingError

    covenant = challenger_participant.side.covenant
    if covenant is None:
        raise NoCommandHierarchyError

    is_champion = CharacterCovenantRole.objects.filter(
        character_sheet=challenger_participant.character_sheet,
        covenant=covenant,
        covenant_role__is_champion_role=True,
        engaged=True,
        left_at__isnull=True,
    ).exists()
    if not is_champion:
        raise NotAChampionError

    room = battle_place.battle.scene.location
    enc = create_lethal_duel(
        challenger_participant.character_sheet,
        opponent_kwargs,
        room,
        tier=tier,
    )
    # Stamped exclusively here (#2536 slice 3) — the narrowest point that ONLY
    # Champion duels reach. open_siege_engine_encounter shares create_lethal_duel
    # but never sets this, so siege-engine DUEL encounters stay False.
    enc.is_champion_duel = True
    enc.save(update_fields=["is_champion_duel"])
    battle_place.combat_encounter = enc
    battle_place.save(update_fields=["combat_encounter"])
    install_champion_duel_trigger(enc)
    return enc


@transaction.atomic
def open_siege_engine_encounter(
    *,
    battle_place: BattlePlace,
    participant: BattleParticipant,
    opponent_kwargs: dict,
    tier: str = OpponentTier.ELITE,
) -> CombatEncounter:
    """Bind *battle_place* to a discrete siege-engine skirmish (#1713).

    Reuses the same BattlePlace.combat_encounter bridge and create_lethal_duel
    call as open_champion_duel, but without the Champion-role requirement — a
    siege-engine skirmish (sabotaging a ram's crew, defending a tower) is an
    ordinary discrete fight, not a Champion-only duel. Siege engines themselves
    are ordinary BattleUnit rows, not a separate model (#1713 Decision 3) —
    content authors differentiate one via the #1794 properties/capabilities
    taxonomy, not a dedicated composition/kind field. This function only opens
    the discrete-combat bridge for a skirmish over one.
    The distinction from open_champion_duel is about who may open the duel, not
    the opponent's tier: create_lethal_duel only accepts significant-NPC tiers
    (ELITE/BOSS/HERO_KILLER) regardless of which function calls it, so this
    function keeps create_lethal_duel's own bare default rather than overriding
    it downward.

    Args:
        battle_place: The front the skirmish is bound to. Must have no existing
            combat_encounter.
        participant: The BattleParticipant initiating the skirmish.
        opponent_kwargs: Forwarded to add_opponent via create_lethal_duel.
        tier: Opponent tier; must be a significant-NPC tier accepted by
            create_lethal_duel (ELITE/BOSS/HERO_KILLER). Defaults to ELITE.

    Raises:
        PlaceAlreadyDuelingError: If battle_place.combat_encounter is already set.

    Returns:
        The newly created CombatEncounter.
    """
    from world.combat.duels import create_lethal_duel  # noqa: PLC0415

    if battle_place.combat_encounter_id is not None:
        raise PlaceAlreadyDuelingError

    room = battle_place.battle.scene.location
    enc = create_lethal_duel(
        participant.character_sheet,
        opponent_kwargs,
        room,
        tier=tier,
    )
    battle_place.combat_encounter = enc
    battle_place.save(update_fields=["combat_encounter"])
    return enc


@transaction.atomic
def open_place_encounter(*, battle_place: BattlePlace) -> CombatEncounter:
    """Bind *battle_place* to a new general party-scale combat encounter (#2008).

    Unlike ``open_champion_duel``/``open_siege_engine_encounter`` (both seed exactly
    one PC participant and one significant-NPC opponent via ``create_lethal_duel``),
    this creates a bare ``CombatEncounter`` — no pre-seeded participant or opponent.
    The GM populates it afterward via the existing, unmodified
    ``AddOpponentAction``/``AddEncounterParticipantAction``
    (``actions/definitions/gm_combat.py``). ``encounter_type`` is ``PARTY_COMBAT``
    (the model's own default), distinguishing a general front fight from the two
    duel-shaped creators, which use ``DUEL``. No Champion-role gate — a GM verb, not
    a player challenge, so there is no "opener" participant argument.

    Args:
        battle_place: The front the encounter is bound to. Must have no existing
            ``combat_encounter``.

    Raises:
        PlaceAlreadyDuelingError: If ``battle_place.combat_encounter`` is already
            set.

    Returns:
        The newly created ``CombatEncounter``, in DECLARING status.
    """
    from world.battles.place_encounter_wiring import (  # noqa: PLC0415
        install_place_encounter_trigger,
    )
    from world.combat.chosen_ground import compute_on_chosen_ground  # noqa: PLC0415
    from world.combat.constants import EncounterType  # noqa: PLC0415
    from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    if battle_place.combat_encounter_id is not None:
        raise PlaceAlreadyDuelingError

    room = battle_place.battle.scene.location
    enc = CombatEncounter.objects.create(
        room=room,
        scene=battle_place.battle.scene,
        encounter_type=EncounterType.PARTY_COMBAT,
        risk_level=RiskLevel.LETHAL,
        status=RoundStatus.DECLARING,
        on_chosen_ground=compute_on_chosen_ground(room),
    )
    assign_default_escalation_curve(enc)

    battle_place.combat_encounter = enc
    battle_place.save(update_fields=["combat_encounter"])
    install_place_encounter_trigger(enc)
    return enc

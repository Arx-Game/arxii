"""Service functions for the battles system.

All public functions are the only permitted entry points for battle state
mutations. Callers (actions, commands, views) must not write to battle models
directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.beat_wiring import activate_stakes_for_battle, resolve_battle_beats
from world.battles.constants import (
    DECISIVE_MARGIN,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitQuality,
)
from world.battles.exceptions import (
    BattleConcludedError,
    CannotStrikeOwnSideError,
    CharacterDoesNotKnowTechniqueError,
    InsufficientCommandTierError,
    MissingScopeTargetError,
    NoCommandHierarchyError,
    NotAChampionError,
    PlaceAlreadyDuelingError,
    PlaceScopeRequiredError,
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
    BattleUnitCapability,
)
from world.combat.constants import OpponentTier
from world.conditions.models import CapabilityType
from world.mechanics.models import Property
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
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
) -> Battle:
    """Create a new Battle (and its backing Scene).

    Args:
        name: Human-readable name for the battle.
        campaign_story: Optional parent Story this battle belongs to.
        round_limit: Maximum number of rounds before auto-conclusion.

    Returns:
        The newly created ``Battle`` instance.
    """
    battle = Battle(name=name, campaign_story=campaign_story, round_limit=round_limit)
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
def add_place(
    *,
    battle: Battle,
    name: str,
    terrain_type: str = TerrainType.OPEN,
    movement_cost: int = 1,
) -> BattlePlace:
    """Add a named front/zone to a battle.

    Args:
        battle: The ``Battle`` to add the place to.
        name: Human-readable name for the front (e.g. "The Main Gates").
        terrain_type: A ``TerrainType`` value (#1711). Defaults to OPEN.
        movement_cost: Authored cost for a future reposition/movement action —
            not yet filed as an issue; #1712 explicitly did not build this
            (#1711). Defaults to 1.

    Returns:
        The newly created ``BattlePlace``.
    """
    return BattlePlace.objects.create(
        battle=battle,
        name=name,
        terrain_type=terrain_type,
        movement_cost=movement_cost,
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
    place: BattlePlace | None = None,
    properties: Iterable[Property] = (),
    capability_values: Iterable[tuple[CapabilityType, int]] = (),
    individual_count: int | None = None,
) -> BattleUnit:
    """Add an abstract typed unit to a battle side.

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
        place: Optional ``BattlePlace`` this unit is stationed at.
        properties: Property tags to attach (#1794) — presence-only.
        capability_values: (CapabilityType, magnitude) pairs to attach (#1794) —
            each becomes a BattleUnitCapability row.
        individual_count: Optional population data point (#1794); mirrors
            CombatOpponent.swarm_count's naming — no swarm-math wired against it yet.

    Returns:
        The newly created ``BattleUnit``.
    """
    unit = BattleUnit.objects.create(
        battle=battle,
        side=side,
        name=name,
        descriptor=descriptor,
        quality=quality,
        commander=commander,
        summoned_by=summoned_by,
        strength=strength,
        status=BattleUnitStatus.ACTIVE,
        place=place,
        individual_count=individual_count,
    )
    unit.properties.set(properties)
    BattleUnitCapability.objects.bulk_create(
        BattleUnitCapability(unit=unit, capability=capability, value=value)
        for capability, value in capability_values
    )
    return unit


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
    unit.commander = commander
    unit.save(update_fields=["commander"])
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

    return BattleRound.objects.create(
        battle=battle,
        round_number=next_number,
        status=RoundStatus.DECLARING,
        round_started_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# Declaration service (Task 6)
# ---------------------------------------------------------------------------


def declare_battle_action(  # noqa: PLR0913 - each param is a distinct declaration facet
    *,
    participant: BattleParticipant,
    action_kind: str,
    technique: Technique,
    target_unit: BattleUnit | None = None,
    target_ally: BattleParticipant | None = None,
    scope: str = BattleActionScope.UNIT,
    target_place: BattlePlace | None = None,
    target_side: BattleSide | None = None,
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
        PlaceScopeRequiredError: If action_kind is REPEL or HOLD and scope is not PLACE.

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

    if (
        action_kind in (BattleActionKind.REPEL, BattleActionKind.HOLD)
        and scope != BattleActionScope.PLACE
    ):
        raise PlaceScopeRequiredError

    if scope in (BattleActionScope.PLACE, BattleActionScope.SIDE):
        _validate_command_scope(participant=participant, scope=scope)

    if scope == BattleActionScope.PLACE and target_place is None:
        raise MissingScopeTargetError
    if scope == BattleActionScope.SIDE and target_side is None:
        raise MissingScopeTargetError

    if (
        action_kind in (BattleActionKind.STRIKE, BattleActionKind.ROUT)
        and scope == BattleActionScope.SIDE
        and target_side is not None
        and target_side.pk == participant.side_id
    ):
        raise CannotStrikeOwnSideError

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
            "resolved": False,
        },
    )
    return declaration


def _validate_command_scope(*, participant: BattleParticipant, scope: str) -> None:
    """Raise unless *participant* holds the command tier *scope* requires.

    PLACE requires an engaged CharacterCovenantRole with command_tier in
    (SUBORDINATE, SUPREME) on the side's covenant; SIDE requires SUPREME.
    A side with no covenant has no command hierarchy at all.
    """
    from world.covenants.constants import CommandTier  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    covenant = participant.side.covenant
    if covenant is None:
        raise NoCommandHierarchyError

    required_tiers = (
        [CommandTier.SUPREME]
        if scope == BattleActionScope.SIDE
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
    does not re-fire).

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

    resolve_battle_beats(battle)

    return battle


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
    battle_place.combat_encounter = enc
    battle_place.save(update_fields=["combat_encounter"])
    install_champion_duel_trigger(enc)
    return enc

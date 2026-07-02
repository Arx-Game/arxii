"""Service functions for the battles system.

All public functions are the only permitted entry points for battle state
mutations. Callers (actions, commands, views) must not write to battle models
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.beat_wiring import activate_stakes_for_battle, resolve_battle_beats
from world.battles.constants import (
    DECISIVE_MARGIN,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionScope,
    BattleOutcome,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.exceptions import (
    BattleConcludedError,
    CharacterDoesNotKnowTechniqueError,
    InsufficientCommandTierError,
    NoCommandHierarchyError,
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
)
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
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
def add_place(*, battle: Battle, name: str) -> BattlePlace:
    """Add a named front/zone to a battle.

    Args:
        battle: The ``Battle`` to add the place to.
        name: Human-readable name for the front (e.g. "The Main Gates").

    Returns:
        The newly created ``BattlePlace``.
    """
    return BattlePlace.objects.create(battle=battle, name=name)


@transaction.atomic
def add_unit(  # noqa: PLR0913 - each param is a distinct unit attribute
    *,
    battle: Battle,
    side: BattleSide,
    name: str,
    unit_type: str,
    strength: int = 100,
    place: BattlePlace | None = None,
) -> BattleUnit:
    """Add an abstract typed unit to a battle side.

    Args:
        battle: The owning ``Battle``.
        side: The ``BattleSide`` this unit belongs to.
        name: Display name for this unit (e.g. "Cavalry").
        unit_type: Descriptive type tag (e.g. "cavalry", "zombies-on-nightmares").
        strength: Starting strength value (default 100).
        place: Optional ``BattlePlace`` this unit is stationed at.

    Returns:
        The newly created ``BattleUnit``.
    """
    return BattleUnit.objects.create(
        battle=battle,
        side=side,
        name=name,
        unit_type=unit_type,
        strength=strength,
        status=BattleUnitStatus.ACTIVE,
        place=place,
    )


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

    if scope in (BattleActionScope.PLACE, BattleActionScope.SIDE):
        _validate_command_scope(participant=participant, scope=scope)

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

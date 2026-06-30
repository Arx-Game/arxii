"""Service functions for the battles system.

All public functions are the only permitted entry points for battle state
mutations. Callers (actions, commands, views) must not write to battle models
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.constants import (
    DECISIVE_MARGIN,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleOutcome,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.exceptions import BattleConcludedError
from world.battles.models import (
    Battle,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
)
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
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
) -> BattleSide:
    """Add a side (attacker or defender) to a battle.

    Args:
        battle: The ``Battle`` to add the side to.
        role: A ``BattleSideRole`` value.
        victory_threshold: VP total required for this side to win.

    Returns:
        The newly created ``BattleSide``.
    """
    return BattleSide.objects.create(
        battle=battle,
        role=role,
        victory_threshold=victory_threshold,
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
        next_number = 1

    return BattleRound.objects.create(
        battle=battle,
        round_number=next_number,
        status=RoundStatus.DECLARING,
        round_started_at=timezone.now(),
    )


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
    """Set the battle's outcome and end the backing scene.

    Does NOT call ``complete_story`` — campaign propagation is deferred to #1716.
    Idempotent: if the battle is already concluded, returns it unchanged.

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

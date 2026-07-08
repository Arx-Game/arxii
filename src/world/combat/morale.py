"""Party-NPC morale state + mutation (#2015).

Mirrors war-scale ``BattleUnit.morale`` (world.battles) at party scale.
Morale is a first-class depletable resource on ``CombatOpponent``; the
derived state (STEADY/FALTER/BREAK) is read via ``morale_state_for`` —
never stored. ``select_npc_actions`` consults the state to weaken
(falter) or flee (break) faltering/broken opponents.

Mindless opponents (``OpponentTierTemplate.has_morale == False``) are NOT
immune — a powerful enough morale check breaks through and imposes morale
damage anyway (Arx's "power can do the impossible" tenet). The mindless flag
adds ``MINDLESS_MORALE_RESISTANCE`` to the check difficulty, not a gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from world.combat.constants import (
    BREAK_MORALE_THRESHOLD,
    FALTER_MORALE_THRESHOLD,
)

if TYPE_CHECKING:
    from world.combat.models import CombatOpponent


class OpponentMoraleState(models.TextChoices):
    """Derived morale state of a party-scale opponent (#2015)."""

    STEADY = "steady", "Steady"
    FALTER = "falter", "Falter"
    BREAK = "break", "Break"


def tier_has_morale(opponent: CombatOpponent) -> bool:
    """Return whether the opponent's tier template has morale (is not mindless).

    Resolves the ``OpponentTierTemplate`` by ``opponent.tier`` (the tier is a
    CharField, not a FK). Returns ``True`` when the template is missing — a
    missing template should not silently make an opponent mindless.

    Args:
        opponent: The combat opponent whose tier template to check.

    Returns:
        True if the tier has morale (the default), False if mindless.
    """
    from world.combat.models import OpponentTierTemplate  # noqa: PLC0415

    tpl = OpponentTierTemplate.objects.filter(tier=opponent.tier).first()
    return tpl.has_morale if tpl is not None else True


def morale_state_for(opponent: CombatOpponent) -> OpponentMoraleState:
    """Return the opponent's derived morale state (STEADY/FALTER/BREAK).

    Reads the raw ``morale`` value regardless of the mindless flag — a mindless
    opponent whose morale has been driven low by a breakthrough still falters
    and breaks (the rock has been made to feel fear).

    Args:
        opponent: The combat opponent whose morale state to derive.

    Returns:
        The derived ``OpponentMoraleState``.
    """
    if opponent.morale <= BREAK_MORALE_THRESHOLD:
        return OpponentMoraleState.BREAK
    if opponent.morale <= FALTER_MORALE_THRESHOLD:
        return OpponentMoraleState.FALTER
    return OpponentMoraleState.STEADY


def apply_morale_damage(opponent: CombatOpponent, amount: int) -> int:
    """Deplete ``opponent.morale`` by ``amount`` (clamped at 0).

    For SWARM tier, morale loss also clears bodies (``swarm_count``) to
    represent bodies fleeing — ``bodies_fled = amount // body_toughness``,
    the same per-body cost ``apply_damage_to_opponent`` uses for raw damage.
    Non-swarm tiers ignore the body-clearing path (morale just depletes).

    Args:
        opponent: The combat opponent whose morale to deplete.
        amount: The morale damage to apply (clamped to ``[0, morale]``).

    Returns:
        The actual morale damage applied (post-clamp).
    """
    from world.combat.constants import OpponentTier  # noqa: PLC0415

    actual = min(amount, opponent.morale)
    opponent.morale = max(0, opponent.morale - actual)

    update_fields = ["morale"]

    if (
        opponent.tier == OpponentTier.SWARM
        and opponent.swarm_count is not None
        and opponent.body_toughness
    ):
        bodies_fled = actual // opponent.body_toughness
        if bodies_fled > 0:
            opponent.swarm_count = max(0, opponent.swarm_count - bodies_fled)
            update_fields.append("swarm_count")

    opponent.save(update_fields=update_fields)
    return actual

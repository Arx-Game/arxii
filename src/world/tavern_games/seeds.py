"""Idempotent seed helpers for tavern games (#3292).

Rides The Big Button (``world.seeds.clusters``): one authored dice game row
so `game open` is exercisable on a fresh clone/dev DB without any manual
authoring step.
"""

from __future__ import annotations

from world.tavern_games.constants import GameResolutionKind
from world.tavern_games.models import TavernGame

DICE_GAME_NAME = "Highest Roll"


def ensure_dice_game() -> TavernGame:
    """Get-or-create the starter highest-roll dice game."""
    game, _ = TavernGame.objects.update_or_create(
        name=DICE_GAME_NAME,
        defaults={
            "rules_blurb": (
                "Every seated player rolls a single six-sided die. Highest roll "
                "takes the pot. A tie among the leaders re-rolls the whole table."
            ),
            "min_ante": 1,
            "max_ante": 500,
            "resolution_kind": GameResolutionKind.HIGHEST_ROLL,
            "is_active": True,
        },
    )
    return game

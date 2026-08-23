"""Choice enums + tunable magnitudes for the tavern games sub-package (#3292)."""

from __future__ import annotations

from django.db import models


class GameResolutionKind(models.TextChoices):
    """How a ``TavernGame`` decides a winner among its seated players.

    One kind at MVP: a single simultaneous highest-roll contest, tied seats
    re-roll. Later kinds (cards, skill-augmented contests) add values here -
    the resolution behavior is carried by ``services.resolve_session``'s
    dispatch on this field, not a code branch per game row.
    """

    HIGHEST_ROLL = "highest_roll", "Highest Roll"


class GameSessionState(models.TextChoices):
    """Lifecycle of a ``GameSession``."""

    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"
    ABANDONED = "abandoned", "Abandoned"


# PLACEHOLDER - a single six-sided die, per seat, per roll. Pending a design
# pass on whether higher-stakes games (a later ``GameResolutionKind``) roll
# more/larger dice.
DICE_SIDES = 6

# A session needs at least this many seated players before anyone can roll -
# without it, ante-in/ante-out at resolve is a costless no-op for a lone
# player rather than a contest.
MIN_SEATS_TO_ROLL = 2

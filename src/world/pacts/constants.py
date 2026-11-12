"""TextChoices for being pacts (#4341)."""

from django.db import models


class CharacterPactCommitmentKind(models.TextChoices):
    """What one commitment on a pact offer asks of the holder.

    FAVOR_EARNED is graded every period against the favor the holder earned with
    the being; CUSTOM is a recorded promise, shown on the pact card and never
    checked by the game.
    """

    FAVOR_EARNED = "favor_earned", "Favor earned per period"
    CUSTOM = "custom", "Custom (recorded promise)"


class CharacterPactEnding(models.TextChoices):
    """Why a character's pact ended."""

    BREACH = "breach", "Breach"
    RENOUNCED = "renounced", "Renounced"
    PARTY_ENDED = "party_ended", "Party ended"

"""Enums for standoffs: the stand-off before a fight, where a group can be read and talked down."""

from django.db import models

from world.combat.constants import CauseKind


class DriveStrength(models.IntegerChoices):
    """How hard a drive pulls on a creature. Larger numbers pull harder."""

    MINOR = 1, "Minor"
    MAJOR = 2, "Major"
    DEFINING = 3, "Defining"


class StandoffGroupState(models.TextChoices):
    """Where one group of creatures stands in a standoff."""

    OPEN = "open", "Open"
    SETTLED = "settled", "Settled"
    FIGHTING = "fighting", "Fighting"


class RevealKind(models.TextChoices):
    """What a reading check uncovered about a group."""

    CAUSE = "cause", "Cause"
    DRIVE = "drive", "Drive"
    REGARD = "regard", "Regard"


class TermsEffect(models.TextChoices):
    """What a successful set of terms does to a group."""

    PASS = "pass", "Let us pass"
    FLEE = "flee", "Clear off"
    TURN = "turn", "Turn"
    TOLL = "toll", "Pay us"


# Placeholder one-line gloss shown under a revealed cause. Staff-authored prose is a later
# slice; this is keyed by CauseKind so each kind carries its own line.
CAUSE_GLOSSES: dict[str, str] = {
    CauseKind.PREDATION: "They think you're prey.",
}

# The five check tiers, by ``success_level``, as one plain word each.
SUCCESS_LEVEL_WORDS: dict[int, str] = {
    -2: "Critical failure",
    -1: "Failure",
    0: "Partial success",
    1: "Success",
    2: "Critical success",
}

FIGHT_BEGINS_MESSAGE = "The fight begins."

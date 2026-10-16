"""Enums for standoffs: the stand-off before a fight, where a group can be read and talked down."""

from django.db import models


class DriveStrength(models.IntegerChoices):
    """How hard a drive pulls on a creature. Larger numbers pull harder."""

    MINOR = 1, "Minor"
    MAJOR = 2, "Major"
    DEFINING = 3, "Defining"


class StandoffGroupState(models.TextChoices):
    """Where one group of creatures stands in a standoff."""

    OPEN = "open", "Open"
    PROPOSED = "proposed", "Proposed"
    SETTLED = "settled", "Settled"
    FIGHTING = "fighting", "Fighting"


class RevealKind(models.TextChoices):
    """What a reading check uncovered about a group."""

    CAUSE = "cause", "Cause"
    DRIVE = "drive", "Drive"
    FACTION_RULE = "faction_rule", "Faction rule"


class TermsEffect(models.TextChoices):
    """What a successful set of terms does to a group."""

    PASS = "pass", "Let us pass"
    FLEE = "flee", "Clear off"
    TURN = "turn", "Turn"
    TOLL = "toll", "Pay us"


# The group states in which a group is still part of a live standoff: the party may act on
# it and its cause is tested. PROPOSED is OPEN with a GM decision pending (#4354).
LIVE_GROUP_STATES: tuple[str, ...] = (StandoffGroupState.OPEN, StandoffGroupState.PROPOSED)


class MoraleDirection(models.TextChoices):
    """Which way the GM morale control moves a group (#4354)."""

    SHAKE = "shake", "Shake"
    STEADY = "steady", "Steady"


class ProposalResolution(models.TextChoices):
    """What a GM did with a standoff proposal (#4354)."""

    CONFIRM = "confirm", "Confirm"
    HOLD = "hold", "Hold for one action"
    OVERRIDE = "override", "Override"


# System strings: why a cause fired, stated on the GM's proposal (#4354).
REASON_OUTWEIGHED = "The party does not outweigh them by their margin."
REASON_PROVOKED_PRESS = "Critical failure on a press (counts as a provocation)."
REASON_PROVOKED_TERMS = "Critical failure on terms (counts as a provocation)."

# The five check tiers, by ``success_level``, as one plain word each.
SUCCESS_LEVEL_WORDS: dict[int, str] = {
    -2: "Critical failure",
    -1: "Failure",
    0: "Partial success",
    1: "Success",
    2: "Critical success",
}

FIGHT_BEGINS_MESSAGE = "The fight begins."

# System strings: why the language gate refuses a verbal approach or terms (#4373).
REFUSAL_NO_LANGUAGE = "They have no language to answer in."
REFUSAL_NO_SHARED_LANGUAGE = "You share no language with them."

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


class CauseEffect(models.TextChoices):
    """What a matched faction rule does to a group's cause (#4415).

    SUPPRESS: the group will not start the fight while every active participant matches a
    suppressing rule. PROVOKE: a participant who matches one sets the group off, whatever
    the force, unless the group is broken.
    """

    NONE = "none", "None"
    SUPPRESS = "suppress", "Suppress"
    PROVOKE = "provoke", "Provoke"


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
# #4415: the remaining causes and the re-test when a hold on an opponent ends.
REASON_HUNGER = "The party does not outweigh them by their margin, widened by hunger to {margin}%."
REASON_RULE_PROVOKES = "{name} matches a faction rule that provokes them."
REASON_TERRITORY = "They waited {count} actions for the party to settle or leave."
REASON_TERRITORY_HELD = "The party is still in their ground."
REASON_RELEASED = "A hold on them ended and their cause still holds: {reason}"

# The five check tiers, by ``success_level``, as one plain word each.
SUCCESS_LEVEL_WORDS: dict[int, str] = {
    -2: "Critical failure",
    -1: "Failure",
    0: "Partial success",
    1: "Success",
    2: "Critical success",
}

FIGHT_BEGINS_MESSAGE = "The fight begins."

# System strings: room lines from the remaining causes and the broken-hold re-test (#4415).
LINE_LOSING_PATIENCE = "{referent} {verb} losing patience."
LINE_RELEASED_LEAVES = "{name} leaves."

# System strings: why the language gate refuses a verbal approach or terms (#4373).
REFUSAL_NO_LANGUAGE = "They have no language to answer in."
REFUSAL_NO_SHARED_LANGUAGE = "You share no language with them."


class ProfileChange(models.TextChoices):
    """One edit a player makes to their own character's standoff profile (#4441)."""

    OPT_IN = "opt_in", "Opt in"
    OPT_OUT = "opt_out", "Opt out"
    CAUSE = "cause", "Set cause"
    DRIVE = "drive", "Set drive"
    DROP_DRIVE = "drop_drive", "Drop drive"


# System strings: the player-character gate and the profile lock (#4441).
REFUSAL_NOT_OPTED_IN = "{name} has not agreed to be read or pressed."
REFUSAL_SELF_TARGET = "You cannot do that to yourself."
PROFILE_LOCKED_MESSAGE = "Your profile cannot change while you stand in a standoff."
PROFILE_NOT_YOURS_MESSAGE = "Only a player's own character has a standoff profile."
PROFILE_NO_SUCH_DRIVE_MESSAGE = "That is not a drive anyone can have."
PROFILE_NO_SUCH_CAUSE_MESSAGE = "That is not a cause."
PROFILE_DRIVE_NOT_HELD_MESSAGE = "You do not have that drive."
PROFILE_NO_SUCH_CHANGE_MESSAGE = "That is not a change to a profile."

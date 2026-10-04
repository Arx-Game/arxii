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

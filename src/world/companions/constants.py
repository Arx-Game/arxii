"""Constants for the Companion substrate (#672)."""

from __future__ import annotations

from django.db import models


class CompanionDomain(models.TextChoices):
    """Discriminator for what kind of bound creature a Companion is.

    Only BEAST is a live consumer in this PR (the Beastlord gift). UNDEAD,
    ELEMENTAL, CONSTRUCT, and SPIRIT are reserved for future Gifts/Paths that
    reuse this same substrate (#672 spec, Decision #14) — no code branches on
    them yet.
    """

    BEAST = "BEAST", "Beast"
    UNDEAD = "UNDEAD", "Undead"
    ELEMENTAL = "ELEMENTAL", "Elemental"
    CONSTRUCT = "CONSTRUCT", "Construct"
    SPIRIT = "SPIRIT", "Spirit"


class CompanionAbilityKind(models.TextChoices):
    """Discriminator for what kind of ability a CompanionAbility is (#1921)."""

    ATTACK = "attack", "Attack"
    UTILITY = "utility", "Utility"


class CompanionOrderKind(models.TextChoices):
    """What a player orders their companion to do this round (#1921)."""

    ATTACK_TARGET = "attack_target", "Attack Target"
    HOLD = "hold", "Hold"
    DEFEND_ALLY = "defend_ally", "Defend Ally"

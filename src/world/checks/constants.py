"""Constants for the checks system."""

from django.db import models


class EffectType(models.TextChoices):
    """Type of mechanical effect applied by a consequence."""

    APPLY_CONDITION = "apply_condition", "Apply Condition"
    REMOVE_CONDITION = "remove_condition", "Remove Condition"
    ADD_PROPERTY = "add_property", "Add Property"
    REMOVE_PROPERTY = "remove_property", "Remove Property"
    DEAL_DAMAGE = "deal_damage", "Deal Damage"
    LAUNCH_ATTACK = "launch_attack", "Launch Attack"
    LAUNCH_FLOW = "launch_flow", "Launch Flow"
    GRANT_CODEX = "grant_codex", "Grant Codex Entry"


class EffectTarget(models.TextChoices):
    """What the effect targets."""

    SELF = "self", "Self (acting character)"
    LOCATION = "location", "Location (challenge's room)"

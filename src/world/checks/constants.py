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
    MAGICAL_SCARS = "magical_scars", "Mage Scars"
    LEGEND_AWARD = "legend_award", "Award Legend"


class EffectTarget(models.TextChoices):
    """What the effect targets."""

    SELF = "self", "Self (acting character)"
    TARGET = "target", "Target (recipient of social or targeted action)"
    LOCATION = "location", "Location (challenge's room)"


class ModifierSourceKind(models.TextChoices):
    """Provenance categories for check modifiers."""

    CONDITION = "condition", "Condition"
    ROLLMOD = "rollmod", "Roll Modifier"
    SCENE = "scene", "Surroundings"
    EQUIPMENT = "equipment", "Equipment"
    EFFORT = "effort", "Effort"
    FATIGUE = "fatigue", "Fatigue"
    STRAIN = "strain", "Strain"

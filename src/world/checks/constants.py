"""Constants for the checks system."""

from django.db import models


class EffectType(models.TextChoices):
    """Type of mechanical effect applied by a consequence."""

    APPLY_CONDITION = "apply_condition", "Apply Condition"
    REMOVE_CONDITION = "remove_condition", "Remove Condition"
    SET_RELATIONSHIP_CONDITION = "set_relationship_condition", "Set Relationship Condition"
    SHIFT_AFFECTION = "shift_affection", "Shift Affection"
    SHIFT_NPC_REGARD = "shift_npc_regard", "Shift NPC Regard"
    ADD_PROPERTY = "add_property", "Add Property"
    REMOVE_PROPERTY = "remove_property", "Remove Property"
    GRANT_DISTINCTION = "grant_distinction", "Grant Distinction"
    DEAL_DAMAGE = "deal_damage", "Deal Damage"
    LAUNCH_ATTACK = "launch_attack", "Launch Attack"
    LAUNCH_FLOW = "launch_flow", "Launch Flow"
    GRANT_CODEX = "grant_codex", "Grant Codex Entry"
    MAGICAL_SCARS = "magical_scars", "Mage Scars"
    LEGEND_AWARD = "legend_award", "Award Legend"
    CAPTURE = "capture", "Capture"
    ESCAPE_CAPTIVITY = "escape_captivity", "Escape Captivity"
    RESCUE_CAPTIVE = "rescue_captive", "Rescue Captive"
    CREATE_POSITION = "create_position", "Create Position"
    MOVE_TO_POSITION = "move_to_position", "Move to Position"
    SEVER_EDGE = "sever_edge", "Sever Edge"
    CONNECT_EDGE = "connect_edge", "Connect Edge"
    GRANT_FLIGHT = "grant_flight", "Grant Flight"
    REMOVE_FLIGHT = "remove_flight", "Remove Flight"


class PositionDestination(models.TextChoices):
    """How a MOVE_TO_POSITION effect resolves its destination within the room."""

    ACTOR_POSITION = "actor_position", "Actor's current position"
    GATING_FAR_SIDE = "gating_far_side", "Far side of the gating edge"
    NAMED = "named", "Named position in the room"
    AWAY_FROM_ACTOR = "away_from_actor", "Away from actor (knockback)"


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
    FASHION = "fashion", "Fashion"
    CHARACTER = "character", "Character"
    EFFORT = "effort", "Effort"
    FATIGUE = "fatigue", "Fatigue"
    STRAIN = "strain", "Strain"
    AFFINITY = "affinity", "Affinity"
    PULL = "pull", "Combat Pull"
    RELATIONSHIP = "relationship", "Relationship"

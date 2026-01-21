# src/world/distinctions/types.py
from django.db import models


class EffectType(models.TextChoices):
    """Types of mechanical effects a distinction can have."""

    STAT_MODIFIER = "stat_modifier", "Stat Modifier"
    AFFINITY_MODIFIER = "affinity_modifier", "Affinity Modifier"
    RESONANCE_MODIFIER = "resonance_modifier", "Resonance Modifier"
    ROLL_MODIFIER = "roll_modifier", "Roll Modifier"
    CODE_HANDLED = "code_handled", "Code Handled"


class DistinctionOrigin(models.TextChoices):
    """How a character acquired a distinction."""

    CHARACTER_CREATION = "character_creation", "Character Creation"
    GAMEPLAY = "gameplay", "Gameplay"


class OtherStatus(models.TextChoices):
    """Status of a freeform 'Other' distinction entry."""

    PENDING_REVIEW = "pending_review", "Pending Review"
    APPROVED = "approved", "Approved"
    MAPPED = "mapped", "Mapped to Distinction"

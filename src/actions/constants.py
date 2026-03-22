"""Constants for the action system."""

from enum import StrEnum

from django.db import models


class EnhancementSourceType(models.TextChoices):
    """The type of model that provides an ActionEnhancement."""

    DISTINCTION = "distinction", "Distinction"
    CONDITION = "condition", "Condition"
    TECHNIQUE = "technique", "Technique"


class TransformType(models.TextChoices):
    """Named transforms for kwarg modification."""

    UPPERCASE = "uppercase", "Uppercase"
    LOWERCASE = "lowercase", "Lowercase"


class Pipeline(models.TextChoices):
    """Resolution pattern for ActionTemplate."""

    SINGLE = "single", "Single Check"
    GATED = "gated", "Gated (with prerequisite checks)"


class GateRole(models.TextChoices):
    """Semantic role of an ActionTemplateGate."""

    ACTIVATION = "activation", "Activation"


class ActionTargetType(models.TextChoices):
    """Target type for data-driven ActionTemplates (mirrors TargetType StrEnum)."""

    SELF = "self", "Self"
    SINGLE = "single", "Single Target"
    AREA = "area", "Area"
    FILTERED_GROUP = "filtered_group", "Filtered Group"


class ResolutionPhase(StrEnum):
    """Phase of the action resolution state machine.

    StrEnum (not TextChoices) because this is in-memory state machine state,
    never stored in a database column.
    """

    GATE_PENDING = "gate_pending"
    GATE_RESOLVED = "gate_resolved"
    MAIN_PENDING = "main_pending"
    MAIN_RESOLVED = "main_resolved"
    CONTEXT_PENDING = "context_pending"
    COMPLETE = "complete"

"""Constants for the action system."""

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

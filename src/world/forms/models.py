from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class TraitType(models.TextChoices):
    COLOR = "color", "Color"
    STYLE = "style", "Style"


class FormTrait(SharedMemoryModel):
    """Definition of a physical characteristic type (e.g., hair_color, ear_type)."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    trait_type = models.CharField(max_length=20, choices=TraitType.choices, default=TraitType.STYLE)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.display_name

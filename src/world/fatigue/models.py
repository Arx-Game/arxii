from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.character_sheets.models import CharacterSheet
from world.fatigue.constants import FatigueCategory


class FatiguePool(SharedMemoryModel):
    """Tracks three independent fatigue pools per character.

    Fatigue accumulates from 0 upward as actions are performed.
    Higher values = more tired. Capacity is calculated dynamically
    from the character's endurance stats.
    """

    character = models.OneToOneField(
        CharacterSheet,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="fatigue",
    )
    physical_current = models.PositiveIntegerField(default=0)
    social_current = models.PositiveIntegerField(default=0)
    mental_current = models.PositiveIntegerField(default=0)
    well_rested = models.BooleanField(default=False, help_text="Grants +50% capacity on next reset")
    rested_today = models.BooleanField(default=False, help_text="Rest command used this IC day")
    dawn_deferred = models.BooleanField(default=False, help_text="In scene at dawn, reset pending")

    VALID_CATEGORIES = {c.value for c in FatigueCategory}

    def get_current(self, category: str) -> int:
        """Get current fatigue for a category."""
        if category not in self.VALID_CATEGORIES:
            msg = f"Invalid fatigue category: {category!r}"
            raise ValueError(msg)
        field_map = {
            "physical": self.physical_current,
            "social": self.social_current,
            "mental": self.mental_current,
        }
        return field_map[category]

    def set_current(self, category: str, value: int) -> None:
        """Set current fatigue for a category."""
        if category not in self.VALID_CATEGORIES:
            msg = f"Invalid fatigue category: {category!r}"
            raise ValueError(msg)
        field_name = f"{category}_current"
        setattr(self, field_name, max(0, value))

    def __str__(self) -> str:
        return (
            f"Fatigue: {self.character}"
            f" (P:{self.physical_current} S:{self.social_current} M:{self.mental_current})"
        )

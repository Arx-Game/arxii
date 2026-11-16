from django.core.validators import MinValueValidator
from django.db import models

from actions.constants import ActionCategory
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.character_sheets.models import CharacterSheet


class FatiguePool(SharedMemoryModel):
    """Tracks three independent fatigue pools per character.

    Fatigue accumulates from 0 upward as actions are performed.
    Higher values = more tired. Capacity is calculated dynamically
    from the character's endurance stats.
    """

    character_sheet = models.OneToOneField(
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

    VALID_CATEGORIES = {c.value for c in ActionCategory}

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
            f"Fatigue: {self.character_sheet}"
            f" (P:{self.physical_current} S:{self.social_current} M:{self.mental_current})"
        )


SINGLETON_PK = 1


class FatigueConfig(SharedMemoryModel):
    """Singleton: the stat terms of fatigue capacity and the well-rested bonus (#5093).

    Capacity works like health: partly from stats, plus a per-level bonus. This row holds the
    stat terms (a stamina-like endurance stat and willpower, each counted per 10 points of the
    stat, #5091) and the well-rested bonus; the per-level bonus is the
    ``FATIGUE_LEVEL_BONUS`` lane's ``ModifierLevelBaseline`` rows, which add nothing until
    staff author them. One row at pk 1, read through ``get_singleton``, which falls back to the
    field defaults (without saving them) on a database that has no row.
    """

    stat_multiplier = models.PositiveSmallIntegerField(
        default=10,
        help_text=(
            "Fatigue capacity each 10 points of the category's endurance stat (stamina for "
            "physical, composure for social, stability for mental) gives."
        ),
    )
    willpower_multiplier = models.PositiveSmallIntegerField(
        default=3,
        help_text="Fatigue capacity each 10 points of willpower gives, in every category.",
    )
    well_rested_percent = models.PositiveSmallIntegerField(
        default=150,
        validators=[MinValueValidator(100)],
        help_text=(
            "A well-rested character's capacity as a percent of normal (150 means one and a "
            "half times, rounded down)."
        ),
    )

    class Meta:
        verbose_name = "Fatigue config"
        verbose_name_plural = "Fatigue config"

    @classmethod
    def get_singleton(cls) -> "FatigueConfig":
        """The row at pk 1, or an unsaved row of the field defaults when a database has none.

        Never writes: capacity is read on paths that must create nothing (the read-only
        fatigue zone behind movement inspection), and the defaults are the shipped terms, so
        a database without the row reads the same numbers a seeded one does.
        """
        try:
            return cls.objects.get(pk=SINGLETON_PK)
        except cls.DoesNotExist:
            return cls(pk=SINGLETON_PK)

    def __str__(self) -> str:
        return (
            f"Fatigue config (stat x{self.stat_multiplier}, "
            f"willpower x{self.willpower_multiplier}, well rested {self.well_rested_percent}%)"
        )

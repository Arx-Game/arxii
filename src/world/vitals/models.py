"""Models for the vitals system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.vitals.constants import WOUND_DESCRIPTIONS, CharacterStatus


class CharacterVitals(SharedMemoryModel):
    """Persistent character life state and health tracking.

    Tracks the character's current life status (alive, unconscious, dying, dead)
    independently of any specific combat encounter. Combat reads and writes
    health directly on this model.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="vitals",
    )
    status = models.CharField(
        max_length=20,
        choices=CharacterStatus.choices,
        default=CharacterStatus.ALIVE,
    )
    died_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the character died (permanent death).",
    )
    unconscious_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the character became unconscious.",
    )
    health = models.IntegerField(
        default=0,
        help_text="Current health points.",
    )
    max_health = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Maximum health points. Derived as base_max_health + thread-derived "
            "VITAL_BONUS MAX_HEALTH addend by recompute_max_health."
        ),
    )
    base_max_health = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Baseline max health before thread-derived VITAL_BONUS addends. "
            "Set by the character-creation / stat pipeline; recompute_max_health "
            "derives max_health = base_max_health + thread_addend."
        ),
    )
    dying_final_round = models.BooleanField(
        default=False,
        help_text="Whether the character gets one final action before death.",
    )

    def __str__(self) -> str:
        return f"{self.character_sheet} ({self.get_status_display()})"

    @property
    def health_percentage(self) -> float:
        """Return health as a fraction of max_health, clamped to [0.0, 1.0]."""
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    @property
    def wound_description(self) -> str:
        """Human-readable wound severity based on current health percentage."""
        pct = self.health_percentage
        for threshold, description in WOUND_DESCRIPTIONS:
            if pct >= threshold:
                return description
        return WOUND_DESCRIPTIONS[-1][1]

"""Models for the vitals system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.vitals.constants import WOUND_DESCRIPTIONS, CharacterLifeState


class CharacterVitals(SharedMemoryModel):
    """Persistent character mortality and health tracking.

    Tracks the character's mortality marker (life_state: alive/dead) and health
    independently of any specific combat encounter. Consciousness and dying are
    modeled as conditions (Unconscious, Bleeding Out), not vitals fields. Combat
    reads and writes health directly on this model.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="vitals",
    )
    died_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the character died (permanent death).",
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
    life_state = models.CharField(
        max_length=10,
        choices=CharacterLifeState.choices,
        default=CharacterLifeState.ALIVE,
        help_text="Mortality axis. Consciousness/dying are conditions, not vitals.",
    )
    death_deferred_pending = models.BooleanField(
        default=False,
        help_text=(
            "Set when CHARACTER_KILLED is suppressed by an active death_deferred condition. "
            "Cleared and CHARACTER_KILLED is emitted when that condition expires."
        ),
    )

    def __str__(self) -> str:
        return f"{self.character_sheet} ({self.get_life_state_display()})"

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


class VitalsConsequenceConfig(SharedMemoryModel):
    """Singleton (pk=1): global knockout pool + default wound/death pools used
    when a DamageType doesn't specify its own. Authored via admin."""

    knockout_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Global knockout consequence pool (damage-type-agnostic).",
    )
    default_wound_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Fallback permanent-wound pool when DamageType.wound_pool is null.",
    )
    default_death_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Fallback death pool when DamageType.death_pool is null.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"VitalsConsequenceConfig(pk={self.pk})"

"""Models for the vitals system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.vitals.constants import (
    AUTO_RETIRE_DAYS,
    DEATH_BASE_DIFFICULTY,
    DEATH_SCALING_PER_PERCENT,
    KNOCKOUT_BASE_DIFFICULTY,
    KNOCKOUT_SCALING_PER_PERCENT,
    WAKE_BASE_DIFFICULTY,
    WAKE_EASE_PER_ROUND,
    WAKE_GUARANTEED_ROUNDS,
    WAKE_SCALING_PER_PERCENT,
    WOUND_BASE_DIFFICULTY,
    WOUND_DESCRIPTIONS,
    WOUND_SCALING_PER_PERCENT,
    CharacterLifeState,
)

# Cross-app FK string for the consequence pool model, referenced by several
# fields below. Centralized to avoid the duplicated-literal SonarCloud smell
# (python:S1192).
_CONSEQUENCE_POOL_FK = "actions.ConsequencePool"


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
    died_in_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deaths",
        help_text=(
            "Scene active at the body's location when the character died; bounds the "
            "ghost emit window and death-kudos eligibility. Null for offscreen deaths."
        ),
    )
    retired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the dead character was released (player retire, staff force, or "
            "auto-retire). Set = the character can no longer be puppeted."
        ),
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
        null=True,
        blank=True,
        help_text="Authored fixed base override; null = derive from level/stamina/role (see services).",  # noqa: E501
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

    objects = ArxSharedMemoryManager()

    knockout_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Global knockout consequence pool (damage-type-agnostic).",
    )
    default_wound_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Fallback permanent-wound pool when DamageType.wound_pool is null.",
    )
    default_death_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Fallback death pool when DamageType.death_pool is null.",
    )
    # ------------------------------------------------------------------
    # Survivability difficulty tuning — authored here, read by services.py
    # ------------------------------------------------------------------

    knockout_base_difficulty = models.PositiveIntegerField(
        default=KNOCKOUT_BASE_DIFFICULTY,
        help_text=(
            "Base difficulty for the knockout check when health is exactly at the 20% threshold."
        ),
    )
    knockout_scaling_per_percent = models.PositiveIntegerField(
        default=KNOCKOUT_SCALING_PER_PERCENT,
        help_text=(
            "Additional difficulty added per percentage point health falls below the 20% threshold."
        ),
    )
    death_base_difficulty = models.PositiveIntegerField(
        default=DEATH_BASE_DIFFICULTY,
        help_text=("Base difficulty for the death check when health is exactly at 0%."),
    )
    death_scaling_per_percent = models.PositiveIntegerField(
        default=DEATH_SCALING_PER_PERCENT,
        help_text=("Additional difficulty added per percentage point health is below 0%."),
    )
    wound_base_difficulty = models.PositiveIntegerField(
        default=WOUND_BASE_DIFFICULTY,
        help_text=(
            "Base difficulty for the permanent-wound check when damage is exactly"
            " at the 50% threshold."
        ),
    )
    wound_scaling_per_percent = models.PositiveIntegerField(
        default=WOUND_SCALING_PER_PERCENT,
        help_text=(
            "Additional difficulty added per percentage point damage exceeds the 50% threshold."
        ),
    )

    stamina_to_health_weight = models.PositiveSmallIntegerField(
        default=3,
        help_text="Health per point of Stamina contributed to base_max_health.",
    )

    # ------------------------------------------------------------------
    # Wake arc (unconscious recovery) tuning (#2287)
    # ------------------------------------------------------------------

    wake_base_difficulty = models.PositiveIntegerField(
        default=WAKE_BASE_DIFFICULTY,
        help_text="Base difficulty of the per-round wake (Endurance) check at full health.",
    )
    wake_scaling_per_percent = models.PositiveIntegerField(
        default=WAKE_SCALING_PER_PERCENT,
        help_text="Additional wake difficulty per percentage point of missing health.",
    )
    wake_ease_per_round = models.PositiveIntegerField(
        default=WAKE_EASE_PER_ROUND,
        help_text="Wake difficulty eased per round spent unconscious.",
    )
    wake_guaranteed_rounds = models.PositiveIntegerField(
        default=WAKE_GUARANTEED_ROUNDS,
        help_text=(
            "Rounds until an unconscious character is guaranteed to wake "
            "(converted to a wall-clock deadline out of combat)."
        ),
    )

    # ------------------------------------------------------------------
    # Death off-ramp tuning (#2287)
    # ------------------------------------------------------------------

    auto_retire_days = models.PositiveIntegerField(
        default=AUTO_RETIRE_DAYS,
        help_text="Days after death before a dead character is auto-retired.",
    )
    death_condolence_body = models.TextField(
        blank=True,
        default="",
        help_text=(
            "OOC message delivered to the player at the moment of death. "
            "Admin-editable; seeded with a PLACEHOLDER paragraph."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"VitalsConsequenceConfig(pk={self.pk})"

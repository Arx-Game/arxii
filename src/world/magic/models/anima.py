"""Character anima resource and recovery rituals.

CharacterAnima tracks a character's magical energy resource.
AnimaRitualPerformance is the historical record of ritual performances.
The personalized recovery ritual is now modelled as a Ritual row with
execution_kind=SCENE_ACTION and a RitualCheckConfig sidecar.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel


class CharacterAnima(SharedMemoryModel):
    """
    Tracks a character's magical energy resource.

    Anima is spent to fuel powers and recovers through personalized rituals.
    Current anima fluctuates during play; max anima may increase with level.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="anima",
        help_text="The character this anima belongs to.",
    )
    current = models.PositiveIntegerField(
        default=10,
        help_text="Current anima available.",
    )
    maximum = models.PositiveIntegerField(
        default=10,
        help_text="Maximum anima capacity.",
    )
    last_recovery = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When anima was last recovered through ritual.",
    )
    pre_audere_maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Stored maximum before Audere expanded the pool. Null when not in Audere.",
    )

    class Meta:
        verbose_name = "Character Anima"
        verbose_name_plural = "Character Anima"

    def __str__(self) -> str:
        return f"Anima of {self.character} ({self.current}/{self.maximum})"

    def clean(self) -> None:
        """Validate that current doesn't exceed maximum."""
        if self.current > self.maximum:
            msg = "Current anima cannot exceed maximum."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class AnimaRitualPerformance(SharedMemoryModel):
    """
    Historical record of an anima ritual performance.

    Links to scene for RP history, tracks success and recovery.
    """

    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="performances",
        help_text="The Ritual (SCENE_ACTION kind) that was performed.",
    )
    performed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the ritual was performed.",
    )
    target_character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        related_name="anima_ritual_participations",
        help_text="The character the ritual was performed with.",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anima_ritual_performances",
        help_text="The scene where this ritual was performed.",
    )
    was_successful = models.BooleanField(
        help_text="Whether the ritual succeeded.",
    )
    anima_recovered = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Amount of anima recovered (if successful).",
    )
    outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anima_ritual_performances",
        help_text=(
            "CheckOutcome resolved for this performance. Nullable for "
            "backward-compat with existing rows that predate Scope 6."
        ),
    )
    severity_reduced = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Severity points the performance removed from the performer's "
            "Soulfray condition. 0 if no reduction."
        ),
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this performance.",
    )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Anima Ritual Performance"
        verbose_name_plural = "Anima Ritual Performances"

    def __str__(self) -> str:
        status = "success" if self.was_successful else "failure"
        return f"{self.ritual} ({status}) at {self.performed_at}"


class AnimaConfig(SharedMemoryModel):
    daily_regen_percent = models.PositiveIntegerField(
        default=5,
        help_text="% of CharacterAnima.maximum regenerated per daily tick",
    )
    daily_regen_blocking_property_key = models.SlugField(
        default="blocks_anima_regen",
        help_text="Property key on a ConditionStage that blocks anima regen",
    )

    @classmethod
    def get_singleton(cls) -> "AnimaConfig":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={})
        return obj

    def __str__(self) -> str:
        return f"{type(self).__name__}"

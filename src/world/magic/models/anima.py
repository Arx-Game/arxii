"""Character anima resource and recovery rituals.

CharacterAnima tracks a character's magical energy resource.
AnimaRitualPerformance is the historical record of ritual performances.
The personalized recovery ritual is now modelled as a Ritual row with
execution_kind=SCENE_ACTION and a RitualCheckConfig sidecar.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import AnimaRitualEndorsement


class CharacterAnima(SharedMemoryModel):
    """
    Tracks a character's magical energy resource.

    Anima is spent to fuel powers and recovers through personalized rituals.
    Current anima fluctuates during play; max anima may increase with level.
    """

    character = models.OneToOneField(
        "arxii.CharacterSheet",
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
    # #2853: overfeeding lands here, NOT in current — clean() forbids current > maximum
    # and that validation stays. Spends draw glut first; glut decays daily and never
    # satisfies appetite-upkeep floors or quiets Ravenous (a temporary high, not a tank).
    glut = models.PositiveIntegerField(
        default=0,
        help_text="Decaying overfill from feeding past maximum (#2853).",
    )

    class Meta:
        verbose_name = "Character Anima"
        verbose_name_plural = "Character Anima"

    def __str__(self) -> str:
        return f"Anima of {self.character} ({self.current}/{self.maximum})"

    @property
    def effective_current(self) -> int:
        """Spendable anima including glut (#2853). Glut spends first."""
        return self.current + self.glut

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
        "arxii.Ritual",
        on_delete=models.CASCADE,
        related_name="performances",
        help_text="The Ritual (SCENE_ACTION kind) that was performed.",
    )
    performed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the ritual was performed.",
    )
    target_character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        related_name="anima_ritual_participations",
        help_text="The character the ritual was performed with.",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
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
        "arxii.CheckOutcome",
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
    endorsement = models.CharField(
        max_length=10,
        choices=AnimaRitualEndorsement.choices,
        default=AnimaRitualEndorsement.NOT_ASKED,
        db_default=AnimaRitualEndorsement.NOT_ASKED,
        help_text=(
            "Where the partner's answer stands: not asked (nobody to answer), pending, "
            "endorsed, withheld or lapsed."
        ),
    )
    outward_amount_pending = models.PositiveIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "The outward resonance growth held until the partner answers. 0 once it is "
            "granted, withheld or lapsed, or when there was none."
        ),
    )
    outward_resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The outward resonance this performance reached for, held for the grant.",
    )
    performer_persona = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anima_ritual_performances_given",
        help_text=(
            "The persona the performer wore for this ritual (the request's initiator "
            "persona), so the partner's card never shows a masked true name."
        ),
    )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Anima Ritual Performance"
        verbose_name_plural = "Anima Ritual Performances"

    def __str__(self) -> str:
        status = "success" if self.was_successful else "failure"
        return f"{self.ritual} ({status}) at {self.performed_at}"


class AnimaConfig(SharedMemoryModel):
    # #3001: regen is a flat trickle, not a percentage — an archmage's pool refills
    # in years, not weeks. Anima rituals, feeding, and blood ARE the recovery economy.
    daily_regen_amount = models.PositiveIntegerField(
        default=1,
        help_text="Flat anima regenerated per daily tick (appetite holders never regen).",
    )
    daily_regen_blocking_property_key = models.SlugField(
        default="blocks_anima_regen",
        help_text="Property key on a ConditionStage that blocks anima regen",
    )
    level_zero_maximum = models.PositiveIntegerField(
        default=10,
        help_text="Maximum anima for a level-0 (quiescent/NPC) character.",
    )
    # The maximum at level N >= 1 is the ANIMA_POOL lane's baseline row (#5093).
    death_harvest_multiplier = models.PositiveIntegerField(
        default=20,
        help_text=(
            "Killing a victim by anima drain yields this multiple of their full "
            "maximum (#3001) - the metaphysical engine of ritual murder."
        ),
    )

    failed_endorsement_percent = models.PositiveSmallIntegerField(
        default=50,
        validators=[MaxValueValidator(100)],
        help_text=(
            "Percent of the Success tier's outward resonance part granted to the performer "
            "when the partner endorses an anima ritual after a failed roll (0 to 100)."
        ),
    )
    attunement_anima_cost = models.PositiveIntegerField(
        default=0,
        help_text="Anima a character spends to attune a new pair of aura resonances.",
    )
    attunement_resonance_cost = models.PositiveIntegerField(
        default=0,
        help_text="Resonance balance a character spends to attune a new pair of aura resonances.",
    )
    attunement_ap_cost = models.PositiveIntegerField(
        default=0,
        help_text="Action points a character spends to attune a new pair of aura resonances.",
    )
    attunement_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The check a character rolls to attune a new pair of aura resonances.",
    )
    attunement_difficulty_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Difficulty of the attunement check, authored as a level (0 = no difficulty): "
            "the roll meets that level's baseline."
        ),
    )

    @classmethod
    def get_singleton(cls) -> "AnimaConfig":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={})
        return obj

    def __str__(self) -> str:
        return f"{type(self).__name__}"

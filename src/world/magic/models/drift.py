"""Drift correction models (#4733, slice 4 of #4672).

Drift correction lets a character convert resonance earned from deeds that pulled them off
their aura back toward resonances they want to grow. A deed in a scene opens one
``DriftConversionOffer``; the offer carries one ``DriftConversionCap`` per target resonance
(how much of the deed's gain may be converted toward it, and which ``ResonanceGrant`` rows
that cap was measured from). Staff tune the rite through ``DriftCorrectionConfig`` and how
much of the cap a roll converts through ``DriftCorrectionOutcomeShare``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.models import OutcomeTierAward

_RESONANCE_FK = "arxii.Resonance"


class DriftCorrectionConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning for the drift correction rite.

    Every foreign key is nullable so the lazily created row is valid before staff author
    it; the rite refuses to run until the rite and check type are set.

    ``check_type`` and ``check_difficulty`` are deliberately NOT a ``RitualCheckConfig``
    sidecar: that model requires a stat and a skill, and ``perform_ritual_check`` looks the
    config up by ritual NAME and accepts no extra modifiers. This rite designates its ritual
    and its check by foreign key and rolls with a focus modifier.
    """

    objects = ArxSharedMemoryManager()

    rite = models.ForeignKey(
        "arxii.Ritual",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The ritual a character performs to correct drift.",
    )
    check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check rolled when the rite is performed.",
    )
    check_difficulty = models.PositiveSmallIntegerField(
        default=0,
        help_text="Difficulty of the rite's check.",
    )
    cap_percent = models.PositiveSmallIntegerField(
        default=50,
        validators=[MaxValueValidator(100)],
        help_text="Percent of a deed's resonance grant that may be converted.",
    )

    class Meta:
        verbose_name = "Drift correction config"
        verbose_name_plural = "Drift correction config"

    def __str__(self) -> str:
        return "Drift correction config"


class DriftCorrectionOutcomeShare(OutcomeTierAward):
    """Share of the cap a rite converts, per outcome tier of its check (decision 15).

    A better outcome never converts a smaller share than a worse one; ``clean`` enforces it.
    """

    converted_share = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text="Fraction of the cap converted, from 0.00 to 1.00.",
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Drift correction outcome share"

    def __str__(self) -> str:
        return f"{self.outcome_tier_id}: {self.converted_share}"

    def clean(self) -> None:
        super().clean()
        if self.converted_share is None or self.outcome_tier_id is None:
            return
        if not 0 <= self.converted_share <= 1:
            raise ValidationError({"converted_share": "A share runs from 0.00 to 1.00."})
        siblings = type(self).objects.exclude(pk=self.pk)
        level = self.outcome_tier.success_level
        worse_above = siblings.filter(
            outcome_tier__success_level__lt=level, converted_share__gt=self.converted_share
        ).exists()
        better_below = siblings.filter(
            outcome_tier__success_level__gt=level, converted_share__lt=self.converted_share
        ).exists()
        if worse_above or better_below:
            raise ValidationError(
                {
                    "converted_share": (
                        "A better outcome must convert at least as much as a worse one."
                    )
                }
            )


class DriftConversionOffer(SharedMemoryModel):
    """A character's open chance to correct drift after a scene's deeds (one per scene)."""

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="drift_conversion_offers",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.CASCADE,
        related_name="drift_conversion_offers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "scene"],
                name="one_drift_conversion_offer_per_sheet_scene",
            ),
        ]

    def __str__(self) -> str:
        return f"DriftConversionOffer(sheet={self.character_sheet_id}, scene={self.scene_id})"


class DriftConversionCap(SharedMemoryModel):
    """How much of an offer's deed gain may be converted toward one target resonance.

    ``cap`` is a deliberate snapshot taken at grant time: a later change to
    ``DriftCorrectionConfig.cap_percent`` mid-scene does not rewrite it. ``grants`` links the
    grants that fed this cap and stops one grant counting twice inside a scene's offer.
    """

    offer = models.ForeignKey(
        DriftConversionOffer,
        on_delete=models.CASCADE,
        related_name="caps",
    )
    target_resonance = models.ForeignKey(
        _RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="drift_conversion_caps",
    )
    cap = models.PositiveIntegerField(
        help_text="Most that may be converted toward this resonance.",
    )
    grants = models.ManyToManyField(
        "arxii.ResonanceGrant",
        related_name="drift_conversion_caps",
        help_text="The deed grants this cap was measured from.",
    )

    class Meta:
        ordering = ["offer", "target_resonance"]
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "target_resonance"],
                name="one_drift_conversion_cap_per_offer_target",
            ),
        ]

    def __str__(self) -> str:
        return f"DriftConversionCap(offer={self.offer_id}, target={self.target_resonance_id})"

"""Drift correction models (#4733, slice 4 of #4672).

Drift correction lets a character convert resonance earned from deeds that pulled them off
their aura back toward resonances they want to grow. A deed in a scene opens one
``DriftConversionOffer``; the offer carries one ``DriftConversionCap`` per target resonance
(how much of the deed's gain may be converted toward it, and which ``ResonanceGrant`` rows
that cap was measured from). Staff tune the rite through ``DriftCorrectionConfig`` and how
much of the cap a roll converts through ``DriftCorrectionOutcomeShare``.

Being unsettled (#4732, #5123) is measured and contested through ``DriftConfig``: a
character grown past who they are rolls to keep her focus when she works her magic.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.models import OutcomeTierAward
from world.traits.constants import TraitType

_RESONANCE_FK = "arxii.Resonance"


class DriftConfig(SharedMemoryModel):
    """Singleton (pk=1) of unsettled tuning, creation points and the focus roll.

    A character is unsettled when a non-main affinity's share of their aura passes its
    settled share by ``unsettled_tolerance_percent``; each ``unsettled_step_percent``
    past that is one step of severity on the conflict condition. These two numbers are the
    general values: an Affinity may set its own range and step for characters whose main
    affinity it is, and ``drift_for`` reads those first.

    Access via ``get_drift_config()`` in ``world.magic.services.drift``.
    """

    objects = ArxSharedMemoryManager()

    unsettled_tolerance_percent = models.PositiveSmallIntegerField(
        default=5,
        validators=[MaxValueValidator(100)],
        help_text=(
            "General range before Unsettled: percentage points an affinity may exceed its "
            "settled share. An Affinity's own value, when set, replaces it for characters "
            "whose main affinity is that one."
        ),
    )
    unsettled_step_percent = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=(
            "General step: percentage points past the range that add one step of severity. "
            "An Affinity's own value, when set, replaces it."
        ),
    )
    own_side_tolerance_percent = models.PositiveSmallIntegerField(
        default=15,
        validators=[MaxValueValidator(100)],
        verbose_name="Own-side range",
        help_text=(
            "Percentage points. A character whose main affinity is Primal is Unsettled by "
            "growth on the side she already leans to only past this."
        ),
    )
    creation_points = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Points a new character spreads across their starting resonances.",
    )
    creation_seed_per_point = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Lifetime resonance points seeded per creation point.",
    )
    second_resonance_level_step = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text=(
            "Thread levels a non-leading resonance reads below the thread's level "
            "when it pays a pull."
        ),
    )
    focus_base_difficulty_level = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Difficulty of the focus roll before any severity steps. Authored as a "
            "level (0 = no difficulty): the roll meets that level's baseline."
        ),
    )
    focus_difficulty_per_step_tenths = models.PositiveIntegerField(
        default=4,
        help_text=(
            "Difficulty added to the focus roll per severity step. Authored in tenths "
            "of one level's width."
        ),
    )
    focus_check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check a character rolls to keep her focus against carried drift.",
    )
    conflict_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The condition applied when a character fails to keep her focus.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drift_config_edits",
    )

    def __str__(self) -> str:
        return f"DriftConfig(pk={self.pk})"


class DriftCorrectionConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning for the drift correction rite.

    Every foreign key is nullable so the lazily created row is valid before staff author
    it; the rite refuses to run until the rite and check type are set.

    ``check_type`` and ``check_difficulty_level`` are deliberately NOT a ``RitualCheckConfig``
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
    check_difficulty_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Difficulty of the rite's check. Authored as a level (0 = no difficulty): "
            "the roll meets that level's baseline."
        ),
    )
    cap_percent = models.PositiveSmallIntegerField(
        default=50,
        validators=[MaxValueValidator(100)],
        help_text="Percent of a deed's resonance grant that may be converted; 0 opens no offer.",
    )
    disown_deed_percent = models.PositiveSmallIntegerField(
        default=75,
        validators=[MaxValueValidator(100)],
        help_text=(
            "Percent of a deed's resonance a rite converts at a full share when a player "
            "Disowns that deed (#5124). A starting value for tuning."
        ),
    )

    class Meta:
        verbose_name = "Drift correction config"
        verbose_name_plural = "Drift correction config"

    def __str__(self) -> str:
        return "Drift correction config"

    def clean(self) -> None:
        """The rite's check weighs no skill: the roll adds the skill of the affinity it turns
        toward itself, so a weighted skill would count twice (#5308)."""
        super().clean()
        if self.check_type_id is None:
            return
        if any(ctt.trait.trait_type == TraitType.SKILL for ctt in self.check_type.traits.all()):
            raise ValidationError(
                {
                    "check_type": (
                        "The rite's check must weigh no skill: the roll adds the skill of the "
                        "affinity it turns toward itself, so a skill on the check type would "
                        "count twice."
                    )
                }
            )


class DriftCorrectionOutcomeShare(OutcomeTierAward):
    """Share of the requested amount a rite converts, per outcome tier of its check (decision 15).

    The rite converts ``floor(amount x converted_share)`` of what the player asked to move
    (never more than the cap allows). A share of 0.00 converts nothing; a tier with no row at
    all makes the rite refuse before anything is spent.

    A better outcome never converts a smaller share than a worse one; ``clean`` enforces it.
    """

    converted_share = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text="Fraction of the requested amount converted, from 0.00 to 1.00.",
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
    """A character's one open chance to correct drift (#4733, one per character since #5124).

    Opened by a main-affinity deed in a live scene, extended by later deeds (caps merge per
    resonance), and open until the rite spends it. ``scene`` is where it first opened.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="drift_conversion_offers",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drift_conversion_offers",
        help_text="The scene the offer first opened in.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                name="one_drift_conversion_offer_per_sheet",
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

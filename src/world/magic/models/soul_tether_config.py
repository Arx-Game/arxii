"""SoulTetherConfig — singleton tuning surface for the Soul Tether bond mechanic (Spec B)."""

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.checks.models import OutcomeTierAward


class SoulTetherConfig(NaturalKeyMixin, SharedMemoryModel):
    """Singleton tuning surface (pk=1).

    All integer fields; multipliers encoded as integer-tenths or integer-hundredths
    to avoid float precision. Access via ``get_soul_tether_config()`` — singleton-by-
    convention, no DB-level uniqueness constraint.

    Sineating fields (#5177):
    - ``sineating_check_type`` / ``sineating_difficulty_level``: the check the Sineater rolls to
      perform the ritual, and its difficulty as a level. Unset means the ritual refuses.
    - ``corruption_per_unit``: corruption one unit moves from the Sinner to the Sineater.
    - ``resonance_per_unit``: resonance one unit earns each of them at a full share. The
      ``SineatingOutcomeAward`` row for the rolled tier scales it.
    - ``per_scene_cap_hard_max``: Hard ceiling on units accepted per scene (default 20).
    - ``per_scene_cap_base``: Base per-scene cap before level scaling (default 5).

    The level scaling of the per-scene cap and of the Hollow's maximum capacity is the
    ``SOUL_TETHER_SCENE_CAP`` and ``HOLLOW_MAX`` lanes' ``ModifierLevelBaseline`` rows, one per
    rung (10 thread levels), seeded at 2 and 10 per rung (#5093).

    Sineater resistance:
    - ``resistance_full_at``: lifetime Sineating (``lifetime_helped``) at which a Sineater's
      resistance to corruption reaches its 90% cap (default 1000).

    Rescue thresholds (minimum Hollow strain to trigger each stage):
    - ``rescue_strain_stage3`` / ``_stage4`` / ``_stage5``: strain thresholds (5/10/18).

    Rescue resonance costs:
    - ``rescue_resonance_stage3`` / ``_stage4`` / ``_stage5``: resonance cost (10/20/35).

    Rescue budget bases:
    - ``rescue_budget_base_stage3`` / ``_stage4`` / ``_stage5``: budget base (60/120/250).

    Rescue budget multipliers (formula = base/10 + success * success/10 + thread rung term):
    - ``rescue_budget_base_mult_tenths``: base multiplier in tenths (default 10 → 1.0).
    - ``rescue_budget_success_mult_tenths``: success-level multiplier in tenths (default 5 → 0.5).
    - The thread term is the ``RESCUE_BUDGET_THREAD`` lane's baseline at the Sineater's thread
      rung, in hundredths (#5093; the seeded rows give 0.5 a rung, what 0.05 a thread level did).
    """

    class NaturalKeyConfig:
        fields = ["pk"]

    objects = NaturalKeyManager()

    # --- Sineating ---
    sineating_check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The check a Sineater rolls to perform Sineating. Until it is set, Sineating "
            "says it has not been set up yet."
        ),
    )
    sineating_difficulty_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Difficulty of the Sineating check. Authored as a level (0 = no difficulty): "
            "the roll meets that level's baseline."
        ),
    )
    corruption_per_unit = models.PositiveIntegerField(
        default=60,
        help_text="Corruption one unit of Sineating moves from the Sinner to the Sineater.",
    )
    resonance_per_unit = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Resonance one unit of Sineating earns the Sinner and the Sineater each, when the "
            "roll's outcome pays a full share."
        ),
    )
    per_scene_cap_hard_max = models.PositiveSmallIntegerField(default=20)
    per_scene_cap_base = models.PositiveSmallIntegerField(default=5)

    # --- Sineater resistance ---
    resistance_full_at = models.PositiveIntegerField(
        default=1000,
        help_text=(
            "How much Sineating a Sineater has done in a resonance before they resist 90% of "
            "the corruption they take on in it, the most resistance they can reach. They "
            "resist a proportional share before that: half this much resists 50%."
        ),
    )

    # --- Rescue strain thresholds ---
    rescue_strain_stage3 = models.PositiveSmallIntegerField(default=5)
    rescue_strain_stage4 = models.PositiveSmallIntegerField(default=10)
    rescue_strain_stage5 = models.PositiveSmallIntegerField(default=18)

    # --- Rescue resonance costs ---
    rescue_resonance_stage3 = models.PositiveSmallIntegerField(default=10)
    rescue_resonance_stage4 = models.PositiveSmallIntegerField(default=20)
    rescue_resonance_stage5 = models.PositiveSmallIntegerField(default=35)

    # --- Rescue budget bases ---
    rescue_budget_base_stage3 = models.PositiveSmallIntegerField(default=60)
    rescue_budget_base_stage4 = models.PositiveSmallIntegerField(default=120)
    rescue_budget_base_stage5 = models.PositiveSmallIntegerField(default=250)

    # --- Rescue budget multipliers (integer-encoded) ---
    # Reconstruct as: base/10 + success * success_tenths/10 + the thread rung lane's term
    rescue_budget_base_mult_tenths = models.PositiveSmallIntegerField(
        default=10,
        help_text="Base budget multiplier in tenths (10 → 1.0).",
    )
    rescue_budget_success_mult_tenths = models.PositiveSmallIntegerField(
        default=5,
        help_text="Per-success-level budget multiplier in tenths (5 → 0.5).",
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="soul_tether_config_updates",
    )

    def __str__(self) -> str:
        return f"SoulTetherConfig(pk={self.pk})"


class SineatingOutcomeAward(OutcomeTierAward):
    """Share of full resonance a Sineating earns each party, per outcome tier of its roll (#5177).

    Each of the Sinner and the Sineater earns
    ``floor(units x SoulTetherConfig.resonance_per_unit x earned_share)`` of the resonance of
    their own half of the bond. 1.00 is a full share, 0.00 earns nothing, and a share above
    1.00 lets staff reward a critical. The corruption moves whatever the roll. A tier with no
    row makes Sineating refuse before anything is written.

    A better outcome never earns a smaller share than a worse one; ``clean`` enforces it.
    """

    earned_share = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text=(
            "Fraction of full resonance each of them earns, from 0.00 up to 9.99. "
            "1.00 is a full share."
        ),
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Sineating outcome award"

    def __str__(self) -> str:
        return f"{self.outcome_tier_id}: {self.earned_share}"

    def clean(self) -> None:
        super().clean()
        if self.earned_share is None or self.outcome_tier_id is None:
            return
        if self.earned_share < 0:
            raise ValidationError({"earned_share": "A share cannot be negative."})
        siblings = type(self).objects.exclude(pk=self.pk)
        level = self.outcome_tier.success_level
        worse_above = siblings.filter(
            outcome_tier__success_level__lt=level, earned_share__gt=self.earned_share
        ).exists()
        better_below = siblings.filter(
            outcome_tier__success_level__gt=level, earned_share__lt=self.earned_share
        ).exists()
        if worse_above or better_below:
            raise ValidationError(
                {"earned_share": "A better outcome must earn at least as much as a worse one."}
            )

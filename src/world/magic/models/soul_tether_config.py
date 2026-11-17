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

    Settling the Mire (#5177), all percents or integers:
    - ``purify_reward_percent``: of the corruption an absolve or condemn clears, what the
      Sineater earns (default 50).
    - ``absolve_affection`` / ``condemn_conflict`` / ``succumb_affection`` /
      ``succumb_conflict``: how far the tie moves at a full share (default 5 each).
    - ``succumb_bonus_percent`` / ``jackpot_percent``: what the Sinner earns when the Sineater
      succumbs, of the amount succumbed and of what the Sineater purified since the last
      payout (default 200 and 25).
    - ``fall_payout_percent`` / ``fall_breaker_bonus_percent``: what each Sinner earns when
      the Sineater falls, of what was succumbed to them, and the extra for the most recent
      (default 300 and 50).

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

    # --- Settling the Mire (#5177) ---
    purify_reward_percent = models.PositiveIntegerField(
        default=50,
        help_text=(
            "When a Sineater absolves or condemns the Mire they carry, the percent of the "
            "corruption cleared that they earn as resonance in their own thread's resonance."
        ),
    )
    absolve_affection = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Affection the Sineater gains toward the Sinner when they absolve, at a full "
            "share of the settling rite."
        ),
    )
    condemn_conflict = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Conflict the Sineater gains toward the Sinner when they condemn, at a full "
            "share of the settling rite."
        ),
    )
    succumb_affection = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Affection the Sineater gains toward the Sinner when they succumb, at a full "
            "share of the settling rite."
        ),
    )
    succumb_conflict = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Conflict the Sineater gains toward the Sinner when they succumb, at a full "
            "share of the settling rite."
        ),
    )
    succumb_bonus_percent = models.PositiveIntegerField(
        default=200,
        help_text=(
            "When a Sineater succumbs, the percent of the amount succumbed that the Sinner "
            "earns as resonance in their own thread's resonance (200 pays twice the amount)."
        ),
    )
    jackpot_percent = models.PositiveIntegerField(
        default=25,
        help_text=(
            "When a Sineater succumbs, the percent of everything they purified for this "
            "Sinner since the last payout that the Sinner also earns."
        ),
    )
    fall_payout_percent = models.PositiveIntegerField(
        default=300,
        help_text=(
            "When a Sineater falls to the Abyss, the percent of what they succumbed to each "
            "Sinner since their last fall that this Sinner earns."
        ),
    )
    fall_breaker_bonus_percent = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Extra percent on top of the fall's payout for the Sinner of the most recent "
            "succumbing, who tipped the Sineater over (50 pays half as much again)."
        ),
    )

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

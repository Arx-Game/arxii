"""Power derivation tuning config singleton (#637)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.magic.constants import StandingCapMode


class LevelPowerConfig(SharedMemoryModel):
    """Staff-tunable singleton controlling how character and technique level feed into power.

    Zero values (the default) disable the term entirely. Access via
    ``get_level_power_config()`` in ``services/power_terms.py``.
    """

    character_level_bonus = models.IntegerField(
        default=0,
        help_text="Flat power added per point of the caster's current character level.",
    )
    technique_level_bonus = models.IntegerField(
        default=0,
        help_text="Flat power added per point of the technique's level.",
    )

    class Meta:
        verbose_name = "Level Power Config"
        verbose_name_plural = "Level Power Configs"

    def __str__(self) -> str:
        return (
            f"LevelPowerConfig(char×{self.character_level_bonus},"
            f" tech×{self.technique_level_bonus})"
        )


class AuraPowerConfig(SharedMemoryModel):
    """Staff-tunable singleton controlling how aura feeds into power (#768).

    Two axes; zero values (the default) disable each axis. Access via
    ``get_aura_power_config()`` in ``services/power_terms.py``.
    """

    affinity_alignment_bonus = models.IntegerField(
        default=0,
        help_text=(
            "Power granted at 100% aura in the affinity matching the technique's "
            "resonance(s); contributes proportionally (aura_pct/100 x this)."
        ),
    )
    resonance_standing_bonus = models.IntegerField(
        default=0,
        help_text=(
            "Power per point of CharacterResonance.lifetime_earned in the "
            "technique's resonance(s) ('aura farming' - standing earned from "
            "scene reactions). Uses lifetime_earned, not spendable balance."
        ),
    )

    class Meta:
        verbose_name = "Aura Power Config"
        verbose_name_plural = "Aura Power Configs"

    def __str__(self) -> str:
        return (
            f"AuraPowerConfig(align={self.affinity_alignment_bonus},"
            f" standing={self.resonance_standing_bonus})"
        )


class StandingCapBand(SharedMemoryModel):
    """Per-character-level cap band for the resonance-standing power term (#853).

    Staff author one row per level threshold. The band with the greatest
    ``min_level`` <= the caster's ``current_level`` sets the cap. HARD clamps to
    ``cap``; SOFT keeps ``diminish_pct`` percent of the excess above ``cap``. No
    bands authored = uncapped (the term stays opt-in).
    """

    min_level = models.PositiveIntegerField(
        unique=True,
        help_text="Lowest character current_level at which this band applies.",
    )
    cap = models.PositiveIntegerField(
        help_text="Cap on the resonance-standing power contribution at this band.",
    )
    mode = models.CharField(
        max_length=4,
        choices=StandingCapMode.choices,
        default=StandingCapMode.HARD,
        help_text="HARD clamps to cap; SOFT diminishes the excess above cap.",
    )
    diminish_pct = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text=(
            "SOFT only: percent (0-100) of each point above cap that still "
            "counts. Ignored for HARD."
        ),
    )

    class Meta:
        ordering = ["min_level"]
        verbose_name = "Standing Cap Band"
        verbose_name_plural = "Standing Cap Bands"

    def clean(self) -> None:
        super().clean()
        if self.mode == StandingCapMode.HARD and self.diminish_pct:
            raise ValidationError({"diminish_pct": "diminish_pct must be 0 for HARD bands."})

    def __str__(self) -> str:
        return f"StandingCapBand(L{self.min_level}+, cap={self.cap}, {self.mode})"


class CovenantRoleBlendConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning for the covenant-role blend power term (#2529).

    Baseline bonus = total_thread_level × blend_weight × multiplier_tenths / 10,
    summed over engaged roles. ``multiplier_tenths`` is integer-tenths
    (10 = ×1.0). Lazy-created via ``get_covenant_role_blend_config()`` in
    ``services/power_terms.py``. Tuning frame (#2529 amendment 2): an engaged
    vow's baseline should read as a visibly higher effective tier; Layer 4
    perks target ≈2× this baseline.
    """

    objects = ArxSharedMemoryManager()

    multiplier_tenths = models.PositiveIntegerField(
        default=10,
        help_text="Blend multiplier in integer-tenths (10 = ×1.0).",
    )

    class Meta:
        verbose_name = "Covenant Role Blend Config"
        verbose_name_plural = "Covenant Role Blend Config"

    def __str__(self) -> str:
        return "Covenant Role Blend Config"

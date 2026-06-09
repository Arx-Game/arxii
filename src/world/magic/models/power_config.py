"""Power derivation tuning config singleton (#637)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


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
    resonance_standing_cap = models.PositiveIntegerField(
        default=0,
        help_text="Soft cap on the resonance-standing axis (0 = uncapped).",
    )

    class Meta:
        verbose_name = "Aura Power Config"
        verbose_name_plural = "Aura Power Configs"

    def __str__(self) -> str:
        return (
            f"AuraPowerConfig(align={self.affinity_alignment_bonus},"
            f" standing={self.resonance_standing_bonus},"
            f" cap={self.resonance_standing_cap})"
        )

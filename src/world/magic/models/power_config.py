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

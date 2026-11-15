"""The check scale's one tunable number: how much of the baseline a character's level is (#5093).

A character's level adds ``level_share`` of that level's baseline to every roll (the level
term); skills and stats supply the rest of the climb. An opponent of the same level is
exactly the level's baseline, so a level-N character with ordinary skills rolls at about rank
N against a level-N opponent. Staff tune the share in this row; nothing in code is a per-level
coefficient.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel

SINGLETON_PK = 1


class CheckScaleConfig(SharedMemoryModel):
    """Singleton: the share of a level's baseline a character's level adds to a roll (#5093).

    Follows the ``AnimaConfig`` pattern: one row at pk 1, read through ``get_singleton``.
    """

    level_share = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal("0.5"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(1))],
        help_text=(
            "The share of a level's baseline that a character's level adds to every roll "
            "(0.500 means level carries half of the baseline, and skills and stats the "
            "rest). Between 0 and 1."
        ),
    )

    class Meta:
        verbose_name = "Check scale config"
        verbose_name_plural = "Check scale config"

    @classmethod
    def get_singleton(cls) -> CheckScaleConfig:
        # A pk read comes from the idmapper cache once the row is loaded; the row is created
        # with the model default only the first time anything reads a database that has none.
        try:
            return cls.objects.get(pk=SINGLETON_PK)
        except cls.DoesNotExist:
            return cls.objects.get_or_create(pk=SINGLETON_PK, defaults={})[0]

    def __str__(self) -> str:
        return f"Check scale config (level share {self.level_share})"

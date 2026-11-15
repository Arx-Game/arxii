"""The one development cost scale every levelling trait shares (#5093).

Development cost grows geometrically, once per character level. A trait value ``v`` sits in
character level ``v // 10`` (its band); every step inside a band costs the same, a tenth of
that band's cost. Staff tune the starting level, the cost of the starting band and the growth
in this row; no cost number is written in code.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel

SINGLETON_PK = 1


class DevelopmentCostConfig(SharedMemoryModel):
    """Singleton: the geometric development point cost curve (#5093).

    Follows the ``AnimaConfig`` pattern: one row at pk 1, read through ``get_singleton``, which
    creates it from the field defaults the first time a database without one is read. The
    defaults are the shipped starting values: a band costs 100 at level 1 and 150 percent of
    the band before it from there.
    """

    start_level = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "The character level whose band costs the base cost. A band below it costs the "
            "base cost too."
        ),
    )
    base_cost = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        help_text=(
            "Development points one whole band (ten steps) costs at the start level. Each "
            "step inside the band costs a tenth of it."
        ),
    )
    growth_percent = models.PositiveSmallIntegerField(
        default=150,
        validators=[MinValueValidator(100)],
        help_text=(
            "Each band costs this percent of the band before it (150 means one and a half "
            "times as much). 100 makes every band cost the same."
        ),
    )

    class Meta:
        verbose_name = "Development cost config"
        verbose_name_plural = "Development cost config"

    @classmethod
    def get_singleton(cls) -> DevelopmentCostConfig:
        # A pk read comes from the idmapper cache once the row is loaded; the row is created
        # from the field defaults only the first time anything reads a database that has none.
        try:
            return cls.objects.get(pk=SINGLETON_PK)
        except cls.DoesNotExist:
            return cls.objects.get_or_create(pk=SINGLETON_PK, defaults={})[0]

    def __str__(self) -> str:
        return (
            f"Development cost config (base {self.base_cost} at level {self.start_level}, "
            f"growth {self.growth_percent}%)"
        )

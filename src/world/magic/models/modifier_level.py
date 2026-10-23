"""How a cast's power and outcome become the level of the modifier it applies (#4594).

A technique's buff or debuff carries a level (#4551 section 5.3): the cast's
effective power picks a level from ``CastPowerLevel`` rows, and the cast's outcome
shifts it by a ``CastOutcomeLevelShift`` row. The modifier's size comes from the
technique's authored row; together they read the lane's value table. Nothing here
reads the target's level.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel


class CastPowerLevel(SharedMemoryModel):
    """A cast of at least ``min_power`` effective power applies modifiers at ``level``.

    The row with the highest ``min_power`` at or below the cast's power wins. A cast
    weaker than every row applies no level, so its modifiers keep their flat authored
    values.
    """

    min_power = models.PositiveIntegerField(
        unique=True,
        help_text="The lowest effective cast power this row covers.",
    )
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="The modifier level a cast of this power applies.",
    )

    class Meta:
        ordering = ["min_power"]
        verbose_name = "Cast power to modifier level"
        verbose_name_plural = "Cast power to modifier level"

    def __str__(self) -> str:
        return f"Power {self.min_power}+ applies level {self.level}"


class CastOutcomeLevelShift(SharedMemoryModel):
    """A cast landing at ``success_level`` shifts its modifiers' level by ``level_shift``.

    A success level with no row shifts nothing. The shifted level never drops below 1.
    """

    success_level = models.SmallIntegerField(
        unique=True,
        help_text="The cast outcome's success level (Partial Success 0, Success 1, "
        "Critical Success 2).",
    )
    level_shift = models.SmallIntegerField(
        help_text="Levels added to (or, if negative, taken from) the applied modifier.",
    )

    class Meta:
        ordering = ["success_level"]
        verbose_name = "Cast outcome level shift"
        verbose_name_plural = "Cast outcome level shifts"

    def __str__(self) -> str:
        return f"Success level {self.success_level}: level {self.level_shift:+d}"

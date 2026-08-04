"""Touchstone cast-bonus tuning config (#2023).

Singleton (pk=1) config for the touchstone combat resonance bonus.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager

_VERBOSE_NAME = "Touchstone Cast Config"


class TouchstoneCastConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning knobs for touchstone combat resonance.

    The per-tier cast bonus is ``resonance_tier.tier_level * config_scale / 10``.
    ``config_scale`` is encoded as integer-tenths (e.g. 10 = x1.0, 15 = x1.5).
    Lazy-created via ``get_touchstone_cast_config()`` in
    ``world/magic/services/touchstone.py``.
    """

    objects = ArxSharedMemoryManager()

    config_scale = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Per-tier bonus multiplier (integer-tenths: 10 = x1.0). "
            "Bonus = resonance_tier.tier_level * config_scale / 10."
        ),
    )

    class Meta:
        verbose_name = _VERBOSE_NAME
        verbose_name_plural = _VERBOSE_NAME

    def __str__(self) -> str:
        return _VERBOSE_NAME

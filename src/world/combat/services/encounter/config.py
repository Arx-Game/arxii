"""Flee, strain, and clash configuration getters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import FleeConfig

if TYPE_CHECKING:
    from world.combat.models import ClashConfig, StrainConfig


def get_flee_config() -> FleeConfig:
    """Return the seeded FleeConfig singleton (#878).

    Uses cached_singleton() — never get_or_create — because this is authored
    content; a fabricated row would have no check_type and silently break flee
    resolution. DoesNotExist propagates loudly. Mirrors
    get_penetration_check_type.
    """
    config = FleeConfig.objects.cached_singleton()
    if config is None:
        raise FleeConfig.DoesNotExist
    return config


# ---------------------------------------------------------------------------
# Clash tuning singleton accessors
# ---------------------------------------------------------------------------


def get_strain_config() -> StrainConfig:
    """Get-or-create the StrainConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        StrainConfig,
    )

    cfg = StrainConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = StrainConfig.objects.get_or_create(pk=1)
    return cfg


def get_clash_config() -> ClashConfig:
    """Get-or-create the ClashConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        ClashConfig,
    )

    cfg = ClashConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = ClashConfig.objects.get_or_create(pk=1)
    return cfg

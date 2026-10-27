"""Flee, strain, and clash configuration getters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import FleeConfig, SocialManeuverConfig

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


def get_social_maneuver_config() -> SocialManeuverConfig:
    """The SocialManeuverConfig singleton (pk=1, #4739), created empty if missing.

    Unlike flee, an empty row is safe: every designation on it is nullable and a
    reader treats an unset one as "not authored yet" (the Required content dashboard
    lists it). The created row is re-read through ``cached_singleton()`` so every
    caller shares the one identity-mapped instance.
    """
    config = SocialManeuverConfig.objects.cached_singleton()
    if config is None:
        SocialManeuverConfig.objects.get_or_create(pk=1)
        config = SocialManeuverConfig.objects.cached_singleton()
    return config

"""Carried-drift services (#4732)."""

from django.db import transaction

from world.magic.models.drift import DriftConfig


def get_drift_config() -> DriftConfig:
    """Get-or-create the drift config singleton (pk=1)."""
    with transaction.atomic():
        cfg = DriftConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = DriftConfig.objects.get_or_create(pk=1)
    return cfg

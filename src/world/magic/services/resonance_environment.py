"""Services for the resonance-environment primitive."""

from django.db import transaction

from world.magic.models import ResonanceEnvironmentConfig


def get_resonance_environment_config() -> ResonanceEnvironmentConfig:
    """Get-or-create the resonance environment config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = ResonanceEnvironmentConfig.objects.get_or_create(pk=1)
        return cfg

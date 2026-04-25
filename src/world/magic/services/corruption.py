"""Services for the Corruption foundation (Magic Scope #7)."""

from world.magic.models.corruption_config import CorruptionConfig


def get_corruption_config() -> CorruptionConfig:
    """Lazy-create the CorruptionConfig singleton at pk=1."""
    config, _ = CorruptionConfig.objects.get_or_create(pk=1)
    return config

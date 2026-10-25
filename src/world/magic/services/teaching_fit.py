"""Tradition teaching fit (slice 2 of #4659)."""

from world.magic.models import TraditionTeachingConfig


def get_teaching_config() -> TraditionTeachingConfig:
    """Lazily create and return the singleton TraditionTeachingConfig (pk=1)."""
    config = TraditionTeachingConfig.objects.cached_singleton()
    if config is None:
        config, _ = TraditionTeachingConfig.objects.get_or_create(pk=1)
    return config

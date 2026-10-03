"""Language training tuning, XP locks and breakthroughs (#4090 amendment).

Trained fluency advances through weekly ``TrainLanguageAction`` sessions whose dp rates
staff tune on ``LanguageTrainingConfig``, and stops one rating below an authored
``TraitRatingUnlock`` until the character spends XP on the breakthrough, the same way
skills park at their XP boundaries (``world.skills.services``).
"""

from __future__ import annotations

from world.species.models import LanguageTrainingConfig


def get_language_training_config() -> LanguageTrainingConfig:
    """Lazily create and return the singleton LanguageTrainingConfig (pk=1)."""
    config = LanguageTrainingConfig.objects.cached_singleton()
    if config is None:
        config, _ = LanguageTrainingConfig.objects.get_or_create(pk=1)
    return config

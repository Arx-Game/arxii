"""Language training config and XP-lock tests (#4090 amendment)."""

from __future__ import annotations

from django.test import TestCase

from world.species.language_progression import get_language_training_config
from world.species.models import LanguageTrainingConfig


class LanguageTrainingConfigTests(TestCase):
    def setUp(self) -> None:
        LanguageTrainingConfig.objects.flush_singleton_cache()

    def test_accessor_lazily_creates_defaults(self) -> None:
        self.assertFalse(LanguageTrainingConfig.objects.exists())
        config = get_language_training_config()
        self.assertEqual(config.teacher_dp_per_session, 15)
        self.assertEqual(config.self_study_dp_per_session, 8)
        self.assertEqual(LanguageTrainingConfig.objects.count(), 1)

    def test_accessor_returns_the_edited_row(self) -> None:
        LanguageTrainingConfig.objects.create(
            pk=1, teacher_dp_per_session=40, self_study_dp_per_session=12
        )
        config = get_language_training_config()
        self.assertEqual(config.teacher_dp_per_session, 40)
        self.assertEqual(config.self_study_dp_per_session, 12)

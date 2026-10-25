"""Tradition teaching fit (slice 2 of #4659)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.factories import AffinityFactory
from world.magic.models import TraditionTeachingConfig
from world.magic.services.teaching_fit import get_teaching_config
from world.magic.types.aura import AffinityType


class TeachingConfigTests(TestCase):
    def test_config_is_lazy_singleton(self) -> None:
        first = get_teaching_config()
        second = get_teaching_config()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(
            (
                first.gift_fit_training_bonus,
                first.affinity_fit_training_bonus,
                first.course_ease_gift_fit,
                first.course_ease_affinity_fit,
            ),
            (10, 10, 2, 2),
        )

    def test_training_bonus_not_a_step_multiple_is_refused(self) -> None:
        config = TraditionTeachingConfig(gift_fit_training_bonus=15)
        with self.assertRaises(ValidationError):
            config.full_clean()


class AffinityAuraTypeTests(TestCase):
    def test_aura_type_unique_when_set_blank_repeats(self) -> None:
        AffinityFactory(aura_type="")
        AffinityFactory(aura_type="")
        AffinityFactory(aura_type=AffinityType.ABYSSAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AffinityFactory(aura_type=AffinityType.ABYSSAL)

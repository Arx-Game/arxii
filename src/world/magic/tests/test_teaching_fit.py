"""Tradition teaching fit (slice 2 of #4659)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import TraditionTeachingConfig
from world.magic.services.teaching_fit import (
    cg_aura_type,
    character_aura_type,
    get_teaching_config,
    teaching_fit,
)
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


class TeachingFitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_teaching_config()
        cls.gift = GiftFactory()
        cls.other_gift = GiftFactory()
        cls.affinity = AffinityFactory(aura_type=AffinityType.CELESTIAL)
        cls.tradition = TraditionFactory()
        cls.tradition.favored_affinities.add(cls.affinity)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)

    def test_both_fit(self) -> None:
        fit = teaching_fit(self.tradition, self.gift, AffinityType.CELESTIAL)
        self.assertTrue(fit.gift_fit and fit.affinity_fit)
        self.assertEqual(fit.favored_gift_name, self.gift.name)
        self.assertEqual(fit.favored_affinity_name, self.affinity.name)
        self.assertEqual(fit.training_bonus(self.config), 20)
        self.assertEqual(fit.course_ease(self.config), 4)

    def test_gift_only(self) -> None:
        fit = teaching_fit(self.tradition, self.gift, AffinityType.ABYSSAL)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (True, False))
        self.assertIsNone(fit.favored_affinity_name)
        self.assertEqual(fit.training_bonus(self.config), 10)

    def test_affinity_only(self) -> None:
        fit = teaching_fit(self.tradition, self.other_gift, AffinityType.CELESTIAL)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, True))
        self.assertIsNone(fit.favored_gift_name)
        self.assertEqual(fit.course_ease(self.config), 2)

    def test_neither(self) -> None:
        fit = teaching_fit(self.tradition, self.other_gift, None)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, False))
        self.assertEqual(fit.training_bonus(self.config), 0)
        self.assertEqual(fit.course_ease(self.config), 0)

    def test_no_tradition(self) -> None:
        fit = teaching_fit(None, self.gift, AffinityType.CELESTIAL)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, False))
        self.assertIsNone(fit.tradition)

    def test_blank_aura_type_affinity_never_fits(self) -> None:
        blank = AffinityFactory(aura_type="")
        tradition = TraditionFactory()
        tradition.favored_affinities.add(blank)
        resonance = ResonanceFactory(affinity=blank)
        fit = teaching_fit(tradition, self.gift, cg_aura_type(resonance))
        self.assertFalse(fit.affinity_fit)

    def test_cg_aura_type(self) -> None:
        resonance = ResonanceFactory(affinity=self.affinity)
        self.assertEqual(cg_aura_type(resonance), AffinityType.CELESTIAL)
        self.assertIsNone(cg_aura_type(None))

    def test_character_aura_type(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertIsNone(character_aura_type(sheet))
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=sheet)
        sheet = type(sheet).objects.get(pk=sheet.pk)
        self.assertEqual(character_aura_type(sheet), AffinityType.PRIMAL)

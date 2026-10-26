"""Tradition teaching fit (slice 2 of #4659)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterGiftFactory,
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import TraditionTeachingConfig
from world.magic.services.teaching_fit import (
    get_teaching_config,
    student_traits,
    teaching_fit,
)


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


class TeachingFitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_teaching_config()
        cls.gift = GiftFactory()
        cls.other_gift = GiftFactory()
        cls.affinity = AffinityFactory()
        cls.other_affinity = AffinityFactory()
        cls.tradition = TraditionFactory()
        cls.tradition.favored_affinities.add(cls.affinity)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)

    def test_both_fit(self) -> None:
        fit = teaching_fit(self.tradition, self.gift, self.affinity)
        self.assertTrue(fit.gift_fit and fit.affinity_fit)
        self.assertEqual(fit.favored_gift_name, self.gift.name)
        self.assertEqual(fit.favored_affinity_name, self.affinity.name)
        self.assertEqual(fit.training_bonus(self.config), 20)
        self.assertEqual(fit.course_ease(self.config), 4)

    def test_gift_only(self) -> None:
        fit = teaching_fit(self.tradition, self.gift, self.other_affinity)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (True, False))
        self.assertIsNone(fit.favored_affinity_name)
        self.assertEqual(fit.training_bonus(self.config), 10)

    def test_affinity_only(self) -> None:
        fit = teaching_fit(self.tradition, self.other_gift, self.affinity)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, True))
        self.assertIsNone(fit.favored_gift_name)
        self.assertEqual(fit.course_ease(self.config), 2)

    def test_neither(self) -> None:
        fit = teaching_fit(self.tradition, self.other_gift, None)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, False))
        self.assertEqual(fit.training_bonus(self.config), 0)
        self.assertEqual(fit.course_ease(self.config), 0)

    def test_no_tradition(self) -> None:
        fit = teaching_fit(None, self.gift, self.affinity)
        self.assertEqual((fit.gift_fit, fit.affinity_fit), (False, False))
        self.assertIsNone(fit.tradition)

    def test_student_affinity_is_the_dominant_aura_affinity(self) -> None:
        celestial, _primal, abyssal = ensure_canonical_affinities()
        sheet = CharacterSheetFactory()
        CharacterGiftFactory(character=sheet, gift=self.gift)
        aura = CharacterAuraFactory(character=sheet, celestial="70", primal="20", abyssal="10")
        traits = student_traits(sheet)
        self.assertEqual(traits.major_gift, self.gift)
        self.assertEqual(traits.affinity, celestial)
        set_aura_split(aura, celestial="10", primal="20", abyssal="70")
        self.assertEqual(student_traits(sheet).affinity, abyssal)

    def test_student_without_an_aura_has_no_affinity(self) -> None:
        sheet = CharacterSheetFactory()
        CharacterGiftFactory(character=sheet, gift=self.gift)
        self.assertIsNone(student_traits(sheet).affinity)
        self.assertIsNone(student_traits(CharacterSheetFactory()).affinity)

    def test_a_gift_thread_does_not_supply_the_affinity(self) -> None:
        sheet = CharacterSheetFactory()
        CharacterGiftFactory(character=sheet, gift=self.gift)
        ThreadFactory(
            owner=sheet,
            resonance=ResonanceFactory(affinity=self.affinity),
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=self.gift,
        )
        traits = student_traits(sheet)
        self.assertEqual(traits.major_gift, self.gift)
        self.assertIsNone(traits.affinity)

"""Tests for TRAIT thread crossing player choices (#1989)."""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.constants import EffectKind, VitalBonusTarget
from world.magic.models.trait_crossing import (
    PendingTraitCrossingOffer,
    TraitCrossingChoice,
    TraitCrossingOption,
)


class TraitCrossingOptionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import ResonanceFactory

        cls.resonance = ResonanceFactory()

    def test_flat_bonus_clean_valid(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Burning Vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )
        opt.clean()  # should not raise

    def test_flat_bonus_clean_missing_amount(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
        )
        with self.assertRaises(ValidationError):
            opt.clean()

    def test_vital_bonus_clean_valid(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Inner Flame",
            effect_kind=EffectKind.VITAL_BONUS,
            vital_bonus_amount=10,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        opt.clean()  # should not raise

    def test_capability_grant_clean_valid(self) -> None:
        from world.conditions.factories import CapabilityTypeFactory

        cap = CapabilityTypeFactory()
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Feverish Insight",
            effect_kind=EffectKind.CAPABILITY_GRANT,
            capability_grant=cap,
        )
        opt.clean()  # should not raise

    def test_narrative_only_clean_valid(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Flavor Text",
            effect_kind=EffectKind.NARRATIVE_ONLY,
            narrative_snippet="Your strength glows with inner fire.",
        )
        opt.clean()  # should not raise

    def test_narrative_only_clean_empty_snippet(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Flavor Text",
            effect_kind=EffectKind.NARRATIVE_ONLY,
        )
        with self.assertRaises(ValidationError):
            opt.clean()

    def test_invalid_effect_kind_rejected(self) -> None:
        opt = TraitCrossingOption(
            resonance=self.resonance,
            crossing_level=3,
            name="Bad",
            effect_kind=EffectKind.INTENSITY_BUMP,
        )
        with self.assertRaises(ValidationError):
            opt.clean()

    def test_is_default_unique_per_resonance_level(self) -> None:
        from django.db import IntegrityError

        TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=3,
            name="Default",
            effect_kind=EffectKind.NARRATIVE_ONLY,
            narrative_snippet="x",
            is_default=True,
        )
        with self.assertRaises(IntegrityError):
            TraitCrossingOption.objects.create(
                resonance=self.resonance,
                crossing_level=3,
                name="Also Default",
                effect_kind=EffectKind.NARRATIVE_ONLY,
                narrative_snippet="y",
                is_default=True,
            )


class TraitCrossingChoiceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
        )
        cls.option = TraitCrossingOption.objects.create(
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

    def test_create_choice(self) -> None:
        choice = TraitCrossingChoice.objects.create(
            thread=self.thread,
            crossing_level=3,
            option=self.option,
        )
        self.assertEqual(choice.option, self.option)
        self.assertEqual(choice.crossing_level, 3)

    def test_unique_choice_per_thread_per_crossing(self) -> None:
        from django.db import IntegrityError

        TraitCrossingChoice.objects.create(
            thread=self.thread,
            crossing_level=3,
            option=self.option,
        )
        with self.assertRaises(IntegrityError):
            TraitCrossingChoice.objects.create(
                thread=self.thread,
                crossing_level=3,
                option=self.option,
            )


class PendingTraitCrossingOfferModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
        )

    def test_create_offer(self) -> None:
        offer = PendingTraitCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )
        self.assertEqual(offer.crossing_level, 3)

    def test_one_pending_per_thread(self) -> None:
        from django.db import IntegrityError

        PendingTraitCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )
        with self.assertRaises(IntegrityError):
            PendingTraitCrossingOffer.objects.create(
                thread=self.thread,
                crossing_level=6,
            )


class TraitCrossingHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=2,
        )
        cls.option = TraitCrossingOption.objects.create(
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
            is_default=True,
        )

    def test_crossing_creates_pending_offer(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)
            mock_beat.assert_called_once()
        self.assertTrue(PendingTraitCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_non_crossing_level_no_offer(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 4
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=3, new_level=4)
            mock_beat.assert_not_called()
        self.assertFalse(PendingTraitCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_multi_crossing_auto_resolves_lower(self) -> None:
        """Crossing from 2->11 auto-resolves 3 and 6, offers 11."""
        from world.magic.crossing.handlers import TraitCrossingHandler

        TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=6,
            name="Greater vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
            is_default=True,
        )
        TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=11,
            name="Master vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=15,
            is_default=True,
        )
        self.thread.level = 11
        with patch("world.magic.crossing.handlers.execute_ceremony_beat"):
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=11)
        self.assertTrue(
            TraitCrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertTrue(
            TraitCrossingChoice.objects.filter(thread=self.thread, crossing_level=6).exists()
        )
        self.assertTrue(
            PendingTraitCrossingOffer.objects.filter(thread=self.thread, crossing_level=11).exists()
        )

    def test_no_crossing_in_range_noop(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 5
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=3, new_level=5)
            mock_beat.assert_not_called()


class ResolveTraitCrossingOfferTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=3,
        )
        cls.option = TraitCrossingOption.objects.create(
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

    def setUp(self) -> None:
        self.offer = PendingTraitCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )

    def test_resolve_creates_choice(self) -> None:
        from world.magic.services.trait_crossing import resolve_trait_crossing_offer

        result = resolve_trait_crossing_offer(self.offer, option=self.option)
        self.assertEqual(result.option_name, "Burning vigor")
        self.assertTrue(
            TraitCrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertFalse(PendingTraitCrossingOffer.objects.filter(pk=self.offer.pk).exists())

    def test_resolve_wrong_resonance_raises_stale(self) -> None:
        from world.magic.exceptions import TraitCrossingOfferStaleError
        from world.magic.factories import ResonanceFactory
        from world.magic.services.trait_crossing import resolve_trait_crossing_offer

        other_resonance = ResonanceFactory()
        wrong_option = TraitCrossingOption.objects.create(
            resonance=other_resonance,
            crossing_level=3,
            name="Wrong",
            effect_kind=EffectKind.NARRATIVE_ONLY,
            narrative_snippet="x",
        )
        with self.assertRaises(TraitCrossingOfferStaleError):
            resolve_trait_crossing_offer(self.offer, option=wrong_option)
        self.assertFalse(PendingTraitCrossingOffer.objects.filter(pk=self.offer.pk).exists())

    def test_resolve_wrong_crossing_level_raises_stale(self) -> None:
        from world.magic.exceptions import TraitCrossingOfferStaleError
        from world.magic.services.trait_crossing import resolve_trait_crossing_offer

        wrong_level_option = TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=6,
            name="Wrong level",
            effect_kind=EffectKind.NARRATIVE_ONLY,
            narrative_snippet="x",
        )
        with self.assertRaises(TraitCrossingOfferStaleError):
            resolve_trait_crossing_offer(self.offer, option=wrong_level_option)


class TraitCrossingReadPathTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=10,
        )

    def test_vital_bonus_from_choice(self) -> None:
        from typeclasses.characters import Character

        option = TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=3,
            name="Inner Flame",
            effect_kind=EffectKind.VITAL_BONUS,
            vital_bonus_amount=10,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        TraitCrossingChoice.objects.create(thread=self.thread, crossing_level=3, option=option)
        char = Character.objects.get(pk=self.sheet.pk)
        total = char.threads.passive_vital_bonuses(VitalBonusTarget.MAX_HEALTH)
        self.assertEqual(total, 10)

    def test_capability_grant_from_choice(self) -> None:
        from typeclasses.characters import Character
        from world.conditions.factories import CapabilityTypeFactory

        cap = CapabilityTypeFactory()
        option = TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=3,
            name="Feverish Insight",
            effect_kind=EffectKind.CAPABILITY_GRANT,
            capability_grant=cap,
        )
        TraitCrossingChoice.objects.create(thread=self.thread, crossing_level=3, option=option)
        char = Character.objects.get(pk=self.sheet.pk)
        granted = char.threads.passive_capability_grants()
        self.assertIn(cap.pk, granted)

    def test_flat_bonus_from_choice(self) -> None:
        from typeclasses.characters import Character

        option = TraitCrossingOption.objects.create(
            resonance=self.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )
        TraitCrossingChoice.objects.create(thread=self.thread, crossing_level=3, option=option)
        char = Character.objects.get(pk=self.sheet.pk)
        total = char.threads.passive_flat_bonus_for_resonance(self.resonance.pk)
        self.assertEqual(total, 5)


class ResolveTraitCrossingOfferActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=3,
        )
        cls.option = TraitCrossingOption.objects.create(
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

    def setUp(self) -> None:
        self.offer = PendingTraitCrossingOffer.objects.create(thread=self.thread, crossing_level=3)

    def test_action_resolves_offer(self) -> None:
        from actions.definitions.trait_crossing import ResolveTraitCrossingOfferAction

        actor = self.sheet.character
        action = ResolveTraitCrossingOfferAction()
        result = action.run(actor=actor, offer=self.offer, option=self.option)
        self.assertTrue(result.success)
        self.assertTrue(
            TraitCrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )

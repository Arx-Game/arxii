"""Tests for TRAIT thread crossing player choices (#1989)."""

from __future__ import annotations

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

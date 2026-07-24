"""Tests for the learn_technique shared commit seam (#1732)."""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import (
    GiftNotOwned,
    TechniqueCapExceeded,
    TechniqueStyleForbidden,
)
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.models import CharacterGift, Thread
from world.magic.services.technique_acquisition import learn_technique


class LearnTechniqueTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        # Give the character the gift + a level-0 thread (cap 3)
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def test_successful_learn_mints_character_technique(self):
        ct = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )
        self.assertEqual(ct.character, self.sheet)
        self.assertEqual(ct.technique, self.technique)

    def test_gift_not_owned_raises(self):
        other_gift = GiftFactory(kind=GiftKind.MINOR)
        other_tech = TechniqueFactory(gift=other_gift)
        with self.assertRaises(GiftNotOwned):
            learn_technique(
                self.sheet,
                other_tech,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_path_style_forbidden_raises(self):
        from world.classes.factories import PathFactory
        from world.progression.factories import CharacterPathHistoryFactory

        allowed = PathFactory()
        other = PathFactory()
        CharacterPathHistoryFactory(character=self.sheet, path=other)
        style = TechniqueStyleFactory(allowed_paths=[allowed])
        forbidden_tech = TechniqueFactory(gift=self.gift, style=style)
        with self.assertRaises(TechniqueStyleForbidden):
            learn_technique(
                self.sheet,
                forbidden_tech,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_cap_exceeded_raises(self):
        # Fill the cap (3 techniques for a level-0 thread)
        for _ in range(3):
            tech = TechniqueFactory(gift=self.gift)
            learn_technique(
                self.sheet,
                tech,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )
        with self.assertRaises(TechniqueCapExceeded):
            learn_technique(
                self.sheet,
                self.technique,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_ap_cost_deducted(self):
        learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
        )
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200 - 10)

    def test_duplicate_raises_value_error(self):
        learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )
        with self.assertRaises(ValueError):
            learn_technique(
                self.sheet,
                self.technique,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )


class TrainingRoomDiscountTests(TestCase):
    """A Training Room in the learner's room discounts technique AP (#675)."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def test_training_room_discounts_ap_cost(self):
        """A Training Room at level 2 reduces the AP spent by 2 (1 per level)."""
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.seeds import ensure_training_room_kind

        kind = ensure_training_room_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind, level=2)

        learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
            location=instance.room_profile.objectdb,
        )
        self.ap_pool.refresh_from_db()
        # 10 - 2 (level 2 * 1 per level) = 8 spent; 200 - 8 = 192
        self.assertEqual(self.ap_pool.current, 192)

    def test_no_training_room_means_full_cost(self):
        """Without a Training Room, the full AP cost is spent (regression)."""
        learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
        )
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200 - 10)

    def test_discount_floors_at_zero(self):
        """The discounted cost never drops below 0 AP."""
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.seeds import ensure_training_room_kind

        kind = ensure_training_room_kind()
        # A level-3 Training Room (max) discounts 3, flooring at 0 for a 2-AP cost.
        instance = RoomFeatureInstanceFactory(feature_kind=kind, level=3)

        learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=2,
            location=instance.room_profile.objectdb,
        )
        self.ap_pool.refresh_from_db()
        # 2 - 3 = -1, floored to 0; 200 - 0 = 200
        self.assertEqual(self.ap_pool.current, 200)

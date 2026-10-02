"""Tests for the learn_technique shared commit seam (#1732)."""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AcquisitionOrigin, GiftKind, TargetKind
from world.magic.exceptions import (
    GiftNotOwned,
    TechniqueCapExceeded,
    TechniqueRequirementsNotMet,
)
from world.magic.factories import (
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterGift, Thread
from world.magic.services.technique_acquisition import learn_technique
from world.progression.models import TechniqueKnownRequirement


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

    def test_learned_technique_carries_trained_origin(self):
        """A technique minted via learn_technique carries origin=TRAINED (#3055).

        This is the shared mint seam for both a ritual TechniqueGrant dispatch and
        a completed TechniqueProgress training meter — regardless of the
        AccessChangeSource narrative label passed in, the acquisition-provenance
        origin is always TRAINED.
        """
        ct = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )
        self.assertEqual(ct.origin, AcquisitionOrigin.TRAINED)

    def test_gift_not_owned_raises(self):
        other_gift = GiftFactory(kind=GiftKind.MINOR)
        other_tech = TechniqueFactory(gift=other_gift)
        with self.assertRaises(GiftNotOwned):
            learn_technique(
                self.sheet,
                other_tech,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_path_does_not_gate_learning(self):
        """A learner's path never blocks a technique from an OWNED gift (#2700).

        Gift ownership plus PathGiftGrant/TraditionGiftGrant curation is the gate;
        the old path-style gate contradicted 71% of authored starter grants and was
        bypassed entirely by grant_path_magic. Style now gates casting, not learning
        (see StyleGatedCastingTests). ADR-0167.
        """
        from world.classes.factories import PathFactory
        from world.magic.factories import TechniqueStyleFactory
        from world.progression.factories import CharacterPathHistoryFactory

        # A path whose style is nothing like the technique's origin.
        subtle = TechniqueStyleFactory(name="Subtle")
        CharacterPathHistoryFactory(
            character=self.sheet, path=PathFactory(name="Path of Whispers", style=subtle)
        )
        technique = TechniqueFactory(gift=self.gift)

        learned = learn_technique(
            self.sheet,
            technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )
        self.assertEqual(learned.technique, technique)

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
        """With ap_cost > 0, a TechniqueProgress meter is created (#2711).

        AP is not spent at meter creation — it's spent per-session via
        ``contribute_to_technique_progress``. The meter total reflects the
        ap_cost (after training-room discount, if any).
        """
        from world.magic.models import TechniqueProgress

        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
        )
        self.assertIsInstance(result, TechniqueProgress)
        self.assertEqual(result.total_required, 10)
        # AP not spent at meter creation
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200)

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
        """A Training Room at level 2 reduces the meter total by 2 (#675, #2711)."""
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.seeds import ensure_training_room_kind

        kind = ensure_training_room_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind, level=2)

        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
            location=instance.room_profile.objectdb,
        )
        # 10 - 2 (level 2 * 1 per level) = 8 meter total
        self.assertEqual(result.total_required, 8)

    def test_no_training_room_means_full_cost(self):
        """Without a Training Room, the full AP cost is the meter total (#2711)."""
        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=10,
        )
        self.assertEqual(result.total_required, 10)

    def test_discount_floors_at_zero(self):
        """The discounted meter total never drops below 0 (#2711)."""
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.seeds import ensure_training_room_kind

        kind = ensure_training_room_kind()
        # A level-3 Training Room (max) discounts 3, flooring at 0 for a 2-AP cost.
        instance = RoomFeatureInstanceFactory(feature_kind=kind, level=3)

        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=2,
            location=instance.room_profile.objectdb,
        )
        # 2 - 3 = -1, floored to 0
        self.assertEqual(result.total_required, 0)


class LearnTechniquePrerequisiteGateTest(TestCase):
    """``learn_technique`` enforces authored prerequisites (#4097 fix round 2).

    ``charge_and_learn`` already ran this check; this third front door (item
    scrolls, rituals, GM award) did not. Mirrors
    ``ChargeAndLearnPrerequisitesTest`` (test_technique_prerequisites_learning.py).
    """

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
            level=10,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.prerequisite = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def test_immediate_mint_blocked_without_prerequisite(self):
        with self.assertRaises(TechniqueRequirementsNotMet):
            learn_technique(
                self.sheet,
                self.technique,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_meter_creation_blocked_without_prerequisite(self):
        """The ap_cost > 0 branch (meter creation) is gated too, not just the mint."""
        with self.assertRaises(TechniqueRequirementsNotMet):
            learn_technique(
                self.sheet,
                self.technique,
                source=AccessChangeSource.TECHNIQUE_GRANT,
                ap_cost=10,
            )

    def test_succeeds_once_prerequisite_known(self):
        CharacterTechniqueFactory(character=self.sheet, technique=self.prerequisite)

        ct = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )

        self.assertEqual(ct.technique, self.technique)

    def test_gm_grant_origin_skips_the_check(self):
        """A GM award is deliberate fiat — it bypasses the prerequisite gate."""
        ct = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.GM_AWARD,
            origin=AcquisitionOrigin.GM_GRANT,
        )

        self.assertEqual(ct.technique, self.technique)

    def test_completing_progress_skips_the_check(self):
        """A meter-completion mint doesn't re-run the gate (already checked at creation)."""
        ct = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            completing_progress=True,
        )

        self.assertEqual(ct.technique, self.technique)

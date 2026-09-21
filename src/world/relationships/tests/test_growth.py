"""Depth and tier writes (#3957): allocation, weekly turn, scene credit, advance."""

from unittest.mock import patch

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory
from world.progression.exceptions import InsufficientXPError
from world.relationships.constants import DepthSource
from world.relationships.exceptions import (
    AllocationTooLargeError,
    CapstoneEntryInvalidError,
    TierNotReachedError,
)
from world.relationships.factories import RelationshipTierFactory
from world.relationships.models import RelationshipDepthTransaction
from world.relationships.services import (
    advance_tier,
    credit_scene_depth,
    get_growth_config,
    get_or_create_side,
    process_weekly_relationship_allocations,
    set_allocation,
)
from world.scenes.factories import InteractionFactory, SceneFactory


def _pool(sheet, current):
    pool = ActionPointPool.get_or_create_for_character(sheet.character)
    pool.current = current
    pool.save(update_fields=["current"])
    return pool


class AllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.side = get_or_create_side(source=cls.a, target=cls.b)

    def test_set_and_replace(self):
        _pool(self.a, 40)
        alloc = set_allocation(side=self.side, ap_amount=9)
        self.assertEqual(alloc.ap_amount, 9)
        alloc = set_allocation(side=self.side, ap_amount=4)
        self.assertEqual(alloc.ap_amount, 4)

    def test_cannot_exceed_pool(self):
        _pool(self.a, 3)
        with self.assertRaises(AllocationTooLargeError):
            set_allocation(side=self.side, ap_amount=9)

    def test_weekly_turn_converts_ap_to_depth(self):
        _pool(self.a, 40)
        set_allocation(side=self.side, ap_amount=9)
        processed = process_weekly_relationship_allocations()
        self.assertEqual(processed, 1)
        self.side.refresh_from_db()
        self.assertEqual(self.side.invested_depth, 9 * get_growth_config().depth_per_ap)
        tx = RelationshipDepthTransaction.objects.get(relationship=self.side)
        self.assertEqual(tx.source, DepthSource.ALLOCATION)
        self.assertEqual(tx.amount, 45)
        pool = ActionPointPool.objects.get(character=self.a)
        self.assertEqual(pool.current, 31)

    def test_weekly_turn_skips_what_the_pool_cannot_afford(self):
        _pool(self.a, 40)
        set_allocation(side=self.side, ap_amount=9)
        _pool(self.a, 2)
        process_weekly_relationship_allocations()
        self.side.refresh_from_db()
        self.assertEqual(self.side.invested_depth, 0)


class SceneCreditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.c = CharacterSheetFactory()
        cls.scene = SceneFactory()
        for sheet in (cls.a, cls.b):
            persona = sheet.personas.first() or sheet.personas.create(name=sheet.character.db_key)
            InteractionFactory(scene=cls.scene, persona=persona)

    def test_both_posed_credits_both_sides_once_per_week(self):
        credited = credit_scene_depth(self.scene)
        self.assertEqual(credited, 2)
        ab = get_or_create_side(source=self.a, target=self.b)
        ba = get_or_create_side(source=self.b, target=self.a)
        gain = get_growth_config().scene_base_gain
        self.assertEqual(ab.scene_depth, gain)
        self.assertEqual(ba.scene_depth, gain)
        self.assertEqual(credit_scene_depth(self.scene), 0)
        self.assertEqual(ab.pair_depth(), 2 * gain)

    def test_non_poser_gets_nothing(self):
        credit_scene_depth(self.scene)
        self.assertFalse(self.c.relationships_as_source.exists())


class AdvanceTierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.side = get_or_create_side(source=cls.a, target=cls.b)
        cls.side.invested_depth = 120
        cls.side.save(update_fields=["invested_depth"])
        RelationshipTierFactory(tier_number=1, depth_threshold=25)
        RelationshipTierFactory(tier_number=2, depth_threshold=100)
        RelationshipTierFactory(tier_number=3, depth_threshold=500)
        cls.entry = JournalEntryFactory(author=cls.a, about=cls.b)

    def test_advance_spends_xp_and_sets_tier(self):
        with patch("world.relationships.services.spend_xp_for_character") as spend:
            receipt = advance_tier(side=self.side, journal_entry=self.entry)
        spend.assert_called_once()
        self.assertEqual(spend.call_args.args[1], 10)
        self.side.refresh_from_db()
        self.assertEqual(self.side.tier, 1)
        self.assertEqual(receipt.tier_claimed, 1)
        self.assertEqual(receipt.journal_entry_id, self.entry.pk)

    def test_cost_scales_with_new_tier(self):
        self.side.tier = 1
        self.side.save(update_fields=["tier"])
        entry = JournalEntryFactory(author=self.a, about=self.b)
        with patch("world.relationships.services.spend_xp_for_character") as spend:
            advance_tier(side=self.side, journal_entry=entry)
        self.assertEqual(spend.call_args.args[1], 20)

    def test_depth_gate(self):
        self.side.tier = 2
        self.side.save(update_fields=["tier"])
        entry = JournalEntryFactory(author=self.a, about=self.b)
        with self.assertRaises(TierNotReachedError):
            advance_tier(side=self.side, journal_entry=entry)

    def test_entry_must_be_own_and_about_them(self):
        wrong = JournalEntryFactory(author=self.b, about=self.a)
        with self.assertRaises(CapstoneEntryInvalidError):
            advance_tier(side=self.side, journal_entry=wrong)
        other = JournalEntryFactory(author=self.a, about=CharacterSheetFactory())
        with self.assertRaises(CapstoneEntryInvalidError):
            advance_tier(side=self.side, journal_entry=other)

    def test_insufficient_xp_propagates(self):
        with (
            patch(
                "world.relationships.services.spend_xp_for_character",
                side_effect=InsufficientXPError(required=10, available=0),
            ),
            self.assertRaises(InsufficientXPError),
        ):
            advance_tier(side=self.side, journal_entry=self.entry)
        self.side.refresh_from_db()
        self.assertEqual(self.side.tier, 0)

"""Depth and tier writes (#3957): allocation, weekly turn, scene credit, advance."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory, PraiseFactory
from world.progression.exceptions import InsufficientXPError
from world.relationships.constants import DepthSource
from world.relationships.exceptions import (
    AllocationTooLargeError,
    CapstoneEntryInvalidError,
    TieError,
    TierNotReachedError,
)
from world.relationships.factories import RelationshipTierFactory
from world.relationships.models import CharacterRelationship, RelationshipDepthTransaction
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

    def test_negative_amount_raises_tie_error(self):
        with self.assertRaises(TieError):
            set_allocation(side=self.side, ap_amount=-1)

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

    def test_second_call_same_week_does_not_double_award(self):
        _pool(self.a, 40)
        set_allocation(side=self.side, ap_amount=9)
        processed_first = process_weekly_relationship_allocations()
        processed_second = process_weekly_relationship_allocations()
        self.assertEqual(processed_first, 1)
        self.assertEqual(processed_second, 0)
        self.side.refresh_from_db()
        self.assertEqual(self.side.invested_depth, 9 * get_growth_config().depth_per_ap)
        self.assertEqual(
            RelationshipDepthTransaction.objects.filter(relationship=self.side).count(), 1
        )
        pool = ActionPointPool.objects.get(character=self.a)
        self.assertEqual(pool.current, 31)  # spent once, not twice


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
        # Never targeted by either poser's side either.
        self.assertFalse(CharacterRelationship.objects.filter(target=self.c).exists())

    def test_inactive_side_is_skipped(self):
        ab = get_or_create_side(source=self.a, target=self.b)
        ab.is_active = False
        ab.save(update_fields=["is_active"])

        credited = credit_scene_depth(self.scene)

        self.assertEqual(credited, 1)
        ab.refresh_from_db()
        self.assertEqual(ab.scene_depth, 0)
        ba = get_or_create_side(source=self.b, target=self.a)
        self.assertEqual(ba.scene_depth, get_growth_config().scene_base_gain)


class SceneCreditQueryCountTests(TestCase):
    """Query-count evidence for the batched credit_scene_depth fan-out (#3957 review)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheets = [CharacterSheetFactory() for _ in range(4)]
        cls.scene = SceneFactory()
        for sheet in cls.sheets:
            persona = sheet.personas.first() or sheet.personas.create(name=sheet.character.db_key)
            InteractionFactory(scene=cls.scene, persona=persona)

    def test_four_poser_scene_query_count(self):
        """Query count for a 4-poser scene (#3957 review): 225 before this fix, 166 after.

        The drop comes from three per-side costs collapsed to once-per-call: the
        already-credited check (was one ``.exists()`` per side, now one upfront
        ``values_list``), ``get_current_game_week()`` (was called inside
        ``_award_depth`` on every award), and the post-award ``refresh_from_db()``
        (skipped entirely in this batch path -- ``flush_from_cache`` alone keeps the
        identity map honest). Asserts a ceiling with headroom under the measured 166
        rather than the exact number, so it still catches a real regression without
        being brittle to an unrelated query shifting by one.
        """
        with CaptureQueriesContext(connection) as ctx:
            credited = credit_scene_depth(self.scene)
        # C(4, 2) = 6 posed-together pairs, each opens both directed sides.
        self.assertEqual(credited, 12)
        self.assertLess(len(ctx.captured_queries), 200)


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

    def test_reply_entry_refused(self):
        reply = PraiseFactory(author=self.a, about=self.b, parent=self.entry)
        with self.assertRaises(CapstoneEntryInvalidError):
            advance_tier(side=self.side, journal_entry=reply)

    def test_entry_already_used_as_capstone_is_refused(self):
        with patch("world.relationships.services.spend_xp_for_character"):
            advance_tier(side=self.side, journal_entry=self.entry)
        # side.tier is now 1; pair_depth (120) still clears tier 2's threshold (100),
        # and self.entry is still author/about-valid -- only the reuse check should fire.
        with self.assertRaises(CapstoneEntryInvalidError):
            advance_tier(side=self.side, journal_entry=self.entry)

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

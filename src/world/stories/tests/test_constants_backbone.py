from django.test import SimpleTestCase

from world.stories.constants import (
    CUSTODY_SCOPE_ORDER,
    BeatKind,
    CustodyClearanceStatus,
    CustodyScope,
    ProgressStatus,
    StoryMaturity,
    StoryScope,
    custody_scope_index,
)


class BackboneConstantsTests(SimpleTestCase):
    def test_story_scope_has_unassigned(self):
        self.assertEqual(StoryScope.UNASSIGNED, "unassigned")
        self.assertIn(StoryScope.UNASSIGNED, StoryScope.values)

    def test_story_maturity_members(self):
        self.assertEqual(set(StoryMaturity.values), {"pitch", "outline", "plot"})

    def test_beat_kind_members(self):
        self.assertEqual(
            set(BeatKind.values),
            {"situation", "encounter", "task", "requirement"},
        )

    def test_progress_status_members(self):
        self.assertEqual(
            set(ProgressStatus.values),
            {"active", "waiting_for_gm", "resting", "completed", "foreclosed"},
        )


class CustodyConstantsTests(SimpleTestCase):
    """#2001 — custody scope + clearance vocabulary (defined here for Task 3)."""

    def test_custody_scope_members(self):
        self.assertEqual(set(CustodyScope.values), {"appear", "harm", "remove"})

    def test_custody_scope_order_matches_choices(self):
        self.assertEqual(set(CUSTODY_SCOPE_ORDER), set(CustodyScope.values))

    def test_custody_scope_index_orders_weakest_to_strongest(self):
        self.assertLess(
            custody_scope_index(CustodyScope.APPEAR), custody_scope_index(CustodyScope.HARM)
        )
        self.assertLess(
            custody_scope_index(CustodyScope.HARM), custody_scope_index(CustodyScope.REMOVE)
        )

    def test_custody_clearance_status_members(self):
        self.assertEqual(
            set(CustodyClearanceStatus.values),
            {"pending", "granted", "denied", "escalated"},
        )

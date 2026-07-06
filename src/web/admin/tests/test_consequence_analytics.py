"""Tests for the consequence-pool inspector (#1221 Task 3).

Covers the pure annotation logic in `consequence_analytics.py` — inherited /
overridden / excluded flags and per-tier selection probabilities, derived
without reimplementing `ConsequencePool.cached_consequences`'s merge — plus a
thin integration test for the fragment view that renders it.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from web.admin.tuning.consequence_analytics import inspect_pool, list_pools
from world.checks.factories import ConsequenceFactory
from world.traits.factories import CheckOutcomeFactory


class InspectPoolTests(TestCase):
    """Annotation correctness for `inspect_pool`."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tier_high = CheckOutcomeFactory(name="Tier1", success_level=5)
        cls.tier_low = CheckOutcomeFactory(name="Tier2", success_level=2)

        cls.alpha = ConsequenceFactory(
            outcome_tier=cls.tier_high, label="Alpha", weight=1, character_loss=False
        )
        cls.bravo = ConsequenceFactory(
            outcome_tier=cls.tier_high, label="Bravo", weight=2, character_loss=True
        )
        cls.charlie = ConsequenceFactory(
            outcome_tier=cls.tier_low, label="Charlie", weight=3, theater=True
        )
        cls.delta = ConsequenceFactory(outcome_tier=cls.tier_high, label="Delta", weight=5)

        cls.parent_pool = ConsequencePoolFactory(name="Parent Pool")
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.alpha)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.bravo)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.charlie)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.delta)

        cls.child_pool = ConsequencePoolFactory(name="Child Pool", parent=cls.parent_pool)
        # Override Alpha's weight, exclude Bravo. Charlie/Delta are untouched
        # (pure inherited passthrough).
        ConsequencePoolEntryFactory(pool=cls.child_pool, consequence=cls.alpha, weight_override=10)
        ConsequencePoolEntryFactory(pool=cls.child_pool, consequence=cls.bravo, is_excluded=True)

    def test_child_pool_flags_and_excluded_label(self) -> None:
        # Beware SharedMemoryModel + cached_property staleness: re-fetch a fresh
        # instance rather than reusing an already-`cached_consequences`'d object.
        child = self.child_pool.__class__.objects.get(pk=self.child_pool.pk)
        inspection = inspect_pool(child)

        assert inspection.pool_name == "Child Pool"
        assert inspection.parent_name == "Parent Pool"
        assert inspection.excluded_labels == ["Bravo"]

        by_label = {row.consequence_label: row for row in inspection.rows}
        assert set(by_label) == {"Alpha", "Charlie", "Delta"}

        alpha_row = by_label["Alpha"]
        assert alpha_row.effective_weight == 10
        assert alpha_row.overridden is True
        assert alpha_row.inherited is False
        assert alpha_row.character_loss is False
        assert alpha_row.theater is False

        delta_row = by_label["Delta"]
        assert delta_row.effective_weight == 5
        assert delta_row.overridden is False
        assert delta_row.inherited is True

        charlie_row = by_label["Charlie"]
        assert charlie_row.effective_weight == 3
        assert charlie_row.overridden is False
        assert charlie_row.inherited is True
        assert charlie_row.theater is True

    def test_selection_probability_sums_to_one_per_tier(self) -> None:
        child = self.child_pool.__class__.objects.get(pk=self.child_pool.pk)
        inspection = inspect_pool(child)

        by_label = {row.consequence_label: row for row in inspection.rows}
        # Tier1 (high): Alpha (10) + Delta (5) = 15 total.
        self.assertAlmostEqual(by_label["Alpha"].selection_probability_within_tier, 10 / 15)
        self.assertAlmostEqual(by_label["Delta"].selection_probability_within_tier, 5 / 15)
        tier1_total = (
            by_label["Alpha"].selection_probability_within_tier
            + by_label["Delta"].selection_probability_within_tier
        )
        self.assertAlmostEqual(tier1_total, 1.0, places=9)

        # Tier2 (low): Charlie alone -> probability 1.0.
        self.assertAlmostEqual(by_label["Charlie"].selection_probability_within_tier, 1.0)

    def test_rows_ordered_by_success_level_desc_then_label(self) -> None:
        child = self.child_pool.__class__.objects.get(pk=self.child_pool.pk)
        inspection = inspect_pool(child)

        labels_in_order = [row.consequence_label for row in inspection.rows]
        assert labels_in_order == ["Alpha", "Delta", "Charlie"]

    def test_root_pool_has_no_inherited_or_overridden_rows(self) -> None:
        parent = self.parent_pool.__class__.objects.get(pk=self.parent_pool.pk)
        inspection = inspect_pool(parent)

        assert inspection.parent_name is None
        assert inspection.excluded_labels == []
        for row in inspection.rows:
            assert row.inherited is False
            assert row.overridden is False


class ListPoolsTests(TestCase):
    """`list_pools` returns (pk, name) pairs ordered by name."""

    def test_list_pools_ordered_by_name(self) -> None:
        ConsequencePoolFactory(name="Zeta Pool")
        ConsequencePoolFactory(name="Alpha Pool")

        pools = list_pools()
        names = [name for _pk, name in pools]
        assert names == sorted(names)
        assert "Alpha Pool" in names
        assert "Zeta Pool" in names


class TuningConsequencesFragmentViewTests(TestCase):
    """Integration test for the real `admin_tuning_consequences` fragment view."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootadmin3", "root3@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("staffer3", "s3@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

        tier = CheckOutcomeFactory(name="ViewTier", success_level=1)
        cls.consequence = ConsequenceFactory(outcome_tier=tier, label="View Alpha", weight=1)
        cls.untouched_consequence = ConsequenceFactory(
            outcome_tier=tier, label="View Gamma", weight=1
        )
        cls.pool = ConsequencePoolFactory(name="View Pool")
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.consequence)
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.untouched_consequence)

        cls.child_consequence = ConsequenceFactory(
            outcome_tier=tier, label="View Beta", weight=1, character_loss=True
        )
        cls.child_pool = ConsequencePoolFactory(name="View Child Pool", parent=cls.pool)
        ConsequencePoolEntryFactory(
            pool=cls.child_pool, consequence=cls.consequence, weight_override=9
        )
        ConsequencePoolEntryFactory(pool=cls.child_pool, consequence=cls.child_consequence)
        # cls.untouched_consequence has no own entry in child_pool -> pure
        # inherited passthrough, so the "Inherited" badge has something to render.

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_consequences"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_sees_default_pool_rendered(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_consequences"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert 'name="pool"' in body
        assert "View Pool" in body

    def test_pool_query_param_selects_child_pool_and_shows_badges(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_consequences"), {"pool": self.child_pool.pk})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert "View Child Pool" in body
        assert "View Alpha" in body
        assert "View Beta" in body
        # Overridden/inherited/character_loss badges rendered as text.
        assert "Overridden" in body
        assert "Inherited" in body
        assert "Character Loss" in body

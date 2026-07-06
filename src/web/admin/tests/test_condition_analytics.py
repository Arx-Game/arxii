"""Tests for the condition-danger analytics panel (#1221 Task 4).

Covers the pure scaling logic in `condition_analytics.py` — the effective
severity / DoT-per-round formulas the dataclass docstring documents — plus a
thin integration test for the fragment view that renders it.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.condition_analytics import compute_condition_danger
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)


class ComputeConditionDangerTests(TestCase):
    """Scaling-formula correctness for `compute_condition_danger`."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Staged template: stage 1 (x1.0), stage 2 (x2.0, worst), with a
        # scaling DoT (base 3) attached to stage 2.
        cls.staged = ConditionTemplateFactory(
            name="Venomous Bite", has_progression=True, passive_decay_per_day=0
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.staged, stage_order=1, severity_multiplier=Decimal("1.00")
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.staged, stage_order=2, severity_multiplier=Decimal("2.00")
        )
        cls.dot = ConditionDamageOverTimeFactory(
            condition=None,
            stage=cls.stage2,
            base_damage=3,
            scales_with_severity=True,
        )

        # Unstaged template with nonzero decay, no DoT.
        cls.decaying = ConditionTemplateFactory(
            name="Fading Bruise", has_progression=False, passive_decay_per_day=2
        )

    def test_effective_severity_uses_worst_stage_multiplier(self) -> None:
        rows = compute_condition_danger(at_severity=4)
        row = next(r for r in rows if r.template_name == "Venomous Bite")

        assert row.at_severity == 4
        assert row.max_stage_multiplier == 2.0
        assert row.effective_severity == 8.0  # 4 * 2.0

    def test_dot_scaling_uses_at_severity_directly_not_stage_multiplier(self) -> None:
        """Scaling severity for DoT is `at_severity` alone (see dataclass docstring):
        the stage multiplier (2.0 here) applies only to effective_severity, so a
        base-3 DoT at severity 4 is 3 * 4 = 12, NOT 3 * 4 * 2.0 = 24."""
        rows = compute_condition_danger(at_severity=4)
        row = next(r for r in rows if r.template_name == "Venomous Bite")

        assert row.dot_per_round == 12.0

    def test_danger_score_combines_effective_severity_and_weighted_dot(self) -> None:
        rows = compute_condition_danger(at_severity=4)
        row = next(r for r in rows if r.template_name == "Venomous Bite")

        # effective_severity (8.0) + dot_per_round (12.0) * DOT_WEIGHT (2.0) = 32.0
        assert row.danger_score == 32.0

    def test_zero_decay_gives_none_days_to_decay(self) -> None:
        rows = compute_condition_danger(at_severity=5)
        row = next(r for r in rows if r.template_name == "Venomous Bite")

        assert row.days_to_decay is None

    def test_nonzero_decay_computes_days_to_decay(self) -> None:
        rows = compute_condition_danger(at_severity=6)
        row = next(r for r in rows if r.template_name == "Fading Bruise")

        assert row.days_to_decay == 3.0  # 6 / 2

    def test_unstaged_template_defaults_multiplier_to_one(self) -> None:
        rows = compute_condition_danger(at_severity=5)
        row = next(r for r in rows if r.template_name == "Fading Bruise")

        assert row.max_stage_multiplier == 1.0
        assert row.effective_severity == 5.0
        assert row.dot_per_round == 0.0

    def test_rows_ordered_by_danger_score_desc(self) -> None:
        rows = compute_condition_danger(at_severity=4)
        scores = [row.danger_score for row in rows]

        assert scores == sorted(scores, reverse=True)
        # Venomous Bite (danger 32.0) must rank above Fading Bruise (danger 4.0).
        names_in_order = [row.template_name for row in rows]
        assert names_in_order.index("Venomous Bite") < names_in_order.index("Fading Bruise")


class TuningConditionsFragmentViewTests(TestCase):
    """Integration test for the real `admin_tuning_conditions` fragment view."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootadmin4", "root4@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("staffer4", "s4@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

        cls.no_decay = ConditionTemplateFactory(
            name="Cursed Silence", passive_decay_per_day=0, has_progression=False
        )

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_conditions"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_sees_default_severity_rendered(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_conditions"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert 'name="severity"' in body
        assert "Cursed Silence" in body

    def test_no_decay_row_shows_no_passive_exit_badge(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_conditions"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert "No passive exit" in body

    def test_severity_query_param_changes_computed_values(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_conditions"), {"severity": 9})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert "9" in body

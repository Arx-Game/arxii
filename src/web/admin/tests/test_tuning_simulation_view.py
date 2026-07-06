"""Tests for the simulation panel view (#1221 Task 6).

The real ``run_party_vs_boss_simulation`` runs dozens of full combat rounds and
can take minutes, so every test here patches it at its origin
(``world.combat.simulation.run_party_vs_boss_simulation``) with a canned,
distinctive ``SimulationReport`` and asserts the mock was actually invoked
(or not) rather than exercising the real simulator.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.combat.constants import OpponentTier, RiskLevel
from world.combat.simulation import SimulationParams, SimulationReport

_PATCH_TARGET = "world.combat.simulation.run_party_vs_boss_simulation"


def _canned_report(**overrides: Any) -> SimulationReport:
    """A distinctive, easy-to-assert-on SimulationReport for mocking the sim."""
    params = overrides.pop("params", None) or SimulationParams(
        party_size=4,
        avg_level=5,
        tier=OpponentTier.BOSS,
        risk_level=RiskLevel.MODERATE,
        iterations=7,
        round_cap=20,
    )
    defaults: dict[str, Any] = {
        "params": params,
        "iterations_run": 7,
        "victories": 5,
        "defeats": 1,
        "stalemates": 1,
        "win_rate": 5 / 7,
        "round_counts": [3, 4, 5, 6, 7, 8, 9],
        "mean_rounds": 6.0,
        "opponent_max_health": 321,
    }
    defaults.update(overrides)
    return SimulationReport(**defaults)


class TestSimulationFragmentView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootadmin2", "root2@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("staffer2", "s2@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _post_data(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "party_size": 4,
            "avg_level": 5,
            "tier": OpponentTier.BOSS,
            "risk_level": RiskLevel.MODERATE,
            "iterations": 7,
        }
        data.update(overrides)
        return data

    def test_anonymous_post_redirected_to_login(self) -> None:
        resp = self.client.post(reverse("admin_tuning_simulation"), self._post_data())
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_post_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_tuning_simulation"), self._post_data())
        self.assertEqual(resp.status_code, 403)

    @patch(_PATCH_TARGET)
    def test_post_invalid_tier_rerenders_form_errors_without_running(self, mock_run: Any) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_simulation"), self._post_data(tier="not-a-real-tier")
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("errorlist", body)
        mock_run.assert_not_called()

    @patch(_PATCH_TARGET)
    def test_post_valid_superuser_runs_simulation_and_renders_result(self, mock_run: Any) -> None:
        mock_run.return_value = _canned_report()
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_simulation"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        mock_run.assert_called_once()

        called_params = mock_run.call_args.args[0]
        self.assertIsInstance(called_params, SimulationParams)
        self.assertEqual(called_params.party_size, 4)
        self.assertEqual(called_params.avg_level, 5)
        self.assertEqual(called_params.tier, OpponentTier.BOSS)
        self.assertEqual(called_params.risk_level, RiskLevel.MODERATE)
        self.assertEqual(called_params.iterations, 7)

        body = resp.content.decode()
        self.assertIn("71", body)  # win_rate 5/7 -> ~71%
        self.assertIn("321", body)  # opponent_max_health surfaced

    @patch(_PATCH_TARGET)
    def test_get_after_post_returns_cached_result_without_rerunning(self, mock_run: Any) -> None:
        mock_run.return_value = _canned_report()
        self.client.force_login(self.super)

        post_resp = self.client.post(reverse("admin_tuning_simulation"), self._post_data())
        self.assertEqual(post_resp.status_code, 200)

        get_resp = self.client.get(reverse("admin_tuning_simulation"))
        self.assertEqual(get_resp.status_code, 200)

        mock_run.assert_called_once()
        body = get_resp.content.decode()
        self.assertIn("321", body)
        self.assertIn("71", body)

    def test_get_with_no_cached_result_renders_form_only(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_simulation"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-simulation-form"', body)

    @patch(_PATCH_TARGET)
    def test_post_out_of_range_iterations_is_clamped_not_rejected(self, mock_run: Any) -> None:
        mock_run.return_value = _canned_report()
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_simulation"), self._post_data(iterations=99999, party_size=0)
        )

        self.assertEqual(resp.status_code, 200)
        mock_run.assert_called_once()
        called_params = mock_run.call_args.args[0]
        self.assertEqual(called_params.iterations, 500)
        self.assertEqual(called_params.party_size, 1)

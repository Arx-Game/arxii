"""Tests for the Techniques combat-power panel view (#3279 Task 3).

Evaluating the whole technique catalog is real DB work (see
`technique_analytics.py`'s module docstring), so every test here patches
`web.admin.tuning.technique_analytics.build_technique_panel` at its origin with a
canned, distinctive `TechniquePanelData` and asserts the mock was actually invoked
(or not) rather than exercising the real evaluator - mirrors
`test_tuning_simulation_view.py`'s patching discipline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.technique_analytics import (
    TechniqueAnalyticsParams,
    TechniquePanelData,
    TechniqueRow,
)
from world.magic.types.technique_power import (
    PayloadValuation,
    ReferenceFrame,
    TechniquePowerReport,
    ValuationProvenance,
)

_PATCH_TARGET = "web.admin.tuning.technique_analytics.build_technique_panel"


def _canned_report(**overrides: Any) -> TechniquePowerReport:
    defaults: dict[str, Any] = {
        "technique_id": 1,
        "name": "Distinctive Firebolt",
        "gift_name": "Pyromancy",
        "level": 4,
        "tier": 1,
        "category": "Attack",
        "baseline_power": 4,
        "amplified_power": 6,
        "baseline_de": 11.0,
        "amplified_de": 16.5,
        "valuations": (
            PayloadValuation(
                kind="damage",
                label="fire",
                value=11.0,
                provenance=ValuationProvenance.FORMULA,
                detail="E[budget x mult] over SL bands = 11.00",
            ),
        ),
        "effective_anima": 5,
        "de_per_anima": 2.2,
        "flags": (),
    }
    defaults.update(overrides)
    return TechniquePowerReport(**defaults)


def _canned_panel(**overrides: Any) -> TechniquePanelData:
    params = overrides.pop("params", None) or TechniqueAnalyticsParams()
    report = overrides.pop("report", None) or _canned_report()
    rows = overrides.pop("rows", [TechniqueRow(report=report, amplification_ratio=1.5)])
    defaults: dict[str, Any] = {
        "rows": rows,
        "zero_bucket": [],
        "provenance_summary": {"FORMULA": 1},
        "params": params,
        "reference": ReferenceFrame(
            outgoing_dpr=9.5, incoming_dpr=9.5, source_label="median-attack estimate"
        ),
    }
    defaults.update(overrides)
    return TechniquePanelData(**defaults)


class TestTechniqueFragmentView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "roottechadmin", "roottech@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("techstaffer", "ts@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _post_data(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "level": 10,
            "thread_level": 3,
            "roller_points": 25,
            "target_difficulty": 25,
            "roll_modifier": 0,
            "sort": "baseline_de",
        }
        data.update(overrides)
        return data

    def test_anonymous_get_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_get_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 403)

    def test_get_with_no_cache_renders_empty_state(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-techniques-form"', body)
        self.assertIn("No evaluation has been run yet", body)

    @patch(_PATCH_TARGET)
    def test_post_valid_superuser_builds_panel_and_renders_rows(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()

        called_params = mock_build.call_args.args[0]
        self.assertIsInstance(called_params, TechniqueAnalyticsParams)
        self.assertEqual(called_params.level, 10)
        self.assertEqual(called_params.thread_level, 3)
        self.assertEqual(called_params.roller_points, 25)
        self.assertEqual(called_params.target_difficulty, 25)
        self.assertEqual(called_params.roll_modifier, 0)
        self.assertEqual(called_params.sort, "baseline_de")

        body = resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)
        self.assertIn("Pyromancy", body)

    @patch(_PATCH_TARGET)
    def test_get_after_post_returns_cached_result_without_rebuilding(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)

        post_resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        self.assertEqual(post_resp.status_code, 200)

        get_resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(get_resp.status_code, 200)

        mock_build.assert_called_once()
        body = get_resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)

    @patch(_PATCH_TARGET)
    def test_get_with_unknown_sort_falls_back_to_baseline_de(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel(params=TechniqueAnalyticsParams(sort="baseline_de"))
        self.client.force_login(self.super)

        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        resp = self.client.get(reverse("admin_tuning_techniques"), {"sort": "not-a-real-key"})

        self.assertEqual(resp.status_code, 200)
        # An unrecognized sort resolves to the same "baseline_de" the cached
        # panel was already built with, so no second build is triggered.
        mock_build.assert_called_once()
        body = resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)

    @patch(_PATCH_TARGET)
    def test_get_with_different_known_sort_rebuilds_panel(self, mock_build: Any) -> None:
        mock_build.side_effect = [
            _canned_panel(params=TechniqueAnalyticsParams(sort="baseline_de")),
            _canned_panel(params=TechniqueAnalyticsParams(sort="name")),
        ]
        self.client.force_login(self.super)

        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        resp = self.client.get(reverse("admin_tuning_techniques"), {"sort": "name"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_build.call_count, 2)
        second_call_params = mock_build.call_args.args[0]
        self.assertEqual(second_call_params.sort, "name")

    @patch(_PATCH_TARGET)
    def test_post_out_of_range_level_is_clamped_not_rejected(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_techniques"),
            self._post_data(level=999, thread_level=-5),
        )

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()
        called_params = mock_build.call_args.args[0]
        self.assertEqual(called_params.level, 30)
        self.assertEqual(called_params.thread_level, 0)

    @patch(_PATCH_TARGET)
    def test_post_invalid_sort_choice_rerenders_form_errors_without_building(
        self, mock_build: Any
    ) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_techniques"), self._post_data(sort="not-a-real-key")
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("errorlist", body)
        mock_build.assert_not_called()

    @patch(_PATCH_TARGET)
    def test_zero_bucket_and_provenance_summary_render(self, mock_build: Any) -> None:
        inert_report = _canned_report(
            technique_id=2,
            name="Inert Placeholder",
            baseline_de=0.0,
            amplified_de=0.0,
            valuations=(
                PayloadValuation(
                    kind="capability",
                    label="Latent Spark",
                    value=0.0,
                    provenance=ValuationProvenance.INERT_PAYLOAD,
                    detail="no capability-grant cast seam exists",
                ),
            ),
            de_per_anima=0.0,
        )
        mock_build.return_value = _canned_panel(
            zero_bucket=[inert_report],
            provenance_summary={"FORMULA": 1, "INERT_PAYLOAD": 1},
        )
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Inert Placeholder", body)
        self.assertIn("INERT_PAYLOAD", body)

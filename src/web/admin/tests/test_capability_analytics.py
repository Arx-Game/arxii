"""Tests for the Capabilities combat-power panel view (#3390).

Evaluating the whole capability catalog is real DB work, so every test here patches
`web.admin.tuning.capability_power_analytics.build_capability_power_panel` at its
origin with a canned, distinctive `CapabilityPowerPanelData` and asserts the mock was
actually invoked (or not) rather than exercising the real evaluator - mirrors
`test_tuning_technique_panel.py`'s patching discipline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.capability_power_analytics import (
    CapabilityPowerAnalyticsParams,
    CapabilityPowerPanelData,
)
from world.magic.types.capability_power import CapabilityPowerReport
from world.magic.types.technique_power import PayloadValuation, ReferenceFrame, ValuationProvenance

_PATCH_TARGET = "web.admin.tuning.capability_power_analytics.build_capability_power_panel"


def _canned_report(**overrides: Any) -> CapabilityPowerReport:
    defaults: dict[str, Any] = {
        "capability_id": 1,
        "name": "Distinctive Grip Strength",
        "total_de": 3.5,
        "valuations": (
            PayloadValuation(
                kind="check_bridge",
                label="Melee Defense",
                value=3.5,
                provenance=ValuationProvenance.ESTIMATE,
                detail="weight=1.00 -> roll_modifier shift 1 -> DE delta 3.50",
            ),
        ),
        "flags": (),
    }
    defaults.update(overrides)
    return CapabilityPowerReport(**defaults)


def _canned_panel(**overrides: Any) -> CapabilityPowerPanelData:
    params = overrides.pop("params", None) or CapabilityPowerAnalyticsParams()
    report = overrides.pop("report", None) or _canned_report()
    rows = overrides.pop("rows", [report])
    defaults: dict[str, Any] = {
        "rows": rows,
        "zero_bucket": [],
        "provenance_summary": {"ESTIMATE": 1},
        "params": params,
        "reference": ReferenceFrame(
            outgoing_dpr=9.5, incoming_dpr=9.5, source_label="median-attack estimate"
        ),
    }
    defaults.update(overrides)
    return CapabilityPowerPanelData(**defaults)


class TestCapabilityFragmentView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootcapadmin", "rootcap@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("capstaffer", "cs@example.com", "pw-123456")
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
        }
        data.update(overrides)
        return data

    def test_anonymous_get_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_tuning_capabilities"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_get_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_capabilities"))
        self.assertEqual(resp.status_code, 403)

    def test_get_with_no_cache_renders_empty_state(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_capabilities"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-capabilities-form"', body)
        self.assertIn("No evaluation has been run yet", body)

    @patch(_PATCH_TARGET)
    def test_post_valid_superuser_builds_panel_and_renders_rows(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_capabilities"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()

        called_params = mock_build.call_args.args[0]
        self.assertIsInstance(called_params, CapabilityPowerAnalyticsParams)
        self.assertEqual(called_params.level, 10)
        self.assertEqual(called_params.thread_level, 3)

        body = resp.content.decode()
        self.assertIn("Distinctive Grip Strength", body)

    @patch(_PATCH_TARGET)
    def test_get_after_post_returns_cached_result_without_rebuilding(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)

        post_resp = self.client.post(reverse("admin_tuning_capabilities"), self._post_data())
        self.assertEqual(post_resp.status_code, 200)

        get_resp = self.client.get(reverse("admin_tuning_capabilities"))
        self.assertEqual(get_resp.status_code, 200)

        mock_build.assert_called_once()
        body = get_resp.content.decode()
        self.assertIn("Distinctive Grip Strength", body)

    @patch(_PATCH_TARGET)
    def test_post_out_of_range_level_is_clamped_not_rejected(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_capabilities"),
            self._post_data(level=999, thread_level=-5),
        )

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()
        called_params = mock_build.call_args.args[0]
        self.assertEqual(called_params.level, 30)
        self.assertEqual(called_params.thread_level, 0)

    @patch(_PATCH_TARGET)
    def test_zero_bucket_and_provenance_summary_render(self, mock_build: Any) -> None:
        unpriced_report = _canned_report(
            capability_id=2,
            name="Unwired Capability",
            total_de=0.0,
            valuations=(
                PayloadValuation(
                    kind="check_bridge",
                    label="no check bridge",
                    value=0.0,
                    provenance=ValuationProvenance.UNPRICEABLE,
                    detail="no authored CheckTypeCapabilityModifier rows",
                ),
            ),
            flags=("no_authored_bridge",),
        )
        mock_build.return_value = _canned_panel(
            zero_bucket=[unpriced_report],
            provenance_summary={"ESTIMATE": 1, "UNPRICEABLE": 1},
        )
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_capabilities"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Unwired Capability", body)
        self.assertIn("no_authored_bridge", body)

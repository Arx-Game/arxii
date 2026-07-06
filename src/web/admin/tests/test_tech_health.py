"""Tests for the Technical Health panel (#1221 Task 8).

Covers `collect_tech_health()`'s shape and status-classification correctness,
plus the superuser gate on its fragment view. `SystemErrorReport` rows created
via the factory double as idmapper-cache warmers (it's a SharedMemoryModel)
and as the data `open_system_errors` counts.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.tech_health import TechHealthSnapshot, collect_tech_health
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.factories import SystemErrorReportFactory


class CollectTechHealthShapeTests(TestCase):
    """`collect_tech_health()` returns a sane, well-typed snapshot."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Warm the idmapper cache for SystemErrorReport so `idmapper_top` is
        # non-empty, and give `open_system_errors` something to count.
        SystemErrorReportFactory(status=SubmissionStatus.OPEN)
        SystemErrorReportFactory(status=SubmissionStatus.OPEN)

    def test_returns_dataclass_instance(self) -> None:
        snapshot = collect_tech_health()
        self.assertIsInstance(snapshot, TechHealthSnapshot)

    def test_idmapper_top_is_bounded_and_shaped(self) -> None:
        snapshot = collect_tech_health()
        self.assertLessEqual(len(snapshot.idmapper_top), 15)
        for row in snapshot.idmapper_top:
            self.assertIsInstance(row, tuple)
            self.assertEqual(len(row), 3)
            label, count, approx_bytes = row
            self.assertIsInstance(label, str)
            self.assertIsInstance(count, int)
            self.assertIsInstance(approx_bytes, int)
            self.assertGreaterEqual(count, 0)
            self.assertGreaterEqual(approx_bytes, 0)

    def test_idmapper_total_bytes_non_negative(self) -> None:
        snapshot = collect_tech_health()
        self.assertGreaterEqual(snapshot.idmapper_total_bytes, 0)

    def test_process_rss_and_cpu_are_sane(self) -> None:
        snapshot = collect_tech_health()
        self.assertIsInstance(snapshot.process_rss_bytes, int)
        self.assertGreater(snapshot.process_rss_bytes, 0)
        self.assertIsInstance(snapshot.process_cpu_percent, float)
        self.assertGreaterEqual(snapshot.process_cpu_percent, 0.0)

    def test_system_errors_url_matches_staff_page(self) -> None:
        snapshot = collect_tech_health()
        self.assertEqual(snapshot.system_errors_url, "/staff/system-errors")

    def test_git_sha_none_when_env_absent(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("GIT_SHA", None)
            os.environ.pop("SOURCE_COMMIT", None)
            snapshot = collect_tech_health()
        self.assertIsNone(snapshot.git_sha)

    def test_sentry_dsn_configured_false_when_env_absent(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("SENTRY_DSN", None)
            snapshot = collect_tech_health()
        self.assertFalse(snapshot.sentry_dsn_configured)


class OpenSystemErrorsCountTests(TestCase):
    """`open_system_errors` counts only non-terminal (OPEN) rows."""

    def test_counts_only_open_status(self) -> None:
        SystemErrorReportFactory(status=SubmissionStatus.OPEN)
        SystemErrorReportFactory(status=SubmissionStatus.OPEN)
        SystemErrorReportFactory(status=SubmissionStatus.REVIEWED)
        SystemErrorReportFactory(status=SubmissionStatus.DISMISSED)

        snapshot = collect_tech_health()
        self.assertEqual(snapshot.open_system_errors, 2)


class GitShaEnvTests(TestCase):
    """`git_sha` reads GIT_SHA first, falling back to SOURCE_COMMIT."""

    def test_git_sha_from_env(self) -> None:
        with patch.dict("os.environ", {"GIT_SHA": "abc1234"}):
            snapshot = collect_tech_health()
        self.assertEqual(snapshot.git_sha, "abc1234")

    def test_git_sha_falls_back_to_source_commit(self) -> None:
        with patch.dict("os.environ", {"SOURCE_COMMIT": "def5678"}, clear=False):
            import os

            os.environ.pop("GIT_SHA", None)
            snapshot = collect_tech_health()
        self.assertEqual(snapshot.git_sha, "def5678")

    def test_git_sha_prefers_git_sha_over_source_commit(self) -> None:
        with patch.dict(
            "os.environ", {"GIT_SHA": "abc1234", "SOURCE_COMMIT": "def5678"}, clear=False
        ):
            snapshot = collect_tech_health()
        self.assertEqual(snapshot.git_sha, "abc1234")


class SentryDsnConfiguredTests(TestCase):
    def test_true_when_env_set(self) -> None:
        with patch.dict("os.environ", {"SENTRY_DSN": "https://example/1"}, clear=False):
            snapshot = collect_tech_health()
        self.assertTrue(snapshot.sentry_dsn_configured)


class IdmapperTopSortingTests(TestCase):
    """`idmapper_top` is the top-15 entries by approx_bytes, descending."""

    def test_sorted_descending_and_capped_at_fifteen(self) -> None:
        fake_snapshot = {f"fake.Model{i}": (i, i * 100) for i in range(20)}
        with patch(
            "web.admin.tuning.tech_health.idmapper_gauge.snapshot",
            return_value=fake_snapshot,
        ):
            snapshot = collect_tech_health()

        self.assertEqual(len(snapshot.idmapper_top), 15)
        byte_values = [row[2] for row in snapshot.idmapper_top]
        self.assertEqual(byte_values, sorted(byte_values, reverse=True))
        # Top 15 by bytes are models 19..5 (byte value == i * 100).
        top_labels = {row[0] for row in snapshot.idmapper_top}
        self.assertIn("fake.Model19", top_labels)
        self.assertNotIn("fake.Model0", top_labels)

    def test_idmapper_total_bytes_sums_full_snapshot_not_just_top(self) -> None:
        fake_snapshot = {f"fake.Model{i}": (i, i * 100) for i in range(20)}
        with patch(
            "web.admin.tuning.tech_health.idmapper_gauge.snapshot",
            return_value=fake_snapshot,
        ):
            snapshot = collect_tech_health()

        expected_total = sum(approx_bytes for _count, approx_bytes in fake_snapshot.values())
        self.assertEqual(snapshot.idmapper_total_bytes, expected_total)


class TechHealthFragmentViewTests(TestCase):
    """Fragment view is superuser-gated, mirroring the other Ops panels."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "techroot", "techroot@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("techstaff", "ts@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_superuser_gets_fragment(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_tech"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("/staff/system-errors", resp.content.decode())

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_ops_tech"))
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_ops_tech"))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_includes_tech_panel_section(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="panel-tech"', resp.content.decode())

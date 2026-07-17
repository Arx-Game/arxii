"""Tests for the superuser-only export-to-content-repo surface (#2448).

Mirrors ``test_content_load_views.py``'s structure: an "unconfigured" class
proving the not-configured state renders cleanly and non-superusers are
rejected, plus a "configured" class exercising a real run against a tmp
content root.
"""

import os
from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.models import EffectType


class TestContentExportUnconfigured(TestCase):
    """CONTENT_REPO_PATH unset: the preview reflects it and the run view bails out cleanly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_preview_reports_not_configured(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.get(reverse("admin_content_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["content_repo_configured"])

    def test_run_without_path_redirects_with_error(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.post(reverse("admin_content_export_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(any("CONTENT_REPO_PATH" in str(m) for m in messages))

    def test_run_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_content_export_run"))
        self.assertEqual(resp.status_code, 403)

    def test_preview_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_content_export"))
        self.assertEqual(resp.status_code, 403)


class TestContentExportConfigured(TestCase):
    """A tmp dir standing in for a content-repo checkout, with one exportable row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        EffectType.objects.get_or_create(
            name="Test Export Effect",
            defaults={"description": "Test effect for export."},
        )

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)

    def test_preview_reports_configured(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(reverse("admin_content_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["content_repo_configured"])
        self.assertGreaterEqual(resp.context["total_records"], 1)

    def test_run_exports_and_flashes_success(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(reverse("admin_content_export_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))

        exported_path = self.root / "fixtures" / "magic" / "effecttype.json"
        self.assertTrue(exported_path.exists())

        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Content export" in m for m in messages))
        self.assertTrue(any("Grid export" in m for m in messages))

"""Tests for the superuser-only external content-repo load surface (#1220)."""

import os
from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.buildings.models import DecorationKind
from world.traits.models import Trait

GOOD_SKILL = """---
name: Performance
category: social
---
PLACEHOLDER Captivating an audience through music, oration, or storytelling.
"""

GOOD_DECORATION_KIND = """---
name: Great Hearth
---
A roaring stone hearth that drives out the worst of the cold.
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestContentLoadUnconfigured(TestCase):
    """CONTENT_REPO_PATH unset: hub reflects it and the run view bails out cleanly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_game_setup_reports_not_configured(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.get(reverse("admin_game_setup"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["content_repo_configured"])

    def test_run_without_path_redirects_with_error(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.post(reverse("admin_content_load_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(any("CONTENT_REPO_PATH" in str(m) for m in messages))

    def test_run_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_content_load_run"))
        self.assertEqual(resp.status_code, 403)

    def test_confirm_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_content_load"))
        self.assertEqual(resp.status_code, 403)

    def test_confirm_page_mentions_upsert_semantics(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_content_load"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("natural key", body.lower())
        self.assertIn("safe to re-run", body.lower())


class TestContentLoadConfigured(TestCase):
    """A tmp dir standing in for a content-repo checkout, with one valid file."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)
        _write(self.root, "skills/performance.md", GOOD_SKILL)
        _write(self.root, "decoration_kinds/hearth.md", GOOD_DECORATION_KIND)

    def test_game_setup_reports_configured(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(reverse("admin_game_setup"))
        self.assertTrue(resp.context["content_repo_configured"])

    def test_run_loads_content_and_flashes_success(self) -> None:
        """One run across two domains (#2266) — the flashed count covers both."""
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(reverse("admin_content_load_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))
        trait = Trait.objects.get(name="Performance")
        self.assertIn("PLACEHOLDER", trait.description)
        self.assertTrue(DecorationKind.objects.filter(name="Great Hearth").exists())
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(any("2 created" in str(m) for m in messages))
        self.assertTrue(any("1 placeholder" in str(m) for m in messages))

    def test_run_with_missing_dir_redirects_with_error(self) -> None:
        self.client.force_login(self.super)
        bogus = str(self.root / "does-not-exist")
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": bogus}):
            resp = self.client.post(reverse("admin_content_load_run"))
        self.assertEqual(resp.status_code, 302)
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(
            any("does not exist" in str(m) or "invalid" in str(m).lower() for m in messages)
        )

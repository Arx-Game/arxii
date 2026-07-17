"""Tests for the superuser-only push-to-content-repo surface (#2448).

Mirrors ``test_content_load_views.py``'s structure for the unconfigured/
superuser-gate cases. The git layer isn't mocked/stubbed — like
``test_content_push.py`` (the library-level tests this view wraps), it runs
real git subprocess calls against a throwaway local repo with its ``origin``
remote pointed at ``/dev/null``, so a push always fails fast locally without
ever touching a network. The view is only asserted against the library
result (``committed``/``pushed``/flash messages), never a real remote push.
"""

import os
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


def _init_git_repo(path: Path) -> None:
    """Initialize a local git repo at ``path`` with a dummy origin and one commit."""
    subprocess.run(["git", "init", "-b", "main", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "/dev/null"],
        capture_output=True,
        check=True,
    )
    readme = path / "README.md"
    readme.write_text("# test repo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True,
        check=True,
    )


def _write_fixture(root: Path) -> None:
    fixtures_dir = root / "fixtures" / "magic"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "effecttype.json").write_text(
        '[{"model": "magic.effecttype", "fields": {"name": "Test"}}]\n', encoding="utf-8"
    )


class TestContentPushUnconfigured(TestCase):
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
            resp = self.client.get(reverse("admin_content_push"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["content_repo_configured"])

    def test_run_without_path_redirects_with_error(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.post(reverse("admin_content_push_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(any("CONTENT_REPO_PATH" in str(m) for m in messages))

    def test_run_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_content_push_run"))
        self.assertEqual(resp.status_code, 403)

    def test_preview_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_content_push"))
        self.assertEqual(resp.status_code, 403)


class TestContentPushConfigured(TestCase):
    """A tmp dir standing in for a content-repo checkout, backed by a real local git repo."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)
        _init_git_repo(self.root)

    def test_preview_reports_configured_no_changes(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(reverse("admin_content_push"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["content_repo_configured"])
        self.assertFalse(resp.context["has_changes"])
        self.assertEqual(resp.context["branch"], "main")

    def test_preview_reports_pending_changes(self) -> None:
        _write_fixture(self.root)
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(reverse("admin_content_push"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["has_changes"])
        self.assertEqual(resp.context["file_count"], 1)

    def test_run_commits_and_flashes_result(self) -> None:
        """Reports the library result — committed locally, push fails against /dev/null."""
        _write_fixture(self.root)
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(reverse("admin_content_push_run"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))

        log = subprocess.run(
            ["git", "-C", str(self.root), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Update content fixtures", log.stdout)

        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("committed" in m for m in messages))

    def test_run_with_no_changes_flashes_info(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(reverse("admin_content_push_run"))
        self.assertEqual(resp.status_code, 302)
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("No changes to commit" in m for m in messages))

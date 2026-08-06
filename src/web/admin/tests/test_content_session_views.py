"""Tests for the content session page + one-pull-request-per-session flow (#3018).

Mirrors ``test_content_row_export_views.py``'s structure: a superuser-only
gate on both views, plus a real tmp clone of a real bare "origin" (never the
network, never the real lore checkout) - ``session_state``/``session_diff``
run real git commands against it, so the fixture has to be an actual
checkout with a real ``origin/main``. ``open_session_pr`` itself is mocked
at this test module's import site of the view module
(``web.admin.content_session_views.open_session_pr``) rather than exercised
for real, since it pushes to origin and calls the GitHub REST API - both
already covered directly by ``core_management.tests.test_content_session``.
"""

from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from core_management.content_push import ContentPushError
from core_management.content_session import commit_row_export, ensure_session_branch
from core_management.tests._git_fixtures import init_origin_and_clone
from web.admin.content_row_export_views import _PENDING_EXPORT_SESSION_KEY


class TestContentSessionViewsGate(TestCase):
    """Superuser gate on both views - no content root needed to fail this early."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_both_views_require_superuser(self) -> None:
        self.client.force_login(self.staff)

        resp = self.client.get(reverse("admin_content_session"))
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(reverse("admin_content_session_pr"), {"title": "t", "body": "b"})
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(reverse("admin_content_session_discard"))
        self.assertEqual(resp.status_code, 403)


class TestContentSessionViewsConfigured(TestCase):
    """A tmp clone of a tmp bare origin, standing in for a content-repo checkout."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.origin = base / "origin.git"
        self.root = base / "clone"
        init_origin_and_clone(self.origin, self.root)
        self.client.force_login(self.super)

    def _env(self):
        return mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)})

    def _write_row(self, name: str = "row.json", content: str = '{"a": 1}\n') -> Path:
        path = self.root / "content" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_empty_session_renders_no_session_state(self) -> None:
        with self._env():
            resp = self.client.get(reverse("admin_content_session"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertFalse(resp.context["state"].on_session)
        self.assertIn("No content session is open yet", body)
        self.assertNotContains(resp, "Open pull request")

    def test_session_page_renders_commits_and_diff(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("state.json")
        commit_row_export(self.root, [path], "state export")

        with self._env():
            resp = self.client.get(reverse("admin_content_session"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["state"].on_session)
        self.assertContains(resp, "state export")
        self.assertContains(resp, "state.json")
        self.assertContains(resp, "Open pull request")

    def test_dirty_session_renders_status_lines_and_names_pending_row(self) -> None:
        """An uncommitted export shows its ``git status`` lines and, when this
        browser session holds the row-export module's pending-export record,
        names the row with a link to its diff page (#3018 review)."""
        ensure_session_branch(self.root)
        self._write_row("pending.json")  # written but never committed - stays dirty

        session = self.client.session
        session[_PENDING_EXPORT_SESSION_KEY] = {
            "model_label": "magic.effecttype",
            "pk": "42",
            "natural_key": "Test Pending Row",
            "is_addition": True,
        }
        session.save()

        with self._env():
            resp = self.client.get(reverse("admin_content_session"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["state"].dirty)
        self.assertContains(resp, "?? content/")
        self.assertContains(resp, "Pending export:")
        self.assertContains(resp, "EffectType")
        self.assertContains(resp, "Test Pending Row")
        diff_url = reverse("admin_content_export_row_diff")
        expected_link = f"{diff_url}?model=magic.effecttype&amp;pk=42"
        self.assertContains(resp, expected_link)

    def test_dirty_session_without_matching_pending_record_omits_named_row(self) -> None:
        """A dirty tree with no pending-export record in *this* session still
        shows the status lines, but never fabricates a named row for it."""
        ensure_session_branch(self.root)
        self._write_row("orphaned.json")

        with self._env():
            resp = self.client.get(reverse("admin_content_session"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["state"].dirty)
        self.assertContains(resp, "?? content/")
        self.assertNotContains(resp, "Pending export:")

    def test_pr_post_calls_open_session_pr_with_posted_title_and_body(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("pr.json")
        commit_row_export(self.root, [path], "pr export")

        with (
            self._env(),
            mock.patch(
                "web.admin.content_session_views.open_session_pr",
                return_value="https://github.com/acme/lore/pull/9",
            ) as mock_open_pr,
        ):
            resp = self.client.post(
                reverse("admin_content_session_pr"),
                {"title": "My session title", "body": "My session body"},
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_session"))
        mock_open_pr.assert_called_once()
        _, kwargs = mock_open_pr.call_args
        self.assertEqual(kwargs["title"], "My session title")
        self.assertEqual(kwargs["body"], "My session body")
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("https://github.com/acme/lore/pull/9" in m for m in msgs))

    def test_pr_post_flashes_content_push_error_and_keeps_typed_title_and_body(self) -> None:
        """A ``ContentPushError`` renders the page in place (no redirect), so the
        operator's typed title/body survive instead of being lost to the GET
        view's recomputed dated default (#3018 review)."""
        ensure_session_branch(self.root)
        path = self._write_row("err.json")
        commit_row_export(self.root, [path], "err export")

        with (
            self._env(),
            mock.patch(
                "web.admin.content_session_views.open_session_pr",
                side_effect=ContentPushError("could not open the session pull request: boom"),
            ),
        ):
            resp = self.client.post(
                reverse("admin_content_session_pr"),
                {"title": "My typed title", "body": "My typed body"},
            )

        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("could not open the session pull request" in m for m in msgs))
        self.assertContains(resp, "My typed title")
        self.assertContains(resp, "My typed body")

    def test_discard_all_without_checkbox_refuses_and_leaves_tree_dirty(self) -> None:
        ensure_session_branch(self.root)
        self._write_row("keepme.json")

        with self._env():
            resp = self.client.post(reverse("admin_content_session_discard"), {})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_session"))
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Check the confirmation box" in m for m in msgs))
        self.assertTrue((self.root / "content" / "keepme.json").exists())

    def test_discard_all_with_checkbox_cleans_working_tree(self) -> None:
        """Discard-all restores tracked edits and removes untracked additions."""
        ensure_session_branch(self.root)
        tracked = self._write_row("tracked.json")
        commit_row_export(self.root, [tracked], "seed tracked")
        tracked.write_text('{"a": 2}\n', encoding="utf-8")
        self._write_row("brand_new.json")

        session = self.client.session
        session[_PENDING_EXPORT_SESSION_KEY] = {
            "model_label": "magic.effecttype",
            "pk": "42",
            "natural_key": "Discard Me",
        }
        session.save()

        with self._env():
            resp = self.client.post(
                reverse("admin_content_session_discard"), {"discard_confirm": "1"}
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_session"))
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Discarded all pending changes" in m for m in msgs))
        self.assertEqual(tracked.read_text(encoding="utf-8"), '{"a": 1}\n')
        self.assertFalse((self.root / "content" / "brand_new.json").exists())
        self.assertNotIn(_PENDING_EXPORT_SESSION_KEY, self.client.session)

"""Tests for the admin load-conflict list/detail/resolve surface (#3017).

Mirrors ``test_content_load_views.py``'s structure: a superuser-only gate on
every view, a real tmp content root standing in for a checkout, and the same
credited-row conflict manufacture pattern ``test_load_conflicts_scan.py``
uses. The resolve view is the interesting one - it must refuse a wrong typed
key with the row untouched, refuse a stale digest (the diff changed between
the detail GET and this POST) with the row untouched, delete-then-reload on
a matching key and digest, and roll back cleanly on a ``ProtectedError``.
"""

from pathlib import Path
import tempfile
from unittest import mock

from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from core_management.load_conflicts import find_load_conflict
from web.admin.content_conflict_views import _detail_url
from world.contributors.factories import ContentContributorFactory
from world.traits.models import Trait


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestContentConflictViews(TestCase):
    """Superuser-only gate on all three views; unconfigured repo bails cleanly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_conflicts_page_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_content_conflicts"))
        self.assertEqual(resp.status_code, 403)

    def test_detail_page_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_content_conflict_detail"))
        self.assertEqual(resp.status_code, 403)

    def test_resolve_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_content_conflict_resolve"))
        self.assertEqual(resp.status_code, 403)

    def test_conflicts_page_without_content_root_redirects(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.get(reverse("admin_content_conflicts"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))

    def test_detail_page_without_content_root_redirects(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.get(
                reverse("admin_content_conflict_detail"),
                {"model": "arxii.trait", "key": "Performance"},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))

    def test_resolve_without_content_root_redirects(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Performance",
                    "digest": "irrelevant",
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_game_setup"))


class TestContentConflictConfigured(TestCase):
    """A tmp dir standing in for a content-repo checkout, with one credited conflict."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)
        # A real checkout always carries fixtures/, even when a given test seeds
        # no entries into it. build_all() rejects a root holding neither domain
        # directories nor fixtures/ as "not a corpus root at all", so create the
        # directory here: an empty corpus is legitimate and must still load.
        (self.root / "fixtures").mkdir(exist_ok=True)

    def _seed_conflict(self) -> None:
        from core_management.content_fixtures import build_all, load_entries

        ContentContributorFactory(name="Tehom")
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Tehom"\n---\nHuman words.\n',
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)

        _write(
            self.root,
            "skills/performance.md",
            "---\n"
            "name: Performance\n"
            "category: social\n"
            'written_by: "Tehom"\n'
            "---\n"
            "Regenerated words.\n",
        )

    def _current_digest(self) -> str:
        """The digest ``find_load_conflict`` would compute right now."""
        conflict = find_load_conflict(self.root, "arxii.trait", "Performance")
        assert conflict is not None
        return conflict.digest

    def test_conflicts_page_lists_credited_diffs(self) -> None:
        self._seed_conflict()
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(reverse("admin_content_conflicts"))
        self.assertEqual(resp.status_code, 200)
        conflicts = resp.context["conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].natural_key, "Performance")
        self.assertContains(resp, "Performance")

    def test_detail_page_shows_field_diff(self) -> None:
        self._seed_conflict()
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(
                reverse("admin_content_conflict_detail"),
                {"model": "arxii.trait", "key": "Performance"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Human words.")
        self.assertContains(resp, "Regenerated words.")

    def test_detail_page_reports_conflict_gone(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.get(
                reverse("admin_content_conflict_detail"),
                {"model": "arxii.trait", "key": "Nonexistent"},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_conflicts"))
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("no longer in conflict" in m for m in messages))

    def test_resolve_refuses_wrong_typed_key(self) -> None:
        self._seed_conflict()
        digest = self._current_digest()
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Not Performance",
                    "digest": digest,
                },
            )
        self.assertEqual(resp.status_code, 302)
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("does not match" in m for m in messages))

        trait = Trait.objects.get(name="Performance")
        self.assertEqual(trait.description, "Human words.")
        self.assertIsNotNone(trait.written_by_id)

    def test_resolve_refuses_stale_digest(self) -> None:
        """The diff changing between the detail GET and this POST is refused (#3017 review).

        Manufacture the conflict, GET the detail page (capturing the digest
        it rendered), mutate the corpus again so the diff the operator
        reviewed is no longer current, then POST with the stale digest and
        the (still correct) typed key. The row must stay untouched, and a
        second POST with the now-current digest must resolve cleanly - the
        digest check is about staleness, not about permanently blocking the
        row.
        """
        self._seed_conflict()
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            detail_resp = self.client.get(
                reverse("admin_content_conflict_detail"),
                {"model": "arxii.trait", "key": "Performance"},
            )
        stale_digest = detail_resp.context["conflict"].digest

        _write(
            self.root,
            "skills/performance.md",
            "---\n"
            "name: Performance\n"
            "category: social\n"
            'written_by: "Tehom"\n'
            "---\n"
            "Yet more regenerated words.\n",
        )

        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Performance",
                    "digest": stale_digest,
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, _detail_url("arxii.trait", "Performance"))
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("changed since you reviewed" in m for m in messages))

        trait = Trait.objects.get(name="Performance")
        self.assertEqual(trait.description, "Human words.")
        self.assertIsNotNone(trait.written_by_id)

        # Happy path: a matching (current) digest still resolves.
        fresh_digest = self._current_digest()
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Performance",
                    "digest": fresh_digest,
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_conflicts"))
        trait = Trait.objects.get(name="Performance")
        self.assertEqual(trait.description, "Yet more regenerated words.")

    def test_resolve_deletes_and_reloads_from_corpus(self) -> None:
        self._seed_conflict()
        original_pk = Trait.objects.get(name="Performance").pk
        digest = self._current_digest()
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Performance",
                    "digest": digest,
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_conflicts"))
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("now matches the repo" in m for m in messages))

        trait = Trait.objects.get(name="Performance")
        self.assertEqual(trait.description, "Regenerated words.")
        self.assertNotEqual(trait.pk, original_pk)

    def test_resolve_reports_protected_fk(self) -> None:
        self._seed_conflict()
        digest = self._current_digest()
        self.client.force_login(self.super)
        with (
            mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}),
            mock.patch(
                "web.admin.content_conflict_views._instance_for_conflict"
            ) as mock_instance_for_conflict,
        ):
            mock_instance = mock.MagicMock()
            mock_instance.delete.side_effect = ProtectedError(
                "Cannot delete some instances because they are referenced", []
            )
            mock_instance_for_conflict.return_value = mock_instance
            resp = self.client.post(
                reverse("admin_content_conflict_resolve"),
                {
                    "model": "arxii.trait",
                    "key": "Performance",
                    "typed_key": "Performance",
                    "digest": digest,
                },
            )
        self.assertEqual(resp.status_code, 302)
        messages = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Cannot delete" in m for m in messages))

        trait = Trait.objects.get(name="Performance")
        self.assertEqual(trait.description, "Human words.")
        self.assertIsNotNone(trait.written_by_id)

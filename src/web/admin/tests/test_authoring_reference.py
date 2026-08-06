"""Tests for the reference search pane: DB search plus opt-in file corpora (#3019 Task 7)."""

import os
from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.authoring.reference import db_search, file_search, reference_roots
from world.magic.factories import GiftFactory, TechniqueFactory


def _make_account(username: str, *, superuser: bool = True) -> AccountDB:
    if superuser:
        return AccountDB.objects.create_superuser(username, f"{username}@example.com", "pw-123456")
    account = AccountDB.objects.create_user(username, f"{username}@example.com", "pw-123456")
    account.is_staff = True
    account.save()
    return account


class DbSearchTests(TestCase):
    """`db_search` against a fixture row's prose."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = TechniqueFactory(
            name="Ember Lance", description="A lance wreathed in ember-bright flame."
        )
        cls.other = GiftFactory(
            name="Untouched Gift", description="Nothing to do with the search term."
        )

    def test_finds_row_by_substring_case_insensitive(self) -> None:
        groups = db_search("EMBER-BRIGHT")

        technique_groups = [g for g in groups if g.model_name == "Technique"]
        self.assertEqual(len(technique_groups), 1)
        hits = technique_groups[0].hits
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].pk, self.subject.pk)
        self.assertEqual(hits[0].label, str(self.subject))

    def test_groups_by_model(self) -> None:
        GiftFactory(name="Widowreach", description="Widowreach was taught to me long ago.")
        TechniqueFactory(name="Widowreach Strike", description="Named for Widowreach itself.")

        groups = db_search("Widowreach")

        model_names = {g.model_name for g in groups}
        self.assertIn("Gift", model_names)
        self.assertIn("Technique", model_names)
        for group in groups:
            self.assertTrue(group.hits)

    def test_cap_bounds_total_hits_across_models(self) -> None:
        for _ in range(3):
            TechniqueFactory(description="Capline appears here too.")
        for _ in range(3):
            GiftFactory(description="Capline appears here too.")

        groups = db_search("Capline", cap=2)

        total_hits = sum(len(g.hits) for g in groups)
        self.assertEqual(total_hits, 2)

    def test_empty_query_returns_no_groups(self) -> None:
        self.assertEqual(db_search(""), [])

    def test_no_match_returns_no_groups(self) -> None:
        self.assertEqual(db_search("Nonexistent Phrase Xyzzy"), [])


class FileSearchTests(TestCase):
    """`file_search` over a tmp file tree."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_finds_fixed_string_match_with_file_and_line(self) -> None:
        target = self.root / "notes.md"
        target.write_text("first line\nsecond line mentions Griefsong here\nthird\n")

        hits = file_search("griefsong", [self.root])

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].path, "notes.md")
        self.assertEqual(hits[0].line, 2)
        self.assertIn("Griefsong", hits[0].text)

    def test_only_text_suffixes_are_read(self) -> None:
        (self.root / "notes.md").write_text("match here\n")
        (self.root / "notes.txt").write_text("match here\n")
        (self.root / "notes.json").write_text('{"key": "match here"}\n')
        (self.root / "notes.py").write_text("match here\n")
        (self.root / "notes.bin").write_text("match here\n")

        hits = file_search("match here", [self.root])

        paths = {hit.path for hit in hits}
        self.assertEqual(paths, {"notes.md", "notes.txt", "notes.json"})

    def test_cap_limits_total_hits(self) -> None:
        (self.root / "a.md").write_text("cline\ncline\ncline\n")
        (self.root / "b.md").write_text("cline\ncline\ncline\n")

        hits = file_search("cline", [self.root], cap=2)

        self.assertEqual(len(hits), 2)

    def test_empty_query_returns_no_hits(self) -> None:
        (self.root / "a.md").write_text("anything\n")
        self.assertEqual(file_search("", [self.root]), [])

    def test_never_escapes_the_given_root_via_symlink(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_root = Path(outside.name)
        secret = outside_root / "secret.md"
        secret.write_text("escaperoot should never be found\n")

        # A symlink inside self.root pointing out at the file above - the
        # `..`-style escape probe the write editor's `is_relative_to` guard
        # exists to stop.
        link = self.root / "escape.md"
        try:
            link.symlink_to(secret)
        except OSError:
            self.skipTest("symlinks unsupported in this environment")

        hits = file_search("escaperoot", [self.root])

        self.assertEqual(hits, [])


class ReferenceRootsTests(TestCase):
    """`reference_roots` against a tmp content root."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "arx2"
        self.root.mkdir()

    def test_returns_only_existing_dirs(self) -> None:
        (self.root / "design").mkdir()
        # world_bibles deliberately absent; arx1 sibling deliberately absent.

        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            roots = reference_roots(staff_docs=True, arx1=True)

        self.assertEqual(roots, [self.root / "design"])

    def test_arx1_sibling_included_when_present(self) -> None:
        arx1 = self.root.parent / "arx1"
        arx1.mkdir()

        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            roots = reference_roots(staff_docs=False, arx1=True)

        self.assertEqual(roots, [arx1])

    def test_toggles_off_return_nothing(self) -> None:
        (self.root / "design").mkdir()
        (self.root.parent / "arx1").mkdir()

        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(self.root)}):
            roots = reference_roots(staff_docs=False, arx1=False)

        self.assertEqual(roots, [])

    def test_unconfigured_content_root_returns_nothing(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            roots = reference_roots(staff_docs=True, arx1=True)

        self.assertEqual(roots, [])


class AuthoringReferenceFragmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = _make_account("referencesuper")
        cls.staff = _make_account("referencestaff", superuser=False)
        cls.subject = TechniqueFactory(
            name="Cindermark", description="Cindermark burns everything it touches."
        )

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_reference"))
        self.assertEqual(resp.status_code, 403)

    def test_no_query_renders_empty_prompt(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_reference"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Type a name or phrase", resp.content.decode())

    def test_search_db_defaults_on_before_any_submission(self) -> None:
        # No querystring at all - the panel's own first `hx-trigger="load"`
        # fetch, before the operator has touched the form even once.
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_reference"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["search_db"])
        self.assertFalse(resp.context["staff_docs"])
        self.assertFalse(resp.context["arx1"])

    def test_db_checked_and_query_finds_a_match(self) -> None:
        # A real browser submit carries every checked box's value, including
        # a still-checked default - `db=1` here stands in for that.
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_reference"), {"q": "Cindermark", "db": "1"})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["search_db"])
        self.assertIn(str(self.subject), resp.content.decode())

    def test_db_results_are_grouped_by_model(self) -> None:
        GiftFactory(name="Widowreach Gift", description="Widowreach shared prose term.")
        TechniqueFactory(name="Widowreach Technique", description="Widowreach shared prose term.")
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin_authoring_reference"), {"q": "Widowreach", "db": "1"})

        model_names = {g.model_name for g in resp.context["db_groups"]}
        self.assertIn("Gift", model_names)
        self.assertIn("Technique", model_names)

    def test_arx1_toggle_off_never_errors_even_with_no_arx1_sibling(self) -> None:
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.get(
                reverse("admin_authoring_reference"),
                {"q": "Cindermark", "db": "1"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["arx1"])
        self.assertEqual(resp.context["file_hits"], [])

    def test_db_unchecked_on_submit_skips_db_search(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_reference"), {"q": "Cindermark"})

        self.assertFalse(resp.context["search_db"])
        self.assertEqual(resp.context["db_groups"], [])

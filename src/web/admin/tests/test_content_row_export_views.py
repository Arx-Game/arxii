"""Tests for the row-export button/diff/confirm/discard surface (#3018).

Mirrors ``test_content_conflict_views.py``'s structure: a superuser-only
gate on every view, plus a real tmp content root standing in for a checkout.
Unlike the conflict tests, the content root here has to be a real clone of a
real bare "origin" (not just a lone repo with ``origin`` pointed at
``/dev/null``, the ``test_content_push_views.py`` idiom) - the row-export
flow's first step is ``ensure_session_branch``, which fetches origin and can
create the session branch off ``origin/main``, so origin has to actually
exist. ``core_management.tests._git_fixtures`` provides that pair; Task 2's
``test_content_session.py`` uses the exact same helper.
"""

from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from core_management.tests._git_fixtures import init_origin_and_clone, run_git
from world.magic.factories import EffectTypeFactory


class TestContentRowExportViewsGate(TestCase):
    """Superuser gate on all three views - no content root needed to fail this early."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_all_three_views_require_superuser(self) -> None:
        self.client.force_login(self.staff)

        resp = self.client.post(
            reverse("admin_content_export_row"), {"model": "magic.effecttype", "pk": "1"}
        )
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get(
            reverse("admin_content_export_row_diff"), {"model": "magic.effecttype", "pk": "1"}
        )
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(
            reverse("admin_content_export_row_confirm"), {"model": "magic.effecttype", "pk": "1"}
        )
        self.assertEqual(resp.status_code, 403)


class TestContentRowExportViewsConfigured(TestCase):
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

    def _export(self, model_label: str, pk: object):
        with self._env():
            return self.client.post(
                reverse("admin_content_export_row"), {"model": model_label, "pk": pk}
            )

    def _diff(self, model_label: str, pk: object):
        with self._env():
            return self.client.get(
                reverse("admin_content_export_row_diff"), {"model": model_label, "pk": pk}
            )

    def test_export_row_writes_working_tree_and_redirects_to_diff(self) -> None:
        effect = EffectTypeFactory(name="Row View Export")

        resp = self._export("magic.effecttype", effect.pk)

        self.assertEqual(resp.status_code, 302)
        diff_url = reverse("admin_content_export_row_diff")
        expected = f"{diff_url}?model=magic.effecttype&pk={effect.pk}"
        self.assertEqual(resp.url, expected)

        path = self.root / "fixtures" / "magic" / "effecttype.json"
        self.assertTrue(path.exists())
        self.assertIn("Row View Export", path.read_text(encoding="utf-8"))
        status = run_git(self.root, "status", "--short").stdout
        self.assertIn("fixtures/", status)
        branch = run_git(self.root, "branch", "--show-current").stdout.strip()
        self.assertEqual(branch, "content-export-session")

    def test_export_refuses_while_same_model_pending(self) -> None:
        """Exporting row B while row A (same model) is still pending is refused.

        ``ensure_session_branch``'s dirty-tree check now fires even on the
        session branch itself (#3018 review), so B is never written at all -
        the operator is redirected to A's diff page instead, with a flash
        naming A as the pending export.
        """
        first = EffectTypeFactory(name="Row Pending A")
        second = EffectTypeFactory(name="Row Pending B")

        first_resp = self._export("magic.effecttype", first.pk)
        self.assertEqual(first_resp.status_code, 302)

        second_resp = self._export("magic.effecttype", second.pk)

        self.assertEqual(second_resp.status_code, 302)
        diff_url = reverse("admin_content_export_row_diff")
        expected = f"{diff_url}?model=magic.effecttype&pk={first.pk}"
        self.assertEqual(second_resp.url, expected)
        msgs = [str(m) for m in second_resp.wsgi_request._messages]
        self.assertTrue(any("Pending:" in m for m in msgs))
        self.assertTrue(any("Pending: EffectType [Row Pending A]" in m for m in msgs))

        path = self.root / "fixtures" / "magic" / "effecttype.json"
        content = path.read_text(encoding="utf-8")
        self.assertIn("Row Pending A", content)
        self.assertNotIn("Row Pending B", content)

    def test_export_succeeds_after_confirming_pending(self) -> None:
        """Once A is confirmed (committed), exporting B proceeds normally."""
        first = EffectTypeFactory(name="Row Sequence A")
        second = EffectTypeFactory(name="Row Sequence B")

        self._export("magic.effecttype", first.pk)
        diff_resp = self._diff("magic.effecttype", first.pk)
        with self._env():
            self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": first.pk,
                    "digest": diff_resp.context["digest"],
                    "action": "confirm",
                    "new_row": "1",
                },
            )

        second_resp = self._export("magic.effecttype", second.pk)

        self.assertEqual(second_resp.status_code, 302)
        diff_url = reverse("admin_content_export_row_diff")
        expected = f"{diff_url}?model=magic.effecttype&pk={second.pk}"
        self.assertEqual(second_resp.url, expected)
        path = self.root / "fixtures" / "magic" / "effecttype.json"
        self.assertIn("Row Sequence B", path.read_text(encoding="utf-8"))

    def test_export_refuses_while_cross_model_pending(self) -> None:
        """A pending export on a different model also refuses the next export."""
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        pending_effect = EffectTypeFactory(name="Row Cross Pending")
        other_trait = TraitFactory(name="row_cross_pending_trait", trait_type=TraitType.OTHER)

        self._export("magic.effecttype", pending_effect.pk)

        resp = self._export("traits.trait", other_trait.pk)

        self.assertEqual(resp.status_code, 302)
        diff_url = reverse("admin_content_export_row_diff")
        expected = f"{diff_url}?model=magic.effecttype&pk={pending_effect.pk}"
        self.assertEqual(resp.url, expected)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Pending: EffectType [Row Cross Pending]" in m for m in msgs))
        trait_path = self.root / "fixtures" / "traits" / "trait.json"
        self.assertFalse(trait_path.exists())

    def test_diff_page_shows_git_diff_and_addition_checkbox_only_for_additions(self) -> None:
        from core_management.content_export import export_to_content_repo

        seeded = EffectTypeFactory(name="Row Diff Seeded", description="Original")
        with self._env():
            export_to_content_repo(self.root)
        run_git(self.root, "add", ".")
        run_git(self.root, "commit", "-m", "seed corpus")
        run_git(self.root, "push", "-u", "origin", "main")

        seeded.description = "Updated"
        seeded.save()

        self._export("magic.effecttype", seeded.pk)
        update_resp = self._diff("magic.effecttype", seeded.pk)

        self.assertEqual(update_resp.status_code, 200)
        self.assertFalse(update_resp.context["is_addition"])
        self.assertNotContains(update_resp, 'name="new_row"')
        self.assertContains(update_resp, "Original")
        self.assertContains(update_resp, "Updated")

        # Confirm (commit) the update before starting a second pending export -
        # ensure_session_branch refuses a dirty tree even on the session
        # branch itself, so the flow enforces at most one uncommitted row
        # export at a time (see test_export_refuses_while_another_pending*).
        with self._env():
            self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": seeded.pk,
                    "digest": update_resp.context["digest"],
                    "action": "confirm",
                },
            )

        added = EffectTypeFactory(name="Row Diff Added")
        self._export("magic.effecttype", added.pk)
        add_resp = self._diff("magic.effecttype", added.pk)

        self.assertEqual(add_resp.status_code, 200)
        self.assertTrue(add_resp.context["is_addition"])
        self.assertContains(add_resp, 'name="new_row"')

    def test_confirm_refuses_stale_digest(self) -> None:
        effect = EffectTypeFactory(name="Row Stale Digest")
        self._export("magic.effecttype", effect.pk)
        diff_resp = self._diff("magic.effecttype", effect.pk)
        stale_digest = diff_resp.context["digest"]

        # Mutate the written file after the GET, so the diff the operator
        # reviewed is no longer current.
        path = self.root / "fixtures" / "magic" / "effecttype.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        with self._env():
            resp = self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": effect.pk,
                    "digest": stale_digest,
                    "action": "confirm",
                    "new_row": "1",
                },
            )

        self.assertEqual(resp.status_code, 302)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("changed since you reviewed" in m for m in msgs))
        log = run_git(self.root, "log", "--oneline", "-5").stdout
        self.assertNotIn("Export EffectType", log)

    def test_confirm_addition_without_checkbox_refuses(self) -> None:
        effect = EffectTypeFactory(name="Row No Checkbox")
        self._export("magic.effecttype", effect.pk)
        diff_resp = self._diff("magic.effecttype", effect.pk)
        digest = diff_resp.context["digest"]
        self.assertTrue(diff_resp.context["is_addition"])

        with self._env():
            resp = self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": effect.pk,
                    "digest": digest,
                    "action": "confirm",
                },
            )

        self.assertEqual(resp.status_code, 302)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("new-row box" in m for m in msgs))
        log = run_git(self.root, "log", "--oneline", "-5").stdout
        self.assertNotIn("Export EffectType", log)

    def test_confirm_commits_and_flashes(self) -> None:
        effect = EffectTypeFactory(name="Row Commit Flash")
        self._export("magic.effecttype", effect.pk)
        diff_resp = self._diff("magic.effecttype", effect.pk)
        digest = diff_resp.context["digest"]

        with self._env():
            resp = self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": effect.pk,
                    "digest": digest,
                    "action": "confirm",
                    "new_row": "1",
                },
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_content_session"))
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("Row Commit Flash" in m for m in msgs))
        log = run_git(self.root, "log", "--oneline", "-1").stdout
        self.assertIn("Export EffectType", log)
        status = run_git(self.root, "status", "--short").stdout
        self.assertEqual(status.strip(), "")

    def test_discard_restores_tree(self) -> None:
        effect = EffectTypeFactory(name="Row Discard")
        self._export("magic.effecttype", effect.pk)
        diff_resp = self._diff("magic.effecttype", effect.pk)
        digest = diff_resp.context["digest"]

        with self._env():
            resp = self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": effect.pk,
                    "digest": digest,
                    "action": "discard",
                },
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin:arxii_effecttype_change", args=[effect.pk]))
        path = self.root / "fixtures" / "magic" / "effecttype.json"
        self.assertFalse(path.exists())
        status = run_git(self.root, "status", "--short").stdout
        self.assertEqual(status.strip(), "")

    def test_second_browser_diff_shows_addition_checkbox_and_enforces_it(self) -> None:
        """A second browser's request session never ran the export (#3018 review).

        The original design read ``is_addition`` out of the exporting browser's
        request session, which defaulted to ``False`` for anyone else - so a
        second superuser hitting this diff URL directly could confirm a
        genuine addition with no new-row checkbox at all. It must now be
        derived straight from git, so a fresh client (standing in for a
        second browser/operator, never touching ``self.client``'s session)
        sees the same checkbox and enforcement as the browser that exported.
        """
        from django.test import Client

        added = EffectTypeFactory(name="Row Second Browser Addition")
        self._export("magic.effecttype", added.pk)

        second = Client()
        second.force_login(self.super)

        with self._env():
            diff_resp = second.get(
                reverse("admin_content_export_row_diff"),
                {"model": "magic.effecttype", "pk": added.pk},
            )
        self.assertEqual(diff_resp.status_code, 200)
        self.assertTrue(diff_resp.context["is_addition"])
        self.assertContains(diff_resp, 'name="new_row"')
        digest = diff_resp.context["digest"]

        with self._env():
            refused = second.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": added.pk,
                    "digest": digest,
                    "action": "confirm",
                },
            )
        self.assertEqual(refused.status_code, 302)
        msgs = [str(m) for m in refused.wsgi_request._messages]
        self.assertTrue(any("new-row box" in m for m in msgs))
        log = run_git(self.root, "log", "--oneline", "-5").stdout
        self.assertNotIn("Export EffectType", log)

        with self._env():
            committed = second.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "magic.effecttype",
                    "pk": added.pk,
                    "digest": digest,
                    "action": "confirm",
                    "new_row": "1",
                },
            )
        self.assertEqual(committed.status_code, 302)
        self.assertEqual(committed.url, reverse("admin_content_session"))
        log = run_git(self.root, "log", "--oneline", "-1").stdout
        self.assertIn("Export EffectType", log)

    def test_second_browser_diff_update_row_stays_not_addition(self) -> None:
        """An update row derives ``is_addition = False`` for a fresh session too.

        The fail-closed fix must not over-fire on the far more common case -
        editing a row the corpus already has - or every ordinary update would
        start spuriously demanding the new-row checkbox.
        """
        from django.test import Client

        from core_management.content_export import export_to_content_repo

        seeded = EffectTypeFactory(name="Row Second Browser Update", description="Original")
        with self._env():
            export_to_content_repo(self.root)
        run_git(self.root, "add", ".")
        run_git(self.root, "commit", "-m", "seed corpus")
        run_git(self.root, "push", "-u", "origin", "main")

        seeded.description = "Updated"
        seeded.save()
        self._export("magic.effecttype", seeded.pk)

        second = Client()
        second.force_login(self.super)
        with self._env():
            diff_resp = second.get(
                reverse("admin_content_export_row_diff"),
                {"model": "magic.effecttype", "pk": seeded.pk},
            )
        self.assertEqual(diff_resp.status_code, 200)
        self.assertFalse(diff_resp.context["is_addition"])
        self.assertNotContains(diff_resp, 'name="new_row"')

    def test_refused_export_flashes_and_never_touches_git(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.seeds_checks import ensure_character_magic_check_type
        from world.skills.factories import SkillFactory
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        sheet = CharacterSheetFactory()
        stat = TraitFactory(name="row_view_willpower", trait_type=TraitType.STAT)
        skill = SkillFactory(trait__name="row_view_ritualism")
        synthesized = ensure_character_magic_check_type(sheet, stat=stat, skill=skill)

        resp = self._export("checks.checktype", synthesized.pk)

        self.assertEqual(resp.status_code, 302)
        msgs = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("excluded from export" in m for m in msgs))
        status = run_git(self.root, "status", "--short").stdout
        self.assertEqual(status.strip(), "")

    def test_markdown_domain_row_exports_diffs_and_confirms(self) -> None:
        """A markdown-domain row (CodexEntry) round-trips through export/diff/confirm.

        Every other test in this module drives a flat-JSON model
        (``magic.effecttype``). This covers the other export shape - one
        markdown file per row, under ``content/`` rather than ``fixtures/``
        - through the exact same three views.
        """
        from core_management.content_fixtures import content_slug
        from world.codex.factories import CodexEntryFactory

        entry = CodexEntryFactory(
            name="Row Markdown Entry",
            summary="A short summary.",
            lore_content="Some in-character lore text.",
            mechanics_content="Some out-of-character mechanics text.",
        )

        export_resp = self._export("codex.codexentry", entry.pk)
        self.assertEqual(export_resp.status_code, 302)

        diff_resp = self._diff("codex.codexentry", entry.pk)
        self.assertEqual(diff_resp.status_code, 200)
        self.assertTrue(diff_resp.context["diff_text"].strip())
        self.assertContains(diff_resp, "Some in-character lore text.")

        with self._env():
            confirm_resp = self.client.post(
                reverse("admin_content_export_row_confirm"),
                {
                    "model": "codex.codexentry",
                    "pk": entry.pk,
                    "digest": diff_resp.context["digest"],
                    "action": "confirm",
                    "new_row": "1",
                },
            )
        self.assertEqual(confirm_resp.status_code, 302)
        self.assertEqual(confirm_resp.url, reverse("admin_content_session"))

        entry_dir = self.root / "content" / "codex_entries"
        expected_name = f"{content_slug(entry.name)}.md"
        matches = list(entry_dir.rglob(expected_name))
        self.assertEqual(len(matches), 1)
        body = matches[0].read_text(encoding="utf-8")
        self.assertIn("Some in-character lore text.", body)
        self.assertIn("Some out-of-character mechanics text.", body)
        log = run_git(self.root, "log", "--oneline", "-1").stdout
        self.assertIn("Export CodexEntry", log)

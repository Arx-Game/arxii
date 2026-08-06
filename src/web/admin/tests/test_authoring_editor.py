"""Tests for the Authoring Workbench row editor fragments (#3019 Task 5)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.codex.factories import CodexEntryFactory
from world.codex.models import CodexEntry
from world.contributors.factories import ContentContributorFactory


def _make_account(username: str, *, superuser: bool = True) -> AccountDB:
    if superuser:
        return AccountDB.objects.create_superuser(username, f"{username}@example.com", "pw-123456")
    account = AccountDB.objects.create_user(username, f"{username}@example.com", "pw-123456")
    account.is_staff = True
    account.save()
    return account


def _db_values(pk: int, *fields: str) -> tuple:
    """Read columns straight off the DB row, bypassing idmapper's identity cache.

    `CodexEntry.objects.get(...)`/`.refresh_from_db()` return the SAME cached
    `SharedMemoryModel` instance the view under test already mutated in
    memory (see the `sharedmemory-model` skill) - after a full_clean()
    failure that instance still carries the rejected in-memory value, so
    re-fetching it that way would make a "this was NOT saved" assertion pass
    even if the row genuinely had been overwritten. `.values_list()` never
    instantiates a model at all, so it always reads what the database
    actually holds.
    """
    return CodexEntry.objects.filter(pk=pk).values_list(*fields).first()


class AuthoringEditorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = _make_account("editorsuper")
        cls.staff = _make_account("editorstaff", superuser=False)
        cls.writer = ContentContributorFactory(name="Editor Writer")
        PlayerData.objects.create(account=cls.super, contributor=cls.writer)

    def _entry(self, **kwargs) -> CodexEntry:
        return CodexEntryFactory(**kwargs)


class TestAuthoringEditorGet(AuthoringEditorTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_editor"))
        self.assertEqual(resp.status_code, 403)

    def test_renders_one_textarea_per_prose_field_with_value_round_trip(self) -> None:
        entry = self._entry(lore_content="The old lore text.")
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "codex.CodexEntry", "pk": entry.pk},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('<textarea name="summary" id="id_summary">', body)
        self.assertIn('<textarea name="lore_content" id="id_lore_content">', body)
        self.assertIn('<textarea name="mechanics_content" id="id_mechanics_content">', body)
        self.assertIn("The old lore text.", body)

    def test_textareas_render_in_declaration_order(self) -> None:
        entry = self._entry()
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "codex.CodexEntry", "pk": entry.pk},
        )
        body = resp.content.decode()

        self.assertLess(body.index('id="id_summary"'), body.index('id="id_lore_content"'))
        self.assertLess(body.index('id="id_lore_content"'), body.index('id="id_mechanics_content"'))

    def test_mechanical_summary_shows_field_and_fk_by_str(self) -> None:
        entry = self._entry()
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "codex.CodexEntry", "pk": entry.pk},
        )
        body = resp.content.decode()

        self.assertIn("share_cost", body)
        self.assertIn(">5<", body)
        self.assertIn(str(entry.subject), body)

    def test_no_textarea_for_mechanical_fields(self) -> None:
        entry = self._entry()
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "codex.CodexEntry", "pk": entry.pk},
        )
        body = resp.content.decode()

        self.assertNotIn('<textarea name="subject"', body)
        self.assertNotIn('<textarea name="share_cost"', body)
        self.assertNotIn('<textarea name="name"', body)

    def test_refuses_non_credited_model(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "contributors.ContentContributor", "pk": self.writer.pk},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("is not a credited content model", body)
        self.assertNotIn("<textarea", body)

    def test_unknown_model_flashes_in_fragment(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "bogus.NoSuchModel", "pk": "1"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Unknown model.", resp.content.decode())

    def test_missing_row_flashes_in_fragment(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"),
            {"model": "codex.CodexEntry", "pk": "999999"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("does not exist", resp.content.decode())


class TestAuthoringEditorSave(AuthoringEditorTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_authoring_editor_save"))
        self.assertEqual(resp.status_code, 403)

    def test_updates_prose_only_mechanical_field_immune_even_if_smuggled(self) -> None:
        entry = self._entry(lore_content="Original lore.")
        original_name = entry.name
        self.client.force_login(self.super)

        resp = self.client.post(
            reverse("admin_authoring_editor_save"),
            {
                "model": "codex.CodexEntry",
                "pk": str(entry.pk),
                "summary": "A fresh summary.",
                "lore_content": "Rewritten lore.",
                "name": "Smuggled Name Change",
            },
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Saved.", body)

        summary, lore_content, name = _db_values(entry.pk, "summary", "lore_content", "name")
        self.assertEqual(summary, "A fresh summary.")
        self.assertEqual(lore_content, "Rewritten lore.")
        self.assertEqual(name, original_name)

    def test_validation_error_re_renders_with_error_and_does_not_save(self) -> None:
        entry = self._entry(lore_content="Kept lore.")
        overlong_summary = "x" * 301
        self.client.force_login(self.super)

        resp = self.client.post(
            reverse("admin_authoring_editor_save"),
            {
                "model": "codex.CodexEntry",
                "pk": str(entry.pk),
                "summary": overlong_summary,
                "lore_content": "Kept lore.",
            },
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("Saved.", body)
        self.assertIn(overlong_summary, body)

        (summary,) = _db_values(entry.pk, "summary")
        self.assertEqual(summary, "")


class TestAuthoringEditorCredit(AuthoringEditorTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_authoring_editor_credit"))
        self.assertEqual(resp.status_code, 403)

    def test_stamps_written_by_and_written_on_and_offers_export_handoff(self) -> None:
        entry = self._entry(lore_content="Lore before credit.")
        self.client.force_login(self.super)

        resp = self.client.post(
            reverse("admin_authoring_editor_credit"),
            {
                "model": "codex.CodexEntry",
                "pk": str(entry.pk),
                "lore_content": "Lore before credit.",
            },
        )

        self.assertEqual(resp.status_code, 200)
        written_by_id, written_on = _db_values(entry.pk, "written_by_id", "written_on")
        self.assertEqual(written_by_id, self.writer.pk)
        self.assertEqual(written_on, timezone.now().date())

        body = resp.content.decode()
        self.assertIn(
            "This row is now credited: content loads will not overwrite it until the "
            "corpus catches up. Export it to the content repo to close the loop.",
            body,
        )
        self.assertIn(f'action="{reverse("admin_content_export_row")}"', body)
        self.assertIn('name="model" value="codex.codexentry"', body)
        self.assertIn(f'name="pk" value="{entry.pk}"', body)

    def test_saves_posted_prose_before_stamping(self) -> None:
        entry = self._entry(lore_content="Old lore.")
        self.client.force_login(self.super)

        self.client.post(
            reverse("admin_authoring_editor_credit"),
            {
                "model": "codex.CodexEntry",
                "pk": str(entry.pk),
                "lore_content": "New credited lore.",
            },
        )

        lore_content, written_by_id = _db_values(entry.pk, "lore_content", "written_by_id")
        self.assertEqual(lore_content, "New credited lore.")
        self.assertIsNotNone(written_by_id)

    def test_unlinked_operator_gets_setup_guidance_and_stamps_nothing(self) -> None:
        lonely = _make_account("editorlonely")
        entry = self._entry(lore_content="Untouched lore.")
        self.client.force_login(lonely)

        resp = self.client.post(
            reverse("admin_authoring_editor_credit"),
            {
                "model": "codex.CodexEntry",
                "pk": str(entry.pk),
                "lore_content": "Untouched lore.",
            },
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f'href="{reverse("admin_authoring")}"', body)

        written_by_id, written_on = _db_values(entry.pk, "written_by_id", "written_on")
        self.assertIsNone(written_by_id)
        self.assertIsNone(written_on)


class TestAuthoringEditorReview(AuthoringEditorTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_authoring_editor_review"))
        self.assertEqual(resp.status_code, 403)

    def test_stamps_reviewed_by_and_on_leaves_authorship_untouched(self) -> None:
        entry = self._entry(
            lore_content="Reviewed lore.",
            written_by=self.writer,
            written_on=timezone.now().date(),
        )
        self.client.force_login(self.super)

        resp = self.client.post(
            reverse("admin_authoring_editor_review"),
            {"model": "codex.CodexEntry", "pk": str(entry.pk)},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Marked reviewed.", resp.content.decode())

        reviewed_by_id, reviewed_on, written_by_id = _db_values(
            entry.pk, "reviewed_by_id", "reviewed_on", "written_by_id"
        )
        self.assertEqual(reviewed_by_id, self.writer.pk)
        self.assertEqual(reviewed_on, timezone.now().date())
        self.assertEqual(written_by_id, self.writer.pk)

    def test_reviewer_may_equal_author_unenforced(self) -> None:
        entry = self._entry(
            lore_content="Self reviewed lore.",
            written_by=self.writer,
            written_on=timezone.now().date(),
        )
        self.client.force_login(self.super)

        resp = self.client.post(
            reverse("admin_authoring_editor_review"),
            {"model": "codex.CodexEntry", "pk": str(entry.pk)},
        )

        self.assertEqual(resp.status_code, 200)
        reviewed_by_id, written_by_id = _db_values(entry.pk, "reviewed_by_id", "written_by_id")
        self.assertEqual(reviewed_by_id, written_by_id)

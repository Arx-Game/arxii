"""Tests for the Authoring Workbench dashboard, stats, and queue panels (#3019)."""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.contributors.factories import ContentContributorFactory
from world.traits.models import Trait, TraitCategory, TraitType


class AuthoringViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.writer = ContentContributorFactory(name="Writer")
        cls.reviewer = ContentContributorFactory(name="Reviewer")
        # These fragment/dashboard tests exercise the post-setup dashboard, not
        # the setup gate itself (that gate is covered in test_authoring_setup.py)
        # - so cls.super carries a linked contributor from the start.
        PlayerData.objects.create(
            account=cls.super, contributor=ContentContributorFactory(name="Root Admin")
        )

    def _trait(
        self, name: str, description: str, *, written: bool = False, reviewed: bool = False
    ) -> Trait:
        return Trait.objects.create(
            name=name,
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description=description,
            written_by=self.writer if written else None,
            written_on=date(2026, 8, 4) if written else None,
            reviewed_by=self.reviewer if reviewed else None,
            reviewed_on=date(2026, 8, 5) if reviewed else None,
        )


class TestAuthoringDashboardView(AuthoringViewsTestCase):
    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_dashboard(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="authoring-root"', body)
        self.assertIn('id="panel-authoring-stats"', body)
        self.assertIn('id="panel-authoring-queue"', body)


class TestAuthoringStatsFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_stats"))
        self.assertEqual(resp.status_code, 403)

    def test_domain_row_renders_from_factory_data(self) -> None:
        self._trait("Alpha", "One two three four words here.")
        self._trait("Beta", "One two three.", written=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_stats"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("traits", body)
        self.assertIn(">2<", body)


class TestAuthoringQueueFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_queue"))
        self.assertEqual(resp.status_code, 403)

    def test_rows_render_worst_first(self) -> None:
        self._trait("Placeholder Row", "PLACEHOLDER prose here.")
        self._trait("Finished Row", "Ordinary finished prose.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertLess(body.index("Placeholder Row"), body.index("Finished Row"))

    def test_domain_filter(self) -> None:
        self._trait("Trait Row", "Ordinary finished prose text.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"domain": "traits"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Trait Row", resp.content.decode())

        resp = self.client.get(reverse("admin_authoring_queue"), {"domain": "tarot"})
        self.assertNotIn("Trait Row", resp.content.decode())

    def test_status_filter_placeholder(self) -> None:
        self._trait("Placeholder Row", "PLACEHOLDER prose here.")
        self._trait("Regular Row", "Ordinary finished prose.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "placeholder"})
        body = resp.content.decode()
        self.assertIn("Placeholder Row", body)
        self.assertNotIn("Regular Row", body)

    def test_status_filter_unwritten(self) -> None:
        self._trait("Unwritten Row", "Ordinary unwritten prose here.")
        self._trait("Written Row", "Ordinary written prose here.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "unwritten"})
        body = resp.content.decode()
        self.assertIn("Unwritten Row", body)
        self.assertNotIn("Written Row", body)

    def test_status_filter_unreviewed(self) -> None:
        self._trait("Unreviewed Row", "Ordinary unreviewed prose.", written=True)
        self._trait("Reviewed Row", "Ordinary reviewed prose.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "unreviewed"})
        body = resp.content.decode()
        self.assertIn("Unreviewed Row", body)
        self.assertNotIn("Reviewed Row", body)

    def test_q_filter_matches_name_substring(self) -> None:
        self._trait("Sunfire Blessing", "Ordinary finished prose here.")
        self._trait("Moonlit Ward", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"q": "sunfire"})
        body = resp.content.decode()
        self.assertIn("Sunfire Blessing", body)
        self.assertNotIn("Moonlit Ward", body)

    def test_row_carries_editor_link(self) -> None:
        trait = self._trait("Linked Row", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        body = resp.content.decode()
        editor_url = reverse("admin_authoring_editor")
        self.assertIn(editor_url, body)
        self.assertIn("model=traits.Trait", body)
        self.assertIn(f"pk={trait.pk}", body)

    def test_display_capped_at_100_with_showing_note(self) -> None:
        for i in range(101):
            self._trait(f"Bulk Row {i:03d}", "Ordinary finished prose text goes here now.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        body = resp.content.decode()
        self.assertIn("Showing 100 of 101", body)


class TestAuthoringEditorFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_editor"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_editor_form_for_a_real_row(self) -> None:
        """A real Trait row renders its prose editor, not just the error shell.

        The original version of this test never created the Trait it
        queried for, so ``pk=1`` almost always resolved to a missing row -
        it was unknowingly asserting against the "does not exist" error
        fragment's own ``<h2>Editing traits.Trait #1</h2>`` heading (which
        renders regardless of whether the row resolved), not a loaded editor
        (#3019 review, Minor).
        """
        trait = self._trait("Editor Shell Trait", "Some prose worth editing.")
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"), {"model": "traits.Trait", "pk": str(trait.pk)}
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("does not exist", body)
        self.assertIn('<textarea name="description" id="id_description">', body)
        self.assertIn("Some prose worth editing.", body)

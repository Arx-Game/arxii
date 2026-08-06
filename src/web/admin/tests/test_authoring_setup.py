"""Tests for the Authoring Workbench first-run contributor setup gate (#3019)."""

from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.authoring.contributors import current_contributor, link_contributor
from world.contributors.factories import ContentContributorFactory
from world.contributors.models import ContentContributor

_CREATE_PATH = "web.admin.authoring.contributors.ContentContributor.objects.create"


def _make_account(username: str) -> AccountDB:
    return AccountDB.objects.create_superuser(username, f"{username}@example.com", "pw-123456")


class TestCurrentContributor(TestCase):
    def test_none_without_player_data(self) -> None:
        account = _make_account("noplayerdata")
        self.assertIsNone(current_contributor(account))

    def test_none_without_link(self) -> None:
        account = _make_account("unlinked")
        PlayerData.objects.create(account=account)
        self.assertIsNone(current_contributor(account))

    def test_resolves_when_linked(self) -> None:
        account = _make_account("linked")
        contributor = ContentContributorFactory(name="Linked Writer")
        PlayerData.objects.create(account=account, contributor=contributor)
        self.assertEqual(current_contributor(account), contributor)


class TestLinkContributor(TestCase):
    def test_creates_and_links_new_contributor(self) -> None:
        account = _make_account("freshaccount")
        self.assertFalse(PlayerData.objects.filter(account=account).exists())

        contributor = link_contributor(account, name="Fresh Writer")

        self.assertEqual(contributor.name, "Fresh Writer")
        player_data = PlayerData.objects.get(account=account)
        self.assertEqual(player_data.contributor, contributor)

    def test_links_existing_unlinked_contributor_by_name(self) -> None:
        account = _make_account("byname")
        existing = ContentContributorFactory(name="Unclaimed Name")

        contributor = link_contributor(account, name="Unclaimed Name")

        self.assertEqual(contributor.pk, existing.pk)
        self.assertEqual(ContentContributor.objects.filter(name="Unclaimed Name").count(), 1)

    def test_links_existing_contributor_by_pk(self) -> None:
        account = _make_account("bypk")
        existing = ContentContributorFactory(name="Picked By Pk")

        contributor = link_contributor(account, existing_pk=existing.pk)

        self.assertEqual(contributor.pk, existing.pk)

    def test_refuses_blank_name(self) -> None:
        account = _make_account("blankname")
        with self.assertRaises(ValueError):
            link_contributor(account, name="   ")

    def test_refuses_em_dash_in_name(self) -> None:
        account = _make_account("emdashname")
        with self.assertRaises(ValueError) as ctx:
            # Deliberately an em-dash: proving link_contributor rejects one.
            link_contributor(account, name="Writer—Name")  # noqa: IDENT_DASH
        self.assertIn("hyphen", str(ctx.exception))

    def test_refuses_en_dash_in_name(self) -> None:
        account = _make_account("endashname")
        with self.assertRaises(ValueError) as ctx:
            # Deliberately an en-dash: proving link_contributor rejects one.
            link_contributor(account, name="Writer–Name")  # noqa: IDENT_DASH
        self.assertIn("hyphen", str(ctx.exception))

    def test_refuses_name_linked_to_another_account(self) -> None:
        owner = _make_account("owner1")
        contributor = ContentContributorFactory(name="Taken Name")
        PlayerData.objects.create(account=owner, contributor=contributor)

        other = _make_account("other1")
        with self.assertRaises(ValueError):
            link_contributor(other, name="Taken Name")

    def test_refuses_pk_linked_to_another_account(self) -> None:
        owner = _make_account("owner2")
        contributor = ContentContributorFactory(name="Taken By Pk")
        PlayerData.objects.create(account=owner, contributor=contributor)

        other = _make_account("other2")
        with self.assertRaises(ValueError):
            link_contributor(other, existing_pk=contributor.pk)

    def test_refuses_name_over_max_length(self) -> None:
        """A name over ``ContentContributor.name``'s 100-char max_length is refused up front.

        SQLite has no column-length constraint at all, so this only ever
        surfaces on Postgres without the explicit check in
        ``link_contributor`` - it would 500 there instead of failing cleanly
        (#3019 review, Minor).
        """
        account = _make_account("overlongname")
        with self.assertRaises(ValueError) as ctx:
            link_contributor(account, name="x" * 101)
        self.assertIn("100", str(ctx.exception))
        self.assertFalse(ContentContributor.objects.filter(name__startswith="x" * 101).exists())

    def test_existing_pk_beyond_integer_range_is_coherent_not_a_500(self) -> None:
        account = _make_account("absurdpkmodel")
        with self.assertRaises(ValueError) as ctx:
            link_contributor(account, existing_pk=9**99)
        self.assertIn("no longer exists", str(ctx.exception))


class TestLinkContributorRace(TestCase):
    """A concurrent double-submit races link_contributor's unique-column writes.

    `link_contributor` does an unlocked read-then-write, so two submits can
    both pass the read and then collide on the write - `ContentContributor`
    raises IntegrityError on the losing `create()`. These tests force that
    exact failure with a mock (real cross-transaction concurrency is not
    reproducible synchronously) and check the two outcomes: the racing write
    already linked this same account (idempotent success), or it linked a
    name to someone else (a coherent ValueError, not a raw IntegrityError).
    """

    def test_integrity_error_with_user_already_linked_is_idempotent(self) -> None:
        account = _make_account("racewinner")
        racer_contributor = ContentContributorFactory(name="Racer Won")
        PlayerData.objects.create(account=account, contributor=racer_contributor)

        with patch(_CREATE_PATH, side_effect=IntegrityError("duplicate key value")):
            contributor = link_contributor(account, name="Never Created")

        self.assertEqual(contributor, racer_contributor)
        self.assertEqual(current_contributor(account), racer_contributor)
        self.assertFalse(ContentContributor.objects.filter(name="Never Created").exists())

    def test_integrity_error_claimed_elsewhere_raises_coherent_value_error(self) -> None:
        account = _make_account("raceloser")

        with patch(_CREATE_PATH, side_effect=IntegrityError("duplicate key value")):
            with self.assertRaises(ValueError) as ctx:
                link_contributor(account, name="Claimed By Another")

        self.assertIn("claimed", str(ctx.exception).lower())
        self.assertIsNone(current_contributor(account))


class TestAuthoringDashboardSetupGate(TestCase):
    def test_unlinked_superuser_gets_setup_panel_instead_of_dashboard(self) -> None:
        account = _make_account("gateunlinked")
        self.client.force_login(account)

        resp = self.client.get(reverse("admin_authoring"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-authoring-setup"', body)
        self.assertIn("Set up your author credit.", body)
        self.assertNotIn('id="panel-authoring-stats"', body)
        self.assertNotIn('id="panel-authoring-queue"', body)

    def test_linked_superuser_gets_normal_dashboard(self) -> None:
        account = _make_account("gatelinked")
        contributor = ContentContributorFactory(name="Gate Linked Writer")
        PlayerData.objects.create(account=account, contributor=contributor)
        self.client.force_login(account)

        resp = self.client.get(reverse("admin_authoring"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-authoring-stats"', body)
        self.assertIn('id="panel-authoring-queue"', body)
        self.assertNotIn('id="panel-authoring-setup"', body)


class TestAuthoringSetupView(TestCase):
    def test_get_not_allowed(self) -> None:
        account = _make_account("setupget")
        self.client.force_login(account)
        resp = self.client.get(reverse("admin_authoring_setup"))
        self.assertEqual(resp.status_code, 405)

    def test_happy_path_creates_links_and_redirects_to_normal_dashboard(self) -> None:
        account = _make_account("setuphappy")
        self.client.force_login(account)

        resp = self.client.post(reverse("admin_authoring_setup"), {"name": "Setup Happy"})

        self.assertRedirects(resp, reverse("admin_authoring"))
        contributor = ContentContributor.objects.get(name="Setup Happy")
        self.assertEqual(current_contributor(account), contributor)

        dashboard = self.client.get(reverse("admin_authoring"))
        body = dashboard.content.decode()
        self.assertIn('id="panel-authoring-stats"', body)

    def test_picking_existing_unlinked_contributor(self) -> None:
        account = _make_account("setuppick")
        existing = ContentContributorFactory(name="Setup Pick Target")
        self.client.force_login(account)

        self.client.post(reverse("admin_authoring_setup"), {"existing_pk": str(existing.pk)})

        self.assertEqual(current_contributor(account), existing)

    def test_blank_name_flashes_error_and_does_not_link(self) -> None:
        account = _make_account("setupblank")
        self.client.force_login(account)

        resp = self.client.post(reverse("admin_authoring_setup"), {"name": "  "}, follow=True)

        self.assertIsNone(current_contributor(account))
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("name" in m.lower() for m in messages))

    def test_second_post_when_already_linked_is_noop_flash(self) -> None:
        account = _make_account("setuptwice")
        contributor = ContentContributorFactory(name="Already Linked")
        PlayerData.objects.create(account=account, contributor=contributor)
        self.client.force_login(account)

        before_count = ContentContributor.objects.count()
        resp = self.client.post(
            reverse("admin_authoring_setup"), {"name": "Something Else"}, follow=True
        )

        self.assertEqual(ContentContributor.objects.count(), before_count)
        self.assertEqual(current_contributor(account), contributor)
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("already linked" in m.lower() for m in messages))

    def test_absurd_existing_pk_digit_string_redirects_not_500(self) -> None:
        account = _make_account("absurdpkview")
        self.client.force_login(account)

        resp = self.client.post(reverse("admin_authoring_setup"), {"existing_pk": "9" * 40})

        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(current_contributor(account))

    def test_concurrent_race_claimed_elsewhere_flashes_coherent_error_not_500(self) -> None:
        account = _make_account("viewraceloser")
        self.client.force_login(account)

        with patch(_CREATE_PATH, side_effect=IntegrityError("duplicate key value")):
            resp = self.client.post(
                reverse("admin_authoring_setup"),
                {"name": "Claimed Elsewhere"},
                follow=True,
            )

        self.assertEqual(resp.redirect_chain[-1], (reverse("admin_authoring"), 302))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(current_contributor(account))
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("claimed" in m.lower() for m in messages))

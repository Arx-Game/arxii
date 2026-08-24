"""Tests for the Arx I archive forward_auth endpoint (#3320, ADR-0232)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.gm.factories import GMProfileFactory
from world.roster.factories import PlayerDataFactory


class Arx1ArchiveAuthorizeTests(TestCase):
    """Caddy's authorization subrequest: who gets 200, 403, or the login page."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("api-arx1-archive-authorize")
        cls.plain = PlayerDataFactory()
        cls.granted = PlayerDataFactory(arx1_archive_access=True)
        cls.staff = AccountFactory(username="archive_staff", is_staff=True)
        cls.gm_profile = GMProfileFactory(
            account=AccountFactory(username="archive_gm"),
        )

    def test_anonymous_is_redirected_to_login(self) -> None:
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.headers["Location"], "/login?next=%2Farxmush-archive%2F")

    def test_anonymous_redirect_preserves_the_requested_page(self) -> None:
        """forward_auth passes the original path as X-Forwarded-Uri."""
        response = self.client.get(
            self.url,
            headers={"x-forwarded-uri": "/arxmush-archive/lore/clues/"},
        )

        self.assertEqual(
            response.headers["Location"],
            "/login?next=%2Farxmush-archive%2Flore%2Fclues%2F",
        )

    def test_offsite_forwarded_uri_falls_back_to_the_archive_index(self) -> None:
        """A spoofed header must not turn our login link into an open redirect."""
        for hostile in ("//evil.example/phish", "https://evil.example/phish"):
            with self.subTest(hostile=hostile):
                response = self.client.get(
                    self.url,
                    headers={"x-forwarded-uri": hostile},
                )

                self.assertEqual(
                    response.headers["Location"],
                    "/login?next=%2Farxmush-archive%2F",
                )

    def test_authenticated_without_a_grant_is_forbidden(self) -> None:
        """Registering for an Arx II account is not itself archive access."""
        self.client.force_login(self.plain.account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_granted_account_is_allowed(self) -> None:
        self.client.force_login(self.granted.account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_is_allowed_without_the_flag(self) -> None:
        self.client.force_login(self.staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gm_is_allowed_without_the_flag(self) -> None:
        """A GMProfile IS the GM identity, so it needs no second per-account tick."""
        self.client.force_login(self.gm_profile.account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_account_with_no_player_data_is_forbidden_and_writes_nothing(self) -> None:
        """An authorization check must never create the row it reads."""
        account = AccountFactory(username="archive_no_player_data")
        self.client.force_login(account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # hasattr() would be useless here - the Account typeclass shadows the
        # reverse accessor with a get_or_create property, so it is always True
        # and asking CREATES the row. Check the table instead.
        self.assertFalse(PlayerData.objects.filter(pk=account.pk).exists())

    def test_flag_defaults_to_false(self) -> None:
        self.assertFalse(PlayerDataFactory().arx1_archive_access)

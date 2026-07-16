"""Rivalry-declaration API (#2170) — the web face of declare/undeclare rival."""

from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.scenes.models import Rivalry


class RivalryApiTests(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.player = PlayerDataFactory(account=self.account)
        self.my_tenure = RosterTenureFactory(player_data=self.player)
        self.target_tenure = RosterTenureFactory()
        self.client.force_authenticate(user=self.account)

    def test_declare_lists_and_withdraw(self) -> None:
        # Declare.
        res = self.client.post(
            reverse("rival-list"),
            {
                "viewer": self.my_tenure.roster_entry.pk,
                "rival": self.target_tenure.roster_entry.pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.data["is_mutual"])
        rivalry = Rivalry.objects.get(rivaler_tenure=self.my_tenure)

        # List (only mine), with entry pks for client-side matching.
        rows = self.client.get(reverse("rival-list")).data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rivaler_entry"], self.my_tenure.roster_entry.pk)
        self.assertEqual(rows[0]["rival_entry"], self.target_tenure.roster_entry.pk)
        self.assertFalse(rows[0]["is_mutual"])

        # Withdraw.
        res = self.client.delete(reverse("rival-detail", args=[rivalry.pk]))
        self.assertIn(res.status_code, (200, 204))
        self.assertFalse(Rivalry.objects.exists())

    def test_mutual_once_both_sides_declare(self) -> None:
        # The target has already declared me — my declaration completes the double opt-in.
        Rivalry.objects.create(rivaler_tenure=self.target_tenure, rival_tenure=self.my_tenure)
        res = self.client.post(
            reverse("rival-list"),
            {
                "viewer": self.my_tenure.roster_entry.pk,
                "rival": self.target_tenure.roster_entry.pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["is_mutual"])
        rows = self.client.get(reverse("rival-list")).data["results"]
        self.assertTrue(rows[0]["is_mutual"])

    def test_cannot_declare_as_someone_elses_character(self) -> None:
        other_tenure = RosterTenureFactory()  # not owned by self.account
        res = self.client.post(
            reverse("rival-list"),
            {"viewer": other_tenure.roster_entry.pk, "rival": self.target_tenure.roster_entry.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_cannot_declare_self(self) -> None:
        res = self.client.post(
            reverse("rival-list"),
            {"viewer": self.my_tenure.roster_entry.pk, "rival": self.my_tenure.roster_entry.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_list_excludes_other_players_rivalries(self) -> None:
        other_player = PlayerDataFactory(account=AccountFactory())
        other_rivaler = RosterTenureFactory(player_data=other_player)
        Rivalry.objects.create(rivaler_tenure=other_rivaler, rival_tenure=self.target_tenure)
        self.assertEqual(self.client.get(reverse("rival-list")).data["results"], [])

    def test_cannot_delete_another_players_declaration(self) -> None:
        other_player = PlayerDataFactory(account=AccountFactory())
        other_rivaler = RosterTenureFactory(player_data=other_player)
        rivalry = Rivalry.objects.create(
            rivaler_tenure=other_rivaler, rival_tenure=self.target_tenure
        )
        res = self.client.delete(reverse("rival-detail", args=[rivalry.pk]))
        self.assertEqual(res.status_code, 404)
        self.assertTrue(Rivalry.objects.filter(pk=rivalry.pk).exists())

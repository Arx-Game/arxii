"""OOC friends-list API (#1727)."""

from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.scenes.models import Friendship


class FriendApiTests(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.player = PlayerDataFactory(account=self.account)
        self.my_tenure = RosterTenureFactory(player_data=self.player)
        self.target_tenure = RosterTenureFactory()
        self.client.force_authenticate(user=self.account)

    def test_create_lists_and_delete(self) -> None:
        # Add.
        res = self.client.post(
            reverse("friend-list"),
            {
                "viewer": self.my_tenure.roster_entry.pk,
                "friend": self.target_tenure.roster_entry.pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        friendship = Friendship.objects.get(friender_tenure=self.my_tenure)

        # List (only mine).
        rows = self.client.get(reverse("friend-list")).data["results"]
        self.assertEqual(len(rows), 1)

        # Remove.
        res = self.client.delete(reverse("friend-detail", args=[friendship.pk]))
        self.assertIn(res.status_code, (200, 204))
        self.assertFalse(Friendship.objects.exists())

    def test_cannot_friend_as_someone_elses_character(self) -> None:
        other_tenure = RosterTenureFactory()  # not owned by self.account
        res = self.client.post(
            reverse("friend-list"),
            {"viewer": other_tenure.roster_entry.pk, "friend": self.target_tenure.roster_entry.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_list_excludes_other_players_friendships(self) -> None:
        # Another player's friendship must not appear in my list.
        other_player = PlayerDataFactory(account=AccountFactory())
        other_friender = RosterTenureFactory(player_data=other_player)
        Friendship.objects.create(friender_tenure=other_friender, friend_tenure=self.target_tenure)
        self.assertEqual(self.client.get(reverse("friend-list")).data["results"], [])

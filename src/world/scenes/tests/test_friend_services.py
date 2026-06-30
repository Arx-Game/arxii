"""OOC friends-list services — symmetric tenure scoping (#1727)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterTenureFactory
from world.scenes.friend_services import (
    add_friend,
    add_friend_all_characters,
    is_friend,
    remove_friend,
)
from world.scenes.models import Friendship


class FriendServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        account = AccountFactory()
        cls.player, _ = PlayerData.objects.get_or_create(account=account)
        cls.owner_tenure = RosterTenureFactory(player_data=cls.player)
        cls.friend_tenure = RosterTenureFactory()

    def test_add_and_is_friend(self) -> None:
        add_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        self.assertTrue(is_friend(owner_tenure=self.owner_tenure, friend_tenure=self.friend_tenure))

    def test_is_friend_false_when_unfriended(self) -> None:
        self.assertFalse(
            is_friend(owner_tenure=self.owner_tenure, friend_tenure=RosterTenureFactory())
        )

    def test_add_is_idempotent(self) -> None:
        add_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        add_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        self.assertEqual(Friendship.objects.filter(friender_tenure=self.owner_tenure).count(), 1)

    def test_alt_privacy_one_character_does_not_friend_another(self) -> None:
        # Same player, two characters. Friending from one does NOT friend from the other.
        other_char = RosterTenureFactory(player_data=self.player)
        add_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        self.assertFalse(is_friend(owner_tenure=other_char, friend_tenure=self.friend_tenure))

    def test_remove_is_per_character(self) -> None:
        other_char = RosterTenureFactory(player_data=self.player)
        add_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        add_friend(friender_tenure=other_char, friend_tenure=self.friend_tenure)
        remove_friend(friender_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        self.assertFalse(
            is_friend(owner_tenure=self.owner_tenure, friend_tenure=self.friend_tenure)
        )
        self.assertTrue(is_friend(owner_tenure=other_char, friend_tenure=self.friend_tenure))

    def test_add_all_characters_fans_out_over_active_tenures(self) -> None:
        RosterTenureFactory(player_data=self.player)  # a 2nd active character
        touched = add_friend_all_characters(
            player_data=self.player, friend_tenure=self.friend_tenure
        )
        self.assertEqual(touched, 2)
        self.assertEqual(Friendship.objects.filter(friend_tenure=self.friend_tenure).count(), 2)

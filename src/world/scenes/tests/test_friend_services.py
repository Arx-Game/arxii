"""OOC friends-list services — symmetric tenure scoping (#1727)."""

from django.core.exceptions import ValidationError
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
from world.scenes.models import Block, Friendship


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


class FriendBlockGateTests(TestCase):
    """#2996 Decision 2 — an account-level block prevents adding a friend, both paths."""

    @classmethod
    def setUpTestData(cls) -> None:
        friender_account = AccountFactory()
        cls.friender_player, _ = PlayerData.objects.get_or_create(account=friender_account)
        cls.friender_tenure = RosterTenureFactory(player_data=cls.friender_player)

        target_account = AccountFactory()
        cls.target_player, _ = PlayerData.objects.get_or_create(account=target_account)
        cls.target_tenure = RosterTenureFactory(player_data=cls.target_player)

        Block.objects.create(
            owner=cls.friender_player, blocked_player=cls.target_player, account_level=True
        )

    def test_add_friend_rejects_a_blocked_pair(self) -> None:
        with self.assertRaises(ValidationError):
            add_friend(friender_tenure=self.friender_tenure, friend_tenure=self.target_tenure)
        self.assertFalse(Friendship.objects.exists())

    def test_add_friend_rejects_the_reverse_direction_too(self) -> None:
        """Block is symmetric — being the blocked side also blocks the add."""
        with self.assertRaises(ValidationError):
            add_friend(friender_tenure=self.target_tenure, friend_tenure=self.friender_tenure)
        self.assertFalse(Friendship.objects.exists())

    def test_add_friend_all_characters_rejects_a_blocked_pair(self) -> None:
        RosterTenureFactory(player_data=self.friender_player)  # a 2nd active character
        with self.assertRaises(ValidationError):
            add_friend_all_characters(
                player_data=self.friender_player, friend_tenure=self.target_tenure
            )
        self.assertFalse(Friendship.objects.exists())

    def test_unblocked_pair_still_friends_normally(self) -> None:
        stranger_tenure = RosterTenureFactory()
        add_friend(friender_tenure=self.friender_tenure, friend_tenure=stranger_tenure)
        self.assertTrue(is_friend(owner_tenure=self.friender_tenure, friend_tenure=stranger_tenure))


class WatchListNotifyTests(TestCase):
    def test_no_friends_is_a_silent_noop(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory
        from world.scenes.friend_services import notify_friends_of_status

        sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry)
        notify_friends_of_status(sheet.character, online=True)  # must not raise

    def test_online_friender_gets_an_alert(self) -> None:
        from unittest.mock import MagicMock

        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory
        from world.scenes.friend_services import add_friend, notify_friends_of_status

        # The friended character + its active tenure.
        friended_sheet = CharacterSheetFactory()
        friended_entry = RosterEntryFactory(character_sheet=friended_sheet)
        friended_tenure = RosterTenureFactory(roster_entry=friended_entry)

        # A player who friended that character and is online.
        account = AccountFactory()
        player, _ = PlayerData.objects.get_or_create(account=account)
        friender_tenure = RosterTenureFactory(player_data=player)
        add_friend(friender_tenure=friender_tenure, friend_tenure=friended_tenure)

        account.msg = MagicMock()

        notify_friends_of_status(friended_sheet.character, online=True)
        account.msg.assert_called_once()
        self.assertIn("come online", account.msg.call_args.args[0])

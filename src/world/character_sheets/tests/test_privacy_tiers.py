"""Player-controlled section visibility tiers (#1271).

Each mechanical sheet section (stats/skills/magic/goals) carries a SELF/FRIENDS/PUBLIC tier.
SELF is the default (owner + staff only — the #1269 behaviour); a player can open a section to
their allow list (FRIENDS) or to everyone (PUBLIC).
"""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerAllowList, PlayerData
from world.character_sheets.types import SheetVisibility
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory


class PrivacyTierTests(APITestCase):
    def _sheet_with_stat(self, account, *, stats_visibility=SheetVisibility.SELF):
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        sheet = roster_entry.character_sheet
        sheet.stats_visibility = stats_visibility
        sheet.save()
        CharacterTraitValueFactory(
            character=sheet, trait=StatTraitFactory(name="strength"), value=5
        )
        return sheet

    def _player(self, account):
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=RosterEntryFactory())
        return player_data

    def _stats(self, sheet, viewer):
        self.client.force_authenticate(user=viewer)
        return self.client.get(f"/api/character-sheets/{sheet.pk}/").data["stats"]

    def test_self_tier_hides_stats_from_a_non_owner(self) -> None:
        sheet = self._sheet_with_stat(AccountFactory())  # default SELF
        viewer = AccountFactory()
        self._player(viewer)
        assert self._stats(sheet, viewer) == {}

    def test_public_tier_shows_stats_to_anyone(self) -> None:
        sheet = self._sheet_with_stat(AccountFactory(), stats_visibility=SheetVisibility.PUBLIC)
        viewer = AccountFactory()
        self._player(viewer)
        assert self._stats(sheet, viewer) == {"strength": 5}

    def test_friends_tier_shows_only_to_the_owners_allow_list(self) -> None:
        owner = AccountFactory()
        sheet = self._sheet_with_stat(owner, stats_visibility=SheetVisibility.FRIENDS)
        owner_pd = PlayerData.objects.get(account=owner)

        friend = AccountFactory()
        friend_pd = self._player(friend)
        PlayerAllowList.objects.create(owner=owner_pd, allowed_player=friend_pd)

        stranger = AccountFactory()
        self._player(stranger)

        assert self._stats(sheet, friend) == {"strength": 5}  # on the allow list
        assert self._stats(sheet, stranger) == {}  # not on the allow list

    def test_owner_and_staff_always_see_regardless_of_tier(self) -> None:
        owner = AccountFactory()
        sheet = self._sheet_with_stat(owner)  # SELF
        staff = AccountFactory(is_staff=True)
        assert self._stats(sheet, owner) == {"strength": 5}
        assert self._stats(sheet, staff) == {"strength": 5}

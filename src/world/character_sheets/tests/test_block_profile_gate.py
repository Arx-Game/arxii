"""Block hides a character's sheet from the blocked viewer (#1278, slice 2).

A blocked viewer gets a 404 — the character "might as well not exist" — never a banner. The gate
is anti-derivation-safe: only the *exact* blocked character's sheet is hidden, never the player's
other characters. Staff bypass.
"""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.models import Block


class BlockProfileGateTests(APITestCase):
    def _played_sheet(self, account):
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        return roster_entry.character_sheet, player_data

    def _status(self, sheet, viewer):
        self.client.force_authenticate(user=viewer)
        return self.client.get(f"/api/character-sheets/{sheet.pk}/").status_code

    def setUp(self) -> None:
        self.blocker_acct = AccountFactory()
        self.target_acct = AccountFactory()
        self.blocker_sheet, self.blocker_pd = self._played_sheet(self.blocker_acct)
        self.target_sheet, self.target_pd = self._played_sheet(self.target_acct)

    def _block(self, **kwargs):
        return Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=self.blocker_sheet.primary_persona,
            blocked_persona=self.target_sheet.primary_persona,
            **kwargs,
        )

    def test_blocker_cannot_see_the_blocked_characters_sheet(self) -> None:
        self._block()
        assert self._status(self.target_sheet, self.blocker_acct) == 404

    def test_blocked_player_cannot_see_the_blockers_sheet(self) -> None:
        # Mutual: the block hides each side from the other.
        self._block()
        assert self._status(self.blocker_sheet, self.target_acct) == 404

    def test_block_does_not_hide_the_players_other_characters(self) -> None:
        # Anti-derivation: only the exact blocked character's sheet is hidden.
        self._block()
        target_alt, _ = self._played_sheet(self.target_acct)
        assert self._status(target_alt, self.blocker_acct) == 200

    def test_account_level_block_hides_all_of_the_blockers_characters(self) -> None:
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=None,
            blocked_persona=self.target_sheet.primary_persona,
            account_level=True,
        )
        blocker_alt, _ = self._played_sheet(self.blocker_acct)
        # The blocked player can't see any of the account-level blocker's characters.
        assert self._status(blocker_alt, self.target_acct) == 404

    def test_unrelated_viewer_and_staff_see_the_sheet(self) -> None:
        self._block()
        stranger = AccountFactory()
        self._played_sheet(stranger)
        assert self._status(self.target_sheet, stranger) == 200
        staff = AccountFactory(is_staff=True)
        assert self._status(self.target_sheet, staff) == 200  # staff bypass

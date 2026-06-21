"""org_join_blocked (#1278): the player-level gate the org/covenant join uses."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.block_services import org_join_blocked
from world.scenes.models import Block


class OrgJoinBlockedTests(TestCase):
    def _played(self, account):
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        return entry.character_sheet, player_data

    def setUp(self) -> None:
        self.joiner_sheet, self.joiner_pd = self._played(AccountFactory())
        self.member_sheet, self.member_pd = self._played(AccountFactory())

    def _gated(self) -> bool:
        return org_join_blocked(joining_sheet=self.joiner_sheet, member_sheets=[self.member_sheet])

    def test_no_block_does_not_gate(self) -> None:
        assert self._gated() is False

    def test_member_blocked_the_joiner_gates(self) -> None:
        Block.objects.create(
            owner=self.member_pd,
            blocked_player=self.joiner_pd,
            blocker_persona=self.member_sheet.primary_persona,
            blocked_persona=self.joiner_sheet.primary_persona,
        )
        assert self._gated() is True

    def test_joiner_blocked_a_member_also_gates(self) -> None:
        # Mutual: either direction keeps them out of the same org.
        Block.objects.create(
            owner=self.joiner_pd,
            blocked_player=self.member_pd,
            blocker_persona=self.joiner_sheet.primary_persona,
            blocked_persona=self.member_sheet.primary_persona,
        )
        assert self._gated() is True

    def test_block_with_an_unrelated_player_does_not_gate(self) -> None:
        other_sheet, other_pd = self._played(AccountFactory())
        Block.objects.create(
            owner=other_pd,
            blocked_player=self.joiner_pd,
            blocker_persona=other_sheet.primary_persona,
            blocked_persona=self.joiner_sheet.primary_persona,
        )
        # other is not a member of this org → no gate.
        assert self._gated() is False

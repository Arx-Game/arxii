"""Blocked-player contact attempts are flagged for staff (#1278).

The coded block stops the exact pair; a blocked player reaching the blocker via *another* identity
is circumvention — not code-prevented (anti-derivation), but recorded here for staff review.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.block_services import flag_blocked_contact_attempt
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block, BlockContactFlag


class BlockContactFlagTests(TestCase):
    def _side(self):
        account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        sheet = entry.character_sheet
        return account, player_data, sheet, sheet.primary_persona

    def setUp(self) -> None:
        self.blocker_acct, self.blocker_pd, self.blocker_sheet, self.blocker_face = self._side()
        self.blocked_acct, self.blocked_pd, self.blocked_sheet, self.blocked_face = self._side()
        self.blocked_alt = PersonaFactory(character_sheet=self.blocked_sheet, name="Sneaky Alt")
        # The blocker blocked the blocked player's main face.
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.blocked_pd,
            blocker_persona=self.blocker_face,
            blocked_persona=self.blocked_face,
        )

    def test_blocked_player_reaching_the_blocker_via_an_alt_is_flagged(self) -> None:
        flag = flag_blocked_contact_attempt(
            initiator_persona=self.blocked_alt, target_persona=self.blocker_face
        )
        assert flag is not None
        assert flag.blocked_account_id == self.blocked_acct.pk
        assert flag.blocker_account_id == self.blocker_acct.pk
        assert flag.initiator_persona_id == self.blocked_alt.pk

    def test_no_block_means_no_flag(self) -> None:
        _, _, _, stranger_face = self._side()
        assert (
            flag_blocked_contact_attempt(
                initiator_persona=stranger_face, target_persona=self.blocker_face
            )
            is None
        )

    def test_blocker_reaching_the_blocked_is_not_flagged(self) -> None:
        # The flag is for the blocked player's circumvention, not the blocker's own outreach.
        assert (
            flag_blocked_contact_attempt(
                initiator_persona=self.blocker_face, target_persona=self.blocked_alt
            )
            is None
        )

    def test_repeated_attempts_in_a_scene_dedupe_to_one_flag(self) -> None:
        flag_blocked_contact_attempt(
            initiator_persona=self.blocked_alt, target_persona=self.blocker_face
        )
        flag_blocked_contact_attempt(
            initiator_persona=self.blocked_face, target_persona=self.blocker_face
        )
        assert (
            BlockContactFlag.objects.filter(
                blocked_account_id=self.blocked_acct.pk, blocker_account_id=self.blocker_acct.pk
            ).count()
            == 1
        )

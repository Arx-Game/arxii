"""Block toggle services (#1278): create-with-reason, cron-delayed unblock, account-wide share."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.block_services import (
    create_block,
    request_unblock,
    share_block_account_wide,
)
from world.scenes.models import Block


class BlockToggleServiceTests(TestCase):
    def _played(self, account):
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        return entry.character_sheet

    def setUp(self) -> None:
        self.blocker_acct = AccountFactory()
        self.blocker_sheet = self._played(self.blocker_acct)
        self.target_sheet = self._played(AccountFactory())

    def _create(self, reason="They were cruel."):
        return create_block(
            blocker_account=self.blocker_acct,
            blocker_persona=self.blocker_sheet.primary_persona,
            blocked_persona=self.target_sheet.primary_persona,
            reason=reason,
        )

    def test_create_block_records_the_pair_and_reason(self) -> None:
        block = self._create()
        assert block.blocker_persona_id == self.blocker_sheet.primary_persona.pk
        assert block.blocked_persona_id == self.target_sheet.primary_persona.pk
        assert block.reason == "They were cruel."
        assert block.account_level is False

    def test_create_block_is_idempotent_per_pair(self) -> None:
        self._create()
        self._create(reason="again")
        assert Block.objects.filter(owner__account=self.blocker_acct).count() == 1

    def test_cannot_block_your_own_character(self) -> None:
        with self.assertRaises(ValidationError):
            create_block(
                blocker_account=self.blocker_acct,
                blocker_persona=self.blocker_sheet.primary_persona,
                blocked_persona=self.blocker_sheet.primary_persona,
                reason="x",
            )

    def test_request_unblock_delays_via_pending_removal(self) -> None:
        block = self._create()
        request_unblock(block)
        block.refresh_from_db()
        # Still active (in the grace window), with a future finalize time.
        assert block.pending_removal_at is not None
        assert block.pending_removal_at > timezone.now()
        assert block.is_active is True

    def test_reblocking_during_grace_cancels_the_pending_removal(self) -> None:
        block = self._create()
        request_unblock(block)
        reblocked = self._create()
        assert reblocked.pk == block.pk
        assert reblocked.pending_removal_at is None

    def test_share_block_account_wide_sets_account_level(self) -> None:
        block = self._create()
        share_block_account_wide(block)
        block.refresh_from_db()
        assert block.account_level is True

"""Covenant treasury (#2992): deposit open to members, withdrawal rank-gated."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.covenants.constants import MembershipStanding
from world.covenants.exceptions import (
    CovenantTreasuryTransferError,
    NotAnActiveCovenantMemberError,
    NotAuthorizedToSpendCovenantTreasuryError,
)
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRankFactory
from world.covenants.treasury import (
    covenant_treasury,
    deposit_covenant_funds,
    withdraw_covenant_funds,
)
from world.currency.models import CurrencyTransfer
from world.currency.services import get_or_create_purse


class CovenantTreasuryTests(TestCase):
    def test_deposit_moves_purse_to_treasury_with_audit_row(self) -> None:
        membership = CharacterCovenantRoleFactory()
        purse = get_or_create_purse(membership.character_sheet)
        purse.balance = 100
        purse.save(update_fields=["balance"])

        transfer = deposit_covenant_funds(membership=membership, amount=50)

        treasury = covenant_treasury(membership.covenant)
        self.assertEqual(treasury.balance, 50)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 50)
        self.assertTrue(
            CurrencyTransfer.objects.filter(
                pk=transfer.pk, from_purse=purse, to_treasury=treasury, amount=50
            ).exists()
        )

    def test_minor_member_may_deposit(self) -> None:
        membership = CharacterCovenantRoleFactory(standing=MembershipStanding.MINOR)
        purse = get_or_create_purse(membership.character_sheet)
        purse.balance = 100
        purse.save(update_fields=["balance"])

        deposit_covenant_funds(membership=membership, amount=30)

        treasury = covenant_treasury(membership.covenant)
        self.assertEqual(treasury.balance, 30)

    def test_withdraw_requires_spend_rank(self) -> None:
        base_rank = CovenantRankFactory(tier=2)
        member = CharacterCovenantRoleFactory(covenant=base_rank.covenant, rank=base_rank)
        treasury = covenant_treasury(member.covenant)
        treasury.balance = 1000
        treasury.save(update_fields=["balance"])

        with self.assertRaises(NotAuthorizedToSpendCovenantTreasuryError):
            withdraw_covenant_funds(membership=member, amount=100)

        founder_rank = CovenantRankFactory(covenant=member.covenant, tier=1)
        founder = CharacterCovenantRoleFactory(covenant=member.covenant, rank=founder_rank)
        withdraw_covenant_funds(membership=founder, amount=100)

        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 900)
        purse = get_or_create_purse(founder.character_sheet)
        self.assertEqual(purse.balance, 100)

    def test_departed_member_cannot_deposit_or_withdraw(self) -> None:
        membership = CharacterCovenantRoleFactory(left_at=timezone.now())

        with self.assertRaises(NotAnActiveCovenantMemberError):
            deposit_covenant_funds(membership=membership, amount=10)
        with self.assertRaises(NotAnActiveCovenantMemberError):
            withdraw_covenant_funds(membership=membership, amount=10)

    def test_insufficient_funds_maps_to_covenant_error(self) -> None:
        top_rank = CovenantRankFactory(tier=1)
        member = CharacterCovenantRoleFactory(covenant=top_rank.covenant, rank=top_rank)

        with self.assertRaises(CovenantTreasuryTransferError) as ctx:
            withdraw_covenant_funds(membership=member, amount=100)
        self.assertEqual(
            ctx.exception.user_message,
            "The covenant treasury transfer could not be completed.",
        )

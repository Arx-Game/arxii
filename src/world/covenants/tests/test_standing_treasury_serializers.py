"""Tests for #2992's serializer additions: ``standing`` on membership rows and
member-gated ``treasury_balance`` on the covenant detail payload.

Avoids ``CovenantSerializer(...).data`` (full serialization triggers
``get_legend_total`` -> a Postgres-only materialized view, #758) — instead calls
``get_treasury_balance`` directly, mirroring the SQLite-safety pattern in
``test_covenant_serializer_battle_fields.py``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import MembershipStanding
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantFactory
from world.covenants.serializers import CharacterCovenantRoleSerializer, CovenantSerializer
from world.covenants.treasury import covenant_treasury
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class StandingFieldTests(TestCase):
    """CharacterCovenantRoleSerializer exposes the durable ``standing`` tier (#2992)."""

    def test_core_standing_is_default(self) -> None:
        membership = CharacterCovenantRoleFactory()
        data = CharacterCovenantRoleSerializer(membership).data
        self.assertEqual(data["standing"], MembershipStanding.CORE)

    def test_minor_standing_serializes(self) -> None:
        # CovenantFactory defaults covenant_type to DURANCE — the only type
        # MembershipStanding.MINOR is valid for (CharacterCovenantRole.clean()).
        covenant = CovenantFactory()
        membership = CharacterCovenantRoleFactory(
            covenant=covenant, standing=MembershipStanding.MINOR
        )
        data = CharacterCovenantRoleSerializer(membership).data
        self.assertEqual(data["standing"], MembershipStanding.MINOR)


class TreasuryBalanceFieldTests(TestCase):
    """CovenantSerializer.get_treasury_balance: int for members, null otherwise (#2992)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory()
        cls.member_account = AccountFactory()
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        player_data = PlayerDataFactory(account=cls.member_account)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=player_data,
            end_date=None,
        )
        cls.membership = CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cls.covenant)
        cls.non_member_account = AccountFactory()

    def _request_for(self, account):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = account
        return request

    def test_member_sees_integer_balance(self) -> None:
        treasury = covenant_treasury(self.covenant)
        treasury.balance = 250
        treasury.save(update_fields=["balance"])

        serializer = CovenantSerializer(context={"request": self._request_for(self.member_account)})
        self.assertEqual(serializer.get_treasury_balance(self.covenant), 250)

    def test_non_member_sees_null(self) -> None:
        treasury = covenant_treasury(self.covenant)
        treasury.balance = 250
        treasury.save(update_fields=["balance"])

        serializer = CovenantSerializer(
            context={"request": self._request_for(self.non_member_account)}
        )
        self.assertIsNone(serializer.get_treasury_balance(self.covenant))

    def test_unauthenticated_viewer_sees_null(self) -> None:
        factory = APIRequestFactory()
        request = factory.get("/")

        class _Anon:
            is_authenticated = False

        request.user = _Anon()
        serializer = CovenantSerializer(context={"request": request})
        self.assertIsNone(serializer.get_treasury_balance(self.covenant))

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


class TreasuryBalanceBatchListTests(TestCase):
    """List-view treasury_balance batching (2026-08 review fix on #2992).

    ``CovenantViewSet.list()`` must bulk-fetch treasury balances in one query
    (mirroring the existing ``_covenant_aggregates`` member_count/legend_total
    pattern) rather than calling ``covenant_treasury()`` — an
    ``OrganizationTreasury.objects.get_or_create`` — once per row.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member_account = AccountFactory()
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        player_data = PlayerDataFactory(account=cls.member_account)
        RosterTenureFactory(roster_entry=roster_entry, player_data=player_data, end_date=None)

        cls.covenant_with_balance = CovenantFactory()
        cls.membership_a = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cls.covenant_with_balance
        )
        treasury = covenant_treasury(cls.covenant_with_balance)
        treasury.balance = 250
        treasury.save(update_fields=["balance"])

        # A member covenant that has never received a deposit — no
        # OrganizationTreasury row exists for it yet.
        cls.covenant_no_treasury_row = CovenantFactory()
        cls.membership_b = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cls.covenant_no_treasury_row
        )

        cls.covenant_non_member = CovenantFactory()

    def _request_for(self, account):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = account
        return request

    def test_covenant_treasury_balances_bulk_fetch_is_one_query(self) -> None:
        from world.covenants.views import CovenantViewSet

        covenants = [
            self.covenant_with_balance,
            self.covenant_no_treasury_row,
            self.covenant_non_member,
        ]
        with self.assertNumQueries(1):
            balances = CovenantViewSet._covenant_treasury_balances(covenants)

        self.assertEqual(balances[self.covenant_with_balance.pk], 250)
        self.assertEqual(balances[self.covenant_no_treasury_row.pk], 0)
        self.assertEqual(balances[self.covenant_non_member.pk], 0)

    def test_covenant_treasury_balances_bulk_fetch_creates_no_rows(self) -> None:
        from world.covenants.views import CovenantViewSet
        from world.currency.models import OrganizationTreasury

        CovenantViewSet._covenant_treasury_balances(
            [self.covenant_no_treasury_row, self.covenant_non_member]
        )

        self.assertFalse(
            OrganizationTreasury.objects.filter(
                organization=self.covenant_no_treasury_row.organization
            ).exists()
        )
        self.assertFalse(
            OrganizationTreasury.objects.filter(
                organization=self.covenant_non_member.organization
            ).exists()
        )

    def test_list_serialization_reads_batch_map_without_per_row_get_or_create(self) -> None:
        """3 covenants, viewer member of 2 (one with a balance, one without a
        treasury row yet), one non-member — bounded query count, no per-row
        ``covenant_treasury()`` (get_or_create) call, no row created for the
        member covenant with no treasury yet."""
        from world.covenants.views import CovenantViewSet
        from world.currency.models import OrganizationTreasury

        covenants = [
            self.covenant_with_balance,
            self.covenant_no_treasury_row,
            self.covenant_non_member,
        ]
        balances = CovenantViewSet._covenant_treasury_balances(covenants)

        context = {
            "request": self._request_for(self.member_account),
            "covenant_treasury_balances": balances,
        }
        serializer = CovenantSerializer(context=context)

        # One query per covenant to memoize its viewer-membership lookup
        # (_resolve_viewer_membership), zero additional queries for treasury —
        # the whole point of threading the batch map through.
        with self.assertNumQueries(3):
            result_with_balance = serializer.get_treasury_balance(self.covenant_with_balance)
            result_no_row = serializer.get_treasury_balance(self.covenant_no_treasury_row)
            result_non_member = serializer.get_treasury_balance(self.covenant_non_member)

        self.assertEqual(result_with_balance, 250)
        self.assertEqual(result_no_row, 0)
        self.assertIsNone(result_non_member)
        self.assertFalse(
            OrganizationTreasury.objects.filter(
                organization=self.covenant_no_treasury_row.organization
            ).exists()
        )

    def test_get_serializer_context_includes_treasury_balances_when_page_precomputed(self) -> None:
        from world.covenants.views import CovenantViewSet

        viewset = CovenantViewSet()
        viewset.request = self._request_for(self.member_account)
        viewset.format_kwarg = None
        viewset._page_treasury_balances = {self.covenant_with_balance.pk: 250}

        context = viewset.get_serializer_context()

        self.assertEqual(
            context["covenant_treasury_balances"], {self.covenant_with_balance.pk: 250}
        )

    def test_get_serializer_context_omits_treasury_balances_outside_list(self) -> None:
        from world.covenants.views import CovenantViewSet

        viewset = CovenantViewSet()
        viewset.request = self._request_for(self.member_account)
        viewset.format_kwarg = None

        context = viewset.get_serializer_context()

        self.assertNotIn("covenant_treasury_balances", context)

    def test_detail_context_still_lazily_creates_treasury_on_first_deposit_path(self) -> None:
        """Outside list context (no batch map), get_treasury_balance falls back to
        the per-object covenant_treasury() (get_or_create) path — legitimate for
        a single detail fetch."""
        from world.currency.models import OrganizationTreasury

        serializer = CovenantSerializer(context={"request": self._request_for(self.member_account)})

        result = serializer.get_treasury_balance(self.covenant_no_treasury_row)

        self.assertEqual(result, 0)
        self.assertTrue(
            OrganizationTreasury.objects.filter(
                organization=self.covenant_no_treasury_row.organization
            ).exists()
        )

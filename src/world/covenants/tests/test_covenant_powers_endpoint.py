"""Tests for GET /api/covenants/covenants/{id}/powers/.

The powers action exposes a covenant's available rites (with per-covenant gate
flags) and per-member role passive powers in one request. It deliberately does
NOT serialize the Covenant via CovenantSerializer (that would touch the
Postgres-only legend materialized view), so these tests run on SQLite.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class CovenantPowersEndpointTestCase(TestCase):
    """Base: an authenticated user with an active membership on a covenant."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        cls.user = AccountDB.objects.create_user(
            username="cov_powers_user",
            email="cov_powers@test.com",
            password="testpass123",
        )

        # Sheet + active tenure for the default user.
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )

        cls.covenant = CovenantFactory(
            name="PowersCov", covenant_type=CovenantType.DURANCE, level=3
        )
        cls.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cls.membership = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.covenant,
            covenant_role=cls.role,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _url(self, pk: int) -> str:
        return f"/api/covenants/covenants/{pk}/powers/"


class PowersRitesTests(CovenantPowersEndpointTestCase):
    """The 'rites' half of the powers payload."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import CovenantRiteFactory

        super().setUpTestData()
        # Gate thresholds chosen so we can assert both flags against the
        # covenant's level (3) and active member count (1).
        # level_met: covenant.level (3) >= 2 → True
        # members_present_met: active_member_count (1) >= 5 → False
        cls.rite = CovenantRiteFactory(
            covenant_type=cls.covenant.covenant_type,
            min_covenant_level=2,
            min_members_present=5,
        )

    def test_powers_returns_rites_with_gate_flags(self) -> None:
        response = self.client.get(self._url(self.covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("rites", response.data)
        rites = response.data["rites"]
        matching = [r for r in rites if r["id"] == self.rite.pk]
        self.assertEqual(len(matching), 1, "Authored rite for the type should appear")
        rite = matching[0]
        self.assertTrue(rite["level_met"])  # level 3 >= min 2
        self.assertFalse(rite["members_present_met"])  # 1 member < min 5
        # Reuses CovenantRiteSerializer fields.
        self.assertIn("min_covenant_level", rite)
        self.assertIn("min_members_present", rite)


class PowersRolePowersTests(TestCase):
    """The 'role_powers' half of the payload — per active membership."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            wire_covenant_role_powers_catalog,
        )
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadFactory
        from world.magic.models import Resonance
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        cls.user = AccountDB.objects.create_user(
            username="cov_rp_user",
            email="cov_rp@test.com",
            password="testpass123",
        )
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )

        # Authored Sword role + two resonances, each with a tier-0 CAPABILITY_GRANT.
        cls.role, cls.caps = wire_covenant_role_powers_catalog()
        cls.cap_ember = cls.caps[0]
        cls.resonance = Resonance.objects.get(name="Ember Wrath")

        # A BATTLE covenant the role belongs to.
        cls.covenant = CovenantFactory(
            name="RolePowersBattleCov",
            covenant_type=CovenantType.BATTLE,
            battle_binding="standing",
        )
        # Member WITH a woven, engaged role-thread on Ember Wrath.
        cls.membership = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.covenant,
            covenant_role=cls.role,
            engaged=True,
        )
        ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=cls.role,
            level=5,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_powers_returns_member_role_power(self) -> None:
        response = self.client.get(f"/api/covenants/covenants/{self.covenant.pk}/powers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("role_powers", response.data)
        rows = response.data["role_powers"]
        mine = [r for r in rows if r["membership_id"] == self.membership.pk]
        self.assertEqual(len(mine), 1)
        row = mine[0]
        self.assertEqual(row["capability_name"], self.cap_ember.name)
        self.assertEqual(row["resonance_name"], self.resonance.name)
        self.assertTrue(row["engaged"])
        self.assertEqual(row["covenant_role_id"], self.role.pk)
        self.assertEqual(row["character_sheet"], self.sheet.pk)
        self.assertIsNotNone(row["narrative_snippet"])


class PowersMemberWithoutThreadTests(CovenantPowersEndpointTestCase):
    """A member with no role-thread has a null power."""

    def test_powers_member_without_thread_has_null_power(self) -> None:
        response = self.client.get(self._url(self.covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["role_powers"]
        mine = [r for r in rows if r["membership_id"] == self.membership.pk]
        self.assertEqual(len(mine), 1)
        row = mine[0]
        self.assertIsNone(row["capability_name"])
        self.assertIsNone(row["resonance_name"])
        self.assertIsNone(row["narrative_snippet"])
        self.assertEqual(row["covenant_role_id"], self.role.pk)


class PowersAuthAndScopingTests(CovenantPowersEndpointTestCase):
    """Auth + per-user visibility scoping (matches the viewset queryset)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import CovenantFactory

        super().setUpTestData()
        # A covenant the user has NO membership on.
        cls.foreign_covenant = CovenantFactory(name="ForeignPowersCov")

    def test_unauthenticated_denied(self) -> None:
        unauthenticated = APIClient()
        response = unauthenticated.get(self._url(self.covenant.pk))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_non_member_cannot_see_foreign_covenant_powers(self) -> None:
        response = self.client.get(self._url(self.foreign_covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

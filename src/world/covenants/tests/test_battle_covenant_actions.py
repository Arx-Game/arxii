"""Tests for POST /api/covenants/covenants/{id}/stand_down/.

The stand_down action stands a risen STANDING battle covenant back down to
dormant (clearing engagement). It deliberately returns a minimal confirmation
dict rather than serializing the Covenant via CovenantSerializer (which would
touch the Postgres-only legend materialized view), so these tests run on SQLite.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class StandDownActionTestCase(TestCase):
    """Base: an authenticated user with an active membership on a covenant."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import BattleBinding, CovenantType
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
            username="cov_standdown_user",
            email="cov_standdown@test.com",
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

        # A risen (is_dormant=False) STANDING BATTLE covenant the user is in.
        cls.battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.battle_covenant = CovenantFactory(
            name="StandDownBattleCov",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        cls.membership = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.battle_covenant,
            covenant_role=cls.battle_role,
            engaged=True,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _url(self, pk: int) -> str:
        return f"/api/covenants/covenants/{pk}/stand_down/"


class StandDownSuccessTests(StandDownActionTestCase):
    """The happy path: a risen standing battle covenant goes dormant."""

    def test_stand_down_dormantizes_risen_standing_battle_covenant(self) -> None:
        response = self.client.post(self._url(self.battle_covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_dormant"])
        self.assertEqual(response.data["id"], self.battle_covenant.pk)

        # Re-fetch from DB to confirm the flip persisted.
        from world.covenants.models import Covenant

        refreshed = Covenant.objects.get(pk=self.battle_covenant.pk)
        self.assertTrue(refreshed.is_dormant)


class StandDownRejectionTests(StandDownActionTestCase):
    """Domain-guard rejections map to 400 with a detail message."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        super().setUpTestData()

        # A non-battle covenant the same user is also a member of.
        cls.durance_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cls.durance_covenant = CovenantFactory(
            name="StandDownDuranceCov",
            covenant_type=CovenantType.DURANCE,
        )
        CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.durance_covenant,
            covenant_role=cls.durance_role,
        )

    def test_stand_down_rejects_non_battle_covenant(self) -> None:
        response = self.client.post(self._url(self.durance_covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

        # Unchanged: a non-battle covenant cannot be dormant.
        from world.covenants.models import Covenant

        refreshed = Covenant.objects.get(pk=self.durance_covenant.pk)
        self.assertFalse(refreshed.is_dormant)


class StandDownScopingTests(StandDownActionTestCase):
    """Non-members cannot target a covenant they have no membership on (404)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.factories import CovenantFactory

        super().setUpTestData()
        cls.foreign_covenant = CovenantFactory(
            name="ForeignStandDownCov",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )

    def test_stand_down_requires_membership(self) -> None:
        response = self.client.post(self._url(self.foreign_covenant.pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Untouched.
        from world.covenants.models import Covenant

        refreshed = Covenant.objects.get(pk=self.foreign_covenant.pk)
        self.assertFalse(refreshed.is_dormant)

    def test_unauthenticated_denied(self) -> None:
        unauthenticated = APIClient()
        response = unauthenticated.post(self._url(self.battle_covenant.pk))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

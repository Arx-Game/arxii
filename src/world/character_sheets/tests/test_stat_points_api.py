"""Level Stat Point endpoints (#3001) — mirrors the maturation API surface."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.classes.factories import CharacterClassFactory
from world.classes.models import PathStage
from world.classes.services import set_primary_class_level
from world.progression.models import MaturationStatCap
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.factories import StatTraitFactory


class StatPointApiTests(APITestCase):
    def _owned_sheet(self, account, *, level=3):
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, player_number=1)
        sheet = roster_entry.character_sheet
        set_primary_class_level(sheet.character, CharacterClassFactory(), level)
        return sheet

    def test_owner_reads_state_and_spends(self):
        MaturationStatCap.objects.create(path_stage=PathStage.POTENTIAL, stat_cap=6)
        stat = StatTraitFactory(name="stamina_stat_point_api_test")
        owner = AccountFactory()
        sheet = self._owned_sheet(owner, level=3)  # 2 points
        self.client.force_authenticate(user=owner)

        state = self.client.get(f"/api/character-sheets/{sheet.pk}/stat-points/").data
        assert state["available_points"] == 2
        assert state["stat_cap"] == 6
        assert state["level"] == 3

        response = self.client.post(
            f"/api/character-sheets/{sheet.pk}/spend-stat-point/",
            {"trait_id": stat.pk},
            format="json",
        )
        assert response.status_code == 200, (response.status_code, response.data)
        assert response.data["available_points"] == 1

    def test_spend_without_points_is_a_clean_400(self):
        stat = StatTraitFactory(name="stamina_stat_point_api_test_2")
        owner = AccountFactory()
        sheet = self._owned_sheet(owner, level=1)
        self.client.force_authenticate(user=owner)

        response = self.client.post(
            f"/api/character-sheets/{sheet.pk}/spend-stat-point/",
            {"trait_id": stat.pk},
            format="json",
        )
        assert response.status_code == 400, (response.status_code, response.data)
        assert "stat points" in response.data["detail"].lower()

    def test_non_owner_gets_404_from_stat_point_endpoints(self):
        sheet = self._owned_sheet(AccountFactory())
        viewer = AccountFactory()
        self.client.force_authenticate(user=viewer)
        response = self.client.get(f"/api/character-sheets/{sheet.pk}/stat-points/")
        assert response.status_code == 404, response.status_code

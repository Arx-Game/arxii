"""Maturation Point endpoints + age-axis visibility gating (#2756)."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.classes.models import PathStage
from world.progression.models import MaturationStatCap
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.factories import StatTraitFactory


class MaturationApiTests(APITestCase):
    def _owned_sheet(self, account, *, matured=30):
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        # player_number=1 = the original creator — what can_edit_character_sheet gates on.
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, player_number=1)
        sheet = roster_entry.character_sheet
        sheet.matured_years = matured
        sheet.withered_years = 5
        sheet.save()
        return sheet

    def test_owner_reads_maturation_state_and_spends(self):
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5)
        stat = StatTraitFactory(name="stamina_api_test")
        owner = AccountFactory()
        sheet = self._owned_sheet(owner, matured=30)  # 4 milestones
        self.client.force_authenticate(user=owner)

        state = self.client.get(f"/api/character-sheets/{sheet.pk}/maturation/").data
        assert state["available_points"] == 4
        assert state["stat_cap"] == 5

        response = self.client.post(
            f"/api/character-sheets/{sheet.pk}/spend-maturation-point/",
            {"trait_id": stat.pk},
            format="json",
        )
        assert response.status_code == 200, (response.status_code, response.data)
        assert response.data["available_points"] == 3

    def test_spend_without_points_is_a_clean_400(self):
        stat = StatTraitFactory(name="stamina_api_test_2")
        owner = AccountFactory()
        sheet = self._owned_sheet(owner, matured=19)
        self.client.force_authenticate(user=owner)

        response = self.client.post(
            f"/api/character-sheets/{sheet.pk}/spend-maturation-point/",
            {"trait_id": stat.pk},
            format="json",
        )
        assert response.status_code == 400, (response.status_code, response.data)
        assert "maturation" in response.data["detail"].lower()

    def test_non_owner_gets_404_from_maturation_endpoints(self):
        sheet = self._owned_sheet(AccountFactory())
        viewer = AccountFactory()
        PlayerData.objects.get_or_create(account=viewer)
        self.client.force_authenticate(user=viewer)

        assert self.client.get(f"/api/character-sheets/{sheet.pk}/maturation/").status_code == 404

    def test_identity_age_axes_gated_to_owner(self):
        owner = AccountFactory()
        sheet = self._owned_sheet(owner, matured=30)
        viewer = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=viewer)
        RosterTenureFactory(player_data=player_data, roster_entry=RosterEntryFactory())

        self.client.force_authenticate(user=owner)
        identity = self.client.get(f"/api/character-sheets/{sheet.pk}/").data["identity"]
        assert identity["age"] == 35  # apparent = matured 30 + withered 5
        assert identity["biological_age"] == 35
        assert identity["withered_years"] == 5

        self.client.force_authenticate(user=viewer)
        identity = self.client.get(f"/api/character-sheets/{sheet.pk}/").data["identity"]
        assert identity["age"] == 35  # apparent age is public
        assert identity["biological_age"] is None
        assert identity["withered_years"] is None
        assert identity["chronological_age"] is None

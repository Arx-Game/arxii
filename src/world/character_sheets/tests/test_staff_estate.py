"""Staff edit mode, piece D: kinship, estate and reputation on a bare sheet (#4226)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.buildings.constants import ConditionTier
from world.buildings.factories import PropertyGrantProfileFactory
from world.buildings.models import Building, BuildingSizeTier
from world.character_creation.estate_writer import (
    bind_house_claim,
    bind_kinship_node,
    bind_vacancy,
    grant_property,
    grant_residence,
    primary_persona,
    set_organization_reputation,
)
from world.character_creation.sheet_writers import SheetWriteError
from world.locations.models import LocationTenancy
from world.roster.factories import (
    FamilyFactory,
    KinspersonFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import Kinsperson
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.models import OrganizationMembership, OrganizationReputation, Vacancy


class EstateWriterTests(TestCase):
    """Each writer creates what a bare sheet lacks, and a second call adds nothing."""

    @classmethod
    def setUpTestData(cls) -> None:
        BuildingSizeTier.objects.get_or_create(tier=1, defaults={"name": "Hut", "space_budget": 50})
        cls.family = FamilyFactory(name="House Estatewright")

    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet
        self.persona = primary_persona(self.sheet)

    def test_kinship_self_serves_a_node_in_the_family_once(self) -> None:
        node = bind_kinship_node(self.sheet, family=self.family)
        again = bind_kinship_node(self.sheet, family=self.family)
        assert node.pk == again.pk
        assert Kinsperson.objects.filter(sheet=self.sheet, family=self.family).count() == 1

    def test_kinship_claims_an_open_position(self) -> None:
        position = KinspersonFactory(is_appable=True, family=self.family, name="Second son")
        bind_kinship_node(self.sheet, node=position)
        assert Kinsperson.objects.get(pk=position.pk).sheet_id == self.sheet.pk

    def test_a_sheet_in_the_tree_may_not_claim_a_second_position(self) -> None:
        bind_kinship_node(self.sheet, family=self.family)
        position = KinspersonFactory(is_appable=True, family=self.family)
        with self.assertRaises(SheetWriteError):
            bind_kinship_node(self.sheet, node=position)
        assert Kinsperson.objects.get(pk=position.pk).sheet_id is None

    def test_a_closed_position_is_refused_with_a_message(self) -> None:
        position = KinspersonFactory(is_appable=False, family=self.family)
        with self.assertRaises(SheetWriteError):
            bind_kinship_node(self.sheet, node=position)

    def test_residence_is_one_open_tenancy(self) -> None:
        room = RoomProfileFactory()
        grant_residence(self.sheet, room)
        grant_residence(self.sheet, room)
        assert (
            LocationTenancy.objects.filter(room_profile=room, tenant_persona=self.persona).count()
            == 1
        )

    def test_property_is_granted_once_per_profile(self) -> None:
        profile = PropertyGrantProfileFactory(activation_target_tier=ConditionTier.RAMSHACKLE)
        first = grant_property(self.sheet, profile)
        second = grant_property(self.sheet, profile)
        assert first.pk == second.pk
        assert Building.objects.filter(owner_persona=self.persona).count() == 1

    def test_a_vacancy_is_taken_and_counted_down(self) -> None:
        org = OrganizationFactory(name="House Estatewright", family=self.family)
        vacancy = VacancyFactory(organization=org, name="Steward", count_remaining=1)
        bind_vacancy(self.sheet, vacancy)
        assert OrganizationMembership.objects.filter(
            persona=self.persona, organization=org
        ).exists()
        assert Vacancy.objects.values_list("count_remaining", flat=True).get(pk=vacancy.pk) == 0
        with self.assertRaises(SheetWriteError):
            bind_vacancy(RosterEntryFactory().character_sheet, vacancy)

    def test_reputation_is_set_to_the_value_not_bumped(self) -> None:
        org = OrganizationFactory(name="The Estate Guild")
        set_organization_reputation(self.sheet, org, 300)
        set_organization_reputation(self.sheet, org, 100)
        assert (
            OrganizationReputation.objects.values_list("value", flat=True).get(
                persona=self.persona, organization=org
            )
            == 100
        )
        with self.assertRaises(SheetWriteError):
            set_organization_reputation(self.sheet, org, 5000)

    def test_an_unapproved_house_claim_is_refused(self) -> None:
        with self.assertRaises(SheetWriteError):
            bind_house_claim(self.sheet, SimpleNamespace(status="pending"))


class EstateApiTests(TestCase):
    """The staff actions are staff-only and answer with the refreshed sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = PlayerDataFactory()

    def setUp(self) -> None:
        self.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=self.player, roster_entry=self.entry, player_number=1)
        self.sheet = self.entry.character_sheet
        self.base = f"/api/character-sheets/{self.sheet.pk}"
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_kinship_and_reputation_show_in_the_staff_rows(self) -> None:
        family = FamilyFactory(name="House Apiwright")
        org = OrganizationFactory(name="The Api Guild")
        response = self.client.post(
            f"{self.base}/staff-kinship/", {"family": family.pk}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        response = self.client.put(
            f"{self.base}/staff-reputation/",
            {"organization": org.pk, "value": 250},
            format="json",
        )
        assert response.status_code == 200, response.content[:800]
        rows = response.data["staff_edit"]["rows"]
        assert rows["kin_node"]["name"].endswith("(House Apiwright)")
        assert rows["reputations"] == [
            {"organization": org.pk, "name": "The Api Guild", "value": 250}
        ]

    def test_a_residence_shows_and_rooms_are_searched(self) -> None:
        room = RoomProfileFactory()
        key = room.objectdb.db_key
        options = self.client.get(f"{self.base}/staff-estate-options/", {"room": key})
        assert options.status_code == 200, options.content[:800]
        assert {"id": room.pk, "name": key} in options.data["rooms"]
        assert self.client.get(f"{self.base}/staff-estate-options/").data["rooms"] == []
        response = self.client.post(
            f"{self.base}/staff-residence/", {"room_profile": room.pk}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        assert response.data["staff_edit"]["rows"]["residences"] == [{"id": room.pk, "name": key}]

    def test_a_property_without_a_profile_needs_one(self) -> None:
        response = self.client.post(f"{self.base}/staff-property/", {}, format="json")
        assert response.status_code == 400

    def test_the_player_cannot_use_the_estate_actions(self) -> None:
        self.client.force_authenticate(user=self.player.account)
        for method, path in (
            ("post", "staff-kinship"),
            ("post", "staff-residence"),
            ("post", "staff-property"),
            ("post", "staff-house-claim"),
            ("post", "staff-vacancy"),
            ("put", "staff-reputation"),
            ("get", "staff-estate-options"),
        ):
            response = getattr(self.client, method)(f"{self.base}/{path}/", {}, format="json")
            assert response.status_code in {403, 404}, (path, response.status_code)

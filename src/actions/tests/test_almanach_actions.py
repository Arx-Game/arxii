"""Tests for the staff Almanach de Catenys actions (#3983).

One ``.run()`` success test per action (staff, plain-int kwargs — the REST
dispatch shape), plus one non-staff rejection test shared across the family
(``StaffOnlyPrerequisite`` gates every key identically, so one refusal proves
the gate for the whole module).
"""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.almanach import (
    AlmanachAddHoldingAction,
    AlmanachBatchUnclaimedAction,
    AlmanachDescribeDemesneAction,
    AlmanachEditHouseAction,
    AlmanachEditKinAction,
    AlmanachNameRungAction,
    AlmanachPlanEstateAction,
    AlmanachPlantRungAction,
    AlmanachPublishAction,
    AlmanachSwearAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.roster.factories import FamilyFactory, KinspersonFactory, UnionKindFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import HouseState, TitleTier
from world.societies.houses.factories import HoldingKindFactory
from world.societies.houses.models import Title


def _staff_actor(db_key: str) -> ObjectDB:
    """A Character whose account is staff."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    return char


def _player_actor(db_key: str) -> ObjectDB:
    """A Character whose account is NOT staff."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=False)
    char.db_account = account
    char.save()
    return char


class AlmanachActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = _staff_actor("AlmanachStaff")
        cls.player = _player_actor("AlmanachPlayer")
        cls.realm = RealmFactory(name="Inferna")
        cls.family = FamilyFactory(name="House Piropa")
        cls.crown = OrganizationFactory(name="Piropa", family=cls.family)
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        # world.seeds.kinship.MARRIAGE_KIND_NAME ("Marriage") — absent on a
        # fresh test DB, so seed it here rather than depend on prod seeding.
        UnionKindFactory()

    def test_player_is_refused(self) -> None:
        result = AlmanachPlantRungAction().run(
            self.player,
            realm_id=self.realm.pk,
            tier="duchy",
            name="Fervor",
            parent_title_id=self.kingdom.pk,
        )
        assert not result.success

    def test_staff_plants_names_batches_edits_and_publishes(self) -> None:
        result = AlmanachPlantRungAction().run(
            self.staff,
            realm_id=self.realm.pk,
            tier="duchy",
            name="",
            parent_title_id=self.kingdom.pk,
        )
        assert result.success, result.message
        duchy = Title.objects.get(pk=result.data["title_id"])

        result = AlmanachNameRungAction().run(self.staff, title_id=duchy.pk, name="Fervor")
        assert result.success, result.message

        result = AlmanachBatchUnclaimedAction().run(
            self.staff, parent_title_id=duchy.pk, tier="county", count=2, baronies_per_county=1
        )
        assert result.success, result.message
        assert len(result.data["title_ids"]) == 2

        result = AlmanachEditHouseAction().run(
            self.staff, org_id=self.crown.pk, words="PLACEHOLDER", house_state=HouseState.STANDING
        )
        assert result.success, result.message
        assert result.data["org_id"] == self.crown.pk

        result = AlmanachPublishAction().run(self.staff, org_id=self.crown.pk, publish=True)
        assert result.success, result.message
        self.crown.refresh_from_db()
        assert self.crown.published_at is not None

    def test_swear(self) -> None:
        vassal = OrganizationFactory(name="House Vassal")
        result = AlmanachSwearAction().run(
            self.staff, vassal_org_id=vassal.pk, liege_org_id=self.crown.pk
        )
        assert result.success, result.message
        assert result.data == {"vassal_org_id": vassal.pk, "liege_org_id": self.crown.pk}

    def test_describe_demesne(self) -> None:
        result = AlmanachDescribeDemesneAction().run(
            self.staff,
            domain_id=self.kingdom.seat_domain_id,
            description="A blasted crag ringed in cinderfall.",
            hall_name="The Ember Hall",
            land_shape_names=[],
        )
        assert result.success, result.message
        assert result.data == {"domain_id": self.kingdom.seat_domain_id}

    def test_add_holding(self) -> None:
        kind = HoldingKindFactory()
        result = AlmanachAddHoldingAction().run(
            self.staff, domain_id=self.kingdom.seat_domain_id, holding_kind_id=kind.pk, name=""
        )
        assert result.success, result.message
        assert result.data["domain_id"] == self.kingdom.seat_domain_id

    def test_plan_estate(self) -> None:
        city = AreaFactory()
        result = AlmanachPlanEstateAction().run(
            self.staff,
            org_id=self.crown.pk,
            city_area_id=city.pk,
            name="Ember House",
            description="A cinder-stone townhouse.",
        )
        assert result.success, result.message
        assert result.data["org_id"] == self.crown.pk
        assert "area_id" in result.data

    def test_edit_kin_child(self) -> None:
        parent = KinspersonFactory(family=self.family, name="Consort Alden")
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Heir Casella",
            relation="child",
            parent_kinsperson_id=parent.pk,
            is_deceased=False,
            believed_deceased=False,
            is_household=False,
        )
        assert result.success, result.message
        assert result.data["org_id"] == self.crown.pk
        heir_id = result.data["kinsperson_id"]

        from world.roster.models import Kinsperson

        heir = Kinsperson.objects.get(pk=heir_id)
        assert heir.family_id == self.family.pk

    def test_edit_kin_household_ward(self) -> None:
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Ward Tomas",
            relation="ward",
            is_deceased=False,
            believed_deceased=False,
            is_household=True,
        )
        assert result.success, result.message
        assert "vacancy_id" in result.data

        from world.societies.models import Vacancy

        vacancy = Vacancy.objects.get(pk=result.data["vacancy_id"])
        assert vacancy.name == "Ward"
        assert vacancy.holder_kinsperson_id == result.data["kinsperson_id"]

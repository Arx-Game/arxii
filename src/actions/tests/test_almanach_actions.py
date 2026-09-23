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
from world.character_sheets.factories import GenderFactory
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

    def test_plant_rung_refuses_parent_title_with_no_seat_domain(self) -> None:
        orphan = Title.objects.create(name="Orphan", tier=TitleTier.BARONY, realm=self.realm)
        result = AlmanachPlantRungAction().run(
            self.staff,
            realm_id=self.realm.pk,
            tier="barony",
            name="Cinderhold",
            parent_title_id=orphan.pk,
        )
        assert not result.success
        assert result.message

    def test_edit_house_replaces_aspects_features_and_succession_law(self) -> None:
        from world.societies.houses.constants import SuccessionDerivation
        from world.societies.houses.models import (
            HouseAspectDefinition,
            HouseAspectOption,
            HouseFeature,
            OrganizationAspect,
            OrganizationFeature,
            SuccessionLaw,
        )

        definition = HouseAspectDefinition.objects.create(name="Quiddity", prompt="Pick one.")
        option_a = HouseAspectOption.objects.create(definition=definition, name="Ember-Touched")
        option_b = HouseAspectOption.objects.create(definition=definition, name="Ashbound")
        feature = HouseFeature.objects.create(
            name="Black Ledger", slug="black-ledger", description="Keeps a debt ledger."
        )
        law = SuccessionLaw.objects.create(
            name="Test Succession", derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK
        )

        result = AlmanachEditHouseAction().run(
            self.staff,
            org_id=self.crown.pk,
            aspect_option_ids=[option_a.pk],
            feature_ids=[feature.pk],
            default_succession_law_id=law.pk,
        )
        assert result.success, result.message
        self.crown.refresh_from_db()
        assert self.crown.default_succession_law_id == law.pk
        assert list(
            OrganizationAspect.objects.filter(organization=self.crown).values_list(
                "option_id", flat=True
            )
        ) == [option_a.pk]
        assert list(
            OrganizationFeature.objects.filter(organization=self.crown).values_list(
                "feature_id", flat=True
            )
        ) == [feature.pk]

        # Replace with the other option; the first row is gone, the second present.
        result = AlmanachEditHouseAction().run(
            self.staff, org_id=self.crown.pk, aspect_option_ids=[option_b.pk]
        )
        assert result.success, result.message
        assert list(
            OrganizationAspect.objects.filter(organization=self.crown).values_list(
                "option_id", flat=True
            )
        ) == [option_b.pk]
        # feature_ids wasn't passed on this call — the earlier feature survives untouched.
        assert list(
            OrganizationFeature.objects.filter(organization=self.crown).values_list(
                "feature_id", flat=True
            )
        ) == [feature.pk]

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

    def test_edit_kin_child_second_edit_does_not_remint_relation_effects(self) -> None:
        """#3983 review fix 1: an update (``kinsperson_id`` given) touches only
        plain fields — it must never re-run the create-time relation wiring."""
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
        heir_id = result.data["kinsperson_id"]

        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            kinsperson_id=heir_id,
            name="Heir Casella the Younger",
            is_deceased=False,
            believed_deceased=False,
        )
        assert result.success, result.message

        from world.roster.models import FamilyMembership, Kinsperson, ParentageEdge

        heir = Kinsperson.objects.get(pk=heir_id)
        assert heir.name == "Heir Casella the Younger"
        assert ParentageEdge.objects.filter(child_id=heir_id).count() == 1
        assert FamilyMembership.objects.filter(kinsperson_id=heir_id).count() == 1

    def test_edit_kin_spouse_second_edit_does_not_remint_union(self) -> None:
        """#3983 review fix 1: same guarantee for the ``spouse`` relation."""
        spouse = KinspersonFactory(family=self.family, name="Consort Beatrys")
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Duke Aldric",
            relation="spouse",
            spouse_kinsperson_id=spouse.pk,
            is_deceased=False,
            believed_deceased=False,
            is_household=False,
        )
        assert result.success, result.message
        duke_id = result.data["kinsperson_id"]

        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            kinsperson_id=duke_id,
            name="Duke Aldric Renamed",
            is_deceased=False,
            believed_deceased=False,
        )
        assert result.success, result.message

        from world.roster.models import Union

        assert Union.objects.filter(members__pk=duke_id).count() == 1

    def test_edit_kin_update_refuses_relation_kwargs(self) -> None:
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Elder Fen",
            relation="head",
            is_deceased=False,
            believed_deceased=False,
            is_household=False,
        )
        assert result.success, result.message
        kin_id = result.data["kinsperson_id"]

        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            kinsperson_id=kin_id,
            name="Elder Fen Renamed",
            relation="head",
            is_deceased=False,
            believed_deceased=False,
        )
        assert not result.success
        assert result.message

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

    def test_edit_kin_update_only_age_leaves_other_fields_untouched(self) -> None:
        """#3983 Task 10 fold-in: a plain field changes ONLY when its kwarg
        was actually passed — an update sending only ``age`` must not blank
        the name, clear the gender, or reset ``is_deceased``."""
        gender = GenderFactory()
        kin = KinspersonFactory(
            family=self.family, name="Elder Fen", gender=gender, is_deceased=True
        )
        result = AlmanachEditKinAction().run(
            self.staff, org_id=self.crown.pk, kinsperson_id=kin.pk, age=42
        )
        assert result.success, result.message

        kin.refresh_from_db()
        assert kin.age == 42
        assert kin.name == "Elder Fen"
        assert kin.gender_id == gender.pk
        assert kin.is_deceased is True

    def test_edit_kin_update_believed_deceased_false_clears_it(self) -> None:
        """#3983 Task 10 fold-in: an explicit ``believed_deceased=False`` is
        honored (not just a truthy value) since the update path checks for
        the kwarg's presence, not its truthiness."""
        kin = KinspersonFactory(family=self.family, name="Elder Fen", believed_deceased=True)
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            kinsperson_id=kin.pk,
            believed_deceased=False,
        )
        assert result.success, result.message

        kin.refresh_from_db()
        assert kin.believed_deceased is False

    def test_edit_kin_update_refuses_foreign_kinsperson(self) -> None:
        """#3983 Task 10 fold-in: a kinsperson whose ``family_id`` isn't this
        house's own family is refused, never silently edited."""
        other_family = FamilyFactory(name="House Outsider")
        stranger = KinspersonFactory(family=other_family, name="Stranger")
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            kinsperson_id=stranger.pk,
            age=10,
        )
        assert not result.success
        assert result.message

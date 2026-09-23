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
from world.roster.constants import MembershipBasis
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

    def test_staff_lay_inferna_and_the_ladder_matches_the_plate(self) -> None:
        """#3983 spec Testing (1): lay Piropa's own holdings through the
        actions, then read the ladder and check it against plate S-I —
        Vampa demesne 4 / vassals 1, the County of Inferna demesne 3, the
        seat barony marked, and the house document's own four baronies."""
        from world.societies.houses.almanach_reads import document_for_house, ladder_for_realm

        chain = {t.tier: t for t in Title.objects.filter(seat_domain=self.kingdom.seat_domain)}
        for tier, rung_name in (
            (TitleTier.DUCHY, "Vampa"),
            (TitleTier.COUNTY, "County of Inferna"),
            (TitleTier.BARONY, "Perdition"),
        ):
            result = AlmanachNameRungAction().run(
                self.staff, title_id=chain[tier].pk, name=rung_name
            )
            assert result.success, result.message

        # Two more baronies the crown keeps personally inside its own county.
        for barony_name in ("Bochorno", "Lumbre"):
            result = AlmanachPlantRungAction().run(
                self.staff,
                realm_id=self.realm.pk,
                tier="barony",
                name=barony_name,
                parent_title_id=chain[TitleTier.COUNTY].pk,
                held_by_org_id=self.crown.pk,
            )
            assert result.success, result.message

        # A county granted away, with one crown barony still inside it.
        solano = OrganizationFactory(name="Solano")
        result = AlmanachPlantRungAction().run(
            self.staff,
            realm_id=self.realm.pk,
            tier="county",
            name="Ardor",
            parent_title_id=chain[TitleTier.DUCHY].pk,
            held_by_org_id=solano.pk,
        )
        assert result.success, result.message
        ardor_id = result.data["title_id"]
        result = AlmanachPlantRungAction().run(
            self.staff,
            realm_id=self.realm.pk,
            tier="barony",
            name="Seawatch",
            parent_title_id=ardor_id,
            held_by_org_id=self.crown.pk,
        )
        assert result.success, result.message

        result = AlmanachPublishAction().run(self.staff, org_id=self.crown.pk, publish=True)
        assert result.success, result.message

        rows = {r.name: r for r in ladder_for_realm(self.realm).rows if r.name}
        vampa = rows["Vampa"]
        assert vampa.demesne == 4, "Perdition, Bochorno, Lumbre and Seawatch"
        assert vampa.vassals == 1, "Solano, once"
        assert rows["County of Inferna"].demesne == 3, "Seawatch lies under Ardor, not here"
        assert rows["Perdition"].is_seat_of == "Piropa"
        assert rows["Seawatch"].house_name == "Piropa", "held inside a vassal's county"
        assert rows["Ardor"].sworn_to == "Piropa (crown)"

        doc = document_for_house(self.crown, viewer=None, staff=True)
        assert {row["name"] for row in doc.realm["demesne"]} == {
            "Perdition",
            "Bochorno",
            "Lumbre",
            "Seawatch",
        }
        assert doc.lands["seat"] == "Perdition"

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
        # The ward's own row, titled by the ward (#3983 review I2): Vacancy is
        # unique on (organization, name), so a shared "Ward" title made the
        # second ward take the first's place.
        assert vacancy.name == "Ward: Ward Tomas"
        assert vacancy.holder_kinsperson_id == result.data["kinsperson_id"]

    def test_edit_kin_position_posts_an_open_slot_with_nobody_in_it(self) -> None:
        """#3983 ruling I2: "Master-at-arms · position · open" — a titled
        post, not an NPC named after the job."""
        result = AlmanachEditKinAction().run(
            self.staff, org_id=self.crown.pk, name="Master-at-arms", relation="position"
        )
        assert result.success, result.message
        assert "kinsperson_id" not in result.data

        from world.roster.models import Kinsperson
        from world.societies.models import Vacancy

        vacancy = Vacancy.objects.get(pk=result.data["vacancy_id"])
        assert vacancy.name == "Master-at-arms"
        assert vacancy.holder_kinsperson_id is None
        assert vacancy.is_open
        assert not Kinsperson.objects.filter(name="Master-at-arms").exists()

    def test_edit_kin_position_needs_a_title(self) -> None:
        result = AlmanachEditKinAction().run(
            self.staff, org_id=self.crown.pk, name="  ", relation="position"
        )
        assert not result.success
        assert result.message == "Name the position."

    def test_edit_kin_unnamed_ward_says_ward(self) -> None:
        """#3983 review N3: the refusal names the row it means — a position's
        own refusal (above) says "position", a ward's says "ward"."""
        result = AlmanachEditKinAction().run(
            self.staff, org_id=self.crown.pk, name="", relation="ward", is_household=True
        )
        assert not result.success
        assert result.message == "Name the ward."

    def test_edit_kin_mother_is_anchored_to_a_relative(self) -> None:
        """#3983 review I3: every relation is written relative to somebody.
        Without the anchor the node had no edge and no membership, so the
        tree never listed it and nothing could reach it again."""
        from world.roster.models import FamilyMembership, Kinsperson, ParentageEdge

        heir = KinspersonFactory(family=self.family, name="Heir Casella")
        refused = AlmanachEditKinAction().run(
            self.staff, org_id=self.crown.pk, name="Dowager Fiamma", relation="mother"
        )
        assert not refused.success

        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Dowager Fiamma",
            relation="mother",
            relative_kinsperson_id=heir.pk,
        )
        assert result.success, result.message
        mother = Kinsperson.objects.get(pk=result.data["kinsperson_id"])
        assert ParentageEdge.objects.filter(child=heir, parent=mother).exists()
        membership = FamilyMembership.objects.get(kinsperson=mother, family=self.family)
        assert membership.basis == MembershipBasis.BORN

    def test_edit_kin_sibling_shares_the_relatives_parents(self) -> None:
        from world.roster.models import Kinsperson, ParentageEdge
        from world.roster.services.kinship import record_parentage

        parent = KinspersonFactory(family=self.family, name="Dowager Fiamma")
        heir = KinspersonFactory(family=self.family, name="Heir Casella")
        record_parentage(child=heir, parent=parent)

        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Second Son",
            relation="sibling",
            relative_kinsperson_id=heir.pk,
        )
        assert result.success, result.message
        sibling = Kinsperson.objects.get(pk=result.data["kinsperson_id"])
        assert ParentageEdge.objects.filter(child=sibling, parent=parent).exists()

    def test_edit_kin_sibling_of_a_parentless_relative_is_refused(self) -> None:
        orphan = KinspersonFactory(family=self.family, name="Orphan")
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Second Son",
            relation="sibling",
            relative_kinsperson_id=orphan.pk,
        )
        assert not result.success

    def test_edit_kin_grandparent_needs_a_parent_to_hang_from(self) -> None:
        from world.roster.models import Kinsperson, ParentageEdge
        from world.roster.services.kinship import record_parentage

        childless = KinspersonFactory(family=self.family, name="Childless")
        refused = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Old Nonna",
            relation="grandparent",
            relative_kinsperson_id=childless.pk,
        )
        assert not refused.success

        parent = KinspersonFactory(family=self.family, name="Dowager Fiamma")
        heir = KinspersonFactory(family=self.family, name="Heir Casella")
        record_parentage(child=heir, parent=parent)
        result = AlmanachEditKinAction().run(
            self.staff,
            org_id=self.crown.pk,
            name="Old Nonna",
            relation="grandparent",
            relative_kinsperson_id=parent.pk,
        )
        assert result.success, result.message
        nonna = Kinsperson.objects.get(pk=result.data["kinsperson_id"])
        assert ParentageEdge.objects.filter(child=parent, parent=nonna).exists()

    def test_plant_rung_at_the_realm_root(self) -> None:
        """#3983 I9: a realm with no ladder at all has to start somewhere —
        a rung with no parent is planted at the realm root."""
        result = AlmanachPlantRungAction().run(
            self.staff, realm_id=self.realm.pk, tier="kingdom", name="Cinderus"
        )
        assert result.success, result.message
        planted = Title.objects.get(pk=result.data["title_id"])
        assert planted.tier == TitleTier.KINGDOM
        assert planted.seat_domain.area.parent.parent.parent.parent is None

    def test_plant_rung_refuses_a_tier_that_does_not_nest(self) -> None:
        """#3983 review M7: a county under a barony is an Atlas-level
        violation; it used to escape as a bare ValidationError."""
        barony = plant_rung(
            realm=self.realm, tier=TitleTier.BARONY, name="Cinderhold", parent_title=self.kingdom
        )
        result = AlmanachPlantRungAction().run(
            self.staff,
            realm_id=self.realm.pk,
            tier="county",
            name="Impossible",
            parent_title_id=barony.pk,
        )
        assert not result.success
        assert result.message

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

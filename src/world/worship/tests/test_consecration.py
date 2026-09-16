"""Shrines and temples (#3778): founding gates, stacking bonuses, growth from rites."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.worship import DedicateTempleAction, FoundShrineAction
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.action_points.factories import ActionPointPoolFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import RoomFeatureInstance
from world.roster.factories import grant_test_tenure
from world.scenes.factories import PersonaFactory, SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.consecration_services import (
    consecration_bonus_percent,
    dedicate_temple,
    dissolve_shrine,
    found_shrine,
    revoke_temple,
    shrine_at,
    temple_over,
)
from world.worship.constants import BeingResonanceTier, ConsecrationScope, RiteTier
from world.worship.exceptions import SiteAlreadyTaken, SiteNotHeld
from world.worship.factories import (
    ConsecrationTierFactory,
    RiteKindFactory,
    ShrineDetailsFactory,
    TempleDedicationFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.models import ShrineDetails, TempleDedication
from world.worship.rite_services import perform_worship_rite


def _points(model, site) -> int:
    return model.objects.filter(pk=site.pk).values_list("consecration_points", flat=True).get()


def _own_room(profile, persona) -> LocationOwnership:
    return LocationOwnership.objects.create(
        parent_type=LocationParentType.ROOM,
        room_profile=profile,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )


class ConsecrationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.other_being = WorshippedBeingFactory()
        cls.building = BuildingFactory()
        cls.room = ObjectDBFactory(db_key="Nave", db_typeclass_path="typeclasses.rooms.Room")
        cls.profile = RoomProfileFactory(objectdb=cls.room, area=cls.building.area)
        cls.sheet = CharacterSheetFactory()
        cls.persona = cls.sheet.primary_persona
        cls.stranger = PersonaFactory()
        ConsecrationTierFactory(scope=ConsecrationScope.SHRINE, min_points=0, bonus_percent=5)
        ConsecrationTierFactory(scope=ConsecrationScope.SHRINE, min_points=10, bonus_percent=20)
        ConsecrationTierFactory(scope=ConsecrationScope.TEMPLE, min_points=0, bonus_percent=10)
        ConsecrationTierFactory(scope=ConsecrationScope.TEMPLE, min_points=10, bonus_percent=50)


class FoundShrineTests(ConsecrationTestBase):
    def test_the_rooms_owner_founds_a_shrine_as_a_room_feature(self) -> None:
        _own_room(self.profile, self.persona)

        shrine = found_shrine(self.profile, self.being, self.persona)

        instance = RoomFeatureInstance.objects.get(room_profile=self.profile)
        self.assertEqual(instance.feature_kind.service_strategy, RoomFeatureServiceStrategy.SHRINE)
        self.assertEqual(shrine.feature_instance, instance)
        self.assertEqual(shrine.founder_character_sheet, self.sheet)
        self.assertEqual(shrine_at(self.profile), shrine)

    def test_a_non_owner_is_refused(self) -> None:
        _own_room(self.profile, self.stranger)
        with self.assertRaises(SiteNotHeld):
            found_shrine(self.profile, self.being, self.persona)
        self.assertFalse(ShrineDetails.objects.exists())

    def test_one_feature_per_room(self) -> None:
        _own_room(self.profile, self.persona)
        RoomFeatureInstanceFactory(
            room_profile=self.profile, feature_kind=RoomFeatureKindFactory(name="Library")
        )
        with self.assertRaises(SiteAlreadyTaken):
            found_shrine(self.profile, self.being, self.persona)

    def test_dissolving_frees_the_room(self) -> None:
        _own_room(self.profile, self.persona)
        shrine = found_shrine(self.profile, self.being, self.persona)

        with self.assertRaises(SiteNotHeld):
            dissolve_shrine(shrine, self.stranger)
        dissolve_shrine(shrine, self.persona)

        self.assertIsNone(shrine_at(self.profile))
        found_shrine(self.profile, self.other_being, self.persona)
        self.assertEqual(shrine_at(self.profile).being, self.other_being)

    def test_the_action_founds_by_being_name(self) -> None:
        _own_room(self.profile, self.persona)
        self.sheet.character.db_location = self.room
        self.sheet.character.save(update_fields=["db_location"])

        result = FoundShrineAction().run(
            actor=self.sheet.character, being_name=self.being.name.lower()
        )

        self.assertTrue(result.success, result.message)
        self.assertEqual(shrine_at(self.profile).being, self.being)


class DedicateTempleTests(ConsecrationTestBase):
    def test_the_buildings_credited_owner_dedicates_it(self) -> None:
        self.building.owner_persona = self.persona
        self.building.save(update_fields=["owner_persona"])

        dedication = dedicate_temple(self.building, self.being, self.persona)

        self.assertEqual(temple_over(self.profile), dedication)

    def test_the_holder_of_the_buildings_area_dedicates_it(self) -> None:
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building.area,
            holder_type=HolderType.PERSONA,
            holder_persona=self.persona,
        )
        dedicate_temple(self.building, self.being, self.persona)
        self.assertIsNotNone(temple_over(self.profile))

    def test_standing_over_one_room_is_not_standing_over_the_building(self) -> None:
        _own_room(self.profile, self.persona)
        with self.assertRaises(SiteNotHeld):
            dedicate_temple(self.building, self.being, self.persona)

    def test_one_active_dedication_per_building(self) -> None:
        self.building.owner_persona = self.persona
        self.building.save(update_fields=["owner_persona"])
        dedication = dedicate_temple(self.building, self.being, self.persona)
        with self.assertRaises(SiteAlreadyTaken):
            dedicate_temple(self.building, self.other_being, self.persona)

        revoke_temple(dedication, self.persona)
        dedicate_temple(self.building, self.other_being, self.persona)
        self.assertEqual(temple_over(self.profile).being, self.other_being)
        self.assertEqual(TempleDedication.objects.count(), 2)

    def test_a_room_in_a_sub_area_of_the_building_is_covered(self) -> None:
        # No level sits below BUILDING today, but the walk is parent-first and
        # cycle-safe should one ever exist.
        self.building.owner_persona = self.persona
        self.building.save(update_fields=["owner_persona"])
        dedicate_temple(self.building, self.being, self.persona)
        loose = RoomProfileFactory(
            objectdb=ObjectDBFactory(db_key="Yard", db_typeclass_path="typeclasses.rooms.Room"),
            area=AreaFactory(level=AreaLevel.NEIGHBORHOOD),
        )
        self.assertIsNone(temple_over(loose))

    def test_the_action_dedicates_the_building_you_stand_in(self) -> None:
        self.building.owner_persona = self.persona
        self.building.save(update_fields=["owner_persona"])
        self.sheet.character.db_location = self.room
        self.sheet.character.save(update_fields=["db_location"])

        result = DedicateTempleAction().run(actor=self.sheet.character, being=self.being)

        self.assertTrue(result.success, result.message)
        self.assertEqual(temple_over(self.profile).being, self.being)


class ConsecrationBonusTests(ConsecrationTestBase):
    def test_shrine_and_temple_bonuses_stack_by_addition(self) -> None:
        ShrineDetailsFactory(
            feature_instance__room_profile=self.profile, being=self.being, consecration_points=10
        )
        TempleDedicationFactory(building=self.building, being=self.being, consecration_points=0)

        self.assertEqual(consecration_bonus_percent(self.profile, self.being), 20 + 10)

    def test_a_site_of_another_being_adds_nothing(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.other_being)
        TempleDedicationFactory(building=self.building, being=self.other_being)

        self.assertEqual(consecration_bonus_percent(self.profile, self.being), 0)

    def test_no_site_no_bonus(self) -> None:
        self.assertEqual(consecration_bonus_percent(self.profile, self.being), 0)
        self.assertEqual(consecration_bonus_percent(None, self.being), 0)


class RiteGrowsTheSiteTests(ConsecrationTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.tenure = grant_test_tenure(cls.sheet)
        cls.sheet.character.db_location = cls.room
        cls.sheet.character.save(update_fields=["db_location"])
        cls.scene = SceneFactory(location=cls.room, is_active=True)
        SceneParticipationFactory(scene=cls.scene, account=cls.tenure.player_data.account)
        ActionPointPoolFactory(character=cls.sheet, current=20, maximum=20)
        cls.rite = WorshipRiteFactory(
            being=cls.being, kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEMANDING)
        )
        cls.rite.resonance.tier = BeingResonanceTier.ASSOCIATED
        cls.rite.resonance.save(update_fields=["tier"])
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        WorshipRiteTierAwardFactory(
            tier=RiteTier.DEMANDING, outcome_tier=cls.success, resonance_amount=10, favor_amount=4
        )

    def test_a_rite_at_its_beings_sites_is_boosted_and_consecrates_them(self) -> None:
        shrine = ShrineDetailsFactory(
            feature_instance__room_profile=self.profile, being=self.being, consecration_points=0
        )
        temple = TempleDedicationFactory(building=self.building, being=self.being)

        with force_check_outcome(self.success):
            outcome = perform_worship_rite(self.sheet, self.rite, scene=self.scene)

        self.assertEqual(outcome.consecration_bonus_percent, 5 + 10)
        self.assertEqual(outcome.resonance_granted, 10 * 115 // 100)
        # Database truth, not the identity-mapped instance (refresh_from_db is a
        # no-op on a SharedMemoryModel: the re-fetch returns the same object).
        self.assertEqual(_points(ShrineDetails, shrine), 2)  # tier 2 rite
        self.assertEqual(_points(TempleDedication, temple), 2)
        self.assertEqual(shrine.consecration_points, 2)  # and the held row was told

    def test_a_rite_of_another_being_neither_gains_nor_grows(self) -> None:
        shrine = ShrineDetailsFactory(
            feature_instance__room_profile=self.profile, being=self.other_being
        )

        with force_check_outcome(self.success):
            outcome = perform_worship_rite(self.sheet, self.rite, scene=self.scene)

        self.assertEqual(outcome.consecration_bonus_percent, 0)
        self.assertEqual(outcome.resonance_granted, 10)
        self.assertEqual(_points(ShrineDetails, shrine), 0)

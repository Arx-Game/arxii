"""Tests for the PropertyGrantProfile model and world.buildings.property_grant_services."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingKindFactory, PropertyGrantProfileFactory
from world.buildings.models import BuildingSizeTier, PropertyGrantProfile
from world.buildings.room_services import RoomBuildError
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.scenes.factories import PersonaFactory


class PropertyGrantProfileModelTests(TestCase):
    def test_profile_defaults(self):
        profile = PropertyGrantProfileFactory()
        assert profile.initial_condition_tier == ConditionTier.DECAYED
        assert profile.activation_target_tier is None
        assert profile.activation_cost_floor_coppers == 0

    def test_profile_str_is_name(self):
        profile = PropertyGrantProfileFactory(name="Test Grant Profile")
        assert str(profile) == "Test Grant Profile"

    def test_profile_name_unique(self):
        PropertyGrantProfileFactory(name="Dup")
        with self.assertRaises(Exception):  # noqa: B017 — IntegrityError vs ValidationError varies
            PropertyGrantProfile.objects.create(name="Dup", building_kind=BuildingKindFactory())


def _ensure_hut_tier():
    BuildingSizeTier.objects.get_or_create(tier=1, defaults={"name": "Hut", "space_budget": 50})


class GrantPropertyHouseTests(TestCase):
    def setUp(self):
        _ensure_hut_tier()

    def test_grant_creates_owned_building(self):
        from world.buildings.property_grant_services import grant_property_house

        persona = PersonaFactory()
        profile = PropertyGrantProfileFactory()
        building = grant_property_house(persona, profile)
        assert building.owner_persona_id == persona.pk
        assert building.condition_tier == ConditionTier.DECAYED
        assert building.granted_via_profile_id == profile.pk
        assert building.property_granted_at is not None
        assert building.entry_room is not None

    def test_grant_with_no_activation_arc_is_immediately_active(self):
        from world.buildings.property_grant_services import grant_property_house

        persona = PersonaFactory()
        profile = PropertyGrantProfileFactory(
            initial_condition_tier=ConditionTier.GOOD, activation_target_tier=None
        )
        building = grant_property_house(persona, profile)
        assert building.condition_tier == ConditionTier.GOOD
        assert building.property_activated_at is not None

    def test_grant_with_activation_arc_starts_unactivated(self):
        from world.buildings.property_grant_services import grant_property_house

        persona = PersonaFactory()
        profile = PropertyGrantProfileFactory(activation_target_tier=ConditionTier.RAMSHACKLE)
        building = grant_property_house(persona, profile)
        assert building.property_activated_at is None

    def test_grant_uses_placeholder_ward_when_profile_ward_unset(self):
        from world.buildings.property_grant_services import grant_property_house

        persona = PersonaFactory()
        profile = PropertyGrantProfileFactory(ward_area=None)
        building = grant_property_house(persona, profile)
        assert building.area.parent is not None
        assert building.area.parent.level == AreaLevel.WARD
        assert building.area.parent.slug == "property-grant-placeholder-ward"

    def test_grant_placeholder_ward_is_idempotent(self):
        from world.buildings.property_grant_services import grant_property_house

        profile = PropertyGrantProfileFactory(ward_area=None)
        b1 = grant_property_house(PersonaFactory(), profile)
        b2 = grant_property_house(PersonaFactory(), profile)
        assert b1.area.parent_id == b2.area.parent_id

    def test_grant_uses_profile_ward_when_set(self):
        from world.areas.factories import AreaFactory
        from world.buildings.property_grant_services import grant_property_house

        ward = AreaFactory(level=AreaLevel.WARD)
        persona = PersonaFactory()
        profile = PropertyGrantProfileFactory(ward_area=ward)
        building = grant_property_house(persona, profile)
        assert building.area.parent_id == ward.pk


def _owned_building_with_persona():
    """A granted, un-activated Building with an owning Persona and an entry room."""
    from world.buildings.property_grant_services import grant_property_house

    _ensure_hut_tier()
    persona = PersonaFactory()
    profile = PropertyGrantProfileFactory(
        activation_target_tier=ConditionTier.RAMSHACKLE,
        activation_cost_floor_coppers=100,
    )
    building = grant_property_house(persona, profile)
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=building.area,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )
    return persona, building


class StartBuildingActivationTests(TestCase):
    def test_commissions_activation_project(self):
        from world.buildings.property_grant_services import start_building_activation

        persona, building = _owned_building_with_persona()
        project = start_building_activation(persona=persona, building=building)
        assert project.kind == ProjectKind.BUILDING_ACTIVATION
        assert project.completion_mode == CompletionMode.SINGLE_THRESHOLD
        assert project.building_activation_details.target_tier == ConditionTier.RAMSHACKLE

    def test_project_starts_active(self):
        from world.buildings.property_grant_services import start_building_activation

        persona, building = _owned_building_with_persona()
        project = start_building_activation(persona=persona, building=building)
        assert project.status == ProjectStatus.ACTIVE

    def test_non_owner_refused(self):
        from world.buildings.property_grant_services import start_building_activation

        _, building = _owned_building_with_persona()
        other = PersonaFactory()
        with self.assertRaises(RoomBuildError):
            start_building_activation(persona=other, building=building)

    def test_not_a_grant_refused(self):
        from world.buildings.factories import BuildingFactory
        from world.buildings.property_grant_services import start_building_activation

        persona = PersonaFactory()
        building = BuildingFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=building.area,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        from world.buildings.services import create_entry_room

        room = create_entry_room(building, "Entry Hall")
        building.entry_room = room
        building.save(update_fields=["entry_room"])
        with self.assertRaises(RoomBuildError):
            start_building_activation(persona=persona, building=building)

    def test_already_activated_refused(self):
        from world.buildings.property_grant_services import (
            complete_building_activation,
            start_building_activation,
        )

        persona, building = _owned_building_with_persona()
        project = start_building_activation(persona=persona, building=building)
        complete_building_activation(project)
        with self.assertRaises(RoomBuildError):
            start_building_activation(persona=persona, building=building)

    def test_duplicate_open_project_refused(self):
        from world.buildings.property_grant_services import start_building_activation

        persona, building = _owned_building_with_persona()
        start_building_activation(persona=persona, building=building)
        with self.assertRaises(RoomBuildError):
            start_building_activation(persona=persona, building=building)


class CompleteBuildingActivationTests(TestCase):
    def test_completion_sets_tier_and_stamps_activated_at(self):
        from world.buildings.property_grant_services import (
            complete_building_activation,
            start_building_activation,
        )

        persona, building = _owned_building_with_persona()
        project = start_building_activation(persona=persona, building=building)
        complete_building_activation(project)
        building.refresh_from_db()
        assert building.condition_tier == ConditionTier.RAMSHACKLE
        assert building.property_activated_at is not None

    def test_completion_is_idempotent(self):
        from world.buildings.property_grant_services import (
            complete_building_activation,
            start_building_activation,
        )

        persona, building = _owned_building_with_persona()
        project = start_building_activation(persona=persona, building=building)
        complete_building_activation(project)
        first_stamp = building.__class__.objects.get(pk=building.pk).property_activated_at
        complete_building_activation(project)
        second_stamp = building.__class__.objects.get(pk=building.pk).property_activated_at
        assert first_stamp == second_stamp

    def test_handler_registered_for_building_activation_kind(self):
        from world.projects.constants import ProjectKind
        from world.projects.services import get_kind_handler

        handler = get_kind_handler(ProjectKind.BUILDING_ACTIVATION)
        assert handler.__name__ == "complete_building_activation"

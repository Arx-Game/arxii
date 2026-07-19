"""Tests for the PropertyGrantProfile model and world.buildings.property_grant_services."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingKindFactory, PropertyGrantProfileFactory
from world.buildings.models import BuildingSizeTier, PropertyGrantProfile
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

"""Action-level tests for ``StartBuildingActivationAction``.

Owner-gated commissioning tests are ``@tag("postgres")`` for the same reason
as ``test_renovation_action.py``: the service's ``is_owner`` gate walks the
``AreaClosure`` materialized view.
"""

from django.test import TestCase, tag

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.factories import AreaFactory
from world.buildings.constants import ConditionTier
from world.buildings.factories import PropertyGrantProfileFactory
from world.buildings.models import BuildingSizeTier
from world.buildings.property_grant_services import grant_property_house
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.projects.constants import ProjectKind


def _make_owner_of_granted_building(*, activation_target_tier=ConditionTier.RAMSHACKLE):
    BuildingSizeTier.objects.get_or_create(tier=1, defaults={"name": "Hut", "space_budget": 50})
    actor = CharacterFactory()
    CharacterSheetFactory(character=actor)
    persona = actor.sheet_data.primary_persona
    profile = PropertyGrantProfileFactory(
        activation_target_tier=activation_target_tier, activation_cost_floor_coppers=100
    )
    building = grant_property_house(persona, profile)
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=building.area,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )
    actor.db_location = building.entry_room.objectdb
    actor.save(update_fields=["db_location"])
    return actor, building


@tag("postgres")
class StartBuildingActivationActionTests(TestCase):
    def test_commission_creates_project(self) -> None:
        actor, building = _make_owner_of_granted_building()
        action = get_action("start_building_activation")
        result = action.run(actor)
        assert result.success
        assert "project #" in result.message
        from world.projects.models import Project

        project = Project.objects.filter(kind=ProjectKind.BUILDING_ACTIVATION).first()
        assert project is not None
        assert project.building_activation_details.building_id == building.pk

    def test_non_owner_refused(self) -> None:
        actor, _ = _make_owner_of_granted_building()
        other_actor = CharacterFactory()
        CharacterSheetFactory(character=other_actor)
        other_actor.db_location = actor.db_location
        other_actor.save(update_fields=["db_location"])
        action = get_action("start_building_activation")
        result = action.run(other_actor)
        assert not result.success

    def test_no_activation_arc_refused(self) -> None:
        # grant_property_house immediately stamps property_activated_at when the
        # profile carries no activation arc, so the "already activated" guard
        # would otherwise fire first — reset it to isolate the "no activation
        # arc" guard the same way the service's own test suite does.
        actor, building = _make_owner_of_granted_building(activation_target_tier=None)
        building.property_activated_at = None
        building.save(update_fields=["property_activated_at"])
        action = get_action("start_building_activation")
        result = action.run(actor)
        assert not result.success
        assert "doesn't need activation" in result.message.lower()

    def test_non_building_room_errors(self) -> None:
        # The actor owns a *non-building* room — the owner prerequisite passes,
        # but the room isn't part of any building, so the action reports that.
        area = AreaFactory()
        bare_room = ObjectDBFactory(db_key="Void", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(objectdb=bare_room, defaults={"area": area})
        actor = CharacterFactory()
        CharacterSheetFactory(character=actor)
        persona = actor.sheet_data.primary_persona
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        actor.db_location = bare_room
        actor.save(update_fields=["db_location"])
        action = get_action("start_building_activation")
        result = action.run(actor)
        assert not result.success
        assert "building" in result.message.lower()

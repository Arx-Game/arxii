"""Action-level tests for ``StartBuildingRenovationAction``.

Owner-gated commissioning tests are ``@tag("postgres")`` because the service's
``is_owner`` gate walks the ``AreaClosure`` materialized view. The list-on-empty
and wrong-name paths return before the service call and run on SQLite too.
"""

from django.test import TestCase, tag

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory, BuildingKindFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.projects.constants import ProjectKind


def _room_in(area, *, name="A Room"):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(objectdb=room, defaults={"area": area})
    return room


def _owned_building(persona, *, budget=100):
    area = AreaFactory(level=AreaLevel.BUILDING)
    building = BuildingFactory(area=area, space_budget=budget)
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=area,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )
    return building


def _make_owner_in_building():
    actor = CharacterFactory()
    CharacterSheetFactory(character=actor)
    persona = actor.sheet_data.primary_persona
    building = _owned_building(persona)
    entry = _room_in(building.area, name="Entry Hall")
    building.entry_room = entry.room_profile
    building.save(update_fields=["entry_room"])
    actor.db_location = entry
    actor.save(update_fields=["db_location"])
    return actor, building


@tag("postgres")
class RenovationCommissionTests(TestCase):
    """Commission / no-op / non-building paths reach the service's is_owner gate."""

    def setUp(self) -> None:
        self.actor, self.building = _make_owner_in_building()
        self.target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)

    def test_commission_creates_project(self) -> None:
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind="Occult Manor")
        assert result.success
        assert "Occult Manor" in result.message
        assert "project #" in result.message
        from world.projects.models import Project

        project = Project.objects.filter(kind=ProjectKind.BUILDING_RENOVATION).first()
        assert project is not None
        assert project.building_renovation_details.target_kind == self.target_kind

    def test_noop_renovation_refused(self) -> None:
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind=self.building.kind.name)
        assert not result.success
        assert "already" in result.message.lower()

    def test_non_building_room_errors(self) -> None:
        # The actor owns a *non-building* room — the owner prerequisite passes,
        # but the room isn't part of any building, so the action reports that.
        area = AreaFactory()
        bare_room = ObjectDBFactory(db_key="Void", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(objectdb=bare_room, defaults={"area": area})
        persona = self.actor.sheet_data.primary_persona
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        self.actor.db_location = bare_room
        self.actor.save(update_fields=["db_location"])
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind="Occult Manor")
        assert not result.success
        assert "building" in result.message.lower()


@tag("postgres")
class RenovationListingTests(TestCase):
    """Listing + wrong-name paths — ``is_owner`` runs in the prerequisite gate."""

    def setUp(self) -> None:
        self.actor, self.building = _make_owner_in_building()
        self.current_kind = self.building.kind
        self.other_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)

    def test_bare_invocation_lists_kinds_excluding_current(self) -> None:
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind="")
        assert not result.success
        assert "Occult Manor" in result.message
        assert self.current_kind.name not in result.message

    def test_wrong_kind_name_errors(self) -> None:
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind="Nonexistent Kind")
        assert not result.success
        assert "Nonexistent Kind" in result.message

    def test_kind_flags_shown_in_listing(self) -> None:
        action = get_action("start_building_renovation")
        result = action.run(self.actor, target_kind="")
        assert "occult" in result.message.lower()

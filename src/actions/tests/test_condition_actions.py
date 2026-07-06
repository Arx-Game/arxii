"""Action-level tests for the #1930 building-condition family.

``@tag("postgres")`` because ``IsRoomOwnerPrerequisite``'s ``is_owner`` gate
walks the ``AreaClosure`` materialized view. Setup mirrors
``test_renovation_action.py``.
"""

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingFactory
from world.buildings.models import PolishCategory, ProjectTemplate, ProjectTemplatePolishIncrement
from world.buildings.polish_services import apply_project_completion
from world.buildings.upkeep_services import set_condition_tier
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership


def _room_in(area, *, name="A Room"):
    room = ObjectDB.objects.create(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(objectdb=room, defaults={"area": area})
    return room


def _make_owner_in_building(*, gold: int = 0):
    actor = CharacterFactory()
    CharacterSheetFactory(character=actor)
    persona = actor.sheet_data.primary_persona
    area = AreaFactory(level=AreaLevel.BUILDING)
    building = BuildingFactory(area=area, owner_persona=persona)
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=area,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )
    entry = _room_in(area, name="Entry Hall")
    building.entry_room = entry.room_profile
    building.save(update_fields=["entry_room"])
    actor.db_location = entry
    actor.save(update_fields=["db_location"])
    if gold:
        transfer(amount=gold, reason="test seed", to_purse=get_or_create_purse(actor.sheet_data))
    return actor, building


def _add_upkeep_feature(building, *, weekly=10):
    cat = PolishCategory.objects.create(name=f"Opulence-{building.pk}")
    template = ProjectTemplate.objects.create(name=f"Hall-{building.pk}", weekly_upkeep_cost=weekly)
    ProjectTemplatePolishIncrement.objects.create(template=template, category=cat, value=100)
    apply_project_completion(building, template)


@tag("postgres")
class ConditionActionFamilyTests(TestCase):
    def setUp(self) -> None:
        self.actor, self.building = _make_owner_in_building(gold=1_000_000)
        _add_upkeep_feature(self.building)

    def test_refurbish_bare_invocation_quotes_status_and_cost(self) -> None:
        set_condition_tier(self.building, ConditionTier.WORN)
        result = get_action("refurbish_building").run(self.actor)
        assert not result.success
        assert "Condition: Worn." in result.message
        assert "coppers" in result.message

    def test_refurbish_confirm_restores_to_excellent(self) -> None:
        set_condition_tier(self.building, ConditionTier.WORN)
        result = get_action("refurbish_building").run(self.actor, confirm=True)
        assert result.success
        self.building.refresh_from_db()
        assert self.building.condition_tier == ConditionTier.EXCELLENT

    def test_settle_confirm_pays_arrears(self) -> None:
        self.building.upkeep_arrears = 300
        self.building.save(update_fields=["upkeep_arrears"])
        result = get_action("settle_building_arrears").run(self.actor, confirm=True)
        assert result.success
        assert "300" in result.message
        self.building.refresh_from_db()
        assert self.building.upkeep_arrears == 0

    def test_prepare_confirm_climbs_above_excellent(self) -> None:
        result = get_action("prepare_building").run(self.actor, confirm=True)
        assert result.success
        assert "Extravagantly Polished" in result.message
        self.building.refresh_from_db()
        assert self.building.condition_tier == ConditionTier.EXTRAVAGANT

    def test_prepare_with_arrears_reports_refusal(self) -> None:
        self.building.upkeep_arrears = 50
        self.building.save(update_fields=["upkeep_arrears"])
        result = get_action("prepare_building").run(self.actor, confirm=True)
        assert not result.success
        assert "settled" in result.message.lower()

    def test_toggle_ultra_upkeep_round_trip(self) -> None:
        result = get_action("toggle_ultra_upkeep").run(self.actor)
        assert result.success
        self.building.refresh_from_db()
        assert self.building.ultra_upkeep is True
        result = get_action("toggle_ultra_upkeep").run(self.actor)
        assert result.success
        self.building.refresh_from_db()
        assert self.building.ultra_upkeep is False

"""Rescue-as-clue mechanism (#931 Phase 4) — RESCUE clue kind + plant + grant + clear."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.captivity.constants import CaptivityStatus
from world.captivity.services import capture_character, resolve_captivity
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueTargetKind
from world.clues.models import Clue, RoomClue
from world.clues.services import (
    clear_rescue_clues,
    grant_clue_target,
    plant_rescue_clue,
    search_room,
)
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory


def _rescue_template(name: str = "rescue-run"):
    """A minimal grantable template (entry node → one BRANCH option)."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER find the cell",
        branch_target=second,
    )
    return template


def _finder():
    roster = RosterEntryFactory()
    return roster, roster.character_sheet.character


class PlantRescueClueTests(TestCase):
    def test_plants_a_rescue_targeted_clue_at_the_location(self) -> None:
        captivity = capture_character(captive=CharacterSheetFactory())
        room = RoomProfileFactory()

        placement = plant_rescue_clue(
            captivity,
            room,
            name="Signs of a struggle",
            description="PLACEHOLDER",
            detect_difficulty=2,
        )

        assert placement.room_profile == room
        assert placement.detect_difficulty == 2
        clue = placement.clue
        assert clue.target_kind == ClueTargetKind.RESCUE
        assert clue.target_captivity == captivity
        clue.full_clean()  # the RESCUE-target invariant holds


class GrantRescueTargetTests(TestCase):
    def _held_with_rescue(self):
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)
        captivity.rescue_template = _rescue_template()
        captivity.save()
        return captive, captivity

    def test_grant_hands_the_finder_the_rescue_mission(self) -> None:
        captive, captivity = self._held_with_rescue()
        placement = plant_rescue_clue(captivity, RoomProfileFactory(), name="x", description="y")
        roster, character = _finder()

        grant_clue_target(placement.clue, roster)

        instance = MissionInstance.objects.get(template=captivity.rescue_template)
        assert instance.rescue_target == captive
        assert instance.participants.filter(character=character, is_contract_holder=True).exists()

    def test_grant_is_noop_without_a_rescue_template(self) -> None:
        captivity = capture_character(captive=CharacterSheetFactory())  # no rescue_template
        placement = plant_rescue_clue(captivity, RoomProfileFactory(), name="x", description="y")
        roster, _ = _finder()

        grant_clue_target(placement.clue, roster)

        assert not MissionInstance.objects.exists()

    def test_grant_is_noop_once_the_captive_is_freed(self) -> None:
        _, captivity = self._held_with_rescue()
        placement = plant_rescue_clue(captivity, RoomProfileFactory(), name="x", description="y")
        resolve_captivity(captivity, status=CaptivityStatus.ESCAPED)
        roster, _ = _finder()

        grant_clue_target(placement.clue, roster)

        assert not MissionInstance.objects.exists()


class SearchFindsRescueClueTests(TestCase):
    def test_search_discovers_the_clue_and_grants_the_rescue(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)
        captivity.rescue_template = _rescue_template()
        captivity.save()
        room = RoomProfileFactory()
        plant_rescue_clue(captivity, room, name="Signs", description="y", detect_difficulty=0)
        _, character = _finder()
        search_check = CheckTypeFactory(name="Search")

        with force_check_outcome(CheckOutcomeFactory(name="Hit", success_level=3)):
            found = search_room(character, room, search_check)

        assert len(found) == 1
        assert MissionInstance.objects.filter(
            template=captivity.rescue_template, rescue_target=captive
        ).exists()


class ClearRescueCluesTests(TestCase):
    def test_clear_deletes_the_clue_and_its_placement(self) -> None:
        captivity = capture_character(captive=CharacterSheetFactory())
        placement = plant_rescue_clue(captivity, RoomProfileFactory(), name="x", description="y")
        clue_id = placement.clue_id

        clear_rescue_clues(captivity)

        assert not Clue.objects.filter(pk=clue_id).exists()
        assert not RoomClue.objects.filter(pk=placement.pk).exists()

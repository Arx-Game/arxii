"""Room-anchored clue discovery (#1154 slice A) — search_room + grant_clue_target."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.factories import ClueFactory, RoomClueFactory
from world.clues.models import CharacterClue
from world.clues.services import acquire_clue, grant_clue_target, search_room
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.missions.constants import MissionStatus
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInstance
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory


def _searcher():
    """A roster entry + its puppet character (ObjectDB), the search subject."""
    roster = RosterEntryFactory()
    return roster, roster.character_sheet.character


class SearchRoomTests(TestCase):
    def setUp(self) -> None:
        self.search_check = CheckTypeFactory(name="Search")
        self.room = RoomProfileFactory()
        self.success = CheckOutcomeFactory(name="SearchSuccess", success_level=3)
        self.failure = CheckOutcomeFactory(name="SearchFailure", success_level=-3)

    def test_finds_and_acquires_a_hidden_clue_on_success(self) -> None:
        roster, character = _searcher()
        placement = RoomClueFactory(room_profile=self.room)

        with force_check_outcome(self.success):
            found = search_room(character, self.room, self.search_check)

        assert found == [placement.clue]
        assert CharacterClue.objects.filter(roster_entry=roster, clue=placement.clue).exists()

    def test_eligibility_gate_hides_clue_from_ineligible_searcher(self) -> None:
        # An always-false rule (empty OR) gates the placement shut regardless of the
        # roll — the clue is never surfaced or acquired.
        roster, character = _searcher()
        RoomClueFactory(room_profile=self.room, eligibility_rule={"op": "OR", "of": []})

        with force_check_outcome(self.success):
            found = search_room(character, self.room, self.search_check)

        assert found == []
        assert not CharacterClue.objects.filter(roster_entry=roster).exists()

    def test_empty_eligibility_rule_is_open_to_anyone(self) -> None:
        roster, character = _searcher()
        placement = RoomClueFactory(room_profile=self.room, eligibility_rule={})

        with force_check_outcome(self.success):
            found = search_room(character, self.room, self.search_check)

        assert found == [placement.clue]
        assert CharacterClue.objects.filter(roster_entry=roster, clue=placement.clue).exists()

    def test_finds_nothing_on_failure(self) -> None:
        roster, character = _searcher()
        RoomClueFactory(room_profile=self.room)

        with force_check_outcome(self.failure):
            found = search_room(character, self.room, self.search_check)

        assert found == []
        assert not CharacterClue.objects.filter(roster_entry=roster).exists()

    def test_skips_an_already_held_clue(self) -> None:
        roster, character = _searcher()
        placement = RoomClueFactory(room_profile=self.room)
        acquire_clue(roster, placement.clue)  # already found previously

        with force_check_outcome(self.success):
            found = search_room(character, self.room, self.search_check)

        assert found == []  # not surfaced again
        assert CharacterClue.objects.filter(roster_entry=roster, clue=placement.clue).count() == 1

    def test_ignores_inactive_placements(self) -> None:
        _, character = _searcher()
        RoomClueFactory(room_profile=self.room, is_active=False)

        with force_check_outcome(self.success):
            found = search_room(character, self.room, self.search_check)

        assert found == []

    def test_automatic_mission_clue_grants_the_mission_on_find(self) -> None:
        roster, character = _searcher()
        template = _mission_template()
        clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=template,
            resolution_mode=ClueResolution.AUTOMATIC,
        )
        RoomClueFactory(room_profile=self.room, clue=clue)

        with force_check_outcome(self.success):
            search_room(character, self.room, self.search_check)

        assert _holds_mission(roster, template)

    def test_automatic_codex_clue_grants_known_on_find(self) -> None:
        roster, character = _searcher()
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry, resolution_mode=ClueResolution.AUTOMATIC)
        RoomClueFactory(room_profile=self.room, clue=clue)

        with force_check_outcome(self.success):
            search_room(character, self.room, self.search_check)

        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN


class GrantClueTargetTests(TestCase):
    def test_codex_target_becomes_known(self) -> None:
        roster = RosterEntryFactory()
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry)

        grant_clue_target(clue, roster)

        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN

    def test_mission_target_grants_the_mission(self) -> None:
        roster = RosterEntryFactory()
        template = _mission_template()
        clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=template,
        )

        grant_clue_target(clue, roster)

        assert _holds_mission(roster, template)

    def test_mission_target_skips_a_character_already_holding_it(self) -> None:
        roster = RosterEntryFactory()
        template = _mission_template()
        clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=template,
        )
        grant_clue_target(clue, roster)

        grant_clue_target(clue, roster)  # second find must not raise or double-grant

        assert MissionInstance.objects.filter(template=template).count() == 1


def _mission_template():
    """A MissionTemplate with the entry node ``staff_assign_mission`` requires."""
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


def _holds_mission(roster, template) -> bool:
    return MissionInstance.objects.filter(
        template=template,
        status=MissionStatus.ACTIVE,
        participants__character_id=roster.character_sheet.character.pk,
        participants__is_contract_holder=True,
    ).exists()

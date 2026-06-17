"""Passive clue triggers (#1160) — maybe_grant_clue_triggers on room entry."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.clues.constants import ClueResolution
from world.clues.factories import ClueFactory, ClueTriggerFactory
from world.clues.models import CharacterClue
from world.clues.services import acquire_clue, maybe_grant_clue_triggers
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.roster.factories import RosterEntryFactory


def _entrant():
    roster = RosterEntryFactory()
    return roster, roster.character_sheet.character


class ClueTriggerTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb

    def test_eligible_entrant_is_granted_the_clue(self) -> None:
        roster, character = _entrant()
        trigger = ClueTriggerFactory(room_profile=self.room_profile)

        granted = maybe_grant_clue_triggers(character, self.room)

        assert granted == [trigger.clue]
        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).exists()

    def test_already_held_clue_is_not_regranted(self) -> None:
        roster, character = _entrant()
        trigger = ClueTriggerFactory(room_profile=self.room_profile)
        acquire_clue(roster, trigger.clue)

        granted = maybe_grant_clue_triggers(character, self.room)

        assert granted == []
        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).count() == 1

    def test_ineligible_entrant_is_skipped(self) -> None:
        roster, character = _entrant()
        ClueTriggerFactory(room_profile=self.room_profile, eligibility_rule={"op": "OR", "of": []})

        granted = maybe_grant_clue_triggers(character, self.room)

        assert granted == []
        assert not CharacterClue.objects.filter(roster_entry=roster).exists()

    def test_inactive_trigger_does_not_fire(self) -> None:
        _, character = _entrant()
        ClueTriggerFactory(room_profile=self.room_profile, is_active=False)

        assert maybe_grant_clue_triggers(character, self.room) == []

    def test_no_triggers_is_a_noop(self) -> None:
        _, character = _entrant()

        assert maybe_grant_clue_triggers(character, self.room) == []

    def test_automatic_codex_clue_resolves_on_trigger(self) -> None:
        roster, character = _entrant()
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry, resolution_mode=ClueResolution.AUTOMATIC)
        ClueTriggerFactory(room_profile=self.room_profile, clue=clue)

        maybe_grant_clue_triggers(character, self.room)

        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN


class ClueTriggerOnMoveTests(TestCase):
    def test_entering_a_room_fires_the_trigger(self) -> None:
        # The at_post_move hook wires the passive grant onto real movement.
        roster, character = _entrant()
        room_profile = RoomProfileFactory()
        trigger = ClueTriggerFactory(room_profile=room_profile)

        character.move_to(room_profile.objectdb, quiet=True)

        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).exists()

"""Clue services (#1144) — acquire (idempotent) + already-known dispatch."""

from django.test import TestCase

from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.clues.services import acquire_clue, target_already_known
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.missions.factories import (
    MissionInstanceFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.roster.factories import RosterEntryFactory


class AcquireClueTests(TestCase):
    def test_acquire_is_idempotent(self) -> None:
        roster = RosterEntryFactory()
        clue = ClueFactory()

        first = acquire_clue(roster, clue)
        second = acquire_clue(roster, clue)

        assert first.pk == second.pk
        assert CharacterClue.objects.filter(roster_entry=roster, clue=clue).count() == 1


class TargetAlreadyKnownTests(TestCase):
    def test_codex_target_unknown_while_only_uncovered(self) -> None:
        entry = CodexEntryFactory()
        clue = ClueFactory(target_codex_entry=entry)
        roster = RosterEntryFactory()

        CharacterCodexKnowledgeFactory(
            roster_entry=roster, entry=entry, status=CodexKnowledgeStatus.UNCOVERED
        )
        assert target_already_known(clue, roster) is False  # uncovered != known

    def test_codex_target_known_once_entry_is_known(self) -> None:
        entry = CodexEntryFactory()
        clue = ClueFactory(target_codex_entry=entry)
        roster = RosterEntryFactory()

        assert target_already_known(clue, roster) is False

        CharacterCodexKnowledgeFactory(
            roster_entry=roster, entry=entry, status=CodexKnowledgeStatus.KNOWN
        )
        assert target_already_known(clue, roster) is True

    def test_mission_target_known_when_character_holds_a_run(self) -> None:
        template = MissionTemplateFactory()
        clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=template,
        )
        roster = RosterEntryFactory()

        assert target_already_known(clue, roster) is False

        character = roster.character_sheet.character
        instance = MissionInstanceFactory(template=template)
        MissionParticipantFactory(instance=instance, character=character)

        assert target_already_known(clue, roster) is True

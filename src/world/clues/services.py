"""Clue services (#1144) — acquire a clue, and the already-known check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.clues.constants import ClueTargetKind
from world.clues.models import CharacterClue, Clue

if TYPE_CHECKING:
    from world.roster.models import RosterEntry


def acquire_clue(roster_entry: RosterEntry, clue: Clue) -> CharacterClue:
    """Record that a character has found a clue (idempotent).

    The single entry point acquisition surfaces (room search, triggers) call once a
    clue is surfaced to a character. Creates the held-clue row on first find and
    returns the existing one thereafter — re-finding the same clue is harmless.
    """
    held, _ = CharacterClue.objects.get_or_create(roster_entry=roster_entry, clue=clue)
    return held


def target_already_known(clue: Clue, roster_entry: RosterEntry) -> bool:
    """Whether the character already has what this clue points at.

    Drives the "this clue refers to X, but you already know this" flag — discovery
    surfaces a known-target clue rather than hiding it. Dispatches on target kind.
    """
    if clue.target_kind == ClueTargetKind.CODEX:
        from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
        from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

        return CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            entry=clue.target_codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        ).exists()

    if clue.target_kind == ClueTargetKind.MISSION:
        from world.missions.models import MissionParticipant  # noqa: PLC0415

        character = roster_entry.character_sheet.character
        if character is None:
            return False
        return MissionParticipant.objects.filter(
            character=character,
            instance__template=clue.target_mission,
        ).exists()

    return False

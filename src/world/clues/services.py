"""Clue services (#1144) — acquire a clue, and the already-known check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import CharacterClue, Clue, RoomClue

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.checks.models import CheckType
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


def grant_clue_target(clue: Clue, roster_entry: RosterEntry) -> None:
    """AUTOMATIC resolution — grant a clue's target to the character on the spot.

    CODEX: the character learns the entry (KNOWN, firing the codex reactivity hook).
    Other target kinds (mission/secret) are a documented extension point — rescue grants
    its mission through the rescue flow, secrets are unbuilt.
    """
    if clue.target_kind != ClueTargetKind.CODEX:
        return
    entry = clue.target_codex_entry
    if entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    knowledge, _ = CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=entry,
        defaults={"status": CodexKnowledgeStatus.UNCOVERED},
    )
    knowledge.add_progress(entry.learn_threshold)


def search_room(
    character: ObjectDB,
    room_profile: RoomProfile,
    search_check_type: CheckType,
) -> list[Clue]:
    """Search a room: roll ``search_check_type`` against each hidden clue's difficulty.

    Surfaces and acquires every not-yet-held clue the character spots (a success against
    its ``detect_difficulty``); AUTOMATIC clues also grant their target immediately. The
    caller (the Search action) charges AP + fatigue and resolves which check type to use.
    Returns the clues found this search (empty if the searcher has no roster entry).
    """
    from world.checks.services import perform_check  # noqa: PLC0415

    roster_entry = _roster_entry_for(character)
    if roster_entry is None:
        return []
    held_ids = set(
        CharacterClue.objects.filter(roster_entry=roster_entry).values_list("clue_id", flat=True)
    )
    found: list[Clue] = []
    placements = RoomClue.objects.filter(room_profile=room_profile, is_active=True).select_related(
        "clue"
    )
    for placement in placements:
        clue = placement.clue
        if clue.pk in held_ids:
            continue
        result = perform_check(
            character, search_check_type, target_difficulty=placement.detect_difficulty
        )
        if result.outcome is None or result.outcome.success_level < 0:
            continue
        acquire_clue(roster_entry, clue)
        if clue.resolution_mode == ClueResolution.AUTOMATIC:
            grant_clue_target(clue, roster_entry)
        found.append(clue)
    return found


def _roster_entry_for(character: ObjectDB) -> RosterEntry | None:
    """The searching character's roster entry, or None (off-roster / sheet-less)."""
    try:
        return character.sheet_data.roster_entry
    except (AttributeError, ObjectDoesNotExist):
        return None

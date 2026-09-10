"""Read selectors for character progression (#954, #3748).

`current_path_for_character` previously lived in `world.magic.audere_majora`,
but it queries the progression model `CharacterPathHistory`; it belongs here.
Magic imports it back for `eligible_paths_for_threshold`.

`character_xp_ledger` answers "what has a player earned on, and invested in, this
character" for the sheet, the admin and the death-kudos cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Q, Sum
from evennia.objects.models import ObjectDB

from world.classes.models import Path
from world.classes.services import stage_for_level
from world.progression.models import CharacterPathHistory, CharacterXP

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def current_path_for_character(character: ObjectDB) -> Path | None:  # noqa: OBJECTDB_PARAM
    """Return the Path from the latest CharacterPathHistory row, or None."""
    history = (
        # pk filter: callers pass the ObjectDB; the FK targets CharacterSheet (PK-shared).
        CharacterPathHistory.objects.filter(character_id=character.pk)
        .select_related("path")
        .order_by("-selected_at")
        .first()
    )
    if history is None:
        return None
    return history.path


def next_path_options(character: ObjectDB) -> list[Path]:  # noqa: OBJECTDB_PARAM
    """Return the active next-stage child paths the character can pursue.

    Empty when the character has no current path or the current path is terminal.
    """
    current = current_path_for_character(character)
    if current is None:
        return []
    # Deliberately unfiltered by stage (unlike eligible_paths_for_threshold, which
    # pins the crossing's target_stage): this is the generic "what can I pursue next"
    # picker. The path tree's children are the immediate next stage by construction.
    return list(current.child_paths.filter(is_active=True))


def eligible_advanced_paths_for(sheet: CharacterSheet) -> list[Path]:
    """Active child paths of the character's current path at their next level's stage.

    Mirrors the gate in advance_class_level_via_session's semi-crossing resolver
    (pre-fire semantics: target stage = stage_for_level(current_level + 1)).
    Empty when not at a stage boundary / no current path.

    Paths with authored TraitRequirements the character does not meet are
    filtered out (#2538). Fail-open: a path with no requirements is always eligible.
    """
    from world.progression.services.spends import check_requirements_for_path  # noqa: PLC0415

    current = current_path_for_character(sheet.character)
    if current is None:
        return []
    target_stage = stage_for_level(sheet.current_level + 1)
    candidates = current.child_paths.filter(stage=target_stage, is_active=True)
    return [path for path in candidates if check_requirements_for_path(sheet.character, path)[0]]


def resolve_advanced_path_by_name(sheet: CharacterSheet, name: str) -> Path | None:
    """Case-insensitive match of *name* against eligible_advanced_paths_for(sheet)."""
    needle = (name or "").strip().casefold()
    for path in eligible_advanced_paths_for(sheet):
        if path.name.casefold() == needle:
            return path
    return None


@dataclass(frozen=True)
class CharacterXPLedger:
    """What a player has earned on, and invested in, one character (#3748).

    The reviewer's two questions, side by side. ``spent`` is the number the
    death-kudos cap is sized on (ADR-0131) and that character-loss
    reimbursement will read; it can exceed ``earned``, because XP earned on one
    character is routinely spent on another. ``locked`` is the separate CG
    conversion pool, reported apart so it is never mistaken for play earnings.
    """

    earned: int
    spent: int
    locked: int


def character_xp_ledger(sheet: CharacterSheet) -> CharacterXPLedger:
    """Lifetime XP earned on and spent on ``sheet``.

    One aggregate over the character's ``CharacterXP`` rows. Rows exist only
    once something has moved, so a character nobody has awarded or spent on
    reports zeroes rather than raising.
    """
    rows = CharacterXP.objects.filter(character_id=sheet.pk).aggregate(
        earned=Sum("total_earned", filter=Q(transferable=True)),
        spent=Sum("total_spent"),
        locked=Sum("total_earned", filter=Q(transferable=False)),
    )
    return CharacterXPLedger(
        earned=rows["earned"] or 0,
        spent=rows["spent"] or 0,
        locked=rows["locked"] or 0,
    )

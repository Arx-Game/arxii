"""Read selectors for character path progression (#954).

`current_path_for_character` previously lived in `world.magic.audere_majora`,
but it queries the progression model `CharacterPathHistory`; it belongs here.
Magic imports it back for `eligible_paths_for_threshold`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.classes.models import Path
from world.classes.services import stage_for_level
from world.progression.models import CharacterPathHistory

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

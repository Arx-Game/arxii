"""Read selectors for character path progression (#954).

`current_path_for_character` previously lived in `world.magic.audere_majora`,
but it queries the progression model `CharacterPathHistory`; it belongs here.
Magic imports it back for `eligible_paths_for_threshold`.
"""

from evennia.objects.models import ObjectDB

from world.classes.models import Path
from world.progression.models import CharacterPathHistory


def current_path_for_character(character: ObjectDB) -> Path | None:  # noqa: OBJECTDB_PARAM
    """Return the Path from the latest CharacterPathHistory row, or None."""
    history = (
        CharacterPathHistory.objects.filter(character=character)
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
    return list(current.child_paths.filter(is_active=True))

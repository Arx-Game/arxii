"""Service functions for a character's declared next-path intent (#543/#1348).

The path-intent web view previously mutated the model directly; these functions
are the single mutation seam shared by the web ``PathIntentViewSet`` and the
telnet ``CmdPathIntent`` via ``SetPathIntentAction`` / ``ClearPathIntentAction``.
"""

from world.character_sheets.models import CharacterSheet
from world.classes.models import Path
from world.progression.models.path_intent import PathIntent


def set_path_intent(sheet: CharacterSheet, path: Path) -> PathIntent:
    """Declare or replace the character's intended next path (re-declaring overwrites)."""
    intent, _ = PathIntent.objects.update_or_create(
        character_sheet=sheet,
        defaults={"intended_path": path},
    )
    return intent


def clear_path_intent(sheet: CharacterSheet) -> None:
    """Clear the character's declared intent (idempotent — no error if absent)."""
    PathIntent.objects.filter(character_sheet=sheet).delete()

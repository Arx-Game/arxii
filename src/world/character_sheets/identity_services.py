from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterIdentity, CharacterSheet
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


def ensure_character_identity(character: ObjectDB) -> CharacterIdentity:
    """Ensure a CharacterIdentity exists for the character.

    Creates a CharacterSheet and primary Persona if needed, then a
    CharacterIdentity pointing at the primary persona. Idempotent -- safe
    to call multiple times.

    NOTE: CharacterIdentity is slated for removal in a later task. Callers
    should prefer `character.sheet_data.primary_persona` directly.
    """
    try:
        return character.character_identity
    except CharacterIdentity.DoesNotExist:
        pass

    sheet, _ = CharacterSheet.objects.get_or_create(character=character)
    persona, _ = Persona.objects.get_or_create(
        character_sheet=sheet,
        persona_type=PersonaType.PRIMARY,
        defaults={"name": character.db_key},
    )
    return CharacterIdentity.objects.create(
        character=character,
        active_persona=persona,
    )

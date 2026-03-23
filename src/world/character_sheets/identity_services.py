from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterIdentity
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


def ensure_character_identity(character: ObjectDB) -> CharacterIdentity:
    """Ensure a CharacterIdentity exists for the character.

    Creates the primary persona and CharacterIdentity if needed.
    Idempotent -- safe to call multiple times.

    The creation order handles the circular FK (Persona -> CharacterIdentity,
    CharacterIdentity -> Persona) by creating CharacterIdentity first with
    active_persona=NULL, then creating the Persona, then setting active_persona.
    """
    try:
        return character.character_identity
    except CharacterIdentity.DoesNotExist:
        pass

    # Create CharacterIdentity with active_persona=NULL (temporarily)
    identity = CharacterIdentity.objects.create(
        character=character,
        active_persona=None,
    )

    # Create primary persona
    persona = Persona.objects.create(
        character_identity=identity,
        character=character,
        name=character.db_key,
        persona_type=PersonaType.PRIMARY,
    )

    # Set active persona
    identity.active_persona = persona
    identity.save(update_fields=["active_persona_id"])

    return identity

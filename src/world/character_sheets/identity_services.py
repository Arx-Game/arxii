from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterIdentity, Guise
from world.scenes.models import Persona


def ensure_character_identity(character: ObjectDB) -> CharacterIdentity:
    """Ensure a CharacterIdentity exists for the character.

    Creates the default guise, default persona, and CharacterIdentity if needed.
    Idempotent -- safe to call multiple times.
    """
    # Ensure default guise exists (save() auto-creates default persona)
    guise, _ = Guise.objects.get_or_create(
        character=character,
        is_default=True,
        defaults={"name": character.db_key},
    )

    # Get the default persona (created by Guise.save)
    persona = Persona.objects.filter(
        guise=guise,
        is_fake_name=False,
        participation=None,
    ).first()
    if persona is None:
        persona = Persona.objects.create(
            guise=guise,
            is_fake_name=False,
            participation=None,
            name=guise.name,
            character=character,
        )

    # Ensure CharacterIdentity exists
    identity, _ = CharacterIdentity.objects.get_or_create(
        character=character,
        defaults={
            "primary_guise": guise,
            "active_guise": guise,
            "active_persona": persona,
        },
    )

    return identity

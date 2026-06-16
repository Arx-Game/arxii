"""Singleton 'Narrator' persona that authors system OUTCOME interactions.

The Narrator is a scenes-layer concept: a shared system Persona that authors
durable OUTCOME lines so they appear in the scene log. Moved here from
world/combat/narrator so scenes-layer code can import it without a
wrong-direction dependency.
"""

from __future__ import annotations

from world.scenes.models import Persona

NARRATOR_PERSONA_NAME = "Narrator"


def get_or_create_narrator_persona() -> Persona:
    """Return the singleton Narrator persona, creating it on first use.

    Looked up by the unique persona name. When absent, creates a Character +
    CharacterSheet + PRIMARY Persona triple via create_character_with_sheet
    (the same invariant-preserving path factories use), then returns its
    persona.
    """
    existing = Persona.objects.filter(name=NARRATOR_PERSONA_NAME).first()
    if existing is not None:
        # Heal rows that predate the is_system flag (#643).
        if not existing.is_system:
            existing.is_system = True
            existing.save(update_fields=["is_system"])
        return existing

    from world.character_sheets.services import (  # noqa: PLC0415
        create_character_with_sheet,
    )

    _character, _sheet, persona = create_character_with_sheet(
        character_key=NARRATOR_PERSONA_NAME,
        primary_persona_name=NARRATOR_PERSONA_NAME,
    )
    persona.is_system = True
    persona.save(update_fields=["is_system"])
    return persona

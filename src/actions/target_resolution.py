"""Resolve a persona-pk action target to the character underneath it (#4030).

Web surfaces name personas: a pose, a room-list row and a Who row all carry the persona
the viewer sees, which may be a mask. Registry actions act on the character ``ObjectDB``
underneath. This is the single persona-to-character hop, shared by Look, Identify,
Challenge and the scene guard actions; each action still applies its own perception,
consent and presence checks after it, so resolving never grants anything by itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def resolve_persona_pk_to_character(persona_id: object) -> ObjectDB | None:
    """Return the character behind the ``Persona`` with pk ``persona_id``, or ``None``."""
    from world.scenes.models import Persona  # noqa: PLC0415

    if persona_id is None:
        return None
    try:
        persona = (
            Persona.objects.filter(pk=persona_id)
            .select_related("character_sheet__character")
            .first()
        )
    except (TypeError, ValueError):
        return None
    if persona is None:
        return None
    return persona.character_sheet.character

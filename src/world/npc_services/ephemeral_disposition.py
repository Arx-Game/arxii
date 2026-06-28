"""Ephemeral disposition store for persona-less NPCs outside combat (#1591).

A persona-less NPC (mook, beast, random guard) has no Persona, so it has no
``NPCStanding`` row. Its disposition toward an acting PC lives in a
session/scene-scoped store — mirroring the ``InteractionSession``/``request.
session`` pattern (ADR-0058). It self-cleans: when the mook is deleted at
encounter end (combat) or the session clears (social), the disposition is gone.

The store is a dict-like mapping (Django ``request.session`` in production; a
plain ``dict`` in tests). Keys are ``"ephemeral_disposition:<pc_sheet_pk>:<npc_pk>"``.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet

_PREFIX = "ephemeral_disposition"


def _key(pc_sheet: CharacterSheet, npc_character: Character) -> str:
    return f"{_PREFIX}:{pc_sheet.pk}:{npc_character.pk}"


def get_disposition(
    store: MutableMapping, pc_sheet: CharacterSheet, npc_character: Character
) -> int:
    """Return the ephemeral disposition (default 0)."""
    return int(store.get(_key(pc_sheet, npc_character), 0))


def adjust_disposition(
    store: MutableMapping,
    pc_sheet: CharacterSheet,
    npc_character: Character,
    *,
    delta: int,
) -> int:
    """Apply ``delta`` to the ephemeral disposition; return the new value."""
    key = _key(pc_sheet, npc_character)
    new_value = int(store.get(key, 0)) + delta
    store[key] = new_value
    return new_value


def clear_for_pair(
    store: MutableMapping, pc_sheet: CharacterSheet, npc_character: Character
) -> None:
    """Remove the single (pc_sheet, npc) entry (used by promotion flush, Task 7)."""
    store.pop(_key(pc_sheet, npc_character), None)


def clear_scene_disposition(store: MutableMapping, pc_sheet: CharacterSheet) -> None:
    """Remove all ephemeral disposition entries for one PC (scene end)."""
    prefix = f"{_PREFIX}:{pc_sheet.pk}:"
    for key in [k for k in store if isinstance(k, str) and k.startswith(prefix)]:
        del store[key]

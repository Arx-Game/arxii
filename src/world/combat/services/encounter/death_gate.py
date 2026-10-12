"""The death gate for characters who would die."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import CharacterKilledPayload
from world.combat import services as _svc

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character


def _character_has_death_deferred(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Return True if the character has any active condition granting death_deferred.

    Delegates to the canonical shared helper in world.conditions.services so
    there is one query definition. Kept as a thin wrapper for call-site
    compatibility within this module.
    """
    from world.conditions.services import has_death_deferred  # noqa: PLC0415

    return has_death_deferred(character)


def _emit_death_gate(character: Character, room: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Fire the death gate: defer when death-deferred is active, else CHARACTER_KILLED."""
    if _character_has_death_deferred(character):
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        try:
            vitals = CharacterVitals.objects.get(character_sheet=character.sheet_data)
            vitals.death_deferred_pending = True
            vitals.save(update_fields=["death_deferred_pending"])
        except CharacterVitals.DoesNotExist:
            pass
    else:
        _svc.emit_event(
            EventName.CHARACTER_KILLED,
            CharacterKilledPayload(
                character=character,
                source_event=EventName.DAMAGE_PRE_APPLY,
            ),
            location=room,
        )

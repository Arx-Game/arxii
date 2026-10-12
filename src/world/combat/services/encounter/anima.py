"""Looking up a character's anima."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models.anima import CharacterAnima


def _get_anima(character: ObjectDB) -> CharacterAnima | None:  # noqa: OBJECTDB_PARAM
    """Return the CharacterAnima row for *character*, or None if absent.

    Uses the ``anima`` reverse OneToOneField relation set by
    ``CharacterAnima.character`` (``related_name="anima"``). Mirrors the
    accessor used by ``CombatParticipant.available_strain``.

    Returns None when no CharacterAnima row exists (defensive; characters
    without an anima pool cannot sustain reactive conditions).
    """
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    try:
        return CharacterAnima.objects.get(character_id=character.pk)
    except CharacterAnima.DoesNotExist:
        return None

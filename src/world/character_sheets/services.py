"""Service functions for character sheets."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import transaction
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from world.character_sheets.models import CharacterIdentity, CharacterSheet
from world.roster.models import RosterEntry
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


def can_edit_character_sheet(
    user: AbstractBaseUser | AnonymousUser, roster_entry: RosterEntry
) -> bool:
    """True if the user is the original creator (player_number=1) or staff.

    Requires tenures to be prefetched with select_related("player_data__account").
    """
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    first = roster_entry.first_tenure
    return first is not None and first.player_data.account == user


@transaction.atomic
def create_character_with_sheet(
    *,
    character_key: str,
    primary_persona_name: str,
    typeclass: str = "typeclasses.characters.Character",
    **sheet_kwargs: Any,
) -> tuple[ObjectDB, CharacterSheet, Persona]:
    """Atomically create a Character + CharacterSheet + PRIMARY Persona.

    This is the blessed way to create a playable character. The three
    objects are created in a single database transaction so partial
    failures do not leave the system in an inconsistent state.

    Args:
        character_key: The in-game name/key for the Character object.
        primary_persona_name: The name for the PRIMARY persona.
        typeclass: Optional typeclass path (default: standard Character).
        **sheet_kwargs: Additional CharacterSheet fields (age, gender, etc.).

    Returns:
        tuple[ObjectDB, CharacterSheet, Persona]

    Raises:
        Anything the underlying create_object / save calls raise. The
        transaction rolls back on any failure.
    """
    character = create_object(typeclass=typeclass, key=character_key)
    sheet = CharacterSheet.objects.create(character=character, **sheet_kwargs)
    primary_persona = Persona.objects.create(
        character_sheet=sheet,
        # character_identity and character set during the transition period.
        # Task 15 will drop these.
        character=character,
        character_identity=_ensure_identity(character),
        name=primary_persona_name,
        persona_type=PersonaType.PRIMARY,
    )
    return character, sheet, primary_persona


def _ensure_identity(character: ObjectDB) -> CharacterIdentity:
    """Temporary shim during the refactor transition.

    Before Task 15 drops CharacterIdentity, the Persona model still has
    non-nullable FK to CharacterIdentity. Create one if absent.
    """
    identity, _ = CharacterIdentity.objects.get_or_create(character=character)
    return identity

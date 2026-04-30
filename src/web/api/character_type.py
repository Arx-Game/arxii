"""Derive high-level character_type for the account payload."""

from typing import Final

from evennia.objects.models import ObjectDB

TYPECLASS_TO_CHARACTER_TYPE: Final[dict[str, str]] = {
    "typeclasses.gm_characters.GMCharacter": "GM",
    "typeclasses.gm_characters.StaffCharacter": "STAFF",
}


def derive_character_type(character: ObjectDB) -> str:
    """Map a Character typeclass path to a high-level account-payload type.

    Returns "PC" for the default Character typeclass, "GM" for GMCharacter,
    "STAFF" for StaffCharacter. Future typeclasses (e.g., NPC) plug in here.
    """
    return TYPECLASS_TO_CHARACTER_TYPE.get(character.db_typeclass_path, "PC")

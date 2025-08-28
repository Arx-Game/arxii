"""Type definitions for Arx II typeclasses."""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    from typeclasses.characters import Character

    # noinspection PyUnresolvedReferences
    from typeclasses.exits import Exit

    # noinspection PyUnresolvedReferences
    from typeclasses.objects import Object

    # noinspection PyUnresolvedReferences
    from typeclasses.rooms import Room

# Union type representing any of our custom typeclasses
# Add new typeclasses here as they are created
ArxTypeclass = Union[
    "Character",
    "Room",
    "Exit",
    "Object",
]

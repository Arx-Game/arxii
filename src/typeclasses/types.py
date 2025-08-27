"""Type definitions for Arx II typeclasses."""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from typeclasses.exits import Exit
    from typeclasses.objects import Object
    from typeclasses.rooms import Room

# Union type representing any of our custom typeclasses
# Add new typeclasses here as they are created
ArxTypeclass = Union[
    "Character",
    "Room",
    "Exit",
    "Object",
]

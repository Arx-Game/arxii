"""
Data handlers for Evennia objects.

This package provides specialized handlers for different object types,
allowing unified data access across the type hierarchy.
"""

from evennia_extensions.data_handlers.base_data import BaseItemDataHandler
from evennia_extensions.data_handlers.character_data import CharacterItemDataHandler
from evennia_extensions.data_handlers.exit_data import ExitItemDataHandler
from evennia_extensions.data_handlers.object_data import ObjectItemDataHandler
from evennia_extensions.data_handlers.room_data import RoomItemDataHandler

__all__ = [
    "BaseItemDataHandler",
    "CharacterItemDataHandler",
    "ExitItemDataHandler",
    "ObjectItemDataHandler",
    "RoomItemDataHandler",
]

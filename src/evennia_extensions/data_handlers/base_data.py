"""
Base item data handler for all Evennia object types.

This provides a unified interface for accessing basic object properties
and ensures compatibility with Django REST Framework serialization.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class BaseItemDataHandler:
    """
    Base handler for object data access that works with any Evennia object.

    This provides a unified interface for accessing basic object properties
    and ensures compatibility with Django REST Framework serialization.
    """

    def __init__(self, obj: "DefaultObject"):
        self.obj = obj

    def __class_getitem__(cls, item):
        # Prevent metaclass confusion that can cause issubclass errors
        raise TypeError(f"'{cls.__name__}' object is not subscriptable")

    def __instancecheck__(self, instance):
        # Prevent isinstance confusion in DRF serialization
        return isinstance(instance, type(self))

    def __subclasscheck__(self, subclass):
        # Prevent issubclass confusion in DRF serialization
        return issubclass(subclass, type(self))

    # Basic properties that all objects can provide
    @property
    def name(self) -> str:
        """Object's display name."""
        return self.obj.db_key

    @property
    def key(self) -> str:
        """Object's key (same as name for most objects)."""
        return self.obj.db_key

    @property
    def longname(self) -> str:
        """Long form name from display data."""
        display_data = self._get_display_data()
        return display_data.longname or ""

    # Default empty values for character-specific fields
    # These ensure the CharacterSerializer doesn't crash on regular objects
    @property
    def age(self) -> int:
        """Default age for non-character objects."""
        return 0

    @property
    def gender(self) -> str:
        """Default gender for non-character objects."""
        return ""

    @property
    def concept(self) -> str:
        """Default concept for non-character objects."""
        return ""

    @property
    def family(self) -> str:
        """Default family for non-character objects."""
        return ""

    @property
    def vocation(self) -> str:
        """Default vocation for non-character objects."""
        return ""

    @property
    def social_rank(self) -> int:
        """Default social rank for non-character objects."""
        return 0

    @property
    def background(self) -> str:
        """Default background for non-character objects."""
        return ""

    @property
    def race(self):
        """Default race for non-character objects."""
        return None

    @property
    def subrace(self):
        """Default subrace for non-character objects."""
        return None

    @property
    def quote(self) -> str:
        """Default quote for non-character objects."""
        return ""

    def _get_display_data(self):
        """Get or create display data for this object, with caching."""
        if getattr(self, "_display_data_cache", None) is None:
            from evennia_extensions.models import ObjectDisplayData

            self._display_data_cache, created = ObjectDisplayData.objects.get_or_create(
                object=self.obj, defaults={"longname": ""}
            )
        return self._display_data_cache

    def get_display_description(self) -> str:
        """Get object's current display description from ObjectDisplayData."""
        display_data = self._get_display_data()
        return display_data.get_display_description() or ""

    def get_display_name(self, include_colored=True):
        """
        Get the appropriate display name with fallback hierarchy.

        Args:
            include_colored (bool): Whether to include colored names

        Returns:
            str: The most appropriate display name
        """
        display_data = self._get_display_data()
        return display_data.get_display_name(include_colored=include_colored)

    @property
    def colored_name(self) -> str:
        """Character's colored name from display data."""
        display_data = self._get_display_data()
        return display_data.colored_name or ""

    @property
    def permanent_description(self) -> str:
        """Character's permanent description from display data."""
        display_data = self._get_display_data()
        return display_data.permanent_description or ""

    @property
    def temporary_description(self) -> str:
        """Character's temporary description from display data."""
        display_data = self._get_display_data()
        return display_data.temporary_description or ""

    @property
    def thumbnail(self):
        """Character's thumbnail from display data."""
        display_data = self._get_display_data()
        return display_data.thumbnail

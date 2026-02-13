"""
Natural key mixins for Django models.

These mixins add natural_key() methods and custom managers for Django's
fixture serialization system. Natural keys allow fixtures to work across
different database instances where primary key IDs may differ.

Usage:
    class Category(NaturalKeyMixin, models.Model):
        name = models.CharField(unique=True)

        class NaturalKeyConfig:
            fields = ["name"]

        objects = NaturalKeyManager()

    class Item(NaturalKeyMixin, models.Model):
        name = models.CharField(max_length=100)
        category = models.ForeignKey(Category, on_delete=models.CASCADE)

        class Meta:
            unique_together = [("name", "category")]

        class NaturalKeyConfig:
            fields = ["name", "category"]
            dependencies = ["myapp.Category"]

        objects = NaturalKeyManager()

    # natural_key() flattens FK natural keys into the tuple:
    # item.natural_key() -> ("widget", "electronics")
    #   where "widget" is item.name and "electronics" is category.natural_key()

    # get_by_natural_key() reconstructs FK lookups automatically:
    # Item.objects.get_by_natural_key("widget", "electronics")
    #   -> looks up Category by natural_key("electronics") first
    #   -> then looks up Item with name="widget", category=<Category instance>
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models.fields.related import ForeignKey

if TYPE_CHECKING:
    from collections.abc import Sequence


class NaturalKeyConfigError(ValueError):
    """Raised when NaturalKeyConfig is missing or invalid."""


class NaturalKeyManager(models.Manager["NaturalKeyMixin"]):
    """Manager that supports get_by_natural_key lookups."""

    def get_by_natural_key(self, *args: Any) -> NaturalKeyMixin:
        """
        Look up object by natural key fields.

        For ForeignKey fields, this method introspects the related model to
        determine how many natural key values belong to that FK, consumes them
        from args, and looks up the related object first.
        """
        if not hasattr(self.model, "NaturalKeyConfig"):
            msg = f"{self.model.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        config = self.model.NaturalKeyConfig
        fields: Sequence[str] = config.fields

        # Build lookup dict, handling FKs by consuming multiple args if needed
        lookup: dict[str, Any] = {}
        args_list = list(args)

        for field_name in fields:
            if not args_list:
                msg = f"Not enough natural key values provided for {self.model.__name__}"
                raise NaturalKeyConfigError(msg)

            # Check if this field is a ForeignKey
            field = self.model._meta.get_field(field_name)  # noqa: SLF001
            if isinstance(field, ForeignKey):
                related_model = field.related_model
                # Check if related model has natural key support
                if hasattr(related_model, "NaturalKeyConfig"):
                    # Calculate how many args we need for this FK's natural key
                    num_args = _count_natural_key_args(related_model)
                    if len(args_list) < num_args:
                        msg = (
                            f"Not enough values for FK {field_name}: "
                            f"expected {num_args}, have {len(args_list)}"
                        )
                        raise NaturalKeyConfigError(msg)
                    fk_args = args_list[:num_args]
                    args_list = args_list[num_args:]
                    # Handle nullable FKs: if all consumed args are None,
                    # the FK itself is null
                    if all(v is None for v in fk_args):
                        lookup[field_name] = None
                    else:
                        # Look up the related object
                        related_obj = related_model.objects.get_by_natural_key(*fk_args)
                        lookup[field_name] = related_obj
                else:
                    # FK without natural key - use single value as PK
                    lookup[field_name] = args_list.pop(0)
            else:
                # Regular field - use single value
                lookup[field_name] = args_list.pop(0)

        if args_list:
            msg = f"Too many natural key values for {self.model.__name__}: {len(args)} given"
            raise NaturalKeyConfigError(msg)

        return self.get(**lookup)


def _count_natural_key_args(model: type) -> int:
    """
    Recursively count how many args a model's natural key consumes.

    For models with FK fields that also have natural keys, this recursively
    counts the total number of args needed.
    """
    if not hasattr(model, "NaturalKeyConfig"):
        return 1  # No natural key config = assume single PK value

    fields = model.NaturalKeyConfig.fields
    count = 0
    for field_name in fields:
        field = model._meta.get_field(field_name)  # noqa: SLF001
        if isinstance(field, ForeignKey):
            related_model = field.related_model
            count += _count_natural_key_args(related_model)
        else:
            count += 1
    return count


class NaturalKeyMixin:
    """
    Mixin that adds natural_key() method based on NaturalKeyConfig.

    Define NaturalKeyConfig.fields as a list of field names that uniquely
    identify the object. For foreign keys, use the related object's natural
    key by specifying the field name (the mixin will call natural_key() on it).
    """

    def natural_key(self) -> tuple[Any, ...]:
        """Return natural key tuple for this object."""
        if not hasattr(self.__class__, "NaturalKeyConfig"):
            msg = f"{self.__class__.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        config = self.__class__.NaturalKeyConfig
        key_parts: list[Any] = []
        for field_name in config.fields:
            value = getattr(self, field_name)
            # If value is a model instance, get its natural key
            if hasattr(value, "natural_key"):
                key_parts.extend(value.natural_key())
            else:
                key_parts.append(value)

        return tuple(key_parts)

    @classmethod
    def natural_key_dependencies(cls) -> list[str]:
        """Return list of model dependencies for serialization order."""
        if not hasattr(cls, "NaturalKeyConfig"):
            return []
        config = cls.NaturalKeyConfig
        if hasattr(config, "dependencies"):
            return config.dependencies
        return []

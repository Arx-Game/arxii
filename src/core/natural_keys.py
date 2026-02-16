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

Self-referential FKs (ForeignKey("self")) are handled specially:
    # Instead of flattening (which would require infinite args for variable
    # tree depth), self-referential FK values are nested as a single arg:
    #   facet.natural_key() -> ("Wolf", ["Mammals", ["Creatures", None]])
    #   Root facet: ("Creatures", None)
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

        Self-referential FKs consume a single arg that is either None (null FK)
        or a nested list to be recursively resolved.
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

            field = self.model._meta.get_field(field_name)  # noqa: SLF001
            if isinstance(field, ForeignKey):
                _resolve_fk_arg(self.model, field, field_name, args_list, lookup)
            else:
                lookup[field_name] = args_list.pop(0)

        if args_list:
            msg = f"Too many natural key values for {self.model.__name__}: {len(args)} given"
            raise NaturalKeyConfigError(msg)

        return self.get(**lookup)


def _resolve_fk_arg(
    model: type,
    field: ForeignKey,
    field_name: str,
    args_list: list[Any],
    lookup: dict[str, Any],
) -> None:
    """Consume FK arg(s) from *args_list* and populate *lookup*."""
    related_model = field.related_model

    if related_model is model:
        # Self-referential FK: single arg (None or nested list)
        raw_value = args_list.pop(0)
        if raw_value is None:
            lookup[field_name] = None
        else:
            lookup[field_name] = related_model.objects.get_by_natural_key(*raw_value)
        return

    if hasattr(related_model, "NaturalKeyConfig"):
        num_args = count_natural_key_args(related_model)
        if len(args_list) < num_args:
            msg = (
                f"Not enough values for FK {field_name}: expected {num_args}, have {len(args_list)}"
            )
            raise NaturalKeyConfigError(msg)
        fk_args = args_list[:num_args]
        args_list[:num_args] = []
        # Handle nullable FKs: if all consumed args are None, the FK is null
        if all(v is None for v in fk_args):
            lookup[field_name] = None
        else:
            lookup[field_name] = related_model.objects.get_by_natural_key(*fk_args)
        return

    # FK without natural key - use single value as PK
    lookup[field_name] = args_list.pop(0)


def count_natural_key_args(model: type, _seen: set[type] | None = None) -> int:
    """
    Recursively count how many args a model's natural key consumes.

    For models with FK fields that also have natural keys, this recursively
    counts the total number of args needed.

    Self-referential and circular FK references are treated as consuming
    a single arg (a nested list or None), preventing infinite recursion.
    """
    if not hasattr(model, "NaturalKeyConfig"):
        return 1  # No natural key config = assume single PK value

    if _seen is None:
        _seen = set()

    fields = model.NaturalKeyConfig.fields
    count = 0
    for field_name in fields:
        field = model._meta.get_field(field_name)  # noqa: SLF001
        if isinstance(field, ForeignKey):
            related_model = field.related_model
            if related_model is model or related_model in _seen:
                # Self-referential or circular: single nested value
                count += 1
            else:
                _seen.add(model)
                count += count_natural_key_args(related_model, _seen)
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
        """Return natural key tuple for this object.

        Self-referential FK values are nested as a single element (list or
        None) rather than flattened, so the arg count stays fixed regardless
        of tree depth.
        """
        if not hasattr(self.__class__, "NaturalKeyConfig"):
            msg = f"{self.__class__.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        config = self.__class__.NaturalKeyConfig
        key_parts: list[Any] = []
        for field_name in config.fields:
            value = getattr(self, field_name)
            field = self.__class__._meta.get_field(field_name)  # noqa: SLF001
            is_self_ref = isinstance(field, ForeignKey) and field.related_model is self.__class__

            if is_self_ref:
                # Self-referential FK: nest as single value
                if value is not None and hasattr(value, "natural_key"):
                    key_parts.append(list(value.natural_key()))
                else:
                    key_parts.append(None)
            elif hasattr(value, "natural_key"):
                # Regular FK: flatten into tuple
                key_parts.extend(value.natural_key())
            elif value is None:
                # Null FK: expand to the right number of None values so
                # get_by_natural_key() can consume the correct argument count
                if isinstance(field, ForeignKey) and hasattr(
                    field.related_model, "NaturalKeyConfig"
                ):
                    num_args = count_natural_key_args(field.related_model)
                    key_parts.extend([None] * num_args)
                else:
                    key_parts.append(None)
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

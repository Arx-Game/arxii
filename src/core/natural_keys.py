"""
Natural key mixins for Django models.

These mixins add natural_key() methods and custom managers for Django's
fixture serialization system. Natural keys allow fixtures to work across
different database instances where primary key IDs may differ.

Usage:
    class MyModel(NaturalKeyMixin, models.Model):
        name = models.CharField(unique=True)

        class NaturalKeyConfig:
            fields = ["name"]
"""

from django.db import models


class NaturalKeyConfigError(ValueError):
    """Raised when NaturalKeyConfig is missing or invalid."""


class NaturalKeyManager(models.Manager):
    """Manager that supports get_by_natural_key lookups."""

    def get_by_natural_key(self, *args):
        """Look up object by natural key fields."""
        if not hasattr(self.model, "NaturalKeyConfig"):
            msg = f"{self.model.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        config = self.model.NaturalKeyConfig
        fields = config.fields
        if len(args) != len(fields):
            msg = f"Expected {len(fields)} natural key values, got {len(args)}"
            raise NaturalKeyConfigError(msg)

        lookup = dict(zip(fields, args, strict=True))
        return self.get(**lookup)


class NaturalKeyMixin:
    """
    Mixin that adds natural_key() method based on NaturalKeyConfig.

    Define NaturalKeyConfig.fields as a list of field names that uniquely
    identify the object. For foreign keys, use the related object's natural
    key by specifying the field name (the mixin will call natural_key() on it).
    """

    def natural_key(self):
        """Return natural key tuple for this object."""
        if not hasattr(self.__class__, "NaturalKeyConfig"):
            msg = f"{self.__class__.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        config = self.__class__.NaturalKeyConfig
        key_parts = []
        for field_name in config.fields:
            value = getattr(self, field_name)
            # If value is a model instance, get its natural key
            if hasattr(value, "natural_key"):
                key_parts.extend(value.natural_key())
            else:
                key_parts.append(value)

        return tuple(key_parts)

    # Set dependencies if defined
    @classmethod
    def natural_key_dependencies(cls):
        """Return list of model dependencies for serialization order."""
        if not hasattr(cls, "NaturalKeyConfig"):
            return []
        config = cls.NaturalKeyConfig
        if hasattr(config, "dependencies"):
            return config.dependencies
        return []

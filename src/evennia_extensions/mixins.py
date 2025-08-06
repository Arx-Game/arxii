"""
Mixins for Evennia extensions.
Provides utilities for managing cached properties and other common patterns.
"""

from functools import cached_property as functools_cached_property

from django.utils.functional import cached_property as django_cached_property


class CachedPropertiesMixin:
    """
    Mixin that provides automatic cache clearing for cached_property decorators.

    This mixin automatically clears all @cached_property values when save() is called,
    preventing stale cached data. Models using this mixin should use the standard
    @cached_property decorator from functools.

    Example:
        class MyModel(CachedPropertiesMixin, models.Model):
            @cached_property
            def expensive_calculation(self):
                return some_expensive_operation()
    """

    def clear_cached_properties(self):
        """Clear all cached properties from this object."""
        cls = self.__class__

        # Find all cached_property descriptors in the class hierarchy
        # Support both Django's and functools cached_property
        cached_props = []
        for klass in cls.__mro__:
            for name, attr in klass.__dict__.items():
                if isinstance(
                    attr, (functools_cached_property, django_cached_property)
                ):
                    cached_props.append(name)

        # Clear each cached property from the instance dict
        for prop_name in cached_props:
            self.__dict__.pop(prop_name, None)

    def save(self, *args, **kwargs):
        """Save and automatically clear cached properties."""
        super().save(*args, **kwargs)
        self.clear_cached_properties()

    def refresh_from_db(self, using=None, fields=None):
        """Refresh from database and clear cached properties."""
        super().refresh_from_db(using=using, fields=fields)
        self.clear_cached_properties()


class RelatedCacheClearingMixin(CachedPropertiesMixin):
    """
    Advanced mixin that can also clear cached properties on related objects.

    Models using this mixin should define a `related_cache_fields` class attribute
    that lists field names or paths to related objects that should have their
    caches cleared when this object is saved.

    Example:
        class PlayerTenure(RelatedCacheClearingMixin, models.Model):
            player_data = models.ForeignKey(PlayerData, ...)

            # Clear player_data's cached properties when tenure changes
            related_cache_fields = ['player_data']
    """

    related_cache_fields = []  # Override in subclasses

    def clear_related_caches(self):
        """Clear cached properties on related objects."""
        for field_path in self.related_cache_fields:
            try:
                # Handle dot notation for nested relationships
                obj = self
                for part in field_path.split("."):
                    obj = getattr(obj, part, None)
                    if obj is None:
                        break

                # Clear caches if the related object has the method
                if obj and hasattr(obj, "clear_cached_properties"):
                    obj.clear_cached_properties()
                    # Also clear related caches if the object supports it
                    if hasattr(obj, "clear_related_caches"):
                        obj.clear_related_caches()
                elif obj:
                    # For objects without the mixin, manually clear functools cached_property
                    # This handles Evennia objects like Account that don't use our mixins
                    cls = obj.__class__
                    for klass in cls.__mro__:
                        for name, attr in klass.__dict__.items():
                            if isinstance(attr, functools_cached_property):
                                obj.__dict__.pop(name, None)

            except (AttributeError, ValueError, TypeError):
                # Silently handle cases where related objects don't exist
                # or don't have cache clearing capabilities
                pass

    def save(self, *args, **kwargs):
        """Save, clear own caches, and clear related object caches."""
        result = super().save(*args, **kwargs)
        self.clear_related_caches()
        return result

    def delete(self, *args, **kwargs):
        """Delete and clear related object caches."""
        self.clear_related_caches()
        super().delete(*args, **kwargs)

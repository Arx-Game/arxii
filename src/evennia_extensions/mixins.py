"""
Mixins for Evennia extensions.
Provides utilities for managing cached properties and other common patterns.
"""

from functools import (
    cached_property as functools_cached_property,  # noqa: CACHED_PROPERTY_IMPORT
)
from typing import ClassVar

from django.utils.functional import cached_property as django_cached_property


def clear_django_cached_properties(obj) -> None:
    """Drop every cached_property entry (Django's or functools') from *obj*.

    The single implementation behind ``CachedPropertiesMixin.clear_cached_properties``
    and ``Account.clear_cached_properties`` — walk the MRO, find both descriptor
    kinds, pop their names from the instance ``__dict__``.
    """
    names = [
        name
        for klass in type(obj).__mro__
        for name, attr in klass.__dict__.items()
        if isinstance(attr, (functools_cached_property, django_cached_property))
    ]
    for name in names:
        obj.__dict__.pop(name, None)


class CachedPropertiesMixin:
    """
    Mixin that provides automatic cache clearing for cached_property decorators.

    This mixin automatically clears all @cached_property values when save() is called,
    preventing stale cached data. Models using this mixin should use the
    @cached_property decorator from django.utils.functional (see
    src/evennia_extensions/CACHED_PROPERTY_STANDARD.md). The mixin still
    isinstance-checks against functools.cached_property defensively to handle
    any legacy or non-Django callers.

    Example:
        class MyModel(CachedPropertiesMixin, models.Model):
            @cached_property
            def expensive_calculation(self):
                return some_expensive_operation()
    """

    def clear_cached_properties(self):
        """Clear all cached properties from this object."""
        clear_django_cached_properties(self)

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

    related_cache_fields: ClassVar[list[str]] = []  # Override in subclasses

    def _resolve_related_object(self, field_path: str):
        """Follow a dotted field path to return a related object."""

        obj = self
        for part in field_path.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    @staticmethod
    def _clear_functools_caches(obj) -> None:
        """Clear cached_property entries on an arbitrary object.

        Delegates to the same implementation ``clear_cached_properties`` uses.
        This used to walk the MRO for ``functools.cached_property`` alone, which
        made ``related_cache_fields`` a no-op against the spelling this repo
        actually mandates: a related object without its own
        ``clear_cached_properties`` kept every Django ``cached_property`` it had
        (#3673, found on ``OriginTemplate.questions``).
        """

        clear_django_cached_properties(obj)

    def _clear_caches_for_object(self, obj) -> None:
        """Clear caches on ``obj`` if supported."""

        if hasattr(obj, "clear_cached_properties"):
            obj.clear_cached_properties()
            if hasattr(obj, "clear_related_caches"):
                obj.clear_related_caches()
            return

        self._clear_functools_caches(obj)

    def clear_related_caches(self):
        """Clear cached properties on related objects."""

        for field_path in self.related_cache_fields:
            try:
                obj = self._resolve_related_object(field_path)
                if obj is None:
                    continue
                self._clear_caches_for_object(obj)
            except (AttributeError, ValueError, TypeError):
                # Silently handle cases where related objects don't exist
                # or don't have cache clearing capabilities
                pass

    #: Opt-in only -- default False preserves the original always-clear-on-save
    #: behavior for every existing consumer. Set True on a subclass ONLY after
    #: verifying, for every ``cached_property`` this relation's parent(s)
    #: expose, that the Prefetch/fallback queryset behind it filters SOLELY
    #: on the tracked FK path(s) in ``related_cache_fields`` -- never on any
    #: OTHER field this model carries. Skipping the clear on an unchanged FK
    #: is unsafe whenever the parent's cached list is also filtered by some
    #: other mutable field: a field-only update to THAT field changes cache
    #: membership without changing the FK, and would silently miss its clear.
    #: Found live on ``DistinctionOffer`` -> ``GlimpseTag.offers``, which
    #: filters on ``is_active`` in addition to ``glimpse_tag`` (#3816 final
    #: review) -- toggling ``is_active`` alone must still clear, so that
    #: relation stays on the default (always clear).
    skip_related_cache_clear_when_fk_unchanged: ClassVar[bool] = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.skip_related_cache_clear_when_fk_unchanged:
            self._related_cache_field_snapshot = self._snapshot_related_cache_fields()

    def _snapshot_related_cache_fields(self) -> dict[str, object]:
        """Cheap, query-free snapshot of each single-segment FK's raw id.

        ``save()`` uses this (only when ``skip_related_cache_clear_when_fk_unchanged``
        is True) to skip ``clear_related_caches()`` when nothing that could
        change cache MEMBERSHIP on a related object actually changed. A plain
        field-only update (e.g. a balance or round_number bump) leaves every
        tracked FK's id untouched; since the cached list on the parent
        already holds this SAME idmapper-shared instance, the field change is
        visible for free to any later reader of that list -- only a genuine
        create (a new member) or a reassignment (a different member) needs
        the clear. Dotted paths are excluded: they resolve through a
        multi-hop attribute chain rather than one ``<field>_id``, so they
        always count as changed below (conservative, not optimized).
        """
        return {
            path: getattr(self, f"{path}_id", None)
            for path in self.related_cache_fields
            if "." not in path
        }

    def _related_cache_fields_changed(self) -> bool:
        """True if a clear is needed: a new row, a dotted-path relation
        (conservatively always treated as changed), or a single-segment FK
        whose id now differs from its snapshot at load/instantiation time.

        Only called when ``skip_related_cache_clear_when_fk_unchanged`` is
        True -- see that flag's docstring for the safety precondition.
        """
        if self._state.adding:
            return True
        for path in self.related_cache_fields:
            if "." in path:
                return True
            current = getattr(self, f"{path}_id", None)
            if self._related_cache_field_snapshot.get(path) != current:
                return True
        return False

    def save(self, *args, **kwargs):
        """Save, clear own caches, and clear related caches if they could
        have changed."""
        should_clear = (
            self._related_cache_fields_changed()
            if self.skip_related_cache_clear_when_fk_unchanged
            else True
        )
        result = super().save(*args, **kwargs)
        if should_clear:
            self.clear_related_caches()
            if self.skip_related_cache_clear_when_fk_unchanged:
                self._related_cache_field_snapshot = self._snapshot_related_cache_fields()
        return result

    def delete(self, *args, **kwargs):
        """Delete and clear related object caches."""
        self.clear_related_caches()
        super().delete(*args, **kwargs)

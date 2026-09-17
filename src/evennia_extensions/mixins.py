"""
Mixins for Evennia extensions.
Provides utilities for managing cached properties and other common patterns.
"""

from contextlib import suppress
from functools import (
    cached_property as functools_cached_property,  # noqa: CACHED_PROPERTY_IMPORT
)
from typing import ClassVar

from django.core.exceptions import FieldDoesNotExist
from django.utils.functional import cached_property as django_cached_property

_DEFERRED_RELATED_CACHE_FIELD = object()


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

        parts = field_path.split(".")
        obj = self
        for index, part in enumerate(parts):
            if index == 0:
                obj = self._resolve_current_single_segment_object(part)
            else:
                obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    @staticmethod
    def _is_snapshot_field(field) -> bool:
        """Return whether a field is a concrete forward FK relation."""
        return bool(
            field
            and field.concrete
            and field.is_relation
            and (field.many_to_one or field.one_to_one)
        )

    def _resolve_current_single_segment_object(self, field_path: str):
        """Resolve a direct FK using its raw id, avoiding stale field caches."""
        field = self._get_related_cache_field(field_path)
        if not self._is_snapshot_field(field):
            return getattr(self, field_path, None)

        current_id = self.__dict__.get(field.attname, _DEFERRED_RELATED_CACHE_FIELD)
        cached = field.get_cached_value(self, _DEFERRED_RELATED_CACHE_FIELD)
        if cached is not _DEFERRED_RELATED_CACHE_FIELD:
            if cached is None:
                if current_id in (None, _DEFERRED_RELATED_CACHE_FIELD):
                    return None
                field.delete_cached_value(self)
            elif current_id is _DEFERRED_RELATED_CACHE_FIELD or cached.pk == current_id:
                return cached
            else:
                field.delete_cached_value(self)

        if current_id is None:
            return None
        # A deferred FK has no raw id in __dict__. Resolving it here is allowed
        # during a save (but never during __init__) so the default invalidation
        # behavior still clears the current parent.
        return getattr(self, field.name, None)

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

    def clear_related_caches(self, previous_objects: list[object] | None = None):
        """Clear cached properties on current and previously related objects.

        ``previous_objects`` is supplied by ``save()`` when a tracked FK was
        reassigned. Deleting a row only needs the current relation and leaves it
        unset, preserving the public no-argument behavior.
        """
        objects = []
        for field_path in self.related_cache_fields:
            try:
                obj = self._resolve_related_object(field_path)
                if obj is not None:
                    objects.append(obj)
            except (AttributeError, ValueError, TypeError):
                # Silently handle cases where related objects don't exist
                # or don't have cache clearing capabilities.
                pass

        objects.extend(previous_objects or [])
        seen = set()
        for obj in objects:
            identity = id(obj)
            if identity in seen:
                continue
            seen.add(identity)
            with suppress(AttributeError, ValueError, TypeError):
                self._clear_caches_for_object(obj)

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
        # Keep raw ids so a later FK reassignment can invalidate both sides
        # without querying any relation during model construction. Retain any
        # already-loaded objects too, so the common reassignment path needs no
        # old-parent query.
        self._related_cache_field_snapshot = self._snapshot_related_cache_fields()
        self._related_cache_field_object_snapshot = self._snapshot_related_cache_objects()

    def _get_related_cache_field(self, field_path: str):
        """Return a direct model field, or ``None`` for an invalid path."""
        try:
            return self._meta.get_field(field_path)
        except FieldDoesNotExist:
            return None

    def _snapshot_related_cache_fields(self) -> dict[str, object]:
        """Return a cheap, query-free snapshot of each single-segment FK id.

        Dotted paths are excluded because they resolve through a multi-hop
        attribute chain and cannot be represented by one ``<field>_id`` value.
        They are handled conservatively by ``_related_cache_fields_changed``.
        """
        snapshot = {}
        for path in self.related_cache_fields:
            if "." in path:
                continue
            field = self._get_related_cache_field(path)
            if self._is_snapshot_field(field):
                snapshot[path] = self.__dict__.get(field.attname, _DEFERRED_RELATED_CACHE_FIELD)
        return snapshot

    def _snapshot_related_cache_objects(self) -> dict[str, object]:
        """Snapshot already-loaded single-segment FK objects without querying."""
        snapshot = {}
        for path in self.related_cache_fields:
            if "." in path:
                continue
            field = self._get_related_cache_field(path)
            if not self._is_snapshot_field(field):
                continue
            current_id = self.__dict__.get(field.attname, _DEFERRED_RELATED_CACHE_FIELD)
            cached = field.get_cached_value(self, _DEFERRED_RELATED_CACHE_FIELD)
            if (
                cached is not _DEFERRED_RELATED_CACHE_FIELD
                and cached is not None
                and current_id is not _DEFERRED_RELATED_CACHE_FIELD
                and cached.pk == current_id
            ):
                snapshot[path] = cached
        return snapshot

    def _resolve_snapshot_related_object(self, field_path: str):
        """Resolve a previously related object when its FK has changed.

        A relation already loaded before reassignment is reused. Otherwise the
        old id is looked up only when a save actually changed that FK.
        """
        previous_id = self._related_cache_field_snapshot.get(field_path)
        field = self._get_related_cache_field(field_path)
        if not self._is_snapshot_field(field):
            return None

        if previous_id is _DEFERRED_RELATED_CACHE_FIELD:
            # An explicitly reassigned deferred FK has no old id in memory.
            # Read the persisted attname only on this changed-save path.
            if self.pk is None:
                return None
            previous_id = (
                type(self)
                ._base_manager.db_manager(self._state.db)
                .filter(pk=self.pk)
                .values_list(field.attname, flat=True)
                .first()
            )
        if previous_id is None:
            return None

        cached = self._related_cache_field_object_snapshot.get(field_path)
        if cached is not None and cached.pk == previous_id:
            return cached

        related_model = field.remote_field.model
        lookup_name = field.target_field.name
        return (
            related_model._base_manager.db_manager(self._state.db)
            .filter(**{lookup_name: previous_id})
            .first()
        )

    def _field_is_in_update_fields(self, field_path: str, update_fields) -> bool:
        """Return whether a tracked field is included in ``update_fields``."""
        if update_fields is None:
            return True
        field = self._get_related_cache_field(field_path)
        if field is None:
            return False
        return field.name in update_fields or field.attname in update_fields

    def _get_changed_related_objects(self, update_fields=None) -> list[object]:
        """Return old parent objects whose FK was reassigned and persisted."""
        objects = []
        for path in self.related_cache_fields:
            if "." in path or not self._field_is_in_update_fields(path, update_fields):
                continue
            field = self._get_related_cache_field(path)
            if not self._is_snapshot_field(field):
                continue
            current = self.__dict__.get(field.attname, _DEFERRED_RELATED_CACHE_FIELD)
            if self._related_cache_field_snapshot.get(path) == current:
                continue
            previous = self._resolve_snapshot_related_object(path)
            if previous is not None:
                objects.append(previous)
        return objects

    def _related_cache_fields_changed(self, update_fields=None) -> bool:
        """Return whether a related cache may have changed.

        A new row, a dotted path, or a changed single-segment FK requires a
        clear. This is used by the opt-in save optimization; the default remains
        to clear related caches on every save.
        """
        if update_fields is not None and not update_fields:
            return False
        if self._state.adding:
            return True
        for path in self.related_cache_fields:
            if "." in path:
                return True
            if not self._field_is_in_update_fields(path, update_fields):
                continue
            field = self._get_related_cache_field(path)
            if not self._is_snapshot_field(field):
                continue
            current = self.__dict__.get(field.attname, _DEFERRED_RELATED_CACHE_FIELD)
            if self._related_cache_field_snapshot.get(path) != current:
                return True
        return False

    def _update_related_cache_snapshot(self, update_fields=None) -> None:
        """Record only FK values that a successful save or refresh persisted."""
        current_ids = self._snapshot_related_cache_fields()
        current_objects = self._snapshot_related_cache_objects()
        if update_fields is None:
            self._related_cache_field_snapshot = current_ids
            self._related_cache_field_object_snapshot = current_objects
            return

        snapshot = dict(self._related_cache_field_snapshot)
        object_snapshot = dict(self._related_cache_field_object_snapshot)
        for path in current_ids:
            if not self._field_is_in_update_fields(path, update_fields):
                continue
            snapshot[path] = current_ids[path]
            if path in current_objects:
                object_snapshot[path] = current_objects[path]
            else:
                object_snapshot.pop(path, None)
        self._related_cache_field_snapshot = snapshot
        self._related_cache_field_object_snapshot = object_snapshot

    def refresh_from_db(self, using=None, fields=None):
        """Refresh the model and its FK snapshot from the database."""
        super().refresh_from_db(using=using, fields=fields)
        self._update_related_cache_snapshot(fields)

    def save(self, *args, **kwargs):
        """Save, clear own caches, and clear related caches if they could
        have changed."""
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            kwargs["update_fields"] = update_fields
        has_fields_to_update = update_fields is None or bool(update_fields)
        should_clear = has_fields_to_update and (
            self._related_cache_fields_changed(update_fields)
            if self.skip_related_cache_clear_when_fk_unchanged
            else True
        )
        previous_objects = self._get_changed_related_objects(update_fields) if should_clear else []
        result = super().save(*args, **kwargs)
        if should_clear:
            self.clear_related_caches(previous_objects)
        self._update_related_cache_snapshot(update_fields)
        return result

    def delete(self, *args, **kwargs):
        """Delete and clear related object caches."""
        self.clear_related_caches(self._get_changed_related_objects())
        super().delete(*args, **kwargs)

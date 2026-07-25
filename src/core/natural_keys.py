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

from core.managers import ArxSharedMemoryManager

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


#: Per-model natural-key index: casefolded natural-key tuple -> pk.
#:
#: Keyed by the model's ``__dbclass__`` (Evennia stores the identity map there so
#: proxies share one cache), so a proxy and its concrete model share an index.
#: A module-level registry rather than a class attribute, so an index can never be
#: silently inherited by a sibling model.
#:
#: Stores pks rather than instances deliberately (#2687): the index can then never
#: retain an instance or grow beyond what the identity map already holds, instance
#: freshness stays the identity map's concern, and a deleted row self-heals because
#: ``get(pk=N)`` raises ``DoesNotExist``.
_NK_PK_INDEX: dict[type, dict[tuple, int]] = {}

#: Models whose whole table has been warmed (``NaturalKeyConfig.lookup_table``).
_NK_WARMED: set[type] = set()


def index_owner(model: type) -> type:
    """Return the class that owns *model*'s natural-key index.

    ``SharedMemoryModel`` subclasses share one identity map per ``__dbclass__``;
    mirror that here. Models using ``NaturalKeyManager`` without being a
    ``SharedMemoryModel`` have no ``__dbclass__`` and own their index directly.
    """
    # try/except rather than getattr(): duck-typing an attribute this way needs
    # no GETATTR_LITERAL suppression, matching the precedent in core/mixins.py.
    try:
        return model.__dbclass__
    except AttributeError:
        return model


def natural_key_index(model: type) -> dict[tuple, int]:
    """Return (creating if needed) the natural-key -> pk index for *model*."""
    return _NK_PK_INDEX.setdefault(index_owner(model), {})


def _index_key(values: Iterable[Any]) -> tuple[Any, ...]:
    """Normalize a natural-key value sequence into a hashable, caseless key.

    Two normalizations, both required:

    * nested lists -> tuples. Self-referential FK natural keys nest their value
      as a list (``("Wolf", ["Mammals", ["Creatures", None]])``), and lists are
      unhashable.
    * ``str`` -> ``str.casefold()``. Natural-key lookups are case-insensitive
      (#2687): there is no case in which a natural key should match
      case-sensitively. ``casefold()`` rather than ``lower()`` — it is the
      correct operation for caseless matching.

    Every key entering or querying the index goes through this one function, so
    the stored and queried spellings can never diverge.
    """
    normalized: list[Any] = []
    for value in values:
        if isinstance(value, str):
            normalized.append(value.casefold())
        elif isinstance(value, (list, tuple)):
            normalized.append(_index_key(value))
        else:
            normalized.append(value)
    return tuple(normalized)


def flush_natural_key_indexes() -> None:
    """Clear every natural-key index and warm flag.

    Called between tests (see ``core.testing``). Tests roll the database back but
    leave this process-level index intact, so a pk recycled across a rollback
    would otherwise resolve to the wrong row — and the ``DoesNotExist`` self-heal
    does NOT catch that, because the pk is live, just wrong.
    """
    for index in _NK_PK_INDEX.values():
        index.clear()
    _NK_WARMED.clear()


def is_lookup_table(model: type) -> bool:
    """Whether *model* declares ``NaturalKeyConfig.lookup_table = True``.

    Lookup-table status is a per-model judgement about that table's size and
    access pattern — a small set used everywhere versus a table that must never
    be bulk-loaded. Opt-in, deliberately NOT the default (#2687).

    ``lookup_table`` is expected to be a plain class attribute. Each access is
    guarded separately so a missing attribute reads as False without also
    swallowing an error raised from inside a descriptor.
    """
    try:
        config = model.NaturalKeyConfig
    except AttributeError:
        return False
    try:
        return bool(config.lookup_table)
    except AttributeError:
        return False


class NaturalKeyConfigError(ValueError):
    """Raised when NaturalKeyConfig is missing or invalid."""


class NaturalKeyManager(ArxSharedMemoryManager, models.Manager["NaturalKeyMixin"]):
    """Manager that supports get_by_natural_key lookups.

    Inherits from ``ArxSharedMemoryManager`` so that singleton config models
    using this manager retain ``cached_singleton()`` and ``cached_all()``
    in addition to natural-key support. The ``SharedMemoryManager`` base
    ensures ``.get(pk=N)`` hits the Evennia identity-map cache before
    issuing SQL when the underlying model is a ``SharedMemoryModel``. For
    non-SharedMemoryModel models with this manager, the cache check is a
    no-op (the model has no ``get_cached_instance`` classmethod, so the
    cache lookup raises and the manager falls through to ``super().get()``).
    """

    def get_by_natural_key(self, *args: Any) -> NaturalKeyMixin:
        """
        Look up object by natural key fields.

        For ForeignKey fields, this method introspects the related model to
        determine how many natural key values belong to that FK, consumes them
        from args, and looks up the related object first.

        Self-referential FKs consume a single arg that is either None (null FK)
        or a nested list to be recursively resolved.

        Repeat lookups are served from a process-level natural-key -> pk index
        and resolve through SharedMemoryModel's identity map (zero queries).
        The index check happens BEFORE the arg->lookup resolution, so a hit on a
        composite key also skips the recursive FK lookups it would otherwise do.
        """
        if not hasattr(self.model, "NaturalKeyConfig"):
            msg = f"{self.model.__name__} missing NaturalKeyConfig"
            raise NaturalKeyConfigError(msg)

        key = _index_key(args)
        index = natural_key_index(self.model)

        if is_lookup_table(self.model):
            return self._get_from_lookup_table(key)

        cached_pk = index.get(key)
        if cached_pk is not None:
            try:
                return self.get(pk=cached_pk)
            except self.model.DoesNotExist:
                # Poisoned entry (row deleted, or a pk recycled). Drop it and
                # fall through to a fresh natural-key query.
                index.pop(key, None)

        instance = self.get(**self._natural_key_lookup(args))
        if isinstance(instance, NaturalKeyMixin):
            index[key] = instance.pk
            instance._nk_index_key = key  # noqa: SLF001
        return instance

    def _natural_key_lookup(self, args: tuple[Any, ...]) -> dict[str, Any]:
        """Build the field->value lookup dict for a natural-key arg tuple.

        Extracted from ``get_by_natural_key`` so the index fast path can skip it
        entirely — on a composite key this also skips the recursive
        ``get_by_natural_key`` calls that resolve each FK component.
        """
        config = self.model.NaturalKeyConfig
        fields: Sequence[str] = config.fields

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
                value = args_list.pop(0)
                lookup[_text_lookup_key(field, field_name, value)] = value

        if args_list:
            msg = f"Too many natural key values for {self.model.__name__}: {len(args)} given"
            raise NaturalKeyConfigError(msg)

        return lookup

    def warm_lookup_table(self) -> None:
        """Load the whole table once and index every row by natural key.

        Only legal for FK-free natural keys: building the index calls
        ``natural_key()`` per row, which traverses FK descriptors and would cost
        a query per row on an FK-bearing key.

        Deliberately does its own ``self.all()`` pass rather than reusing
        ``cached_all()``: ``cached_all()`` returns ``__instance_cache__.values()``,
        so it goes empty if the identity map is flushed while its ``_all_loaded``
        flag survives. Storing pks keeps this index valid across an identity-map
        flush. The pass still primes the identity map as a side effect.

        Raises ``NaturalKeyConfigError`` if two rows casefold to the same key —
        a case-variant duplicate is a content bug, and this is where it surfaces.
        """
        owner = index_owner(self.model)
        if owner in _NK_WARMED:
            return

        self._assert_natural_key_is_fk_free()

        index = natural_key_index(self.model)
        for instance in self.all():
            key = _index_key(instance.natural_key())
            existing = index.get(key)
            if existing is not None and existing != instance.pk:
                msg = (
                    f"{self.model.__name__} has two rows whose natural keys differ only "
                    f"by case: {key!r} matches pk {existing} and pk {instance.pk}. "
                    "Natural keys are case-insensitive — rename or merge one row."
                )
                raise NaturalKeyConfigError(msg)
            index[key] = instance.pk
            if isinstance(instance, NaturalKeyMixin):
                instance._nk_index_key = key  # noqa: SLF001
        _NK_WARMED.add(owner)

    def _assert_natural_key_is_fk_free(self) -> None:
        """Raise if this model's natural key contains a ForeignKey component."""
        for field_name in self.model.NaturalKeyConfig.fields:
            field = self.model._meta.get_field(field_name)  # noqa: SLF001
            if isinstance(field, ForeignKey):
                msg = (
                    f"{self.model.__name__} cannot be a lookup_table: its natural key "
                    f"field {field_name!r} is a ForeignKey. Warming would traverse FK "
                    "descriptors and cost a query per row."
                )
                raise NaturalKeyConfigError(msg)

    def _get_from_lookup_table(self, key: tuple) -> NaturalKeyMixin:
        """Resolve *key* purely from the warmed index — never issues an iexact.

        A dead pk (poisoned entry, or a row deleted since the warm) invalidates
        the warm and re-warms exactly once, which is one extra query and cannot
        recurse.
        """
        self.warm_lookup_table()
        index = natural_key_index(self.model)
        pk = index.get(key)
        if pk is not None:
            try:
                return self.get(pk=pk)
            except self.model.DoesNotExist:
                _NK_WARMED.discard(index_owner(self.model))
                index.clear()
                self.warm_lookup_table()
                pk = index.get(key)
                if pk is not None:
                    return self.get(pk=pk)
        msg = f"{self.model.__name__} matching natural key {key!r} does not exist."
        raise self.model.DoesNotExist(msg)


def _text_lookup_key(field: Any, field_name: str, value: Any) -> str:
    """Return the queryset lookup key for a non-FK natural-key component.

    Natural-key lookups are case-insensitive (#2687), so text components match
    with ``__iexact``. Numeric and boolean components keep exact matching — a
    natural key is a mix of text (``name``, ``stat_key``), integers
    (``min_roll``, ``rank_difference``) and FKs.

    Note: ``"<field>__iexact"`` does not collide with Evennia's
    ``SharedMemoryManager.get()``, which strips a trailing ``"__exact"`` only.
    """
    if isinstance(value, str) and isinstance(field, (models.CharField, models.TextField)):
        return f"{field_name}__iexact"
    return field_name


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

    #: The index key this instance was last cached under, if any (#2687).
    #: Set by ``NaturalKeyManager.get_by_natural_key``; consumed by ``save()``.
    _nk_index_key: tuple | None = None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save, then drop this instance's stale natural-key index entry.

        After a rename the old key still points at a live pk, so without this the
        index would return the renamed row instead of raising ``DoesNotExist``.
        The stashed key is popped unconditionally rather than compared against a
        recomputed ``natural_key()`` — recomputation traverses FK descriptors and
        could fire a query on the save path. The cost of dropping an entry that
        did not actually change is one ``SELECT`` on the next lookup.

        Known limitation: ``queryset.update(name=...)`` bypasses ``save()`` and
        leaves a stale entry. This is the same class of hazard the identity map
        already has — ``.update()`` does not refresh cached instances either.
        """
        super().save(*args, **kwargs)
        model = type(self)
        index = natural_key_index(model)
        old_key = self._nk_index_key
        if old_key is not None:
            index.pop(old_key, None)
            self._nk_index_key = None
        if is_lookup_table(model) and index_owner(model) in _NK_WARMED:
            # Keep a warmed table complete: newly created and renamed rows must
            # be findable without a re-warm. FK-free by construction, so this is
            # pure attribute reads — no query.
            new_key = _index_key(self.natural_key())
            index[new_key] = self.pk
            self._nk_index_key = new_key

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

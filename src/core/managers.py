"""Project-level manager subclasses for SharedMemoryModel."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import models
from evennia.utils.idmapper.manager import SharedMemoryManager


class SharedMemoryWriteError(RuntimeError):
    """Raised when a queryset write would bypass the identity map."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"QuerySet.{operation}() is disabled for ArxSharedMemoryModel because it "
            f"bypasses the identity map. Use {operation}_with_reason(reason=..., ...) "
            "for an intentional cache-bypassing write."
        )


class SharedMemoryWriteReasonError(ValueError):
    """Raised when an identity-map bypass has no stated reason."""

    def __init__(self) -> None:
        super().__init__("An explicit reason is required for an identity-map-bypassing write.")


_WRITE_BYPASS_REASON: ContextVar[str | None] = ContextVar(
    "shared_memory_write_reason", default=None
)


@contextmanager
def _allow_shared_memory_write(reason: str) -> Iterator[None]:
    """Temporarily allow one intentional cache-bypassing write operation."""
    _require_write_reason(reason)
    token = _WRITE_BYPASS_REASON.set(reason.strip())
    try:
        yield
    finally:
        _WRITE_BYPASS_REASON.reset(token)


class ArxSharedMemoryQuerySet(models.QuerySet):
    """QuerySet that requires an explicit reason for cache-bypassing writes."""

    def update(self, **kwargs: Any) -> int:
        """Reject a raw UPDATE that would leave cached instances stale."""
        if _WRITE_BYPASS_REASON.get() is None:
            operation = "update"
            raise SharedMemoryWriteError(operation)
        return super().update(**kwargs)

    def bulk_update(
        self, objs: Iterable[Any], fields: Iterable[str], batch_size: int | None = None
    ) -> int:
        """Reject a bulk UPDATE that would leave cached instances stale."""
        if _WRITE_BYPASS_REASON.get() is None:
            operation = "bulk_update"
            raise SharedMemoryWriteError(operation)
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def update_with_reason(self, *, reason: str, **kwargs: Any) -> int:
        """Perform an intentional raw UPDATE after requiring its reason."""
        with _allow_shared_memory_write(reason):
            return super().update(**kwargs)

    def bulk_update_with_reason(
        self,
        objs: Iterable[Any],
        fields: Iterable[str],
        batch_size: int | None = None,
        *,
        reason: str,
    ) -> int:
        """Perform an intentional bulk UPDATE after requiring its reason."""
        with _allow_shared_memory_write(reason):
            return super().bulk_update(objs, fields, batch_size=batch_size)


def _require_write_reason(reason: str) -> None:
    """Require a non-empty explanation for bypassing the identity map."""
    if not isinstance(reason, str) or not reason.strip():
        raise SharedMemoryWriteReasonError


class GuardedSharedMemoryManager(SharedMemoryManager):
    """SharedMemoryManager whose querysets require explicit write escapes."""

    _queryset_class = ArxSharedMemoryQuerySet

    def update_with_reason(self, *, reason: str, **kwargs: Any) -> int:
        """Delegate the explicit raw-update escape to the guarded queryset."""
        return self.get_queryset().update_with_reason(reason=reason, **kwargs)

    def bulk_update_with_reason(
        self,
        objs: Iterable[Any],
        fields: Iterable[str],
        batch_size: int | None = None,
        *,
        reason: str,
    ) -> int:
        """Delegate the explicit bulk-update escape to the guarded queryset."""
        return self.get_queryset().bulk_update_with_reason(
            objs, fields, batch_size=batch_size, reason=reason
        )


class CachedAllMixin:
    """Adds a full-table, never-invalidated-in-production cache to a manager.

    ``cached_all()`` forces one full-table load (which populates the model's
    own SharedMemoryModel identity map, ``__instance_cache__``, as a side
    effect of iterating real instances) and remembers a per-manager-instance
    ``_all_loaded`` flag. Every subsequent call reads back through that same
    identity map rather than keeping a second, separate cached list -- so an
    unrelated ``Model.objects.get(pk=X)`` call elsewhere in the codebase also
    becomes a free hit once a catalog is warm (#1846).

    Use on small, admin-authored catalog tables (property/terrain/weather
    modifier rows, intensity tiers, mishap pool tiers, etc.) where "cache the
    whole table forever" is correct -- NOT for tables holding many
    independent entities scoped to a parent (e.g. BattleUnit rows across many
    battles), where a full-table cache would mix unrelated parents together.
    See BattleStateCache (world/battles/state_cache.py) for that shape.
    """

    def cached_all(self) -> list:
        """Return every row, querying the DB only on the very first call."""
        if not self.__dict__.get("_all_loaded"):
            list(self.all())  # each row self-registers in __instance_cache__
            self.__dict__["_all_loaded"] = True
        return list(self.model.__dbclass__.__instance_cache__.values())

    def flush_all_cache(self) -> None:
        """Clear the stashed full-table-loaded flag on this manager instance.

        Called by ``core.testing.flush_test_caches`` between tests so each
        test starts with a fresh cached_all() cache (mirroring a fresh
        process).
        """
        self.__dict__.pop("_all_loaded", None)


class ArxSharedMemoryManager(CachedAllMixin, GuardedSharedMemoryManager):
    """SharedMemoryManager subclass adding a pk-discovering singleton cache
    (``cached_singleton()``) and a full-table cache (``cached_all()``, via
    ``CachedAllMixin``).

    ``.first()`` bypasses the SharedMemoryModel identity map because it isn't a
    pk lookup — every call issues ``SELECT ... LIMIT 1``. ``cached_singleton()``
    does ``.first()`` once, stashes the discovered pk on the manager *instance*,
    then serves ``.get(pk=stashed_pk)`` on subsequent calls — hitting the
    identity map (zero SQL after the first call).

    If the stashed pk becomes stale (row deleted + recreated),
    ``.get()`` raises ``DoesNotExist`` -> re-discovery via ``.first()``.

    Use on singleton config models (one row per table). Not for multi-row tables
    — use ``cached_all()`` for those instead.

    The pk is cached per-manager-instance (not per-class) so each model's
    ``objects`` manager has its own cache. ``flush_singleton_cache()`` clears
    the instance-level cache; the test teardown walker in ``core.testing``
    calls it on every ``ArxSharedMemoryManager`` instance.
    """

    _queryset_class = ArxSharedMemoryQuerySet

    def cached_singleton(self):
        """Return the singleton row, cached after the first call.

        Returns ``None`` when no row exists (matching ``.first()`` semantics).
        Callers that need lazy-creation or fail-loud behavior should handle
        ``None`` in their accessor function.
        """
        pk = self.__dict__.get("_singleton_pk")
        if pk is not None:
            try:
                return self.get(pk=pk)
            except self.model.DoesNotExist:
                self.__dict__.pop("_singleton_pk", None)
        instance = self.first()
        if instance is not None:
            self.__dict__["_singleton_pk"] = instance.pk
        return instance

    def flush_singleton_cache(self) -> None:
        """Clear the stashed singleton pk on this manager instance.

        Called by ``core.testing.flush_test_caches`` between tests so each
        test starts with a fresh singleton cache (mirroring a fresh process).
        """
        self.__dict__.pop("_singleton_pk", None)

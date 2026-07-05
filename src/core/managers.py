"""Project-level manager subclasses for SharedMemoryModel."""

from __future__ import annotations

from evennia.utils.idmapper.manager import SharedMemoryManager


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


class ArxSharedMemoryManager(CachedAllMixin, SharedMemoryManager):
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

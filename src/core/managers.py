"""Project-level manager subclasses for SharedMemoryModel."""

from __future__ import annotations

from evennia.utils.idmapper.manager import SharedMemoryManager


class ArxSharedMemoryManager(SharedMemoryManager):
    """SharedMemoryManager subclass adding a pk-discovering singleton cache.

    ``.first()`` bypasses the SharedMemoryModel identity map because it isn't a
    pk lookup — every call issues ``SELECT ... LIMIT 1``. ``cached_singleton()``
    does ``.first()`` once, stashes the discovered pk on the manager *instance*,
    then serves ``.get(pk=stashed_pk)`` on subsequent calls — hitting the
    identity map (zero SQL after the first call).

    If the stashed pk becomes stale (row deleted + recreated),
    ``.get()`` raises ``DoesNotExist`` -> re-discovery via ``.first()``.

    Use on singleton config models (one row per table). Not for multi-row tables.

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

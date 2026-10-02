"""Deletes that keep the identity map honest about the links they null.

Deleting a row whose referrers use ``on_delete=SET_NULL`` makes Django's
``Collector`` null those links with one ``UPDATE`` through the referrer's plain
``_base_manager``. That write skips ``ArxSharedMemoryQuerySet``'s guard and
never loads the referring rows, so a referrer already resident in the idmapper
cache keeps the deleted row's id for the life of the process.
``refresh_from_db()`` and a fresh ``get()`` both hand back that same instance,
and a later ``select_related`` of the link sets the related object to ``None``
beside the stale ``<fk>_id``. Code that tests ``<fk>_id is not None`` and then
reads ``<fk>.<attr>`` raises on every read until a restart: an admin delete of
a house took both Almanach ladder endpoints down in production this way
(ARX2-S, ARX2-T; #4086).

``IdentityMapCollector`` records every row it removes, cascades included, and
after the delete clears those ids from cached ``SET_NULL`` referrers, which is
what the ``Collector`` would have done had they been in memory.
``ArxSharedMemoryModel.delete`` and ``ArxSharedMemoryQuerySet.delete`` use it.

Inside a transaction the delete can still roll back (the admin's reviewed
delete removes blocking rows, then refuses the root and undoes them all), and a
referrer nulled in memory would then write NULL over its restored link on its
next ``save()``. So inside an atomic block the affected referrers are evicted
from the identity map at once, which makes every fresh read load the row, and
are nulled in place only on commit. Eviction alone would leave a copy someone
already holds stale for good: a cached ``x`` keeps its ``Title`` in its own
field cache, so ``x.title.house`` would still reach the gone house. The commit
callback corrects that copy; on rollback it never runs, and the held copy's old
id is right again. Outside an atomic block the referrers are nulled in place
straight away. The clear runs after the SQL, never before: only ``collect()``
knows the cascaded rows, and a read between an early eviction and the
``UPDATE`` would cache the stale row again.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from typing import Any

from django.db import connections, transaction
from django.db.models import SET_NULL, Model
from django.db.models.deletion import Collector
from evennia.utils.idmapper.models import SharedMemoryModel


def _null_links(objs: list[Any], attname: str, deleted: set[Any]) -> None:
    """Null ``attname`` on each object still pointing at a deleted row."""
    for obj in objs:
        if obj.__dict__.get(attname) in deleted:
            setattr(obj, attname, None)


def clear_set_null_referrers(
    model: type[Model], pks: Iterable[Any], *, using: str | None = None
) -> None:
    """Null the link on every cached row that pointed at a deleted ``model`` row.

    With ``using`` inside an atomic block, evict those rows from the identity map
    now and null them on commit instead (see the module docstring).

    Only ``SET_NULL`` links on identity-mapped referrers are touched; those are
    the only ones whose database value changed without the cache seeing it.
    Assigning the raw id also drops the cached related object. Every reverse
    relation is walked, so a ``keep_parents=True`` delete of a multi-table child
    (no caller does one) would also clear its surviving parent's referrers.
    """
    deleted = {pk for pk in pks if pk is not None}
    if not deleted:
        return
    deferred = using is not None and connections[using].in_atomic_block
    for rel in model._meta.related_objects:  # noqa: SLF001 - Django's model introspection API
        if rel.on_delete is not SET_NULL:
            continue
        referrer = rel.related_model
        if not issubclass(referrer, SharedMemoryModel):
            continue
        attname = rel.field.attname
        stale = [
            obj
            for obj in referrer.get_all_cached_instances()
            if obj.__dict__.get(attname) in deleted
        ]
        if not stale:
            continue
        if not deferred:
            _null_links(stale, attname, deleted)
            continue
        for obj in stale:
            obj.flush_from_cache(force=True)
        transaction.on_commit(partial(_null_links, stale, attname, deleted), using=using)


class IdentityMapCollector(Collector):
    """A ``Collector`` that carries its ``SET_NULL`` updates into the identity map."""

    def delete(self) -> tuple[int, dict[str, int]]:
        # The base delete nulls each collected instance's pk, so read them first.
        deleted = {model: [obj.pk for obj in objs] for model, objs in self.data.items()}
        result = super().delete()
        for model, pks in deleted.items():
            clear_set_null_referrers(model, pks, using=self.using)
        return result

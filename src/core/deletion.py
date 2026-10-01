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
Like Django's own nulling of a deleted instance's pk, the clear is not undone
if an enclosing transaction later rolls back.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import SET_NULL, Model
from django.db.models.deletion import Collector
from evennia.utils.idmapper.models import SharedMemoryModel


def clear_set_null_referrers(model: type[Model], pks: Iterable[Any]) -> None:
    """Null the link on every cached row that pointed at a deleted ``model`` row.

    Only ``SET_NULL`` links on identity-mapped referrers are touched; those are
    the only ones whose database value changed without the cache seeing it.
    Assigning the raw id also drops the cached related object.
    """
    deleted = {pk for pk in pks if pk is not None}
    if not deleted:
        return
    for rel in model._meta.related_objects:  # noqa: SLF001 - Django's model introspection API
        if rel.on_delete is not SET_NULL:
            continue
        referrer = rel.related_model
        if not issubclass(referrer, SharedMemoryModel):
            continue
        attname = rel.field.attname
        for obj in referrer.get_all_cached_instances():
            if obj.__dict__.get(attname) in deleted:
                setattr(obj, attname, None)


class IdentityMapCollector(Collector):
    """A ``Collector`` that carries its ``SET_NULL`` updates into the identity map."""

    def delete(self) -> tuple[int, dict[str, int]]:
        # The base delete nulls each collected instance's pk, so read them first.
        deleted = {model: [obj.pk for obj in objs] for model, objs in self.data.items()}
        result = super().delete()
        for model, pks in deleted.items():
            clear_set_null_referrers(model, pks)
        return result

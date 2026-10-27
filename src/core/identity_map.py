"""Putting identity-mapped rows back after a transaction that did not commit.

Every concrete model here is an idmapper ``SharedMemoryModel`` (ADR-0008): one pk is one
Python object for the life of the process. A rollback restores the table, never that
object, so a row written and then rolled back keeps the refused values in memory, and
``refresh_from_db()`` cannot undo it (its query goes through the identity map).

``CacheGuard`` keeps a row's column values and cached relations before anything changes
them and writes them back onto the same object when the transaction does not commit
(ADR-4626). The admin site takes one around every POST (``web.admin.authoring.identity_map``);
a game service whose writes can be rolled back by a later refusal takes one too (the
ritual perform's component consumption, the full Fall's conversion; #4735).
"""

from __future__ import annotations

from django.db.models import Model
from evennia.utils.idmapper.models import SharedMemoryModel

#: SharedMemoryModel.delete() marks the Python object deleted; a typeclassed row then
#: refuses its own attributes. A rolled-back delete must clear it.
_DELETED_FLAG = "_is_deleted"


def _unlink_one_to_one_targets(row: Model, kept_relations: dict[str, object]) -> None:
    """Clear the reverse cache a form wrote onto a one-to-one target it picked.

    Assigning ``row.<o2o> = target`` also caches ``row`` as ``target``'s reverse
    accessor, on a shared row nobody kept. Before ``row`` gets its kept relations back,
    drop that back-pointer from any target it now caches but did not when kept.
    """
    cached = row._state.fields_cache  # noqa: SLF001
    for field in row._meta.concrete_fields:  # noqa: SLF001
        if not field.one_to_one or not field.is_cached(row):
            continue
        target = cached.get(field.cache_name)
        if target is None or target is kept_relations.get(field.cache_name):
            continue
        reverse = field.remote_field
        if reverse.is_cached(target) and reverse.get_cached_value(target) is row:
            reverse.delete_cached_value(target)


class CacheGuard:
    """Puts identity-mapped rows back as they were when a POST does not commit.

    ``keep`` records a saved row's column values and its cached relations before
    anything changes them; ``restore`` writes those back onto the same Python
    objects, so every holder of the cached instance sees the committed state
    again. Keeping a row twice keeps the first (pre-change) state. A row kept while
    still unsaved is evicted by ``restore`` if a rolled-back save cached it since.
    ``restore`` can run more than once.
    """

    def __init__(self) -> None:
        self._kept: dict[int, tuple[Model, dict[str, object], dict[str, object]]] = {}
        self._unsaved: dict[int, Model] = {}
        self._cached_before: dict[type[SharedMemoryModel], set[object]] = {}

    def watch_created(self, *models: type[SharedMemoryModel]) -> None:
        """Note which pks of ``models`` the identity map holds now, so ``restore`` can
        evict the rows a rolled-back transaction created. Eviction, never a refetch."""
        for model in models:
            self._cached_before[model] = {row.pk for row in model.get_all_cached_instances()}

    def keep(self, *rows: Model | None) -> None:
        for row in rows:
            if row is None or id(row) in self._kept or id(row) in self._unsaved:
                continue
            if row._state.adding:  # noqa: SLF001
                self._unsaved[id(row)] = row
                continue
            values = {
                f.attname: row.__dict__[f.attname]
                for f in row._meta.concrete_fields  # noqa: SLF001
                if f.attname in row.__dict__
            }
            if _DELETED_FLAG in row.__dict__:
                values[_DELETED_FLAG] = row.__dict__[_DELETED_FLAG]
            self._kept[id(row)] = (row, values, dict(row._state.fields_cache))  # noqa: SLF001

    def restore(self) -> None:
        for row, values, relations in self._kept.values():
            _unlink_one_to_one_targets(row, relations)
            if _DELETED_FLAG not in values:
                row.__dict__.pop(_DELETED_FLAG, None)
            row.__dict__.update(values)
            row._state.fields_cache = dict(relations)  # noqa: SLF001
        for row in self._unsaved.values():
            model = type(row)
            if (
                isinstance(row, SharedMemoryModel)
                and row.pk is not None
                and model.get_cached_instance(row.pk) is row
            ):
                model.flush_cached_instance(row, force=True)
        for model, before in self._cached_before.items():
            for row in model.get_all_cached_instances():
                if row.pk not in before:
                    model.flush_cached_instance(row, force=True)

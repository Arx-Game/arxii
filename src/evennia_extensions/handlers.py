"""Handlers that own cached rows for a parent model.

The layer beneath serializers. A serializer turns model data into a wire
format; it should not know where the rows came from, and it should not be
responsible for cleaning them up. Telnet commands, flows and service functions
read the same rows and never touch a serializer at all, so a guard that lives
in serialization is a guard half the game does not get.

Two hazards this layer exists to close, both consequences of ADR-0008's
identity map:

* **Stale rows.** A cache hung off an identity-mapped parent outlives the
  request that filled it. Writers clear it through
  ``RelatedCacheClearingMixin``: a child that names its parent in
  ``related_cache_fields`` drops the parent's cached properties whenever it is
  saved or deleted, which takes the handler with it.

* **Deleted rows.** ``Collector.delete()`` sets ``pk = None`` on every instance
  it deleted, cascades included, and under the identity map those are the
  shared instances - so a deleted row survives in memory as a pk-less zombie.
  Writer-side clearing does not catch all of these: a cascade and a
  ``queryset.delete()`` both bypass ``Model.delete()``, so the parent is never
  told. A handler therefore drops any row whose pk has gone falsey before it
  hands anything back. That is the belt to the writer-side braces, and it is
  why the discard lives here rather than in any one consumer (#3673).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from django.db.models import Model


class CachedRowsHandler[T: "Model"]:
    """One cached, ordered list of rows belonging to ``parent``.

    Subclasses implement ``load()``. Reads go through ``rows``, which never
    returns a row the database no longer has. Hang the handler off the parent
    as a ``cached_property`` so ``clear_cached_properties()`` drops it, and give
    the child model ``related_cache_fields = ["<parent field>"]`` so its own
    saves and deletes do that clearing.
    """

    def __init__(self, parent: Model) -> None:
        self.parent = parent
        self._rows: list[T] | None = None

    def load(self) -> list[T]:
        """Every row this handler owns, in the order consumers want them."""
        raise NotImplementedError

    @property
    def rows(self) -> list[T]:
        """The cached rows, minus any the collector has since nulled the pk on."""
        if self._rows is None:
            self._rows = list(self.load())
        elif not all(row.pk for row in self._rows):
            self._rows = [row for row in self._rows if row.pk]
        return self._rows

    def invalidate(self) -> None:
        """Drop the cache; the next read reloads. Writers go through the mixin."""
        self._rows = None

    def seed(self, rows: list[T]) -> None:
        """Fill the cache from rows someone else already fetched. See ``prime``."""
        self._rows = list(rows)

    #: The parent attribute holding this handler, for ``prime`` to reach.
    attname: ClassVar[str] = ""

    @classmethod
    def rows_for(cls, parents: list[Model]) -> dict[int, list[T]]:
        """Every row for every parent, from ONE query, bucketed by parent pk."""
        raise NotImplementedError

    @classmethod
    def prime(cls, parents: list[Model]) -> None:
        """Fill each parent's handler from one query, for a list endpoint.

        A handler loads for one parent, so a page of N parents is N queries
        unless something says otherwise. This is that something, and it is the
        only sanctioned way to batch: consumers still read the handler and stay
        ignorant of where the rows came from, which is the whole point of the
        layer. It is not a prefetch - nothing is written onto the parent by
        Django, so nothing can be silently skipped on an already-warm instance
        the way a ``to_attr`` prefetch is (ADR-0263). Priming overwrites, so a
        primed handler is as fresh as the request that primed it.
        """
        if not parents:
            return
        grouped = cls.rows_for(parents)
        for parent in parents:
            getattr(parent, cls.attname).seed(grouped.get(parent.pk, []))

    def __iter__(self) -> Iterator[T]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return bool(self.rows)

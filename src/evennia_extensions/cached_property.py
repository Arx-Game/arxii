"""A cached_property that stays correct as a Prefetch(..., to_attr) target.

Django's own ``Prefetch`` with a ``to_attr`` decides whether to run a prefetch
by checking whether the instance already has that attribute — for a genuine
``cached_property`` target that check is ``X in instance.__dict__`` (correct:
empty on a fresh instance), for anything else it falls back to
``hasattr(instance, X)`` (unsafe: a getter that never raises makes this
always True, so the batched query never runs at all). See #3816 for the full
trace against ``django/db/models/query.py::get_prefetcher``.

``PrunedCachedProperty`` is plain ``cached_property`` plus one addition: it
re-filters any row whose ``pk`` has gone falsey out of the cached list on
EVERY read, not just the first. This guards a ``Collector.delete()``, a
cascade, or a ``queryset.delete()`` — all of which bypass ``Model.delete()``
and so bypass ``RelatedCacheClearingMixin``/``related_cache_fields`` too,
leaving a "zombie" row (shared under the identity map) sitting in an
already-cached list forever otherwise.

It must be a DATA descriptor (define ``__set__``) so ``__get__`` runs on
every access — a plain ``cached_property`` is a non-data descriptor, and once
it has populated ``instance.__dict__``, Python's normal attribute lookup
finds that entry directly and never calls ``__get__`` again.
"""

from __future__ import annotations

from django.utils.functional import cached_property


class PrunedCachedProperty(cached_property):
    """A cached_property for a list of rows, self-healing against nulled pks."""

    def __set__(self, instance, value) -> None:
        instance.__dict__[self.name] = value

    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        if self.name not in instance.__dict__:
            instance.__dict__[self.name] = self.func(instance)
        rows = instance.__dict__[self.name]
        if not all(row.pk for row in rows):
            rows = instance.__dict__[self.name] = [row for row in rows if row.pk]
        return rows

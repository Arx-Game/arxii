# Cached Property Usage Standard

## Rule

**Always use `from django.utils.functional import cached_property`** in `src/`. Never use `from functools import cached_property`.

A custom pre-commit linter (`tools/lint_cached_property_import.py`, token `CACHED_PROPERTY_IMPORT`) enforces this.

## Why

`functools.cached_property` and `django.utils.functional.cached_property`
expose the same Python-level descriptor protocol (`__get__`, `__set_name__`,
set-on-instance-dict semantics). Behavior differs in threaded first-access
— stdlib `functools.cached_property` uses a global lock, Django's does not
— but in single-threaded request handling (Django's normal mode) they're
observationally equivalent.

But Django's `prefetch_related(Prefetch(..., to_attr="cached_X"))` machinery only recognizes its own class via `isinstance`. With `functools.cached_property`, Django's `is_to_attr_fetched()` decides "this isn't my cached_property, assume the attr is already populated" and **silently skips the batched prefetch**. Subsequent attribute access fires the cached_property's fallback query — once per row. Classic N+1, no warning, no exception, correct data, slow performance.

That interaction is a footgun wherever a prefetch and a cached_property meet, so the choice is made once, project-wide: Django's version everywhere.

**Note (#3673, narrowed by ADR-0298/#3816): a bare `to_attr` prefetch is still rejected, but a `to_attr` onto a genuine `PrunedCachedProperty` is sanctioned.** ADR-0263 records the original failure — Django decides whether to run a `to_attr` prefetch by asking whether the attribute is already there, and under the identity map (ADR-0008) the same instance answers the next request, so the second request re-serves the first one's rows. A row deleted in between comes back with a null id, because `Collector.delete()` nulls the pk on the shared instance. A bare-string `prefetch_related("x")` goes stale the same way through `_prefetched_objects_cache`.

Tracing the exact mechanism during #3816 (`django/db/models/query.py::get_prefetcher`/`is_to_attr_fetched`) found the defect is narrower than "never `to_attr`": Django's `__dict__`-based freshness check is correct on a cold instance for a genuine `cached_property` target — the staleness ADR-0263 documents is about nobody invalidating that cache afterward, not the check itself being wrong. ADR-0298 records the fuller reasoning. So the rule splits in two:

- **`to_attr=` onto `PrunedCachedProperty`** (`evennia_extensions/cached_property.py`) **is sanctioned**, provided write-side invalidation is wired explicitly at every place that mutates the underlying rows — either direct mutation of the cached list (append/filter) where write sites are concentrated, or `related_cache_fields`/`RelatedCacheClearingMixin` where they're scattered or admin-only. `PrunedCachedProperty` only solves cold-start batching and self-healing against pk-nulled zombie rows; it does not solve cross-write freshness by itself.
- **`to_attr=` onto anything else remains rejected, for three distinct failure modes:**
  - A **plain `@property`** (not `cached_property`) never satisfies Django's `isinstance` check at all — its getter never raises, so `hasattr()` reads `True` unconditionally even on a cold instance, and the batched query silently never runs, ever.
  - A **bare/unset attribute** (no property declared at all) is not the same failure — `hasattr()` correctly reads `False` on a cold instance, so the *first* prefetch does batch correctly. Its failure is the other one: under the identity map, once set, the instance answers "already fetched" forever across later requests, so a write made after the first load never shows up again (ADR-0263's original finding).
  - A **`CachedRowsHandler`-style wrapper** fed via `Prefetch(to_attr=...)` is worse than either: `Prefetch`'s `setattr(obj, to_attr, vals)` assigns a raw list, which *replaces* the handler object outright. Every `.rows`/`__iter__`/`__len__` consumer then breaks immediately on the next access, not eventually.

  `CachedRowsHandler` is retired as its consumers migrate to `PrunedCachedProperty`; a new `to_attr` outside that migration still fails the repo-wide `pattern:PREFETCH_TO_ATTR` ratchet, and the `prefetch-to-attr` hook covers the surfaces already converted.

The cached_property rule above still stands, and matters more under handlers, not less: a handler is held on its parent as a Django `cached_property` so `clear_cached_properties()` can drop it.

## Suppression

If a non-Django context genuinely needs `functools.cached_property` (e.g., a defensive `isinstance` target, a script outside `src/`, or a pure utility class that will never be a Prefetch target and where stdlib alignment matters), suppress with:

```python
from functools import cached_property  # noqa: CACHED_PROPERTY_IMPORT — <reason>
```

The canonical example is `src/evennia_extensions/mixins.py`, which `isinstance`-checks against both classes to clear caches defensively. Suppressions in `src/` should be rare and accompanied by a clear reason. The default answer is "use Django's."

## History

The original standard recommended `functools.cached_property` for stdlib
alignment. That advice predated discovery of the silent Prefetch+to_attr
breakage; the senior-dev review pass for Stories Phase 6a documented
the bug, and the project-wide sweep that followed inverted the
recommendation.

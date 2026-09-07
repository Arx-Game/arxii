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

**Note (#3673): the `to_attr` prefetch pattern this section describes is no longer the recommended shape.** ADR-0263 records why — Django decides whether to run a `to_attr` prefetch by asking whether the attribute is already there, and under the identity map (ADR-0008) the same instance answers the next request, so the second request re-serves the first one's rows. A row deleted in between comes back with a null id, because `Collector.delete()` nulls the pk on the shared instance. A bare-string `prefetch_related("x")` goes stale the same way through `_prefetched_objects_cache`.

Rows a parent owns belong behind a `CachedRowsHandler` (`evennia_extensions/handlers.py`): one place that loads them, one that drops rows whose pk has gone falsey, cleared by writers through `related_cache_fields`, batched for a list endpoint with `prime()`. Consumers — serializers, telnet commands, flows, service functions — read the handler. A new `to_attr` fails the repo-wide `pattern:PREFETCH_TO_ATTR` ratchet; the `prefetch-to-attr` hook covers the surfaces already converted and says what to build instead.

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

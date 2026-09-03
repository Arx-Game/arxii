---
name: sharedmemory-model
compatibility: polytoken
description: Use when adding or working with Django models in this repo, resolving an apparent N+1, optimizing queries, caching, or walking foreign-key relationships — and before writing any resolve_/batch_fetch_ helper or flushing the identity map.
---

# SharedMemoryModel

All concrete Django models in this repo use Evennia's `SharedMemoryModel`, which is an identity map: once an instance is loaded, it persists as a Python object whose FK walks are cached. This skill carries the usage rules (especially the import path) and the identity-map caching discipline that prevents reinventing query-batching infrastructure.

## Usage rules

- **Use SharedMemoryModel for All Models**: All concrete Django models must use SharedMemoryModel. A pre-commit linter enforces this
- **Correct Import Path**: Always import from `evennia.utils.idmapper.models.SharedMemoryModel`
- **NEVER** import from `evennia.utils.models` - this path contains utilities that trigger Django setup during import and will break the Django configuration with "settings are not configured" errors
- **Example**:
  ```python
  # CORRECT - this works
  from evennia.utils.idmapper.models import SharedMemoryModel

  # WRONG - this breaks Django setup
  from evennia.utils.models import SharedMemoryModel
  ```
- **When to Use**: SharedMemoryModel is required for all concrete models. It is especially beneficial for:
  - Trait definitions and conversion tables
  - Configuration data that changes rarely
  - Lookup tables for game mechanics
  - Any model that's read frequently but modified infrequently

## Trust the Identity Map — Don't Reinvent Caching

**SharedMemoryModel is a cache. Trust it. Do not reinvent caching infrastructure around it.**

Once a model instance is loaded, it is a persistent Python object in the identity map. Every subsequent lookup of that pk returns the same object with all previously-fetched FKs already resolved. Walking `persona.character.roster_entry.current_tenure.player_data.account` fires one query per relation *on first access*, and zero queries on every subsequent access — across the entire request, and often across requests. The "N+1" you are worried about is usually a mirage if the objects were already loaded upstream.

**When you think you see an N+1, the ONLY correct fix is:**
1. Check whether the objects being walked are already identity-mapped from an upstream query. If yes, there is no N+1.
2. If not, add `select_related` / `Prefetch(..., to_attr=...)` to the upstream queryset.
3. Let the code walk the FKs normally.

**Do NOT:**
- Write `resolve_*` or `batch_fetch_*` helpers that re-query data the identity map already has
- Replace a per-row `objects.get(pk=...)` with `filter(pk__in=[...])` to "batch away an N+1". Only a **single-kwarg pk lookup** short-circuits to the identity map (`SharedMemoryManager.get`, evennia/utils/idmapper/manager.py); `pk__in` is an ordinary queryset and issues SQL on every call, warm or cold. On an authored catalog the per-row `get(pk=...)` is the *cheaper* form once warm - see `core.managers.CachedAllMixin`, whose whole point is that "an unrelated `Model.objects.get(pk=X)` call elsewhere in the codebase also becomes a free hit once a catalog is warm" (#1846). Batching it trades zero queries for one.
- Flush the cache and re-fetch an object to "refresh" it after a mutation (`.save()` already updates the in-memory instance)
- Pass raw field values through serializer context to avoid attribute traversal
- Build parallel `{id: tuple}` lookups to "pre-resolve" related objects
- Call `.values()` or `.values_list()` to avoid instantiating model objects you think are "too expensive"
- Narrow a queryset with `.only(...)` or `.defer(...)`. The identity map answers every later load of that pk with the resident instance and never copies the fresh columns onto it, so a row first loaded narrowed stays narrowed for the whole process, and the next read of a missing column raises `KeyError` from Django's deferred-attribute getter (Sentry ARX2-9: the CG beginnings list narrowed codex grants, the Beginnings admin 500'd on `is_perspective` until restart). Narrowing saves nothing on a row that is loaded once and served from memory. If you genuinely want a projection rather than instances, that is the one place `.values_list()` belongs. Enforced by `lint_only_defer.py`; see ADR-0261.

**Signs you are fighting SharedMemoryModel instead of using it:**
- You wrote a function that fetches related data already reachable via FK walks
- You are constructing tuples/dicts to carry pre-extracted field values through multiple layers
- You are passing data "through context" that the serializer could read from `obj.related.field` for free
- Your "optimization" is more code than the straightforward FK walk it replaces

**The correct mental model:** SharedMemoryModel is not a Django model that loads from the database each time. It is a persistent Python object whose attributes sometimes hit the database on first access and never again. Use it like a Python object.

**Why this matters for mutations:** `.save()` on a SharedMemoryModel updates the in-memory instance. Cached properties (`@cached_property`, `Prefetch(to_attr=...)`) can go stale — update them in-place when you mutate, don't flush the whole cache. See `src/world/combat/views.py` for examples of in-place list updates on `participants_cached` after adding/removing participants.

## Known stale-cache traps

If a `@tag("postgres")` test fails with `obj.<fk> != expected` after a `refresh_from_db()` or a bulk `SET_NULL` elsewhere, the identity map can be stale in two distinct, easy-to-conflate ways — see [`references/stale-cache-traps.md`](references/stale-cache-traps.md) for the decision procedure before reaching for a fix (a cache-pop only helps one of the two cases; the other needs `flush_instance_cache()`, and the most common cause is neither — a service that never wrote the row).

## `path` is a reserved idmapper attribute name

A model field literally named **`path`** on a SharedMemoryModel is silently replaced by Evennia's idmapper metaclass with the model's dotted module-path string — Django's meta never sees the field, so it just vanishes with no error and no migration column. Use a different name (e.g. `training_path`). If a field mysteriously doesn't appear in `makemigrations` on an idmapper model, suspect a reserved-name collision like this one.

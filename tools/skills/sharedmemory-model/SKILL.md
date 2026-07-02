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
- Flush the cache and re-fetch an object to "refresh" it after a mutation (`.save()` already updates the in-memory instance)
- Pass raw field values through serializer context to avoid attribute traversal
- Build parallel `{id: tuple}` lookups to "pre-resolve" related objects
- Call `.values()` or `.values_list()` to avoid instantiating model objects you think are "too expensive"

**Signs you are fighting SharedMemoryModel instead of using it:**
- You wrote a function that fetches related data already reachable via FK walks
- You are constructing tuples/dicts to carry pre-extracted field values through multiple layers
- You are passing data "through context" that the serializer could read from `obj.related.field` for free
- Your "optimization" is more code than the straightforward FK walk it replaces

**The correct mental model:** SharedMemoryModel is not a Django model that loads from the database each time. It is a persistent Python object whose attributes sometimes hit the database on first access and never again. Use it like a Python object.

**Why this matters for mutations:** `.save()` on a SharedMemoryModel updates the in-memory instance. Cached properties (`@cached_property`, `Prefetch(to_attr=...)`) can go stale — update them in-place when you mutate, don't flush the whole cache. See `src/world/combat/views.py` for examples of in-place list updates on `participants_cached` after adding/removing participants.

## Known stale-cache traps

Two distinct ways the identity map can go stale, easy to conflate — diagnose with the decision procedure below before reaching for a fix:

1. **`refresh_from_db()` reloads the scalar `<fk>_id` but not the cached related object.** After `obj.refresh_from_db()`, `obj.some_fk_id` is correct but `obj.some_fk` can still return the old cached related instance from `__dict__`. But this is NOT the most common cause of a "stale after refresh" test failure — far more often, a **service simply never wrote the row**. Don't pop the cache reflexively.
2. **A `Collector`-driven bulk `SET_NULL`/`SET`/`CASCADE` update (from deleting the FK *target*) bypasses per-instance `.save()` entirely**, so the identity map never sees it — even `refresh_from_db()` or a fresh `Model.objects.get(pk=...)` returns the same long-lived cached instance with the stale scalar `<fk>_id`, even though raw SQL confirms the DB row is correct. This is a step further than #1: the *scalar* id itself is stale, not just the cached object. Fix: call `<Model>.flush_instance_cache()` before re-reading. `on_delete=SET_NULL` is enforced by Django's ORM Collector in Python, not a DB constraint — it behaves identically on SQLite and Postgres, so **don't** reach for `@tag("postgres")` here; that masks a real assertion gap rather than documenting a genuine backend divergence.

**Decision procedure when a `@tag("postgres")` test fails with `obj.<fk> != expected` after a refresh:**
1. Add a one-line assertion/print on `obj.<fk>_id` (not `obj.<fk>`) before the failing line. If `._id` is correct but `.<fk>` is wrong → stale cached object, case #1 (pop `obj.__dict__.pop("<fk>", None)` or use `flush_instance_cache()`).
2. If `._id` is ALSO wrong → either the writing service never ran (most common — check the service first), or it was a Collector-driven bulk update on someone else's `.delete()` (case #2 — use `flush_instance_cache()`, not a cache-pop).
3. `@tag("postgres")` tests never run on the SQLite fast tier — a test that only fails in CI's PG shard is the signature of a postgres-tagged test, not necessarily a genuine PG-vs-SQLite behavior difference. Check the tag before assuming a backend divergence.

## `path` is a reserved idmapper attribute name

A model field literally named **`path`** on a SharedMemoryModel is silently replaced by Evennia's idmapper metaclass with the model's dotted module-path string — Django's meta never sees the field, so it just vanishes with no error and no migration column. Use a different name (e.g. `training_path`). If a field mysteriously doesn't appear in `makemigrations` on an idmapper model, suspect a reserved-name collision like this one.

---
name: sharedmemory-model
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

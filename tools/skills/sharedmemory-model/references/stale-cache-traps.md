# Known Stale-Cache Traps

Consult this when a `@tag("postgres")` test fails with `obj.<fk> != expected` after a refresh — not general reading.

Two distinct ways the identity map can go stale, easy to conflate:

1. **`refresh_from_db()` reloads the scalar `<fk>_id` but not the cached related object.** After `obj.refresh_from_db()`, `obj.some_fk_id` is correct but `obj.some_fk` can still return the old cached related instance from `__dict__`. But this is NOT the most common cause of a "stale after refresh" test failure — far more often, a **service simply never wrote the row**. Don't pop the cache reflexively.
2. **A `Collector`-driven bulk `SET_NULL`/`SET`/`CASCADE` update (from deleting the FK *target*) bypasses per-instance `.save()` entirely**, so the identity map never sees it — even `refresh_from_db()` or a fresh `Model.objects.get(pk=...)` returns the same long-lived cached instance with the stale scalar `<fk>_id`, even though raw SQL confirms the DB row is correct. This is a step further than #1: the *scalar* id itself is stale, not just the cached object. Fix: call `<Model>.flush_instance_cache()` before re-reading. `on_delete=SET_NULL` is enforced by Django's ORM Collector in Python, not a DB constraint — it behaves identically on SQLite and Postgres, so **don't** reach for `@tag("postgres")` here; that masks a real assertion gap rather than documenting a genuine backend divergence.

**Decision procedure:**
1. Add a one-line assertion/print on `obj.<fk>_id` (not `obj.<fk>`) before the failing line. If `._id` is correct but `.<fk>` is wrong → stale cached object, case #1 (pop `obj.__dict__.pop("<fk>", None)` or use `flush_instance_cache()`).
2. If `._id` is ALSO wrong → either the writing service never ran (most common — check the service first), or it was a Collector-driven bulk update on someone else's `.delete()` (case #2 — use `flush_instance_cache()`, not a cache-pop).
3. `@tag("postgres")` tests never run on the SQLite fast tier — a test that only fails in CI's PG shard is the signature of a postgres-tagged test, not necessarily a genuine PG-vs-SQLite behavior difference. Check the tag before assuming a backend divergence.

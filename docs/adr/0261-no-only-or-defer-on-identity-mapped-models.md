# ADR-0261: No `.only()` or `.defer()` on identity-mapped models

**Date:** 2026-09-03
**Status:** Accepted
**Context:** Sentry ARX2-9 (production, 2026-09-03): the Beginnings admin change page
500'd with `KeyError: 'is_perspective'`. Extends ADR-0008.

## Decision

A queryset over a `SharedMemoryModel` never narrows its columns with `.only(...)` or
`.defer(...)`. Rows are loaded whole. When code wants a projection rather than
instances (a pk walk, a count, an id set), it uses `.values()` or `.values_list()`,
which never instantiate a model and so never touch the identity map. Enforced
repo-wide by `tools/lint_only_defer.py` (`lint-only-defer` hook); the
`# noqa: IDMAPPER_ONLY` suppression is ratcheted at zero and exists only for a model
that is provably not identity-mapped.

## Why

Evennia's idmapper metaclass answers every construction of an already-resident pk
with the resident instance and does not copy the freshly-read columns onto it. That
is the entire point of the identity map (ADR-0008), and it has a corollary that is
easy to miss: **the first load of a row in a process decides which columns that row
has for the rest of the process.** A row first loaded through `.only("a", "b")` is
resident with every other column deferred. Every later full-column query for the
same pk still hands back that narrowed instance. Reading a missing column goes
through Django's deferred-attribute getter, whose `refresh_from_db(fields=[...])`
fetches the row, gets the same resident instance back, sees the field still
deferred, skips it, and raises `KeyError`.

That is exactly what happened. The CG beginnings list prefetched codex grants with
`.only("beginnings_id", "entry_id")`, a player opened character creation, and from
then on the Beginnings admin's inline formset asked those resident grant rows for
`is_perspective` and crashed, for every staff member, until the server restarted.
The narrowing had saved one boolean column on a row the identity map loads once
and then serves from memory.

Seventeen sites carried the same construct: codex-grant prefetches for beginnings,
paths, traditions and distinctions, passable-edge prefetches for positioning,
declaration prefetches for battles, dramatic-moment tags for scenes, an area
subtree walk and a mission-route lookup. Each was a latent copy of the same 500,
waiting for the narrowed load to happen before the full one. All were removed in
the same change. A guard test loads the CG list on a cold cache and then opens the
admin change page.

## Rejected

- **Overriding `from_db` / the metaclass to merge fresh columns onto a resident
  instance.** Dependency code is read-only, and a first-party shim on the base
  model would make every load a per-column write into a shared object under
  concurrent requests. The identity map's contract is "one object per row"; the
  fix is to stop asking it for partial objects.
- **Flushing the cache before the admin loads.** A cache-flush in a view is the
  reinvented-caching pattern the sharedmemory-model skill forbids, and it would only
  protect the one page that happened to crash this time.
- **Keeping `.only()` where "the narrowed columns are all anyone reads."** The
  claim cannot be checked: the admin, a serializer, a factory-held reference or a
  later feature reads any column of any row, and the failure shows up in a different
  request from the one that narrowed the row. The saving is nil on a cached row, so
  there is no trade to make.

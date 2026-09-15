# ADR-0298: `to_attr` onto a genuine `cached_property` is safe; narrows ADR-0263/ADR-0278

**Status:** Accepted (2026-09, #3816)

**Context.** ADR-0263 documented `Prefetch(..., to_attr=X)` silently skipping
re-fetch under the identity map and concluded, blanket, "never `to_attr` on
an identity-mapped model, always `CachedRowsHandler`." Tracing the precise
mechanism (`django/db/models/query.py::get_prefetcher`/`is_to_attr_fetched`)
during #3816 found the actual defect is narrower: Django's `__dict__`-based
freshness check for a genuine `cached_property` target is correct on first
access; the staleness ADR-0263 documents is about nobody invalidating it
afterward, not `cached_property` itself being unsafe. Checked all 5 of
`CachedRowsHandler`'s existing consumers for a case `Prefetch` genuinely
can't express (per-parent parameterized filtering) — found none, though one
needs a companion property rather than a single drop-in swap:
`CompanionOrderHandler.rows_for()`'s batch path already does
`filter(encounter_id__in=ids)` (no round filter at the DB level) and then
filters to the current round in a Python loop
(`row.round_number == row.encounter.round_number`). Migrating it off
`CachedRowsHandler` means a `PrunedCachedProperty`-backed raw list holding
*all* rounds' orders (fed via `Prefetch(to_attr=...)`, unfiltered), plus a
separate plain `@property` — not itself cached, cheap to recompute — that
filters that already-fetched list down to the current round in Python at
read time.

**Decision.** `PrunedCachedProperty` (`evennia_extensions/cached_property.py`)
is the sanctioned primitive for a parent-owned list of rows fed via
`Prefetch(to_attr=...)`. It solves two narrow things only: satisfying
Django's own freshness-detection `isinstance` check (so a cold page load
batches correctly), and re-filtering pk-nulled rows on every read. It does
NOT by itself solve cross-write staleness — that remains owned explicitly
per relation, by direct handler mutation (append/filter) where write sites
are concentrated, or `related_cache_fields`/`RelatedCacheClearingMixin` as
the primary mechanism where they're scattered or admin-only.
`CachedRowsHandler` is retired once its consumers migrate to this pattern.

**Rejected alternative: keep `CachedRowsHandler`, add a `prime()` warm-skip.**
Its `rows_for()`/`prime()` batching duplicates what Django's own
`prefetch_related_objects` already does for free (`obj_to_fetch = [obj for
obj in obj_list if not is_fetched(obj)]`) once the target is a genuine
`cached_property` — a wrapper object cannot be a `Prefetch` `to_attr` target
at all (Prefetch always assigns a raw list), so keeping the wrapper forecloses
using Django's own machinery regardless.

**How to apply.** New parent-owned-row-list code uses `PrunedCachedProperty`
directly + `Prefetch(to_attr=...)`, paired with explicit write-side
invalidation — never `CachedRowsHandler` (retired) and never a plain
`@property`/bare `to_attr` attribute (both unsafe per the two distinct
failure modes #3816 traced: the former never batches at all since a getter
that never raises defeats Django's `hasattr` fallback check; the latter
batches once then never refreshes, ADR-0263's original finding). See
`evennia_extensions/CACHED_PROPERTY_STANDARD.md` for the mechanism.

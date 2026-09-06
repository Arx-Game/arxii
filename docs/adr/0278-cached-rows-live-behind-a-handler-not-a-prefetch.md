# ADR-0278: Rows a parent owns live behind a handler, not a prefetch

**Status:** Accepted (2026-09-06, #3673). Extends ADR-0263 (no `to_attr` prefetch onto
identity-mapped instances) and ADR-0008 (SharedMemoryModel everywhere); ADR-0263's rule 1
(a grouped query instead of a `to_attr` prefetch) is the mechanism this decision puts a
name and a home to.

**Context.** ADR-0263 recorded that a `Prefetch(..., to_attr=X)` onto an identity-mapped
parent silently stops running once `X` is set, so later requests re-serve the first
request's rows. #3673 found the same defect on the CG Upbringing list and added a second
failure to it: `Collector.delete()` sets `pk = None` on every instance it deleted,
cascades included, and under the identity map those are the shared instances. So a
question a staff member deleted in the Builder kept being offered to players, arriving
as `"id": null`. Two half-fixes were considered and rejected on the way. Clearing the
cache on delete does not cover it: a cascade and a `queryset.delete()` both bypass
`Model.delete()`, so no writer-side hook fires. Filtering pk-less rows in the serializer
does not cover it either, because telnet commands, flows and service functions read the
same rows and never reach a serializer - a guard there is a guard half the game does not
get.

**Decision.** Rows a parent owns are reached through a handler
(`evennia_extensions/handlers.py::CachedRowsHandler`), never through a prefetch attribute
and never through a per-consumer query. A handler owns the load, the ordering and the
cache for one parent, and:

1. **Drops any row whose pk has gone falsey** before returning anything. This is the belt
   that covers cascades and `queryset.delete()`, and it is why the check lives in the
   layer rather than in a consumer.
2. **Is cleared by writers** through the existing `RelatedCacheClearingMixin`: the child
   names its parent in `related_cache_fields`, and the handler dies with the parent's
   cached properties on every child save and delete.
3. **Batches with `prime()`**, not with a prefetch, so a list endpoint stays at one query
   while consumers still just read the handler. Nothing is written onto the parent by
   Django, so nothing can be silently skipped on a warm instance.

A serializer turns model data into a wire format. It does not know where the rows came
from and is not responsible for cleaning them up.

**Rejected alternative: a base serializer that filters pk-less rows.** It is the smaller
change and it fixes the symptom that was reported, because the report came from the API.
It fixes nothing for telnet, flows or service functions, which is most of the game's own
reading. Rejected for that reason, not for cost.

**Rejected alternative: a `SharedMemoryModel` subclass that guards reads.** There is
nothing to hook. `to_attr` writes a plain entry into the instance `__dict__`, so no
descriptor runs on the read and a model base class never sees it.

**How to apply.** `grep -rn "to_attr=" src/` is the audit; 343 sites are grandfathered by
the `pattern:PREFETCH_TO_ATTR` ratchet in `tools/noqa_ratchet_baseline.txt`, whose count
may only go down. A new one fails anywhere in `src/`. The `prefetch-to-attr` hook covers
the surfaces already converted and names what to build instead; an app joins its `files:`
regex when its count reaches zero. `OriginTemplate.questions` is the worked example - one
handler read by the CG API serializer, the questionnaire resolver, the draft validators,
the finalize service and the Builder's rail.

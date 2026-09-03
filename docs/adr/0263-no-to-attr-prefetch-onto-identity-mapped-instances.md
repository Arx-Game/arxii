# ADR-0263: No `to_attr` prefetch onto identity-mapped instances

**Status:** Accepted (2026-09-03, #3564; the failure was found in #3563). Extends ADR-0008
(SharedMemoryModel everywhere) and ADR-0261 (no .only()/.defer() on identity-mapped models: the same cache, a sibling hazard).

**Context.** Django decides whether to run a `Prefetch(..., to_attr=X)` by asking whether the
instance already has `X` (`django/db/models/query.py::get_prefetcher`: `X in instance.__dict__`
for a `cached_property` target, else `hasattr`). Under the idmapper (ADR-0008) every queryset
returns the same Python object for a pk for the life of the process. So the first prefetch that
sets `X` on an instance makes every later prefetch onto that instance a silent no-op: rows a
staff member edited afterwards never show up until the worker restarts. #3563 found this on
`Transition.cached_required_outcomes`, where `get_eligible_transitions`, the GM queue and the
transition payload all read stale routing rules after a GM edited them.

**Decision.** Two rules, both cheap:

1. A loader that needs fresh related rows for many identity-mapped parents assigns the attribute
   itself from one grouped query (`filter(parent_id__in=ids)`, bucketed by parent id), never a
   `to_attr` prefetch. Same query count, never skipped. `world/gm/services.py::find_situations`
   is the pattern here; #3563 (PR #3600) adds a second one,
   `world/stories/services/routing.py::routing_reports_for_episodes`.
2. Every writer of rows that a cached attribute mirrors pops that attribute from the parent's
   `__dict__` after writing (`save_transition_with_outcomes`, the raw rules viewset,
   `TransitionAdmin.save_related`), with a regression test that reads, writes, reads.

**Rejected alternative: keep `to_attr` prefetches and clear the idmapper.** Flushing the cache
between requests throws away the identity map's whole benefit and still leaves in-process
readers (the resolve path, flows) stale within a request. Deleting `cached_property` targets in
favour of plain attributes does not help either; the skip keys on presence, not on the property.

**How to apply.** `grep -rn "to_attr=" src/` is the audit: each hit needs either a writer-side
pop or a rewrite to a grouped query. New code does not add hits. The hits that exist today on
`Transition.cached_required_outcomes` (`get_eligible_transitions`, the GM queue, the transition
payload) are covered by #3563's writer-side pops; they are not yet fixed on the branch that
records this ADR.

# Service functions read through cached handlers, not bare ORM queries

Service functions must not issue `.filter()` / `.all()` / `.exists()` queries against
models whose data is already available on a cached handler attached to the character,
sheet, or other parent object in scope. A handler (e.g. `CharacterThreadHandler`,
`CharacterCovenantRoleHandler`) loads its queryset once with `select_related` /
`prefetch_related` and caches it as a `cached_property`; all downstream lookups are
list comprehensions against that in-memory list. If a mutation adds or removes a row,
the mutator calls `handler.invalidate()` so the next read sees fresh data — the service
never re-queries mid-flow. We rejected per-call `.filter()` lookups because they
silently produce N+1 query patterns and bypass the identity-map / prefetch warming the
handlers exist to provide. As a rule of thumb, any `.filter()` or `.all()` inside a
service function is automatically suspect: you'd expect the parent object (the
character sheet, org, or other FK owner) to carry the handler and be passed in, then
the answer derived via a list comprehension on the cached data.

> Status: accepted · Source: #1913 design discussion · Confidence: derived from existing
> handler pattern (`CharacterThreadHandler`, `CharacterCovenantRoleHandler`), verify
> against code

# Paginate list endpoints by default; opt out explicitly

`REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` is now set to
`web.api.pagination.DefaultPagination` (PageNumber, `page_size=50`,
`?page_size=` override capped at 200), so **every list endpoint is paginated
unless it declares `pagination_class = None`**. Before this, no default was
set: a ViewSet that forgot `pagination_class` silently shipped an *unbounded*
bare array — 43 of ~202 viewset classes were in exactly that state, one HTTP
request from returning every row in the table. Pagination-by-default makes the
safe posture the *default* posture: a new ViewSet can no longer leak an
unbounded list by omission, and the ~40 pre-existing bare-array endpoints keep
their exact current shape via an explicit `= None` that now *documents* the
choice instead of leaving it to chance.

**Behavior-preserving by construction.** This change flips zero existing
endpoints: every currently-unpaginated viewset got an explicit `= None`, and
the generated OpenAPI schema (`src/schema.json`) is byte-identical to before —
verified by regenerating it and confirming no response shape changed
array→paginated or paginated→array. So no frontend consumer breaks. Genuinely
paginating the ~13 can-grow lists that today opt out (media galleries, market
listings, the ResonanceGrant audit ledger, endorsement ledgers, …) is
deliberately **out of scope here** — each needs its own frontend-consumer
rewire and testing, and lands as a focused follow-up PR. This ADR is only about
the *default* and the opt-out convention.

`DefaultPagination` lives in `web/api/` (the API-infrastructure home, alongside
the shared exception handler) — **not** reusing `world.stories.pagination
.StandardResultsSetPagination`, because a project-wide setting must not depend
on a specific game app.

**Rejected: targeted gap-fill without a global default** — add pagination
case-by-case only where a list is known to grow. Closes today's gap but leaves
the trap armed: the *next* viewset authored without `pagination_class` ships
unbounded again. The whole value here is making omission safe, which only a
default delivers. **Rejected: `page_size=20`** (the `StandardResultsSetPagination`
value) — 50 is the modal per-endpoint `page_size` already in the codebase, so it
minimizes surprise for the endpoints that inherit the default going forward.

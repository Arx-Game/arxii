# ADR-0260: request.user is the Account typeclass; account data caches on the Account, request data goes through middleware

**Date:** 2026-09-02
**Status:** Accepted
**Context:** Sentry ARX2-7 and ARX2-8 (production, first day with an outside player).

## Decision

1. `request.user`, when authenticated, **is** the `Account` typeclass. Views read
   typeclass attributes off it directly (`cached_primary_persona_ids`,
   `get_available_characters`, `played_character_sheet_ids`). They do not branch on
   the account's shape, and they do not re-derive account facts per request.
2. Data about the **account** is cached on the Account object. It is fully persistent
   and identity-mapped, so a `cached_property` there is computed once per account per
   process and invalidated through `related_cache_fields`. That is the home for
   "this account's PRIMARY persona ids" and its kin.
3. Data about the **request** (a viewer scope that only makes sense for this call)
   is attached once, at the boundary, by middleware, as a documented attribute.
   Never lazily memoized on a viewset instance or `setattr` onto `request`
   mid-request (#3597).
4. "Who is this request acting as" on the web is the durable selection
   (`PlayerData.selected_entry`, ADR-0241), read through
   `world.roster.services.selection.selected_character`. Not `request.user.puppet`.
5. `ArxAccountAdapter.new_user` instantiates `settings.BASE_ACCOUNT_TYPECLASS`, so
   signup produces a typeclassed row. Rows that predate this are repointed by hand;
   the required-content probe `typeclassed-accounts` names them.

## Why

Evennia swaps an instance's class from `db_typeclass_path` in `__init__`, and when
that column is empty it pins the column to the class the instance was built as.
allauth's default `new_user` is `get_user_model()()`, and Django's `create_superuser`
has the same shape, so every web-signup account and every `createsuperuser` account
was a bare `AccountDB` forever: no `puppet`, no `get_available_characters`, no
`cached_primary_persona_ids`. The events lists, the `X-Character-ID` auth mixin,
checks and combat views all answered 500 for those players. Tests never saw it
because factories build accounts through `create.create_account`.

The first fix attempt moved the persona query off the typeclass into a per-request
memo on the viewset. That was papering over the symptom: the persona list is account
data, the Account is persistent, and the cache on it was already right. The bug was
the account not being an Account.

`request.user.puppet` has a separate problem: under `MULTISESSION_MODE = 2` it is the
list of every puppet, empty with no session and never `None`, so the missions journal
handed a list to `journal_for`. The web already has a server-side answer to "who am
I" that needs no session, and that is the only answer the web should use.

## Rejected

- **Per-request memo on the viewset** (`_x: T | None = None`, filled lazily). Invisible
  state, order-dependent query counts, and it only exists to avoid trusting
  `request.user`'s type. Reverted in the same PR; the wider family is #3597.
- **Guarding reads with `hasattr(request.user, ...)`.** Same objection.
- **A data migration to repoint existing bare rows.** Before launch that is a single
  row, fixed with one shell statement. Schema history is not the place for a
  one-off repair.
- **Patching Evennia's manager so `createsuperuser` typeclasses.** Dependency code
  is read-only; the probe names the row instead.
- **Falling back from selection to `get_all_puppets()`.** Reintroduces the session
  dependency; a live puppet without a selection is not a web state.

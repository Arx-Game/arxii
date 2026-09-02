# ADR-0259: Views read the account model, never the Account typeclass; signup instantiates the typeclass

**Date:** 2026-09-02
**Status:** Accepted
**Context:** Sentry ARX2-7 and ARX2-8 (production, first day with an outside player).

## Decision

1. A DRF view never reads typeclass-only state off `request.user`. What a view needs
   about the requesting account lives in a service function that takes the
   `AccountDB` model (`world.scenes.services.primary_persona_ids_for`,
   `world.roster.services.selection.selected_character`). The `Account` typeclass may
   cache on top of those services; it is never the only place the logic lives.
2. "Who is this request acting as" is the durable selection
   (`PlayerData.selected_entry`, ADR-0241), resolved by `selected_character`. Not
   `request.user.puppet`.
3. `ArxAccountAdapter.new_user` instantiates `settings.BASE_ACCOUNT_TYPECLASS`.

## Why

Evennia swaps an instance's class from `db_typeclass_path` in `__init__`, and when that
column is empty it pins the column to the class the instance was built as. allauth's
default `new_user` is `get_user_model()()`, and Django's `create_superuser` is the
same shape, so every web-signup account and every `createsuperuser` account was a bare
`AccountDB` forever: `request.user` had no `puppet`, no `get_available_characters`, no
`cached_primary_persona_ids`, and the events lists, the `X-Character-ID` auth mixin,
checks and combat views all answered 500 for those players. The dev database's only
account has the same shape, which is why tests (which build accounts through
`create.create_account`) never saw it.

`request.user.puppet` has a second problem on its own: under `MULTISESSION_MODE = 2` it
is the list of every puppet, empty with no session and never `None`, so the missions
journal handed a list to `journal_for`. The web client already has a server-side
answer to "who am I" that needs no session at all, and that is the only answer the
web should use.

## Rejected

- **Guarding each read with `hasattr(request.user, ...)`.** Papers over the shape
  instead of fixing it, and leaves the typeclass as the sole owner of logic a view needs.
- **Repairing rows only, no adapter change.** The next signup would recreate the bug.
- **Fixing `createsuperuser` by patching Evennia's manager.** Dependency code is
  read-only; the required-content probe names the row instead.
- **Falling back from selection to `get_all_puppets()`.** Reintroduces the typeclass
  dependency, and a live puppet without a selection is not a web state.

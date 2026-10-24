# ADR-4626: Refused admin saves are put back in place, by the admin site

**Date:** 2026-10-24
**Status:** Accepted
**Issue:** #4626

## Decision

Every stock admin page over an identity-mapped row gets `RefusedSaveRestoreMixin`
(`web/admin/authoring/identity_map.py`), and no admin lists it: `ArxAdminSite.register` puts
it first in the MRO of each admin whose model, or a declared inline's model, is a
`SharedMemoryModel`, Evennia's own admins included. Before Django validates, the mixin keeps
each bound row's column values and relation cache in a `CacheGuard`; when the save is refused
(the change form, an inline, a list edit) or raises part way (Django's transaction has
rolled back), it writes those values back onto the same Python objects. That way the page,
the API, the game and any row already holding the instance read what the database holds. A
guard test walks the live registry and fails for an admin without the mixin.

## Rejected

Flushing the refused rows from the identity map (#4625's `RefusedSaveFlushMixin`, still the
builder pages' `flush_refused_instances`): a flush only drops the cache entry, so a row that
already held the instance (a character's known technique pointing at its Technique) kept the
refused values, and the next reader got a second object for the same pk. Adding the mixin
admin by admin: one forgotten admin is the bug again, and there were close to 800. A global
flush or `refresh_from_db()`: the first is banned (`sharedmemory-model` skill), and the second
goes through the identity map and copies the refused values onto themselves.

Cost if wrong: the restore hooks two Django internals, `_create_formsets` (the one point
where the change form and every inline are bound and none is validated) and
`render_change_form` on a POST (reached only when a change form is refused). A Django
upgrade that renames either stops the restore without an error. The journeys in
`integration_tests/test_refused_admin_saves_journeys.py` fail if that happens.

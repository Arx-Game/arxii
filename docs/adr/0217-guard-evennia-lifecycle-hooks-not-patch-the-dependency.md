# ADR-0217: Guard Evennia's lifecycle hooks in our own code, not by patching the dependency

Context: production reload crashed with `AttributeError: 'AccountDB' object has no attribute
'at_server_reload'` (#3195). `evennia/server/service.py` `shutdown()` calls `at_server_reload`,
`at_server_shutdown`, `unpuppet_all`, and `_pause_task` directly on every cached `ObjectDB`,
`AccountDB`, and `ScriptDB` instance with no guard, assuming every cached instance is running as
its typeclass. That assumption can be false: `set_class_from_typeclass`
(`evennia/typeclasses/models.py`) has a fallback ladder that can leave an instance bare, and one
branch assigns `__dbclass__` instead of `__class__`. A single bare instance in the idmapper cache
therefore crashes the shutdown Deferred and hangs every reload until systemd kills it. We rejected
two alternatives: editing the vendored Evennia copy in `site-packages` (forbidden outright — see
CLAUDE.md's "Never edit dependency code," and a worktree venv edit silently poisons the shared uv
cache); and waiting for an upstream fix (reload stays broken indefinitely, and every deploy needs a
full player-disconnecting restart in the meantime). Instead, `evennia_extensions.typeclass_hook_guard`
patches the three bare model classes from our own code, at Django `AppConfig.ready()` time, adding a
loudly-logging no-op only for a hook genuinely missing from the bare class — a typeclass's own hook
sits closer in the MRO and is never touched, so the fix is invisible to every correctly-typeclassed
instance and only changes behavior for the already-broken bare case. Root cause (how a bare instance
enters the cache) is tracked separately in #3195 and is not fixed here; the guard makes the symptom
non-fatal without hiding the condition, since each stub firing logs a warning naming the class and
instance pk. A related upstream bug found while diagnosing, not patched here:
`evennia/accounts/models.py:109` sets `AccountDB.__settingsclasspath__` to
`settings.BASE_SCRIPT_TYPECLASS` instead of `BASE_ACCOUNT_TYPECLASS`.

> Status: accepted · Source: issue #3195 (production reload outage, 2026-08-16) · Related: none

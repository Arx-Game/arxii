# Core Management Tests

## The phantom-migration guard, and why it takes two test modules

Django's `makemigrations`, run against this project, wants to create migrations
inside the **Evennia library** for the proxy models our typeclasses imply. Those
files exist only in the venv that generated them, so any migration depending on
one blows up everywhere else with `NodeNotFoundError`. `core_management`'s
custom `makemigrations` prevents that by filtering the excluded apps and
rewriting any dependency on a filtered migration onto that app's real graph leaf.

Two modules guard it, and they are guarding different things:

- **`test_command_resolution.py`** — asserts Django actually *resolves*
  `makemigrations` to `core_management`. This is the one that matters most, and
  it is the newer of the two for an unhappy reason (see below).
- **`test_makemigrations_fix.py`** — unit-tests the filtering and
  dependency-rewriting logic by calling `Command.write_migration_files`
  directly.

### Why both (#2885)

`core_management` and `django_linear_migrations` both ship a `makemigrations`,
and only one wins. Which one is decided entirely by INSTALLED_APPS order, in the
counter-intuitive direction: `get_commands()` walks
`reversed(apps.get_app_configs())` and `update()`s, so the app listed **earliest**
wins.

Ours lost, from the day `django_linear_migrations` was added until #2885. The
filter was dead code that whole time, and every migration generated in that
window carried a phantom dependency.

`test_makemigrations_fix.py` did not notice, because it imports the command class
and exercises it directly — it will happily pass while Django runs somebody
else's command. That is the blind spot `test_command_resolution.py` exists to
close: **it asserts on resolution, never on the class in isolation.**

### These tests are not skipped

They used to be, on the reasoning that they were "demonstration tests, not
regression tests" and that "we're not worried about regressions in this specific
fix." That reasoning is what #2885 disproved — and skipping had a second cost:
the fixtures silently rotted against a later rewrite of
`write_migration_files`, so they errored outright the moment the skip came off.

Both modules run in the normal suite now. They are fast (no database — the
`MigrationLoader` and the MODEL_MAP-regeneration thread are stubbed) and they
guard something whose failure mode is expensive and hard to read from the CI
output it produces.

```bash
arx test core_management --sqlite
```

### If `test_makemigrations_resolves_to_core_management` fails

Somebody reordered INSTALLED_APPS and another app's `makemigrations` now shadows
ours. Fix the order — see the "ORDER IS LOAD-BEARING" comment in
`server/conf/settings.py` — rather than the test.

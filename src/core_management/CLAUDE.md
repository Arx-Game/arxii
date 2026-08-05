# Core Management - Claude Code Instructions

This app provides core Django management commands that solve fundamental issues with Evennia integration.

## Custom makemigrations Command

### The Problem
When Django's `makemigrations` scans all installed apps (including Evennia library apps), it detects that proxy models (typeclasses) need to be created for apps with ForeignKeys to Evennia models. This creates "phantom migrations" in the Evennia library like:
- `objects/migrations/0014_defaultobject_defaultcharacter_defaultexit_and_more.py`
- `accounts/migrations/0013_defaultaccount_account_bot_defaultguest_and_more.py`

These phantom migrations:
1. Don't exist in the Evennia library for other installations
2. Create dependency errors like `NodeNotFoundError`
3. Break the migration system across environments

### Our Solution

**Custom makemigrations command** in `core_management.management.commands.makemigrations`:
- **Uses Django's normal app scanning** to detect all changes comprehensively
- **Filters out problematic migrations** before writing them to disk
- **Automatically works with any apps** - no maintenance required when adding new apps
- **Shows clear warnings** when ignoring proxy model migrations

### Usage

```bash
# Safe makemigrations - completely prevents phantom Evennia migrations
arx manage makemigrations

# Still works - can specify apps when needed
arx manage makemigrations traits
arx manage makemigrations evennia_extensions
```

### Verified behaviour

Re-verified end to end at #2885 (the original write-up below described a state
the code had not actually been in for months — see the ordering warning further
down):

1. **No phantom migration created**: `site-packages/evennia/*/migrations/` is left byte-for-byte stock; no `0014_defaultobject_...` appears
2. **Proper dependency resolution**: generated migrations reference real Evennia migrations (`objects.0013_...`)
3. **Warning system**: one `Ignoring proxy model migration for excluded app: <app>` line per suppressed app (currently `accounts`, `comms`, `objects`, `scripts`, `typeclasses`)

If you run `arx manage makemigrations` and see **no** "Ignoring proxy model
migration" lines while a `Migrations for 'objects':` header *is* printed, the
guard is not running — check the app order.

### Technical Implementation

Our `Command` subclasses **django-linear-migrations'** `makemigrations`, not Django's, so both behaviours survive: our filtering AND the `max_migration.txt` sentinel (#991). It overrides one method, `write_migration_files()`, which does two things:

1. **Filters** out any detected changes to `EXCLUDED_APPS` before they reach disk, warning per dropped app.
2. **Rewrites dependencies** — a kept migration that depends on a migration we just dropped is repointed at that app's real graph leaf. Without this the filtering alone would still leave a dangling reference.

(It also kicks off MODEL_MAP.md regeneration in a daemon thread when anything was kept.)

### ⚠️ It only runs if `core_management` precedes `django_linear_migrations` in `INSTALLED_APPS`

Both apps ship a `makemigrations`, and only one wins. Django's `get_commands()` iterates `reversed(apps.get_app_configs())` and `dict.update()`s, so the app listed **earliest** in `INSTALLED_APPS` wins — the opposite of the natural reading.

This is not hypothetical: from the day `django_linear_migrations` was added until **#2885**, it was ordered first and everything on this page was inert. `arx manage makemigrations` ran *its* command, wrote a phantom Evennia migration into the developer's venv, and generated project migrations depending on it — which fails only on other machines, as `NodeNotFoundError` on CI jobs that never mention migrations (`ty`, `api-types-drift`).

If you reorder `INSTALLED_APPS`, read the "ORDER IS LOAD-BEARING" comment in `server/conf/settings.py` first.

## Testing the Fix

Two modules, guarding different things — both run in the normal suite (`arx test core_management --sqlite`), neither needs a database:

- **`tests/test_command_resolution.py`** — asserts Django actually resolves `makemigrations` to `core_management`, that the winner carries `EXCLUDED_APPS`, that it is still a django-linear-migrations subclass (so the sentinel survives), and that the reorder didn't shadow `squashmigrations`/`rebase_migration`/`create_max_migration_files`.
- **`tests/test_makemigrations_fix.py`** — unit-tests the filtering and dependency-rewriting logic against `Command.write_migration_files` directly.

**Why the second one could not have caught #2885:** it imports the command class and exercises it, so it passes whether or not Django ever runs that class. That is precisely the blind spot the first module closes. A test that asserts on *behaviour of a class* is not a test that the class is *wired up*.

Both were `@unittest.skip`ped until #2885, on the reasoning that they were demonstration rather than regression tests. See `tests/README.md`.


## Content export: additions are withheld by default (#2890, ADR-0191)

`content_export.export_to_content_repo` may **update** rows the content repo already
has, but by default it will not **add** rows it doesn't. A row whose natural key is
absent from the target fixture is withheld and reported in `ExportResult.withheld`;
`allow_additions=True` pushes it and reports it in `ExportResult.added`.

This exists because `SEED_SAMPLE_CONTENT` is a legitimate path — it gives a third
party with no content repo a bootable starter set — and once those rows exist
nothing told them apart from authored ones. An export shipped twelve invented
resonances into the corpus as lore while 22 real ones were missing.

Three cases bypass the gate, deliberately: a model with no fixture file yet, a model
whose `NaturalKeyMixin.identity_fields()` is `None`, and a prose domain whose
directory holds no entries. The last is the one to watch — prose domains write one
file per entry, so "file absent" means "new entry", which on a virgin corpus is true
of every entry; the gate keys on the **domain**, not the entry, and
`ExportAdditionGateProseDomainTests` pins that.

Entry points: `--allow-additions` on `tools/export_content.py`, and a checkbox on the
admin export page.

## Content credit and the prose backlog report (#2980, ADR-0196)

Every prose-bearing content model inherits the abstract `CreditedContent`
(`world.contributors.models`): four nullable columns, `written_by`, `written_on`,
`reviewed_by`, `reviewed_on`, the two `_by` columns FKs to `ContentContributor`
(a content model in its own right, natural key `name`, registered in
`CONTENT_MODELS`). Which text fields on a content model count as prose at all
is decided by `core_management/prose_fields.py`: an exhaustive, test-guarded
list (`PROSE_FIELD_NAMES` / `NON_PROSE_TEXT_FIELDS`) covering every content
text-field name, not a name heuristic, because a heuristic tried first
silently missed nine models carrying real player-facing prose.

Fixture-JSON rows carry the four credit columns as ordinary `fields`, same as
any other column, so `content_export`/`load_entries` need no extra code for
them. The four markdown domains (`content/codex_entries`, `content/beginnings`,
`content/starting_areas`, `content/traditions`) carry them as frontmatter
keys instead, applied by `_apply_credit_meta` in `content_fixtures.py`: the
two `_by` keys resolve as natural-key references, and the two `_on` date keys
are coerced to ISO strings, because `yaml.safe_load` turns an unquoted
`2026-08-04` into a `datetime.date` and `write_fixtures` serializes the
builder's output with `json.dumps`, which raises on a bare date object. An
absent key stays absent rather than clearing an existing credit, the same
"omission means leave this column alone" rule every other optional field
follows.

`core_management/prose_report.py` plus `tools/prose_report.py` (`just
prose-report`) report the writer/reviewer backlog by scanning a content-repo
checkout directly, no Django and no database, the same contract
`content_health.py` keeps: `uv run python tools/prose_report.py
[--content-path /path/to/checkout]`.

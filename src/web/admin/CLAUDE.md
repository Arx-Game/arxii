# Web Admin - Django Admin Customizations

Custom Django admin interface with game data export/import functionality.

## Export/Import System

**Purpose:** Backup and restore all game configuration data (species, traits, goals, distinctions, magic, etc.) as portable JSON fixtures across multiple Arx instances.

**Location:** Links at top of Django admin header (Export / Import) leading to dedicated pages.

## Game Setup Hub (#1333)

**Purpose:** Superuser-only landing page for a freshly-cloned Arx instance — the "can I configure an Arx pls ty??" entry point. Wayfinding for the clone→seed→tweak→export flow plus a per-cluster content inventory so a new host can see what their game contains and where the gaps are.

**Location:** Header link ("Game Setup") visible to superusers, next to the "Load sane defaults" Big Button. The Big Button's post-seed redirect lands here.

- `game_setup_views.py` — `game_setup` view; `@staff_member_required` + superuser gate (same gate as the Big Button, ADR-0022). Read-only.
- `templates/admin/game_setup.html` — extends `base_site.html`. Three regions: (1) the flow (Seed defaults → Author content → Tune mechanics [coming soon, #1221] → Export/Import), (2) a per-cluster content inventory table with live row counts (via `seeded_models_by_cluster()`), (3) "Jump to authoring" links to the World apps.
- URL: `_game_setup/` → name `admin_game_setup`.

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "the admin landing page for a new game"
- "where do I configure a fresh Arx instance"
- "content inventory / what's seeded"
- "Game Setup button at the top of Django admin"


### Key Files

- `services.py` - `analyze_fixture()` dry-run analysis and `execute_import()` atomic pipeline
- `views.py` - `export_preview()`, `export_data()`, `import_upload()`, `import_execute()` views
- `models.py` - `AdminExcludedModel` and `AdminPinnedModel`
- `templates/admin/export_preview.html` - Model inventory with include/exclude checkboxes
- `templates/admin/import_upload.html` - File upload form
- `templates/admin/import_preview.html` - Per-model dry-run analysis with merge/replace/skip controls
- `templates/admin/import_results.html` - Post-import results summary
- `tests/test_export_import.py` - Comprehensive tests for the analysis and import pipeline

### How It Works

**Export (multi-step):**
1. Click "Export" link in admin header -> Export Preview page
2. Preview shows all models with record counts, natural key status, and include/exclude checkboxes
3. Select models to export and click "Download Export"
4. Downloads selected models as JSON with natural keys
5. Filename: `arx-config-YYYY-MM-DD.json`
6. Uses `use_natural_foreign_keys=True` and `use_natural_primary_keys=True`

**Import (multi-step):**
1. Click "Import" link in admin header -> Upload page
2. Upload a fixture JSON file
3. `analyze_fixture()` parses the file and compares against current DB state
4. Import Preview shows per-model breakdown: new/changed/unchanged/local-only records
5. Per-model action controls: Merge (default) / Replace / Skip
6. Merge: update existing by natural key, create new, preserve local-only
7. Replace: delete all then re-insert
8. `execute_import()` runs in `transaction.atomic()` with full rollback on any error
9. Records are deserialized per-model in dependency order (parents before children)

**Blocklist Approach:**
- New models export by default (no code changes needed)
- Exclude specific models via `AdminExcludedModel` table or checkboxes in export preview

### Excluded by Default

Django system apps:
- `sessions`, `contenttypes`, `django_migrations`, `admin`

Evennia internal apps:
- `server`, `scripts`, `comms`, `help`, `typeclasses`

Defined in `services.py` as `HARDCODED_EXCLUDED_APPS` (canonical location, imported by views).

### URLs

- `_export_preview/` - Export preview page with model inventory
- `_export/` - POST endpoint that accepts selected models and returns fixture JSON
- `_import_upload/` - File upload form / fixture analysis
- `_import_execute/` - Execute import with per-model actions
- `_exclude/` - Toggle model exclusion
- `_excluded/` - Check exclusion status
- `_pin/` - Toggle model pinning
- `_pinned/` - Check pin status
- `_seed/` - "Load sane defaults" confirm page (superuser; #651)
- `_seed_run/` - POST: runs `seed_dev_database()` then redirects to the Game Setup hub (superuser)
- `_game_setup/` - "Game Setup" hub: wayfinding + per-cluster content inventory (superuser; #1333)

### When Asked About

If an agent is asked about any of these topics, this is the system:
- "export/import in admin"
- "backup game data"
- "fixture system"
- "how to save/restore configuration"
- "the buttons at top of Django admin"

### Cross-Instance Portability

The export uses natural keys so data can be:
1. Exported from Production
2. Imported into Dev/Staging
3. All relationships resolve correctly (using names, not IDs)

This requires all config models to have `NaturalKeyMixin` from `core.natural_keys`.

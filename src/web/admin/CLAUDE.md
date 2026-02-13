# Web Admin - Django Admin Customizations

Custom Django admin interface with game data export/import functionality.

## Export/Import System

**Purpose:** Backup and restore all game configuration data (species, traits, goals, distinctions, magic, etc.) as portable JSON fixtures across multiple Arx instances.

**Location:** Links at top of Django admin header (Export / Import) leading to dedicated pages.

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

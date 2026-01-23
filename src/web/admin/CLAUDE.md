# Web Admin - Django Admin Customizations

Custom Django admin interface with game data export/import functionality.

## Export/Import System

**Purpose:** Backup and restore all game configuration data (species, traits, goals, distinctions, magic, etc.) as portable JSON fixtures.

**Location:** Buttons at top of Django admin header (Export / Import)

### Key Files

- `views.py` - `export_data()` and `import_data()` functions
- `models.py` - `AdminExcludedModel` for blocklist management
- `templates/admin/base_site.html` - Export/Import button UI
- `static/admin/js/arx_admin.js` - JavaScript handlers for buttons

### How It Works

**Export:**
- Downloads all non-excluded models as JSON with natural keys
- Filename: `arx-config-YYYY-MM-DD.json`
- Uses `use_natural_foreign_keys=True` and `use_natural_primary_keys=True` for cross-instance portability

**Import:**
- Uploads JSON fixture file
- Destructive: deletes existing data for models in fixture, then loads new data
- Wrapped in atomic transaction
- Requires confirmation modal

**Blocklist Approach:**
- New models export by default (no code changes needed)
- Exclude specific models via `AdminExcludedModel` table or checkboxes in admin index

### Excluded by Default

Django system apps:
- `sessions`, `contenttypes`, `django_migrations`, `admin`

Evennia internal apps:
- `server`, `scripts`, `comms`, `help`, `typeclasses`

### URLs

- `_export/` - Download full fixture as JSON
- `_import/` - Upload and import fixture
- `_exclude/` - Toggle model exclusion
- `_excluded/` - Check exclusion status

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

This requires all config models to have `NaturalKeyMixin` - see the `fixture-data-patterns` skill.

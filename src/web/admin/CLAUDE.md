# Web Admin - Django Admin Customizations

Custom Django admin interface with game data export/import functionality.

## Export/Import System

**Purpose:** Backup and restore all game configuration data (species, traits, goals, distinctions, magic, etc.) as portable JSON fixtures across multiple Arx instances.

**Location:** Links at top of Django admin header (Export / Import) leading to dedicated pages.

## Game Setup Hub (#1333)

**Purpose:** Superuser-only landing page for a freshly-cloned Arx instance — the "can I configure an Arx pls ty??" entry point. Wayfinding for the clone→seed→tweak→export flow plus a per-cluster content inventory so a new host can see what their game contains and where the gaps are.

**Location:** Header link ("Game Setup") visible to superusers, next to the "Load sane defaults" Big Button. The Big Button's post-seed redirect lands here.

- `game_setup_views.py` — `game_setup` view; `@staff_member_required` + superuser gate (same gate as the Big Button, ADR-0022). Read-only.
- `templates/admin/game_setup.html` — extends `base_site.html`. Three regions: (1) the flow (Seed defaults → Author content → Load private content repo → Tune mechanics [#1221] → Monitor live game → Export/Import), (2) a per-cluster content inventory table with live row counts (via `seeded_models_by_cluster()`), (3) "Jump to authoring" links to the World apps.
- URL: `_game_setup/` → name `admin_game_setup`.

### External Content-Repo Load (#1220)

**Purpose:** superuser button to build + upsert the maintainers' private
content repository (never named here; located via the `CONTENT_REPO_PATH` env
var, already loaded into the process by the `arx` CLI's dotenv handling) into
the database. Mirrors the seed button's confirm/run shape but is an upsert
(`update_or_create` by natural key), not create-if-missing — the confirm page
copy says so.

- `content_load_views.py` — `content_load_confirm` (GET) + `content_load_run`
  (POST, superuser-only), which drive
  `core_management.content_fixtures.load_world_content` the same way
  `tools/build_content_fixtures.py --load` does. Content-repo path resolution
  (`resolve_content_root()` — env lookup + directory check, also used by
  `game_setup_views.game_setup` for the `content_repo_configured` flag) lives
  in `core_management.content_repo`, the canonical location shared by every
  export/push/load call site (#2448).
- `templates/admin/content_load_confirm.html` — mirrors `seed_confirm.html`.
- URLs: `_content_load/` → `admin_content_load` (GET confirm);
  `_content_load_run/` → `admin_content_load_run` (POST run).
- The Game Setup hub shows a "Load content repo" link when configured, else a
  hint to set `CONTENT_REPO_PATH` in `src/.env` (the Import Data upload
  remains the path for ad-hoc fixture files either way).

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "the admin landing page for a new game"
- "where do I configure a fresh Arx instance"
- "content inventory / what's seeded"
- "Game Setup button at the top of Django admin"

## Game Tuning & Game Ops Dashboards (#1221)

**Purpose:** Two superuser-only, admin-hosted HTMX dashboards linked from the Game Setup
hub's "Tune mechanics" / "Monitor the live game" steps. Built on the existing `ArxAdminSite`
with `django-htmx` + a vendored `htmx.min.js` rather than `django-unfold` (see ADR-0093,
which narrows ADR-0022's admin-hosted decision) — unfold would replace the stock-admin
template tree this app already customizes (Game Setup hub, export/import, pin/exclude).

**Game Tuning** (`_tuning/` → `admin_tuning`) — four HTMX-fragment panels, each its own
sub-URL (`tuning/views.py`): checks-analytics (`tuning_checks_fragment`,
`checks_analytics.py`), consequence-pool inspector (`tuning_consequences_fragment`,
`consequence_analytics.py`), condition danger ranking (`tuning_conditions_fragment`,
`condition_analytics.py`), and Monte Carlo party-vs-boss simulation
(`tuning_simulation_fragment`, `SimulationRunForm` + `world.combat.simulation`). Read+preview
only — sliders/forms re-render fragments via `hx-get`; the simulation run itself writes
nothing persistent (isolation contract in `world/combat/simulation.py`'s module docstring).

**Game Ops** (`_ops/` → `admin_ops`) — five HTMX-fragment panels (`tuning/ops_views.py`):
progression, economy, story/GM, and reports-queue analytics (`tuning/metrics.py`), plus a
refresh-on-demand Technical Health panel (`tuning/tech_health.py`: idmapper RAM via
`evennia_extensions.observability.idmapper_gauge`, process RSS/CPU via `psutil`, open
`SystemErrorReport` count, deploy git SHA / Sentry-configured flag).

Both dashboards gate every view through `web.admin.tuning.views.superuser_required`
(`@staff_member_required` + explicit `is_superuser` check, mirroring the Game Setup hub's
gate). CSRF on every HTMX request goes through one `hx-headers` attribute on each
dashboard's root wrapper div — no hand-written fetch/CSRF JS. Shared panel CSS lives in
one include, `templates/admin/tuning/_panel_css.html`, using Django admin's CSS custom
properties so panels inherit light/dark theming.

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "difficulty tuning / balance dashboard in admin"
- "Monte Carlo combat simulation"
- "Game Ops / live-game analytics dashboard"
- "technical health panel / idmapper memory in admin"

**Details:** `docs/systems/tuning.md`.

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
- `_content_load/` - "Load private content repo" confirm page (superuser; #1220)
- `_content_load_run/` - POST: builds + upserts the external content repo, then redirects to the Game Setup hub (superuser)
- `_game_setup/` - "Game Setup" hub: wayfinding + per-cluster content inventory (superuser; #1333)
- `_tuning/` - Game Tuning dashboard skeleton (superuser; #1221); `_tuning/checks/`,
  `_tuning/consequences/`, `_tuning/conditions/`, `_tuning/simulation/` - the four HTMX panel fragments
- `_ops/` - Game Ops dashboard skeleton (superuser; #1221); `_ops/progression/`, `_ops/economy/`,
  `_ops/story/`, `_ops/reports/`, `_ops/tech/` - the five HTMX panel fragments

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

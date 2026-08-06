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

### Load Conflict Resolution (#3017)

**Purpose:** the admin-side counterpart to the credited-row load guard in
`core_management.content_fixtures._upsert_fixture_object` — a credited row
(`written_by` set) whose incoming corpus value differs from the DB is left
untouched by a load rather than silently overwritten. This surface lists
every current such conflict and resolves one at a time by deleting the row
and reloading it from the corpus, gated on typing the row's own natural key
back exactly. Deliberately no bulk resolve: clearing a human's credited edit
is a one-row, one-typed-confirmation action every time.

- `content_conflict_views.py` — `content_conflicts` (GET, list every current
  conflict via `core_management.load_conflicts.scan_load_conflicts`),
  `content_conflict_detail` (GET, one conflict's field-by-field diff plus the
  typed-confirmation form; querystring `model` + `key`), and
  `content_conflict_resolve` (POST, superuser-only; refuses a wrong typed key
  with the row untouched, otherwise deletes the row and reloads exactly that
  one entry from the corpus inside one transaction — a `ProtectedError` or a
  failed reload rolls the whole thing back and flashes an error). All three
  resolve the content-repo path via the same `resolve_content_root()` as the
  load view.
- `templates/admin/content_conflicts.html`, `content_conflict_detail.html` —
  mirror `content_load_confirm.html`'s structure: plain tables, no JS.
- URLs: `_content_conflicts/` → `admin_content_conflicts` (GET list);
  `_content_conflict/` → `admin_content_conflict_detail` (GET detail,
  `?model=&key=`); `_content_conflict_resolve/` →
  `admin_content_conflict_resolve` (POST resolve).
- The Game Setup hub's "Load private content repo" step links here beside
  the load/export/push links.
- This guard does not reach the generic Import Data surface below (`services.execute_import`):
  its merge/replace pipeline can overwrite a credited row's fields with no credit check at all.
  That is deliberate, not a gap - Import Data is superuser-only disaster-recovery tooling with
  its own dry-run diff preview, not the content pipeline this freeze protects. See ADR-0201's
  trade-offs section and the "Export/Import System" section below.

### Content-Repo Export & Push (PR #2425; grid bundles added #2436/#2448)

**Purpose:** the maintainers'-only inverse of the content-repo load above —
write the DB's authored content back out to the private lore repo as JSON
fixtures, then commit + push that repo. Two separate superuser buttons
(export writes files; push commits/pushes them), so an operator can review
the working-tree diff in between.

- `content_export_views.py` — `content_export_preview` (GET, model inventory
  + record counts from `core_management.content_export.CONTENT_MODELS`, plus a
  `_grid_preview_context()` block showing authored area/room counts) and
  `content_export_run` (POST, superuser-only; carries an **"Also push rows the
  content repo doesn't have yet"** checkbox, off by default — see ADR-0191) — drives
  `core_management.content_export.export_to_content_repo` (flat
  natural-key-serialized fixtures) **and**
  `core_management.grid_export.export_grid_bundles` (the graph-aware
  area/room/exit/sidecar bundles, one JSON file per `origin=AUTHORED` area at
  `fixtures/grid/<area-slug>.json`) in the same run, surfacing grid area/room/
  written-file/error counts alongside the flat-model results.
- `content_push_views.py` — `content_push_preview` (GET, git
  status/diff-stat summary of the content-repo working tree so the operator
  can review before pushing) and `content_push_run` (POST, superuser-only) —
  drives `core_management.content_push.push_content_to_repo` the same way
  `tools/push_content.py` does (commit + push the export output).
- Both view modules resolve the repo path via the same canonical
  `core_management.content_repo.resolve_content_root()` as the load view.
- URLs: `_content_export/` (GET preview) / `_content_export_run/` (POST run);
  `_content_push/` (GET preview) / `_content_push_run/` (POST run).
- Tests: `tests/test_content_export_views.py`, `tests/test_content_push_views.py`
  (view-level HTTP tests added #2448 — both buttons shipped untested in
  PR #2425 originally).

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "the admin landing page for a new game"
- "where do I configure a fresh Arx instance"
- "content inventory / what's seeded"
- "Game Setup button at the top of Django admin"

### Row export and content session (#3018)

**Purpose:** a row-level counterpart to the whole-corpus export above. A
superuser editing one record in any change form can send that single row's
corpus form to the lore checkout, review its diff, and commit it - without
running a full export/push over every content model. Rows accumulate on one
shared branch until the operator opens a pull request for the batch, instead
of every single row needing its own PR.

- **The button** - `templates/admin/change_form.html` (site-wide override of
  Django's stock change form, extending it the same way
  `change_list.html` extends its own stock template - see that file's
  docstring precedent) adds an `object-tools-items` entry: a small POST form
  to `admin_content_export_row` carrying the row's `<domain>.<model_name>`
  label and pk as hidden fields. It only renders for a superuser, on a
  change form (not add), for a model the new
  `web/admin/templatetags/content_export_tags.py` filters
  (`content_exportable`, `content_model_label`) recognize as corpus-owned -
  registered in `core_management.content_export.CONTENT_MODELS` or
  `core_management.content_fixtures.MARKDOWN_EXPORT_DOMAINS`.
- **Write + diff confirm** - `content_row_export_views.py`:
  `content_export_row` (POST from the button) ensures the session branch
  (below) and writes the row via
  `core_management.content_export.export_single_row`, then redirects to
  `content_export_row_diff` (GET), which renders the working-tree diff
  behind a sha256 digest of that diff text.
  `content_export_row_confirm` (POST, `action=confirm|discard`) re-checks
  the posted digest against a freshly recomputed one before doing anything -
  a mismatch means the tree changed since the diff page rendered and is
  refused unconditionally, the same idiom as the load-conflict resolve
  page. An addition (the row's natural key is not yet in the corpus) also
  requires an explicit "new_row" checkbox, mirroring the corpus-wide
  export's addition gate (ADR-0191) at row scope. Addition-ness is derived
  straight from git `HEAD` at both diff-render and confirm time
  (`content_session.row_is_addition_at_head`, fail-closed on any git/parse
  trouble), not read out of the request session - a session record only
  ever answered for the browser that ran the export, so a second browser
  hitting either URL directly used to see a default of "not an addition"
  and could commit a genuine addition with no checkbox at all (#3018
  review).
- **One session branch, one pending export at a time** -
  `core_management.content_session` (`ensure_session_branch`,
  `commit_row_export`, `discard_row_export`) keeps every exported-but-not-
  yet-PR'd row as its own small commit on a fixed branch,
  `content-export-session`, created fresh off `origin/main` (or reused if
  its prior pull request has not merged yet). Git state, not a database
  table, is the source of truth: `ensure_session_branch` refuses to start a
  new row export while the working tree is already dirty, which is how at
  most one pending export exists at a time across browsers and operators.
- **The session page and its pull request** - `content_session_views.py`:
  `content_session` (GET, `admin_content_session`) shows the branch's
  commit list and full diff against `origin/main`, naming the currently
  pending row (if any) with a link straight to its diff page.
  `content_session_pr` (POST, `admin_content_session_pr`) pushes the branch
  and opens (or reuses) its pull request via
  `core_management.content_session.open_session_pr`, one REST call through
  the shared `core_management.github_rest.github_request` client
  (`settings.GITHUB_ISSUE_TOKEN`, falling back to the `GH_TOKEN` env var;
  no token configured is refused with a plain message). The target
  owner/repo is parsed from the checkout's own `origin` remote URL - the
  lore repo is never named anywhere in this code.
- The corpus-wide push (`content_push_run` above) now stages `content/` as
  well as `fixtures/` when committing, so the markdown prose domains travel
  with the same pipeline as the flat JSON fixtures.
- URLs: `_content_export_row/` (POST write), `_content_export_row_diff/`
  (GET diff), `_content_export_row_confirm/` (POST commit/discard),
  `_content_session/` (GET session page), `_content_session_pr/` (POST open
  pull request).
- Tests: `tests/test_content_row_export_views.py`,
  `tests/test_content_session_views.py`,
  `tests/test_change_form_export_button.py`.
- Deliberate no-ADR: the decisions here were recorded in the approved #3018
  spec, and ADR-0191/ADR-0201 already carry the addition-gate and credited-
  row-freeze rationale this flow reuses.

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "export one row from the admin"
- "the Export to content repo button on a change form"
- "content session / session branch / one PR per session"

## Authoring Workbench (#3019)

**Purpose:** a superuser-only dashboard for writing and reviewing the prose
backlog across every credited content model in one place - a worst-first
queue (placeholder text first, then unwritten, then unreviewed), a row
editor scoped to prose fields only, and reference search - instead of a
writer hunting through the stock Django admin's per-model change lists one
model at a time.

**Location:** header link ("Authoring Workbench" button, superuser-only,
beside Tuning/Ops) and a "Author content" link on the Game Setup hub, both
to `_authoring/` (`admin_authoring`).

- **Backlog data tier** - `web/admin/authoring/backlog.py`:
  `build_backlog(scope=None)` scans every model
  `core.app_domains.credited_content_models()` returns, skips any with no
  `core_management.prose_fields.prose_fields_for` fields, and issues one
  `values_list` per remaining model (pk, natural-key fields, the
  `written_by_id`/`reviewed_by_id` credit columns, every prose field).
  `credited_content_models()` is deliberately broader than
  `core_management.content_export.CONTENT_MODELS` - four builder-domain
  models (`ItemTemplate`, `NPCRole`, `BuildingKind`, `DecorationKind`) carry
  `CreditedContent` but sit outside the export registry. Rows sort
  worst-first: placeholder-marked, then unwritten, then unreviewed, then
  alphabetically by domain and identity. An FK-typed natural-key field spans
  one hop into the related row's own first natural-key field for display
  (`"The Sleeper's Rest, Sleeper"`, not a raw related pk) - still one query
  per model, since the span is a SQL join; a related field that is itself
  FK-typed is left as its raw id (documented non-recursive limitation).
  `scope`, when given, narrows every model's queryset uniformly - the seam a
  future GM-restricted variant can use without this module knowing who is
  asking.
- **Dashboard + stats/queue fragments** - `authoring_dashboard` (GET) renders
  the setup panel in place of the stats/queue skeleton for an unlinked
  account (see the setup gate below), else the two HTMX panels:
  `authoring_stats_fragment` (per-domain rows/unwritten/unreviewed/word-count
  rollup) and `authoring_queue_fragment` (the worst-first queue itself,
  filterable by `?domain=`, `?status=` - `web.admin.constants
  .BacklogStatusFilter`: `placeholder`/`unwritten`/`unreviewed` - and `?q=`
  against the row's identity string, one Python-side scan over
  `build_backlog()`'s already-sorted rows, capped at 100 displayed rows with
  a "Showing 100 of N" note when truncated).
- **Guided first-run contributor setup gate** - `authoring/contributors.py`:
  `current_contributor(user)` reads `request.user -> PlayerData ->
  ContentContributor`, `None` at any missing link; `link_contributor(user,
  *, name="", existing_pk=None)` creates-or-picks one atomically and links
  it. The dashboard shows the setup panel (pick an existing unlinked
  contributor from a `<select>`, or type a new name, prefilled with the
  account's username) instead of the stats/queue skeleton until this link
  exists - every downstream panel assumes a contributor identity. No silent
  auto-create: a blank name, an em/en-dash name, a name already linked to
  another account, or an `existing_pk` already linked elsewhere all refuse
  with a coherent message rather than creating or reassigning anything.
  Picking from the list wins over the text field when both are submitted.
  Race-idempotent: a truly concurrent double-submit that gets past the
  sequential no-op check races unique-constraint writes inside
  `link_contributor`'s `transaction.atomic()` block; the resulting
  `IntegrityError` is caught after rollback and resolved by re-reading
  `current_contributor` - if the race already linked this same account, that
  is returned as success, otherwise the caller gets a "claimed a moment ago"
  `ValueError`, never a raw 500. `authoring_setup` (POST-only) is the panel's
  submit handler, always redirecting back to the dashboard with a flash.
- **The prose row editor** - `authoring_editor` (GET, `?model=<domain
  .Model>&pk=`) via the shared `_resolve_target` gate (unknown model, a
  model outside `credited_content_models()`, or a missing row all render the
  same flash-in-fragment error instead of the form). One textarea per prose
  field **in field-declaration order** (`prose_fields_for` iterates
  `model._meta.get_fields()`, e.g. `CodexEntry` renders `summary`,
  `lore_content`, `mechanics_content` in that order, never alphabetized).
  `authoring_editor_save` (POST) assigns only `prose_fields_for(model)` keys
  actually present in the POST body - allowlist-only: a mechanical field
  smuggled into the POST under its own name is never read, let alone
  assigned - then `full_clean()` + `save()`; a validation failure re-renders
  with nothing persisted. `authoring_editor_credit` (POST) runs that same
  prose save first (only if prose keys were posted) and stamps
  `written_by`/`written_on` from the operator's own linked contributor;
  `authoring_editor_review` (POST) only ever stamps `reviewed_by`/
  `reviewed_on` and never touches prose or authorship - **credit and review
  stamping are separate actions**, so confirming review never silently
  overwrites an in-flight, unsaved prose edit. Either POST view falls back
  to the setup-gate guidance line (no stamp written) when the operator has
  no linked contributor, since this editor is reachable by direct URL and
  is not itself behind the dashboard's setup gate. A `full_clean()` failure
  keyed on a mechanical field or Django's own `"__all__"` key has no
  textarea to render next to, so it surfaces in a **mechanical-error
  banner** above the form instead of vanishing silently. After a successful
  credit stamp, the export handoff form (reusing
  `content_export_tags.content_exportable`/`content_model_label` from the
  row-export system above) is **gated on `content_exportable`** - the four
  builder-domain models carry credit but are not exportable, and would
  otherwise 500 on `NoReverseMatch` when the handoff redirects through a
  change-form URL that does not exist for them - showing the sentence "This
  model stays in the database only; the content repo does not carry it."
  in its place.
- **Related-entries pane + prose mentions** - `authoring/relations.py`:
  `related_entries(instance, cap=50)` walks every forward FK/O2O/M2M field
  and every reverse FK/O2O/M2M relation (a `related_name="+"` relation is
  already absent from `_meta.get_fields()`'s default `include_hidden=False`
  list, so no extra check is needed), loading automatically below the
  editor. `prose_mentions(name, exclude=None, cap=200)` OR-`icontains`
  scans every credited model's `prose_fields_for` columns for `name`,
  excluding the edited row's own `(model, pk)`; it only runs on the
  operator's explicit "Search for mentions" click, since it is real query
  work a page load should not pay unconditionally. Both use **bounded
  per-relation slices**, never materializing more than a relation's share of
  the cap before iterating: `related_entries` slices each many-relation's
  queryset to `[: remaining + 1]` (the `+1` a discard-after-use overflow
  sentinel) and, on overflow, issues one exact `.count()` on that relation
  alone so the returned truncated-count is precise, never a lower bound;
  `prose_mentions` slices each model's queryset to `[: cap - len(entries)]`
  before iterating. Each entry links to its workbench editor (only when its
  model is itself credited) and to its Django admin change form (only when
  that model has a registered `ModelAdmin` - three of the four builder-
  domain models never were).
- **Reference search** - `authoring/reference.py`: `db_search(query)` is an
  `icontains` scan across every credited model's prose fields, **on by
  default**; `file_search(query, roots)` covers two **opt-in** file
  corpora - this repo's own staff docs (`design/`, `world_bibles/` under the
  content root) and the maintainers' Arx I dump (the content root's sibling
  `arx1/` directory) - both **default off**, resolved via
  `reference_roots(staff_docs=, arx1=)`. `file_search` is a minimal,
  deliberately duplicated port of the private lore repo's
  `tools/write_editor/reference.py` search semantics (fixed-string,
  case-insensitive, per-line): a **2MB per-file size cap** skips any
  candidate before it is ever opened, a wall-clock **30-second budget**
  (`time.monotonic`) is checked at the per-directory, per-file, and
  per-line level so no single oversized file or line can blow through it on
  its own, and a **symlink escape guard** (`resolved.is_relative_to(root)`)
  keeps a symlinked file from reading outside its configured root. A missing
  or unconfigured `CONTENT_REPO_PATH`, or any individual root that does not
  exist, is silently omitted rather than raised - DB search still works with
  no content repo configured at all.
- **URLs** (`_authoring/...`, all superuser-only): `_authoring/` ->
  `admin_authoring` (dashboard), `_authoring/stats/` ->
  `admin_authoring_stats`, `_authoring/queue/` -> `admin_authoring_queue`,
  `_authoring/setup/` -> `admin_authoring_setup` (POST), `_authoring/editor/`
  -> `admin_authoring_editor` (`?model=&pk=`), `_authoring/editor/save/` ->
  `admin_authoring_editor_save` (POST), `_authoring/editor/credit/` ->
  `admin_authoring_editor_credit` (POST), `_authoring/editor/review/` ->
  `admin_authoring_editor_review` (POST), `_authoring/related/` ->
  `admin_authoring_related` (`?model=&pk=`), `_authoring/mentions/` ->
  `admin_authoring_mentions` (`?model=&pk=`), `_authoring/reference/` ->
  `admin_authoring_reference` (`?q=&db=&staff_docs=&arx1=`).
- Tests: `web/admin/tests/test_authoring_backlog.py`,
  `test_authoring_views.py`, `test_authoring_setup.py`,
  `test_authoring_editor.py`, `test_authoring_relations.py`,
  `test_authoring_reference.py`.
- Deliberate no-ADR: the decisions here were recorded in the approved #3019
  spec, the same precedent #3018 set above.

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "authoring workbench / prose backlog queue in admin"
- "who still needs to write or review this content model"
- "the row editor for credited content"
- "reference search across the content database / staff docs / Arx I dump"

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
- `_content_conflicts/` - "Load conflicts" list page (superuser; #3017)
- `_content_conflict/` - one conflict's field-by-field diff + typed-confirmation
  form (superuser; `?model=&key=`)
- `_content_conflict_resolve/` - POST: typed-confirmation delete-then-reload
  for one conflict (superuser)
- `_content_export/` - "Export to content repo" preview page (superuser; PR #2425), model inventory + grid area/room counts
- `_content_export_run/` - POST: writes flat fixtures + grid bundles to the content repo (superuser)
- `_content_push/` - "Push content to lore repo" preview page (superuser; PR #2425), git status/diff-stat
- `_content_push_run/` - POST: commits + pushes the content-repo working tree (superuser)
- `_content_export_row/` - POST: writes one row's corpus form to the session branch, then
  redirects to its diff page (superuser; #3018)
- `_content_export_row_diff/` - GET: one pending row export's diff behind a digest
  (superuser; `?model=&pk=`; #3018)
- `_content_export_row_confirm/` - POST: commits or discards one pending row export
  after the digest re-checks out (superuser; #3018)
- `_content_session/` - GET: the content session page - commit list, full diff, open-PR
  form (superuser; #3018)
- `_content_session_pr/` - POST: pushes the session branch and opens (or reuses) its
  pull request (superuser; #3018)
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

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
  review). Every "back to the change form" link/redirect
  (`content_export_row`'s refusals, the diff page's back-link, discard) goes
  through `_change_url`, which builds the target model's admin change-form
  URL **only when that model is in `admin.site._registry`** and returns
  `None` otherwise - not every credited+exportable model has a registered
  `ModelAdmin` (13 as of #3019 review, e.g. `missions.MissionTemplate`,
  `magic.PortalAnchorKind`), and building that URL for one used to raise
  `NoReverseMatch` and 500 the diff page. Every caller degrades `None` to
  `web/admin/authoring/links.py:workbench_editor_url` - an Authoring
  Workbench editor deep-link, which always resolves regardless of the admin
  registry.
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
  `core_management.content_export.CONTENT_MODELS` - three builder-domain
  models (`ItemTemplate`, `BuildingKind`, `DecorationKind`) carry
  `CreditedContent` but sit outside the export registry (`NPCRole` left the
  exclusion 2026-08-07: missions name it by natural key, so it now rides
  the catalog). Rows sort
  worst-first: placeholder-marked, then unwritten, then unreviewed; within a
  tier, by domain, then **model**, then **pk**. The model term is what keeps a
  tier readable - sorting straight to identity interleaved every model in a
  domain into one alphabetical soup, so no two adjacent rows shared a shape -
  and pk within a model is authoring order, which for an ordered set like
  `OriginTemplateSlot` tracks its own `sort_order`. Alphabetical-by-identity is
  arbitrary even inside one model and is the tiebreak nowhere. A model still
  appears in up to three clumps, one per tier; the queue's model filter is what
  collapses that to one model's rows worst-first. An FK-typed natural-key field spans
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
  filterable by `?domain=`, `?model=` (a full `domain.Model` label),
  `?status=` - `web.admin.constants
  .BacklogStatusFilter`: `placeholder`/`unwritten`/`unreviewed` - and `?q=`
  against the row's identity string, one Python-side scan over
  `build_backlog()`'s already-sorted rows, capped at 100 displayed rows with
  a "Showing 100 of N" note when truncated). The `?model=` dropdown's options
  come from `_model_options`, built off those same scanned rows and narrowed
  to the picked domain, so it can never offer a model with no rows behind it.
  Each row carries two links: the identity cell `hx-get`s the prose editor
  into `#authoring-editor`, and an "Edit in admin" cell (`_queue_row` ->
  `links.admin_change_url`) opens the stock change form - how an author
  reaches the fields the prose-only editor deliberately does not expose. That
  cell renders empty for a credited model with no registered `ModelAdmin`
  rather than a dead link. The queue's editor link and the
  related/mentions/reference panels' links all anchor
  `href="#authoring-editor"` and swap with `show:top`: the editor panel sits
  **below** the queue table in `dashboard.html`, so the old `href="#"`
  scrolled nowhere and the swapped-in form landed off-screen, reading to an
  operator as a link that does nothing.
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
  credit stamp, the freeze clause ("This row is now credited: content loads
  will not overwrite it until the corpus catches up.") always renders, and
  the export handoff form (reusing
  `content_export_tags.content_exportable`/`content_model_label` from the
  row-export system above) plus its own export clause ("Export it to the
  content repo to close the loop.") render only **inside the
  `content_exportable` branch** - the three builder-domain models carry
  credit but are not exportable at all, so they show the sentence "This
  model stays in the database only; the content repo does not carry it."
  in the handoff form's place instead (#3019 review: the freeze and export
  clauses used to be one sentence, rendering the export clause even for a
  non-exportable model directly above the "stays in the database only"
  line it contradicted). `content_exportable` only rules out the three
  builder-domain models here - it says nothing about whether an
  *exportable* model has a `ModelAdmin` to link back to. Thirteen other
  credited+exportable models never got one (e.g. `missions.MissionTemplate`,
  `magic.PortalAnchorKind`) - that gap is closed one layer down, in the
  row-export system's own `_change_url` (below), not by this gate.
- **Related-entries pane + prose mentions** - `authoring/relations.py`:
  `related_entries(instance, cap=50)` walks every forward FK/O2O/M2M field
  and every reverse FK/O2O/M2M relation (a `related_name="+"` relation is
  already absent from `_meta.get_fields()`'s default `include_hidden=False`
  list, so no extra check is needed), loading automatically below the
  editor. `prose_mentions(name, exclude=None, cap=200, scope=None)`
  OR-`icontains` scans every credited model's `prose_fields_for` columns for
  `name`, excluding the edited row's own `(model, pk)`; it only runs on the
  operator's explicit "Search for mentions" click, since it is real query
  work a page load should not pay unconditionally. `scope`, when given,
  narrows every model's queryset the same way `build_backlog`'s does (#3019
  review, Item 4) - workbench callers pass nothing. Both use **bounded
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
- **Reference search** - `authoring/reference.py`: `db_search(query,
  scope=None)` is an `icontains` scan across every credited model's prose
  fields, **on by default**; `scope`, when given, narrows every model's
  queryset the same way `build_backlog`'s does (#3019 review, Item 4) -
  workbench callers pass nothing. `file_search(query, roots)` covers two
  **opt-in** file
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

### Stock-admin complement (#3020)

The stock changelists carry the same credit story the workbench queue tells:

- **Credit-status filter + column, injected registry-wide** -
  `world/contributors/admin.py` defines `CreditStatusListFilter`
  (`?credit=unwritten|written|reviewed`, a three-way partition derived from
  `written_by`/`reviewed_by` - never stored) and the `credit_status` cell,
  which links each row into the workbench editor whenever the model has
  prose fields. `web/admin/apps.py:_attach_credit_admin_extras` attaches
  both to every `credited_content_models()` entry registered in
  `admin.site` at ready() time (same window as `_patch_external_admins`);
  no admin lists them by hand. Credited models without a registered admin
  are skipped - the workbench is their surface.
- **Fieldset coverage is enforced, not hoped for** - `web_admin.E001`
  (`checks.py:check_credited_admin_fieldsets`) errors when a credited
  model's admin declares explicit `fieldsets` without the four credit
  fields (an explicit fieldsets otherwise silently hides them -
  `ItemTemplateAdmin` shipped that way until #3020). Fix by appending
  `CREDIT_FIELDSET`; nested side-by-side field tuples are flattened, so
  that layout cannot evade the check.
- **Change-form deep link** - `templatetags/authoring_tags.py:workbench_url`
  + a superuser-only "Open in Authoring Workbench" object-tool `<li>` in
  `change_form.html`, beside the #3018 export button, for credited models
  with prose fields. All deep links share one URL builder:
  `web/admin/authoring/links.py:workbench_editor_url` (promoted from
  `content_row_export_views`). Its inverse lives beside it:
  `links.py:admin_change_url` (`(model_label, pk) -> str | None`, promoted
  from `authoring.views._admin_change_url`) is the outward link the
  related-entries pane and the backlog queue both build - it returns `None`,
  never a dead link, for a credited model with no registered `ModelAdmin`.
- Tests: `tests/test_credit_admin_extras.py`,
  `tests/test_change_form_workbench_link.py`, `tests/test_authoring_links.py`,
  plus the E001 class in `tests/test_admin_checks.py`.

**When Asked About**

If an agent is asked about any of these topics, this is the system:
- "authoring workbench / prose backlog queue in admin"
- "who still needs to write or review this content model"
- "the row editor for credited content"
- "reference search across the content database / staff docs / Arx I dump"

## Upbringing Builder (#3660)

**Purpose:** author a whole Upbringing route (the `OriginTemplate`, every
`OriginTemplateSlot` question, and every `OriginTemplateSlotChoice` answer hanging
off it) on one admin page, in one transaction, rather than the stock admin's separate
change forms and inlines for each. Pattern mirrors the Authoring Workbench above:
`superuser_required`, the contributor gate, plain Django forms, `base_site.html`.

- **Files** - `web/admin/upbringing_builder/`: `views.py` (`upbringing_builder`,
  `upbringing_builder_preview`, `upbringing_builder_review`), `forms.py`
  (`UpbringingForm`, `QuestionFormSet`, `AnswerFormSet` via `inlineformset_factory`,
  `answer_formset_for` for the per-question `a<slot.pk>`-prefixed formset), `live.py`
  (the right rail: `for_template` -> `LivePanel`, `rail_counts`), `credit.py`
  (`stamp_written`, `stamp_reviewed`). Templates in
  `web/templates/admin/upbringing_builder/`: `page.html` (the form, wiring up
  "Add question"/"Add answer" against the shared clone-a-formset-row helpers
  in `web/static/admin/js/builder_formsets.js` (also loaded by the tradition
  slate page, #3675) - there is no saved row to fetch an HTMX fragment for
  until the whole route is saved), `_question.html`, `_answers.html`,
  `_rail.html`, `_setup.html`, `_preview.html`, `_css.html`.
- **Stylesheets** - the page links `admin/css/forms.css` itself, in its own
  `extrastyle` block. `admin/base.html` links only `base.css`, `dark_mode.css` and
  `responsive.css`; `forms.css` - where `.form-row`, `.aligned label`,
  `.flex-container`, `.checkbox-row` and `.submit-row` are defined - is linked by
  `change_form.html`. Any custom admin page that renders form rows has the same
  obligation, and without it admin's markup has no rules behind it (#3667). Do not
  test this by looking for the class name: `responsive.css` mentions every one of
  those names in media queries, so the name-presence check passes with the layout
  entirely absent. `BuilderStylingTest` names the stylesheet instead.
- **Rendering** - the page draws its fields through Django's own
  `admin/includes/fieldset.html`, off `UPBRINGING_FIELDSETS`/`QUESTION_FIELDSETS` in
  `forms.py` and the `upbringing_fieldsets`/`question_fieldsets` filters in
  `web/admin/templatetags/upbringing_builder_tags.py`. That is where the label column,
  the model's help lines, the checkbox rows, the required markers and the per-field
  error markup come from, and a field left out of those tuples does not render at all.
  `_css.html` adds only what admin has no class for: the two-column shell (route left,
  live rail right), the question header chips, the live lines, the checks list and the
  rail's stat rows. #3660 shipped `{{ form.as_div }}` and hand-written `<p><label>`
  rows instead, which admin's stylesheet does not target, so the page rendered with
  browser defaults on production (#3667). `BuilderStylingTest` is the guard: it asserts
  the admin contract and that every class the templates emit has a rule on the
  rendered page.
- **URLs** (all superuser-only): `_upbringing_builder/new/` ->
  `admin_upbringing_builder_new` (`?beginning=<id>`), `_upbringing_builder/<pk>/` ->
  `admin_upbringing_builder`, `_upbringing_builder/<pk>/review/` ->
  `admin_upbringing_builder_review` (POST), `_upbringing_builder/<pk>/preview/` ->
  `admin_upbringing_builder_preview` (read-only, the questionnaire the way
  `CGOriginTemplateSerializer` hands it to a player, picking a GROUP question's first
  offered group for display since there is no real draft here).
- **Gate** - `@superuser_required`, then `current_contributor(request.user)`; an
  unlinked operator sees the setup guidance (`_setup.html`) instead and nothing is
  saved, mirroring the Workbench's own gate.
- **Credit** - a POST that validates saves the whole route (`UpbringingForm`,
  `QuestionFormSet`, every question's `AnswerFormSet`) inside one
  `transaction.atomic()` block, then `stamp_written` credits every row on the route
  (the template, every slot, every choice) to the operator's linked contributor in
  the same request - no separate "save" then "credit" step, unlike the Workbench's
  prose editor. "Mark reviewed" (`upbringing_builder_review`) is a separate POST that
  stamps `reviewed_by`/`reviewed_on` on every row and never touches authorship or
  unsaved edits.
- **Right rail (`live.py`)** - live-match lines for a POOL/LISTED group question
  (SAME_AS/SERVED_HOUSE/OWN_FAMILY need a draft to resolve against and stay empty
  here), a placeholder-group count, how many open Vacancies this route can reach
  today (built on an unsaved `CharacterDraft`, never written to the database),
  authoring checks (`("ok"|"warn", text)`: a group question has a source, a
  `same_anchor_as`/`follow_up_to` points at an earlier question, a branch condition
  has a follow-up target to gate it, a `DistinctionOffer` opened by one of this
  route's answers is active (#3675: reads offers, not a field on the answer), an
  OWN_FAMILY group question warns when a claimable family has no house org for it to
  resolve through, #3660 fix round 2 ruling L), and backlog counts (questions, groups
  asked about, people named, answers, distinctions used - a count of distinct active
  offers, not a name list, cheapest/dearest/largest-refund cost spread over required
  questions).
- **What is authored here:** the Upbringing itself, its questions (including the
  `#3660` kind/connection/anchor/follow-up fields), and their answers (including
  `reputation_seed`). Distinctions an answer grants are authored as `DistinctionOffer`
  rows (#3675), not on this page. **What is not:** a Vacancy - membership in
  a staff family is still authored on the `Organization`/`Vacancy` admin page
  (Recipes 11-12 in `family-authoring-recipes.md`), not on this one.
- Deliberate no-ADR for the page-layout/formset decisions: recorded in the approved
  #3660 spec review, the same precedent #3019 set above; ADR-0277 covers the
  questionnaire model itself.

## Tradition Slate (#3675)

**Purpose:** author the standard tradition-step lines once (shared by every
Beginning), and one Beginning's own slate (which traditions it offers, in
which state, with which own wording), on one admin page. Pattern mirrors the
Upbringing Builder: `superuser_required`, the contributor gate, plain Django
forms, `base_site.html`, a page-owned `extrastyle` link to `forms.css`.

- **Files** - `web/admin/tradition_slate/`: `views.py` (`tradition_slate`,
  `tradition_slate_review`), `forms.py` (`TraditionStateLineForm`/
  `SchoolingLineForm` - each carries its own identity field (`state`/`rank`)
  as a `HiddenInput`, never a free select - plus the two factory functions
  `state_line_formset`/`schooling_line_formset` that build a fresh
  `modelformset_factory` class per request, sized `extra=len(missing)`;
  `SlateForm`/`SlateFormSet`, an `inlineformset_factory(Beginnings,
  BeginningTradition, extra=1, can_delete=True)`, the one formset actually
  scoped to the page's Beginning), `live.py` (`rail_counts`, `checks`,
  `preview_line`, `price_text`, `state_line_display`/`schooling_line_display`
  for the derived-price + help-text pair each standard line's row shows).
  Templates in `web/templates/admin/tradition_slate/`: `page.html`, `_css.html`,
  `_rail.html`, `_preview.html` (the entry-line preview, a fragment included
  inside "The slate" module - deliberately not excluded from the styling
  guard's class scan, unlike the Upbringing Builder's standalone
  `_preview.html`). Both this page's and the Upbringing Builder's inline
  "clone a formset row" scripts were promoted to one shared file,
  `web/static/admin/js/builder_formsets.js` (`window.arxBuilderFormsets`:
  `nextFormIndex`/`announceFormsetAdded`/`cloneFromTemplate`, the last taking
  a `wrapperTag` - `"div"` for a whole panel, `"tbody"` for a bare `<tr>`,
  since a `<tr>` parsed into a plain `<div>` is silently dropped by the
  browser's own HTML parser) - #3675 review: this page had shipped a verbatim
  copy of that script.
- **A GET never writes to the database** (#3675 demo-fidelity ruling: a
  `get_or_create` on every GET is a guard by another name). `views._missing_states`/
  `_missing_ranks` diff the current DB against the fixed vocabulary
  (`TraditionState.values`, ranks 0-2); `forms.state_line_formset`/
  `schooling_line_formset` render one form per existing row plus one unsaved
  `extra` form per still-missing state/rank, each extra row's identity fixed
  by the formset's own `initial=` (never typed in, never a free select). A
  still-unauthored row is only written to the database the moment Save
  actually changes one of its visible fields - an author who leaves a new
  row entirely blank saves nothing for it. The three-plus-three sentinel
  the removed write used to stand in for now lives in `required_content.py`
  (below).
- **Required-content sentinel** (`web/admin/tuning/required_content.py`) -
  `_probe_tradition_state_lines`/`_probe_schooling_lines`, both
  `DependencyTier.REQUIRED`: report a missing `TraditionStateLine`/
  `SchoolingLine` row for any `TraditionState` value / rank 0-2, and treat a
  row with a blank `entry_line`/`name` as missing too - the standard lines
  are shared by every Beginning, so a gap here is silent everywhere, not
  just on one Beginning's slate page.
- **Credit** - `web/admin/authoring/credit.py:stamp_written`/`stamp_reviewed`
  take a single `CreditedContent` row rather than a whole route; the
  Upbringing Builder's own `credit.py` was generalised to loop its route's
  rows through these instead of stamping inline. The tradition slate page
  calls them directly on every `TraditionStateLine`/`SchoolingLine` a save
  actually changed (via each formset's own `.save()` return value) and on
  every `DistinctionOffer` row `_sync_schooling_offers` touches (below) - a
  `DistinctionOffer` is `CreditedContent` in its own right, not just the line
  that opens it (#3675 review Important 1: this was missing on first cut).
  `BeginningTradition` carries no authorship fields, so slate rows are never
  stamped. "Mark reviewed" likewise stamps every standard line, not the
  Beginning's own slate rows - the standard lines are shared, so review here
  is not per-Beginning.
- **Save-time side effect (`views._sync_schooling_offers`)** - a POST that
  validates saves all three formsets in one `transaction.atomic()` block,
  then keeps every `SchoolingLine`'s TRADITION_STEP `DistinctionOffer` in
  step with its `grants`: creates the offer (and credits it) for a line that
  gained a grant, keeps an existing offer's `distinction` and `is_active`
  in step (reactivating and crediting it if it had gone inactive), and
  **deactivates** (and credits) an existing active offer for a line whose
  grant was cleared - #3675 review Important 3: a cleared grant used to
  leave its offer active forever. A newly-created offer also flashes a
  message naming it.
- **Reachability** - `web/admin/authoring/links.py:builder_url`/`builder_label`
  (generalised from `upbringing_builder_tags.builder_url`, which now
  delegates to it) resolve the "Open the tradition slate" object tool on the
  `Beginnings` change form (`admin_tradition_slate`, keyed by the Beginning's
  own pk) the same way they resolve "Open in Upbringing Builder" for
  `OriginTemplate`.
- **URLs** (superuser-only): `_tradition_slate/<beginning_pk>/` ->
  `admin_tradition_slate`, `_tradition_slate/<beginning_pk>/review/` ->
  `admin_tradition_slate_review` (POST).
- **Checks (`live.checks`)** - every self-taught/teachers-gone standard line
  carries a drawback; those two drawbacks are each other's
  `mutually_exclusive_with` (worded without naming that attribute, since it
  is staff-facing copy); how many of this Beginning's slate lines are still
  at the model's default state (living masters); every schooling line with a
  grant has its active TRADITION_STEP offer (a warn that clears itself once
  the page is saved, since save is what creates/reactivates the offer); a
  schooling line with **no** grant but a still-active offer (a warn that
  only ever fires for a row edited outside this page, or one from before the
  deactivation fix shipped - saving this page always self-heals it).
- **What is authored here:** the three `TraditionStateLine` rows, the three
  `SchoolingLine` rows, and one Beginning's `BeginningTradition` slate
  (state, own wording, sort order). **What is not:** the `Tradition` row
  itself (name, description) - authored on its own stock admin page - and a
  `DistinctionOffer`'s own fields beyond what this page derives for the
  TRADITION_STEP chapter.
- Deliberate no-ADR: recorded in the approved #3675 spec, the same precedent
  #3660 set above.

## Distinction Builder (#3675)

**Purpose:** author one `Distinction` - its fields, every `DistinctionEffect`,
its `mutually_exclusive_with` M2M, and every `DistinctionOffer` that shows it
in a CG chapter - on one admin page in one transaction, fully replacing the
stock `DistinctionAdmin` for authoring. Pattern mirrors the Upbringing
Builder and the tradition slate page: `superuser_required`, the contributor
gate, plain Django forms, `base_site.html`, a page-owned `extrastyle` link.

- **Files** - `web/admin/distinction_builder/`: `views.py`
  (`distinction_builder`, `distinction_builder_review`), `forms.py`
  (`DistinctionForm` - every field the stock `DistinctionAdmin` fieldsets
  expose today, plus `is_active`/`tags`/`secret_by_default`/
  `default_secret_level` so this page can fully replace it, with
  `mutually_exclusive_with` widgeted `FilteredSelectMultiple`;
  `EffectForm`/`DistinctionEffectFormSet` and `OfferForm`/
  `DistinctionOfferFormSet` via `inlineformset_factory`), `live.py`
  (`price_text`, `effect_reads`, `opener_field_map`, `rail_counts`, `checks`,
  `preview_line`). Templates in `web/templates/admin/distinction_builder/`:
  `page.html`, `_css.html`, `_rail.html`, `_preview.html` (the offer preview,
  a fragment included inside "Where it is offered", not excluded from the
  styling guard's class scan). `templatetags/distinction_builder_tags.py`
  carries `effect_reads` (the template-side wrapper: "" for an unsaved
  formset row rather than raising on a null `target`).
- **Stylesheets** - the page links `admin/css/forms.css` (form-row/help/
  submit-row - not linked outside `change_form.html`, #3667) **and**
  `admin/css/widgets.css` directly, matching what `change_form.html` links
  for the same `FilteredSelectMultiple` widget the "Cannot be held with"
  module uses (`forms.css` `@import`s `widgets.css` too, but this page asks
  for both rather than relying on the transitive import). The widget also
  needs the jsi18n catalog (`{% url 'admin:jsi18n' %}` in `extrahead`,
  loaded automatically by `change_form.html` but not by `base_site.html`).
- **Rendering** - the top module's five main fields and the collapsed "More"
  fieldset (every other field the stock admin exposes) are plain
  `tuning-table` rows, not `admin/includes/fieldset.html` - "More" is a bare
  `<details>`/`<summary>`, native disclosure needing no admin collapse JS.
  Effects and offers are `tuning-table`-styled formsets; "+ Add an effect" /
  "+ Offer it somewhere else" clone the formset's own empty form client-side
  via the shared `web/static/admin/js/builder_formsets.js` helpers (there is
  no saved row to fetch a fragment for until the whole page is saved).
- **The opener cascade** - an offer row always renders all three opener
  widgets (`schooling_line` select, `glimpse_tag` autocomplete, `origin_choice`
  autocomplete), each wrapped `<span class="db-opener" data-opener="...">`;
  `page.html`'s inline script reads a `chapter -> opener field` map
  (`live.opener_field_map()`, `json_script`-embedded, built off
  `DistinctionOffer.opener_field`'s own public per-instance lookup rather than
  its private `_OPENER_FOR_CHAPTER` table) and hides the two the row's current
  `chapter` selection does not want, re-run on every `chapter` change and on
  every cloned row. Server-side validation is unchanged: the model's own
  `DistinctionOffer.clean()`, run automatically by `ModelForm._post_clean()`.
- **`origin_choice`'s autocomplete label** reads
  `"{template.name} › {slot.name} › {choice.name}"` via
  `OriginTemplateSlotChoice.__str__` itself (`world/character_creation/models.py`)
  - both the AJAX search results and the widget's own pre-selected-option
  render call plain `str(obj)`, so overriding `__str__` covers both without a
  custom `AutocompleteJsonView`. A bare slot name is not unique across
  Upbringings, unlike the old `"{slot}: {name}"` form.
- **Autocomplete registrations** - `origin_choice`/`glimpse_tag` need their
  target models registered with `search_fields` (Django's autocomplete view
  404s otherwise): `GlimpseTag` already was (`world/magic/admin.py`);
  `OriginTemplateSlotChoice` got a standalone `ModelAdmin` registration
  (`world/character_creation/admin.py`) alongside its existing
  `OriginTemplateSlotChoiceInline` - the inline alone gives it no
  `search_fields` of its own.
- **URLs** (superuser-only): `_distinction_builder/new/` ->
  `admin_distinction_builder_new`, `_distinction_builder/<pk>/` ->
  `admin_distinction_builder`, `_distinction_builder/<pk>/review/` ->
  `admin_distinction_builder_review` (POST).
- **Gate** - `@superuser_required`, then `current_contributor(request.user)`;
  an unlinked operator sees the setup guidance instead and nothing is saved.
- **Credit** - a POST that validates saves `DistinctionForm`, the effects
  formset and the offers formset in one `transaction.atomic()` block, then
  `stamp_written` (`web/admin/authoring/credit.py`) credits the distinction
  and every effect/offer the save actually touched - all three inherit
  `CreditedContent`. "Mark reviewed" stamps the distinction plus every one of
  its effects and offers in a separate POST.
- **Reachability** - `web/admin/authoring/links.py:builder_url`/
  `builder_label` add a `Distinction` branch ("Open in Distinction Builder"),
  read generically by `change_form.html`'s object-tools block the same way
  as `OriginTemplate`/`Beginnings`.
- **Checks (`live.checks`)** - offered somewhere (any active offer); every
  effect names a modifier target that exists (the FK is required, so this
  only ever warns for a row that reached the database some other way);
  description does not start with `PLACEHOLDER`; a LINEAGE offer whose
  `origin_choice` answer has gone inactive; a TRADITION_STEP offer whose
  `schooling_line` now grants a different distinction than this one.
- **What is authored here:** the distinction's own fields, its effects, its
  `mutually_exclusive_with` exclusions, and every `DistinctionOffer` line
  naming it. **What is not:** the standard tradition-step lines themselves
  (authored on the tradition slate page) or an Upbringing's questions/answers
  (authored on the Upbringing Builder) - this page only adds/edits the offer
  row that links a distinction to one of those.
- Deliberate no-ADR: recorded in the approved #3675 spec, the same precedent
  #3660/#3675 set above.

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

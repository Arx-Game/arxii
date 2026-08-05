# ADR-0201: Credited rows are frozen against loads; sample content only seeds an empty universe

**Decision:** `written_by` (null = placeholder row, set = a human touched it) is the sole
provenance signal on every `CreditedContent` row. `_upsert_fixture_object` freezes a credited row
whenever the incoming corpus value differs from the DB on ANY set field - not just prose - rather
than overwriting it; the only way back to the repo version is a per-row, typed-confirmation
delete-then-reload in the admin's Load Conflicts pages, never a bulk resolve. The guard applies
wherever `CreditedContent` shows up, not only the fixture-JSON/markdown pipeline:
`grid_import.py`'s `_ensure_ambient_group_trigger` freezes a credited `TriggerDefinition` on its
digest-collision refresh branch, reporting through `GridImportResult.reports`
(`FlowDefinition` needs no guard - it is only ever get-or-created, never updated, in this module).
`world.weather.seed.upsert_weather_emits` freezes a credited `WeatherEmit` the same way, returning
conflicts through the same shape the fixture loader uses. Separately, `SEED_SAMPLE_CONTENT`
sample invention is refused once any `CONTENT_MODELS` table already has a row within the same
`seed_dev_database()` press (`assert_sampling_allowed()`, called between the content load and the
cluster loop), so an invented row can never mix into a real content universe.

**Why:** a free-text or best-effort merge can't tell a byte-identical re-export from a genuine
edit apart from noise, and this repo has no sync bookkeeping (ADR-0007 rules out a JSON diff
column, and a per-field dirty marker was explicitly considered and rejected below). Once a human
has set `written_by`, the safest default is to touch nothing and force a deliberate, one-row
confirmation rather than silently pick a side. The weather path needed its own credit-name
resolution (`_resolve_credit_names`) added alongside the freeze: a raw fixture credit
(`written_by` as a natural-key list, e.g. `["Apostate"]`) crashed `update_or_create` with a bare
`ValueError` before this task, since `WeatherEmit.written_by` is a real FK and Django's descriptor
rejects a list outright - every row carrying a credit would have failed to load at all. The fix
mirrors `content_fixtures._resolve_or_drop_credit_fields`'s #2980 rule: an unresolvable credit
name is dropped and logged, never the row.

**Rejected:**
- **Prose-only guard scope.** Freezing only the prose fields on a credited row would leave the
  same row half-frozen, half-overwritten field by field on every load - the guard exists to
  protect a human's editorial pass over the whole row, not just its text, so a mechanical or flag
  field differing freezes the row exactly the same as a prose field.
- **Two-way diff/sync bookkeeping.** Tracking a per-field dirty/edited marker so the loader could
  tell "an unexported staff DB tweak" apart from "the repo genuinely moved on" was rejected as
  complexity this repo cannot afford pre-launch. The freeze-plus-manual-resolve shape is cheap and
  correct even though it cannot distinguish the two cases automatically.
- **Keeping the lore repo's `authored_by` frontmatter as a second provenance system.** The lore
  repo strips it instead (lore-repo issue #60), so `written_by`/`written_on` on the row itself is
  the only place credit lives, never a second source that could drift from the DB.

**Trade-offs / accepted cost:**
- No sync bookkeeping means the freeze cannot distinguish "someone hand-edited this row in the
  live DB and never exported it" from "the repo's fixture genuinely moved past what's in the DB" -
  both look identical (a credited row, a differing incoming value) and both route through the same
  resolution page. Ruled acceptable by Tehom, 2026-08-05, on #3017.
- The sample-content gate is per-press enforcement, not a standing database-wide invariant: it
  runs once, inside one `seed_dev_database()` call, between the content load and the cluster loop.
  A direct cluster-seeder call outside that call - the test-only helpers in
  `world/seeds/tests/press_helpers.py` - sits outside the gate by design, so this is not a claim
  that no code path can ever write sample rows alongside real content, only that the one press a
  live server takes cannot.
- The read-only conflict scan (`core_management.load_conflicts.scan_load_conflicts`) and the
  admin's single-entry delete-then-reload resolve each object in isolation - no deferred-retry
  pass and no grid-bundle load, unlike `load_world_content`'s full sequence. A row whose incoming
  FK target is itself new in the same corpus update may therefore fail to surface as a conflict,
  or fail to reload, until a full load has brought that target in first. The divergence is
  one-directional - it can under-report a conflict, never invent a false one - and the upsert
  guard inside `_upsert_fixture_object` still protects the row regardless of which path notices it
  first; documented in `load_conflicts.py`'s own module docstring.
- `CreditedContent` is inherited uniformly by every content model, so the freeze reaches two rows
  populated exclusively by generated, content-addressed grid-import automation, never by human
  authoring: `FlowDefinition` never needed a guard (create-or-fetch-unchanged only), and
  `TriggerDefinition`'s guard defends a branch that only fires on a sha1 digest collision -
  defensive width, not a response to an observed incident.
- The admin's generic Import Data surface (`web.admin.services.execute_import`, merge or
  replace) does not run the credited-row freeze and can overwrite a credited row's fields with no
  credit check at all. This is a deliberate bypass, not a gap: it is superuser-only disaster
  recovery tooling with its own dry-run diff preview (`analyze_fixture`) shown before any write,
  operating at whole-model granularity rather than the per-field content pipeline the freeze
  protects. An operator restoring from a known-good export is expected to accept the overwrite
  they are previewing, not be blocked by the same guard that protects an unattended content load.

> Status: accepted · Source: #3017, Tehom's ruling 2026-08-05 · Related: ADR-0196 (content credit
> is a row mixin), ADR-0168/ADR-0171 (CONTENT_MODELS is the seed boundary), ADR-0191 (export
> addition gate), ADR-0142 (content vs config boundary)

# Game Tuning & Game Ops dashboards (#1220 / #1221)

Two admin-hosted, superuser-only HTMX dashboards for iterating on mechanics and watching
the live game, built on the existing `ArxAdminSite` rather than a separate app. See
`docs/adr/0093-admin-hosted-tuning-dashboard-htmx-without-unfold.md` for why these are
admin-hosted with vanilla `django-htmx` instead of `django-unfold` or a React staff hub.

## Game Tuning — `/admin/_tuning/` (`admin_tuning`)

Read+preview only — sliders/forms re-render fragments via `hx-get`; nothing here writes
game config except the Monte Carlo run (which itself writes nothing persistent, see
below). Edits to the underlying config models still go through the normal admin change
forms. Five panels, each its own HTMX fragment endpoint loaded with `hx-trigger="load"`
from `src/web/templates/admin/tuning/dashboard.html`:

| Panel | Fragment view | URL name | Analytics module |
|---|---|---|---|
| Checks | `tuning_checks_fragment` | `admin_tuning_checks` | `checks_analytics.py` |
| Consequences | `tuning_consequences_fragment` | `admin_tuning_consequences` | `consequence_analytics.py` |
| Conditions | `tuning_conditions_fragment` | `admin_tuning_conditions` | `condition_analytics.py` |
| Simulation | `tuning_simulation_fragment` | `admin_tuning_simulation` | `world.combat.simulation` |
| Techniques | `tuning_techniques_fragment` | `admin_tuning_techniques` | `technique_analytics.py` + `world.magic.services.technique_power_eval` |

All views live in `src/web/admin/tuning/views.py` and are wrapped in `superuser_required`
(defined there), which mirrors `game_setup_views.py`'s gate: `@staff_member_required` plus
an explicit `request.user.is_superuser` check that raises `PermissionDenied` otherwise.

### Checks panel — `src/web/admin/tuning/checks_analytics.py`

Mirrors the check engine's roll math exactly rather than approximating it — for every
possible roll 1..100 it applies the same clamp `perform_check` applies
(`world.checks.services.py:92-96`, `effective = max(1, min(100, roll + roll_modifier))`)
and looks up the same `ResultChartOutcome` row the engine would land in.

- `compute_chart_distributions(*, roll_modifier: int = 0) -> list[ChartDistribution]` —
  probability breakdown for every seeded `ResultChart`, ordered by `rank_difference`.
- `compute_matchup(*, roller_points: int, target_difficulty: int, roll_modifier: int = 0) -> ChartDistribution | None` —
  single-chart distribution for one roller-points/target-difficulty pairing. Derives
  `rank_difference` the same way `_compute_check_breakdown` does (via
  `CheckRank.get_rank_for_points`) and always reports that *derived* value in the
  result, even when `ResultChart.get_chart_for_difference` falls back to the nearest
  seeded chart — the fallback chart's own `rank_difference` field never leaks through.
  Returns `None` only when no `ResultChart` exists at all.
- `ChartDistribution` (frozen dataclass): `rank_difference`, `chart_name`,
  `bands: list[OutcomeBand]`, `success_probability`, `expected_success_level`.
- `OutcomeBand` (frozen dataclass): `name`, `success_level`, `probability` (0.0-1.0).

The panel template (`_checks_panel.html`) hosts the `roll_modifier` / `roller_points` /
`target_difficulty` slider form itself, since each slider re-renders this same fragment.

### Consequences panel — `src/web/admin/tuning/consequence_analytics.py`

An inspector over `ConsequencePool` — annotates each pool's already-resolved entries
(inherited from parent / overridden by the child / excluded by the child) without
reimplementing the merge semantics owned by `ConsequencePool.cached_consequences`
(`actions/models/consequence_pools.py:52`); it only cross-references the pool's own
entries and its parent's entries against that already-resolved list.

- `list_pools() -> list[tuple[int, str]]` — `(pk, name)` pairs for every
  `ConsequencePool`, ordered by name, for the panel's pool selector.
- `inspect_pool(pool: ConsequencePool) -> PoolInspection` — builds the annotated view.
- `PoolInspection` (frozen dataclass): `pool_name`, `parent_name: str | None`,
  `rows: list[PoolEntryRow]` (sorted by success_level desc then label),
  `excluded_labels: list[str]` (parent entries the child excludes).
- `PoolEntryRow` (frozen dataclass): `consequence_label`, `outcome_tier_name`,
  `tier_success_level`, `effective_weight`, `selection_probability_within_tier`,
  `inherited`, `overridden`, `character_loss`, `theater`.

The `pool` query param selects which pool to inspect (defaults to the first pool by
name); the selector `<select>` lives inside `_consequences_panel.html` so its own
`hx-get` re-render preserves the current selection.

### Conditions panel — `src/web/admin/tuning/condition_analytics.py`

Ranks every `ConditionTemplate` by a composite "danger score" at a chosen severity, with
a bounded, fixed query count regardless of table size (one query for templates, one for
stages via `Prefetch`, one for all `ConditionDamageOverTime` rows grouped in Python).

- `compute_condition_danger(*, at_severity: int = 5) -> list[ConditionDangerRow]` —
  sorted by `danger_score` desc, then `template_name`.
- `DOT_WEIGHT = 2.0` — module constant weighting DoT throughput inside `danger_score`
  higher than the one-time `effective_severity` figure, since DoT fires every round.
- `ConditionDangerRow` (frozen dataclass): `template_name`, `at_severity`,
  `max_stage_multiplier`, `effective_severity` (`at_severity * max_stage_multiplier`),
  `dot_per_round` (scaled by `at_severity` directly — the stage multiplier does NOT
  apply here, keeping the two figures independently legible), `days_to_decay: float | None`,
  `danger_score` (`effective_severity + dot_per_round * DOT_WEIGHT`).

The `severity` query param drives the slider re-render; the form lives inside
`_conditions_panel.html`.

**DE column (#3390, Decision 1).** Alongside the unchanged `danger_score` column, the
panel now shows each condition's standalone DE (damage-equivalent) figure — the same
currency the Techniques panel uses, computed by
`world.magic.services.condition_power_eval.evaluate_condition` at the panel's
`severity`/`duration_rounds` knobs. `danger_score` is a cheap, reference-frame-free
heuristic kept for a quick eyeball; DE is the panel's **default sort**. The
`web.admin.tuning.condition_power_analytics` module mirrors `technique_analytics.py`'s
two-tier caching contract (`ConditionPowerAnalyticsParams` /
`build_condition_power_panel` / `_CORPUS_CACHE_TIMEOUT`), and
`tuning_conditions_fragment` merges the two data sources into one
`ConditionPanelRow(power, danger)` list, joined by condition name (both scan every
`ConditionTemplate`, so every row finds its match). A condition whose payload can't be
priced standalone — the team-damage-percent lane or a stage-scoped DoT row, both of
which need technique-wrapper context a bare `ConditionTemplate` doesn't carry — shows a
named `UNPRICEABLE` valuation and a `team_lane_excluded`/`stage_dot_excluded` flag
rather than a silent zero (Decision 6).

### Simulation panel — Monte Carlo party-vs-boss batches

`tuning_simulation_fragment` (in `views.py`) renders `SimulationRunForm`, runs a batch on
POST, and caches the resulting `SimulationReport` for 24h (`_SIMULATION_CACHE_TIMEOUT`)
under both an exact-param cache key (`_simulation_cache_key`) and a fixed pointer key
(`_SIMULATION_LAST_KEY = "tuning-sim:last"`) so a plain GET/reload re-renders the most
recently cached result instead of losing it.

`SimulationRunForm` (a plain `django.forms.Form` in `views.py`):

- `party_size`, `avg_level`, `iterations` — `IntegerField`s, each clamped in
  a `clean_*` method (`party_size` to 1..8, `avg_level` to 1..30, `iterations` to
  1..500) rather than rejected, so a fat-fingered value gets a capped run instead of a
  form error.
- `tier` (`OpponentTier.choices`), `risk_level` (`RiskLevel.choices`) — `ChoiceField`s;
  an unrecognized value IS a real form error (there's no sane way to clamp a string into
  an enum member).

The view calls `simulation.run_party_vs_boss_simulation` via the module object (not a
bare `from ... import`) so tests can patch the function at its origin module and still
intercept the call from `ops_views`/`views`.

#### `world.combat.simulation` — the simulator itself

`run_party_vs_boss_simulation(params: SimulationParams) -> SimulationReport` drives
`world.combat.services.resolve_round` — the exact same production combat pipeline a
live encounter uses — through `params.iterations` independent, fully-synthetic
party-vs-opponent encounters, each running until one side is wiped or
`params.round_cap` rounds elapse (a stalemate). This module never reimplements combat
math and never calls `world.checks.test_helpers.force_check_outcome` — every round
resolves through real dice via the normal pipeline. Choosing to drive the real engine
rather than hand-roll a parallel probability model is a direct instance of the "no
reinventing the wheel" / no-parallel-implementations rule (see
`docs/adr/0093-admin-hosted-tuning-dashboard-htmx-without-unfold.md`).

`SimulationParams` (frozen dataclass): `party_size: int = 4`, `avg_level: int = 5`,
`tier: str = OpponentTier.BOSS`, `risk_level: str = RiskLevel.MODERATE`,
`iterations: int = 50`, `round_cap: int = 20`.

`SimulationReport` (frozen dataclass): `params`, `iterations_run`, `victories`,
`defeats`, `stalemates`, `win_rate`, `round_counts: list[int]`, `mean_rounds`,
`opponent_max_health` — the scaled `max_health` used for the opponent in the batch's
last-run iteration (deterministic across the batch since every iteration shares the
same params); it reflects whatever tier scaling was live in the DB at run time.

**Isolation contract** (the entire point of the module — nothing it does is ever
persisted):

1. The whole batch runs inside one `transaction.atomic()`; each iteration runs inside
   its own nested savepoint (a second `transaction.atomic()`), unwound by raising an
   internal `_IterationRollback` sentinel caught immediately outside that savepoint —
   so the iteration's rows roll back while the tally already captured in Python
   survives. At the end the whole batch is unwound too via `_BatchRollback`, so even
   outer setup (seeding calls) rolls back with it.
2. Every synthetic object (encounter, opponent, PCs) is built locationless
   (`room=None`): `emit_event` with `location=None` gathers zero triggers
   (`flows/emit.py:60-72`), and encounter completion skips its `ENCOUNTER_COMPLETED`
   emit when `room is None` (`services.py:4735`) — so no reactive flow/trigger side
   effects fire while the simulated combat resolves.
3. `flush_cache()` runs in a `finally` — the `SharedMemoryModel` identity map would
   otherwise keep stale rolled-back rows cached for the rest of the process.
4. Only real dice through the normal pipeline; never `force_check_outcome`, never
   reinvented check/damage math.
5. Existing scaling tuning is ALWAYS respected: `seed_scaling_defaults()` is only
   called when `EncounterScalingConfig` has zero rows (a fresh/unseeded dev DB). Once
   scaling config exists — including a GM's live tuning edits — this module never
   overwrites it, so the preview tool can't silently reset the very tuning it's
   supposed to be previewing.

### Techniques panel — technique combat-power league table (#3279)

Answers "what does this technique contribute to combat power" in one currency: **expected
damage-equivalent (DE) per cast** against a reference matchup, so attacks, buffs,
mitigation, control, and healing are comparable on one axis (see ADR-0223 for the
currency decision). The evaluator lives in `world.magic` (not the web layer) so it reuses
live combat formulas and stays importable by future budget/simulation phases:

- `world/magic/services/technique_power_eval.py` —
  `evaluate_all_with_reference(EvalContext) -> (list[TechniquePowerReport], ReferenceFrame)`
  (and the `evaluate_all` wrapper). Types in `world/magic/types/technique_power.py`.
- **Shared DE formula core (#3390):** `world/magic/services/de_valuation.py` holds every
  row/technique-independent formula this evaluator uses — `matchup_bands`,
  `reference_attack_de`, `cached_damage_multiplier`, `dot_per_round`,
  `modifier_effect_shift`, `mitigation_value`, `is_team_lane_condition`,
  `has_stage_scoped_dot`, and `compute_reference_frame` (the median-baseline-attack
  bootstrap, extracted from this module's own pass 1). The standalone condition
  (`condition_power_eval.py`) and capability (`capability_power_eval.py`) evaluators
  below import this module directly rather than re-deriving any of its math — ONE
  currency across all three instruments (ADR-0239). `technique_power_eval.py` itself
  now delegates to it (thin aliases/wrapper calls); the refactor is byte-identical,
  proven by the pre-existing `test_technique_power_eval_valuators.py` regression suite.
- **SL distribution:** rolls 1..100 enumerated against the context's
  roller-points/target-difficulty matchup (same math as the Checks panel; local
  re-implementation over `world.traits` models because `world` services must not import
  `web` code). Every valuation is an expectation over those bands.
- **Two power contexts per technique:** baseline (the technique's own `intensity`,
  equal to `_derive_power(character=None)`) and a fully-matched-anchor amplification at
  the context's thread level, computed by the SAME pure helpers the live covenant power
  terms call (`blend_power_contribution` / `specialty_power_contribution` in
  `services/power_terms.py`) — retuning `CovenantRoleBlendConfig` moves the panel.
- **Valuators by payload family:** damage profiles through `compute_damage_budget` and
  the `DamageSuccessLevelMultiplier` table; team-damage-lane buffs through the priced
  percent path times reference DPR times expected duration; other modifier conditions as
  the DE shift of a synthetic reference attack; DoT and stat debuffs sign-flipped; hard
  control (HOLD/FEAR/DISTRACTION function tags) as enemy rounds denied times incoming
  DPR; mitigation via `protective_magnitude` (flow-step parse of MODIFY_PAYLOAD triggers,
  e.g. Defend's multiply-0.5); treatments as capped healing. Dispel is deliberately
  unpriced; capability grants are valued 0 (no cast seam exists).
- **Provenance on every valuation:** FORMULA / PARSED / ESTIMATE / UNPRICED_DISPEL /
  UNPRICEABLE / INERT_PAYLOAD — the panel shows per-corpus provenance counts, and
  UNPRICEABLE rows double as an authoring-gap worklist.
- **Reference DPR is self-anchoring:** the median baseline attack DE of the corpus at the
  chosen context (labeled "median-attack estimate"); no hand-maintained constant.

Panel mechanics mirror the Simulation panel: a param form (level, thread level, matchup
knobs, sort) POSTs a recompute cached 24h under an exact-param key with a
`tuning-tech-power:last` pointer; `technique_analytics.py` adds an inner cache keyed on
the analytics knobs only (excluding `sort`) so header-sort clicks never re-run the
evaluator. The league table sorts by baseline DE, anchor DE, DE-per-anima, name, or
level (whitelisted); each row has a `<details>` drill-down showing every valuation line
(kind, label, value, provenance, arithmetic detail). Below the table: the zero/unpriced
bucket and provenance summary. Weapon-scaled damage profiles are flagged
(`weapon_scaled`), not weapon-augmented; execute ramps are flagged, not folded into the
headline; windup techniques divide DE by `1 + windup_rounds`.

### Capabilities panel — DE-per-point league table (#3390)

Answers "what does one point of this capability mechanically buy in combat power,"
extending the DE currency to the third instrument — `CapabilityType`. Lives in
`world.magic` for the same reason the Techniques evaluator does (reuses live combat
formulas, importable by future budget/simulation phases):

- `world/magic/services/capability_power_eval.py` —
  `evaluate_capability(capability, *, context, reference) -> CapabilityPowerReport` (the
  unit-test seam) and
  `evaluate_all_capabilities_with_reference(EvalContext) -> (list[CapabilityPowerReport], ReferenceFrame)`.
  Types in `world/magic/types/capability_power.py`.
- **Pricing model (Decision 3, #3390):** post-#2704/#2708, a capability's mechanical
  value flows into checks entirely through authored `CheckTypeCapabilityModifier` rows.
  Each row's `weight` is the exact pre-truncation marginal rate (the derivative of
  `weight * (value - baseline)` w.r.t. `value` is `weight`) — treated directly as a
  synthetic `roll_modifier` shift and measured via `de_valuation.reference_attack_de`
  base-vs-shifted, the SAME machinery the technique/condition generic-modifier
  valuators use. This is a documented ESTIMATE-provenance linear approximation, not the
  full truncated/largest-remainder allocation (`world.checks.services
  ._capability_point_allocation`) — that needs a real `CharacterSheet`'s simultaneous
  capability set, which doesn't exist for "one abstract point of capability X."
- **No authored bridge = 0 DE, not a crash (Decision 5):** a capability with zero
  `CheckTypeCapabilityModifier` rows prices at exactly 0.0 with a `no_authored_bridge`
  flag on the report. As of #3390 no production seeder authors these rows, so a real
  deploy prices **every** capability at 0 today — correct behavior, not a gap.
- **Guardian-reaction leg needs no bespoke code (Decision 4):** guardian reactions
  resolve through ordinary `CheckType`s via `compute_check_rating` — this evaluator
  already iterates every authored `CheckTypeCapabilityModifier` row across every
  `CheckType`, so a guardian-reaction bridge row prices itself automatically the moment
  staff author one.
- **Not reused here:** `CapabilityPowerConfig`/`apply_capability_curve` (the
  caster-power-scales-magnitude geometric curve, ADR-0169) answers a different
  question — this evaluator prices what one point *buys*, not how caster power scales a
  magnitude. No conflict, no duplication.

Panel mechanics mirror the Techniques panel: a param form (level, thread level, matchup
knobs — no severity/duration axis, capabilities have none) POSTs a recompute cached 24h
under an exact-param key with a `tuning-capability-power:last` pointer
(`capability_power_analytics.py`). The league table sorts by `total_de` desc; each row
has a `<details>` drill-down showing every check-bridge valuation line. Below the
table: the zero/unpriced bucket (today, the whole catalog per Decision 5) and
provenance summary.

## Game Ops — `/admin/_ops/` (`admin_ops`)

Parallel structure to Game Tuning: a page skeleton (`src/web/templates/admin/tuning/ops.html`)
of HTMX-loaded panels, all gated by the same `superuser_required` from `tuning/views.py`.
Five panels total — four pure-read analytics panels from `metrics.py` plus a
Technical Health panel from `tech_health.py`:

| Panel | Fragment view | URL name |
|---|---|---|
| Progression | `ops_progression_fragment` | `admin_ops_progression` |
| Economy | `ops_economy_fragment` | `admin_ops_economy` |
| Story/GM | `ops_story_fragment` | `admin_ops_story` |
| Reports | `ops_reports_fragment` | `admin_ops_reports` |
| Technical Health | `ops_tech_fragment` | `admin_ops_tech` |

Views live in `src/web/admin/tuning/ops_views.py`.

### `src/web/admin/tuning/metrics.py`

Every weekly series is one `TruncWeek`-aggregated query, Monday-anchored, zero-filled
over the last N ISO weeks (default 8) so a week with no rows still renders a bar:

- `progression_series(*, weeks: int = 8) -> list[WeeklySeries]` — XP earned
  (`CharacterXPTransaction`, `amount__gt=0`), development points
  (`DevelopmentTransaction`), level-ups (`ClassLevelAdvancement`).
- `level_distribution() -> list[tuple[int, int]]` — `(level, character_count)` for
  primary `CharacterClassLevel` rows, one query.
- `economy_series(*, weeks: int = 8) -> list[WeeklySeries]` — minted / sunk /
  transferred coppers from `CurrencyTransfer`, bucketed by null source (mint), null
  destination (sink), or both populated (transfer) — mutually exclusive and exhaustive
  per `currency/services.py:86-95`.
- `money_supply() -> dict[str, int]` — `{"purses": n, "treasuries": n, "total": n}`,
  summed balances (not row counts).
- `story_series(*, weeks: int = 8) -> list[WeeklySeries]` — beats completed
  (`BeatCompletion`), scenes started (`Scene`).
- `story_snapshot() -> dict[str, int]` — point-in-time counters: `active_stories`,
  `active_gm_tables`, `pending_session_requests`, `gms_active_30d`.
- The Story/GM panel (`ops_story_fragment`, `views.py`, not `metrics.py`) also reads
  `GMRewardConfig.load()` directly and passes it as `reward_config` — a read-only
  surfacing of the GM Story Reward's tunable award values (#2123) alongside the other
  story/GM balance knobs on this panel, with a link to the model's normal admin change
  form for actual edits (this dashboard stays read+preview-only per its own contract).
- `reports_snapshot() -> list[ReportBucket]` — open/total counts for each
  player-submissions queue (Player Feedback, Bug Reports, Player Reports, System
  Errors), one query per model via a single `Count`/`Case`/`When` aggregate; "open"
  means `SubmissionStatus.OPEN` specifically.
- `WeeklySeries` (frozen dataclass): `label`, `points: list[WeeklyPoint]`.
- `WeeklyPoint` (frozen dataclass): `week_start: datetime.date`, `value: float`.
- `ReportBucket` (frozen dataclass): `kind`, `open_count`, `total`, `staff_url` —
  links each bucket to its corresponding React staff page
  (`/staff/feedback`, `/staff/bug-reports`, `/staff/player-reports`, `/staff/system-errors`).

### `src/web/admin/tuning/tech_health.py`

`collect_tech_health() -> TechHealthSnapshot` — pure-read process/cache/error
telemetry: idmapper cache footprint via
`evennia_extensions.observability.idmapper_gauge.snapshot()` (top 15 models by
approximate bytes, via `pympler.asizeof`), this process's RSS/CPU via `psutil`, the
open (`SubmissionStatus.OPEN`) `SystemErrorReport` count, and deploy-identifying env
vars (`GIT_SHA` or `SOURCE_COMMIT`; whether `SENTRY_DSN` is configured).

`TechHealthSnapshot` (frozen dataclass): `idmapper_top: list[tuple[str, int, int]]`
(`model_label`, `instances`, `approx_bytes`), `idmapper_total_bytes`,
`process_rss_bytes`, `process_cpu_percent`, `open_system_errors`, `system_errors_url`,
`git_sha: str | None`, `sentry_dsn_configured: bool`.

Unlike the other Ops panels, Technical Health is admin-triggered on demand (a Refresh
button, `hx-trigger="click from:#panel-tech-refresh, load delay:1s"` in `ops.html`)
rather than loaded plainly on page load, since walking the idmapper cache with
`pympler.asizeof` can be slow with a large cache.

## Content-repo load surface — `/admin/_content_load/` (#1220)

`src/web/admin/content_load_views.py` — a superuser-only upsert of the maintainers'
private content repository into the database, mirroring the "Load sane defaults" seed
button's confirm/run shape but as an `update_or_create`-by-natural-key upsert rather
than create-if-missing:

- `resolve_content_root() -> Path | None` — reads `CONTENT_REPO_PATH` from the process
  environment (already loaded by the `arx` CLI's dotenv handling; this module does not
  re-parse `.env`) and returns it only if set and a real directory. Reused by
  `game_setup_views.game_setup` for the `content_repo_configured` flag shown on the
  Game Setup hub.
- `content_load_confirm` (GET, `admin_content_load`) — renders a confirm page.
- `content_load_run` (POST, `admin_content_load_run`) — drives
  `core_management.content_fixtures.build_all` then `load_entries` (the same path
  `tools/build_content_fixtures.py --load` uses), flashes a created/updated/placeholder
  count via `django.contrib.messages`, and redirects to the Game Setup hub.

The Game Setup hub (`src/web/templates/admin/game_setup.html`) shows a "Load content
repo" link when `CONTENT_REPO_PATH` is configured, else a hint to set it in `src/.env`
— the Import Data upload remains the path for ad-hoc fixture files either way. The hub
also links to both dashboards described above ("Tune mechanics" → Game Tuning, "Monitor
the live game" → Game Ops).

## Permissions

Every view on both dashboards (and the content-load surface) is superuser-only:
`@staff_member_required` (Django admin's own staff gate) plus an explicit
`request.user.is_superuser` check that raises `PermissionDenied` otherwise. On the
tuning/ops surface this is centralized in `web.admin.tuning.views.superuser_required`,
a decorator both `tuning/views.py` and `tuning/ops_views.py` import and apply; it
mirrors the gate `game_setup_views.py` and the seed views already use (ADR-0022).

## HTMX pattern

- Vendored `htmx.min.js` (`src/web/static/admin/js/vendor/htmx.min.js`), loaded via
  `<script src="{% static %}" defer>` at the bottom of each dashboard template — no CDN
  dependency.
- `django-htmx` (`django_htmx` in `INSTALLED_APPS` + `HtmxMiddleware`) provides
  `request.htmx` detection server-side.
- CSRF: one `hx-headers='{"x-csrftoken": "{{ csrf_token }}"}'` attribute on each
  dashboard's root wrapper div (`#tuning-root`, `#ops-root`) — every HTMX request
  under that wrapper inherits the header automatically. No hand-written fetch/CSRF
  JS anywhere on either dashboard.
- Each panel is a `<section class="tuning-panel">` that self-loads via
  `hx-get="{% url '...' %}" hx-trigger="load"` (the Technical Health panel instead
  triggers on `click from:#panel-tech-refresh, load delay:1s`, since it's
  refresh-on-demand). Panels needing their own slider/selector forms (checks,
  consequences, conditions, simulation) embed that form *inside* their fragment
  template so an `hx-get` re-render from the slider itself replaces the whole panel,
  form included.
- Shared panel CSS lives in one include, `admin/tuning/_panel_css.html` (`.tuning-panel`,
  `.bar-row`/`.bar-track`/`.bar`, `.tuning-table`, `.stat-tiles`/`.stat-tile`,
  `.panel-columns`), `{% include %}`d once near the top of each dashboard template.
  All colors reference Django admin's CSS custom properties (`var(--body-fg)`,
  `var(--body-bg)`, `var(--hairline-color)`, `var(--primary)`) so panels inherit
  admin light/dark theming automatically.

## Tests

- `src/web/admin/tests/test_tuning_views.py` — the dashboard skeleton (routing,
  superuser gate, panel scaffolding).
- `src/web/admin/tests/test_checks_analytics.py`,
  `test_consequence_analytics.py`, `test_condition_analytics.py` —
  the checks/consequences/conditions panels.
- `src/web/admin/tests/test_tuning_simulation_view.py` — the simulation
  form/cache flow.
- `src/web/admin/tests/test_ops_views.py`, `test_ops_metrics.py` — Ops panels and
  `metrics.py`'s query helpers.
- `src/web/admin/tests/test_content_load_views.py` — content-load confirm/run flow.
- `src/world/combat/tests/test_simulation.py` — the simulator's isolation contract
  (nothing persists across a batch) and outcome tallying.

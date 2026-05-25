# Clash Post-Ship Cleanup — Pre-Spec Notes

**Date:** 2026-05-23
**Status:** Pre-spec backlog. Captures cleanup items identified during diff review
of the `clash-design` PR. Bundle into the next clash-adjacent PR (or split as the
work shapes up).

## Why this exists

The clash PR landed with one acknowledged design smell on the `Clash` model
itself plus several known-deferred follow-ups documented in the spec, plan, and
roadmap. The smell deserves a focused refactor; the follow-ups deserve a
prioritized pass. This file captures both so neither gets forgotten between PRs.

There may be additional items not in this file — fold them in as needed.

---

## 1. Consequence-pool refactor (the big one)

### What's wrong

`Clash` currently stores two pool FKs as authored-config snapshots:
- `resolution_consequence_pool` — FK, PROTECT, **non-nullable**
- `per_round_consequence_pool` — FK, PROTECT, **nullable**

These conflate authored config with event-record. The "optional"
`per_round_consequence_pool` is the visible symptom: null on a stateful record
is ambiguous between "didn't happen" and "we didn't record it." Worse, the
Clash audit has no field for the actual `Consequence` row that fired — only
the resolution tier. We lose which consequence was selected from the pool.

Additionally, pools are authored per-content-instance today (every
clash-capable technique authors its own CLASH pool, every sustained-attack
threat entry its own WARD pool, etc.). That's a lot of duplicated authoring,
and the existing `ConsequencePool.parent` FK + `cached_consequences`
inheritance is going unused.

### The cleaner shape

- **Drop the pool FKs from `Clash`.** Resolve at runtime from the triggering
  source.
- **Add `default_*_pool` FKs to `ClashConfig`** (or a sibling singleton) —
  `default_clash_resolution_pool`, `default_lock_resolution_pool`,
  `default_ward_resolution_pool`, `default_ward_per_round_pool`,
  `default_break_pool`. These are the global "what happens by default when
  this flavor of clash resolves" pools.
- **Seed those defaults in `ClashContent.create_all()`** (the production
  content path).
- **Per-content `*_pool` fields stay nullable but mean "override the default."**
  Most techniques / threat entries / opponents leave them null → runtime
  resolves to the system default. Specific content that needs unique
  consequences sets its own pool, optionally with `parent=default_<flavor>_pool`
  to inherit-with-overrides.
- **Add `ClashConsequenceFiring(clash_round_id, consequence_id, fired_at_phase)`**
  as an append-only audit child model. Each `fire_clash_per_round` and
  `resolve_clash` writes one row recording the actual `Consequence` selected.
  `fired_at_phase ∈ {PER_ROUND, RESOLUTION}`. This is the actual "what happened"
  audit.

### Net effect

- `Clash` becomes a pure event-record. No "optional" config snapshots; every
  field is either populated state about what happened or set-at-creation
  invariants.
- Pool resolution at runtime is deterministic: `triggering_source.<flavor>_pool
  ?? ClashConfig.default_<flavor>_pool`. The fallback always exists (seeded by
  `ClashContent.create_all()`), so there's no "no pool" case.
- Authoring effort drops dramatically — content authors only override when a
  technique / threat entry / opponent needs unique consequences.

### Migration shape

- New migration: `Clash` drops `resolution_consequence_pool` and
  `per_round_consequence_pool`. `ClashContributionFiring` model added. New
  fields on `ClashConfig`.
- Code: `detect_clash_opportunities` stops setting the pool FKs on Clash;
  `fire_clash_per_round` and `resolve_clash` change pool lookup to walk
  source-then-default and write the firing audit row.
- Seed: `ClashContent.create_all()` gains the default-pool seeding.
- Tests: update existing assertions that check the pools on `Clash`.

Probably 1-2 hours of focused work end-to-end.

---

## 2. Deferred items from the original clash PR

These were intentionally out of scope and documented in the spec's "Out of
scope" section + the roadmap's "Deferred follow-ups." Roughly in priority
order:

### Blocking before Clash is actually playable

- **Clash-contribution dispatch handler.** Task 7.2 emits `PlayerAction`
  descriptors for active clashes; Task 7.2's fix added a guard in
  `_find_combat_player_action_for_ref` that raises `UNKNOWN_ACTION_REF` for
  clash refs (clean failure rather than wrong-action match). Wiring the
  dispatch to call `declare_clash_contribution` is small and focused —
  service + serializer already exist from Task 7.1. **(done — unified-combat-ui Phases 0–12)**
- **Frontend UI** — clash status panel showing meter + opportunity-to-commit /
  lend buttons. Backend reachable via the unified action interface + the new
  dispatch path. **(done — unified-combat-ui Phases 0–12; carry-forward items listed below)**

### Architectural follow-ups (cross-cutting)

- **Startup/admin page that runs `*Content.create_all()` factories.** Not
  clash-specific — populates a fresh instance with every system's seed
  content. Unblocks "play on a fresh DB without manual content creation."
- **Positioning / zones spec** — pending cohort discussion
  (`docs/plans/2026-05-21-positioning-zones-design-notes.md`). Unblocks
  barriers-as-zone-partition, flight-as-zone, spatial Challenges, and the
  general "where in the encounter are participants" surface.
- **Fury lever** — the *other* road to Audere (deliberate control-lowering /
  rage). Recorded in the Clash spec §11 as deliberately out of scope. Its
  own future spec when prioritized.
- **`TECHNIQUE_PRE_CAST` block/modify reactive capability** — still deferred
  (resonance-environment recommended-next-steps #5). Clash didn't end up
  needing it; other reactive content work will.

### Polish / cleanup the Clash work itself surfaced

- **The Mire rename** (Spec B Soul Tether: Tether Strain → The Mire). The
  name was settled during the clash brainstorm; the rename hasn't been done.
  Touches `TetherStrainTemplate`, soul-tether services' "Strain cost"
  references, factories, docs.
- **LOCK starting-position edge case.** The `is_uncontested_creation_round`
  guard in `run_clash_round` is the right pragmatic fix but a band-aid; the
  cleaner fix is making `check_clash_threshold` aware of starting positions
  (a clash can't "win at 0" if it *started* at 0). Defensible to defer until
  LOCK gets real playtest exposure.
- **WARD per-round pool integration test coverage.** Flagged as a Minor gap
  in Task 8.2 review. Per-round firing has its own unit tests; the
  integration test could exercise both layers together.
- **NPC contribution variance.** Currently deterministic per
  `_resolve_npc_action` convention (no per-round randomness). Variance is a
  tuning concern once playtesting reveals whether deterministic NPC pressure
  feels grindy.

---

## 3. Other items (placeholder)

Tehom mentioned having other items to fold into the same cleanup PR. Add
them here as they're identified.

- ...

---

## 4. Carry-forward from unified-combat-ui (Phases 0–12, shipped 2026-05-24)

Items identified during the unified-combat-UI build that were intentionally
deferred per spec §11 or require additional backend work before the UI can
surface them. Source spec: `docs/superpowers/plans/2026-05-23-unified-combat-ui.md`.

### Backend follow-ups

- **`CombatRoundAction` → `Interaction` join FK for effect enumeration.** The
  `GET /api/combat/action-outcome-details/` endpoint (Phase 9) returns empty
  `effects` arrays per action ID because there is no FK linking
  `CombatRoundAction` to the `Interaction` row that represents its outcome.
  Adding this FK is a small migration; once it lands the endpoint can populate
  effect rows from the `InteractionAction` bridge (spec §11 item 5).
- **`ClashStateSerializer` missing `contributors` and `side_favored`.** The
  `clashes` field on `EncounterDetailSerializer` returns clash state without
  per-round contributor breakdowns or a `side_favored` signal. Pairing with
  the ActiveState Commit/Lend wiring below.
- **`CombatParticipant.available_strain` not exposed in API.** The `YourTurn`
  strain slider is hardcoded `max=10`. Exposing `available_strain` on the
  participant serializer unblocks accurate budget rendering.
- **Focused-category resolution stubbed.** `YourTurn` currently resolves the
  focused category as `passive-physical`. Needs `effect_type.category` or
  `style.category` on the `PlayerAction` API response to pick the correct
  category label per action.
- **`lend-to-clash` dispatch not wired.** The Lend button is a UI stub; no
  `CLASH_SUPPORT` `PlayerAction` descriptor exists on the backend. Requires
  a new descriptor type and dispatch path.
- **`submit_pose` REST endpoint does not broadcast via WebSocket.** The
  detach-case path (breaking a pose-action link) uses REST; other scene
  viewers see the new pose only on next refetch. The WebSocket push path
  needs to be added to the `submit_pose` service.
- **Fatigue model not exposed.** `VitalPools` shows `0/10` placeholders for
  physical/social/mental fatigue. The fatigue model (effort pools, categories)
  needs API endpoints before the UI can render real values.
- **Conditions data not surfaced on `CombatantsList` rows.** The per-combatant
  row renders no active conditions. Requires conditions to be included in the
  encounter participant serializer (or a separate prefetch endpoint).

### Frontend follow-ups

- **Deep-link routing for outcome-detail effects.** `PoseUnitDetailPanel` has
  a `{modal, id}` skeleton for navigating to a linked effect detail view, but
  no navigation is wired. Blocked on the backend FK above; once effects are
  returned, add a `useNavigate` call here.
- **Auto-expand pose units on critical events (KO, death).** `PoseUnit` should
  auto-open its detail panel when the linked action's outcome is a KO or death
  event. Requires a player-preference toggle before it can ship (spec §11
  item 6).
- **`CombatOpponent` portrait FK — NPC avatars are initial-letter-only.** The
  `PersonaAvatar` component falls back to an initials badge when no
  `thumbnail_media_url` is present. `CombatOpponent` has an optional Persona
  FK but no portrait field; NPC portraits remain initials-only until a portrait
  FK or URL field is added (spec §11 item 7).
- **ActiveState Commit/Lend buttons are UI stubs.** The `ActiveState` section
  renders buttons that are disabled with a `TODO` marker. Wiring requires the
  `ClashStateSerializer` contributors/side_favored data and the
  `lend-to-clash` dispatch path above.

### Out of scope (intentionally deferred per spec §11)

- **Scene-side adoption of `<ActionDeclarationCard>` without a `ScenePull`
  envelope.** The card component assumes it is rendered inside a combat turn
  panel. Adapting it for the general scene composer is a separate slice.
- **Positioning / zones integration.** Spatial layout of combatants, zone-aware
  POV filtering for clash visibility, and zone-partition mechanics are all
  blocked on the positioning/zones spec
  (`docs/plans/2026-05-21-positioning-zones-design-notes.md`).
- **Mobile responsive layout.** The C-frame `CombatScenePage` is desktop-first.
  Responsive breakpoints are a polish pass, not a functionality blocker.
- **WebSocket real-time push for all combat state.** The current UI polls on
  user action. Full real-time push (encounter state changes, round resolution,
  new poses) requires a WebSocket broadcast layer that is not yet built.

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
  service + serializer already exist from Task 7.1.
- **Frontend UI** — clash status panel showing meter + opportunity-to-commit /
  lend buttons. Backend reachable via the unified action interface + the new
  dispatch path.

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

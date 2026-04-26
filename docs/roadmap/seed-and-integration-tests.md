# Seed Mechanism + Integration Test Coverage

**Status:** Phase 1 complete; Phase 2 in-progress
**Audit:** [`docs/audits/2026-04-26-seed-and-integration-coverage-audit.md`](../audits/2026-04-26-seed-and-integration-coverage-audit.md)

## Why this exists

Two outcomes unlock the rest of the project:

1. **Anyone can clone the repo and run `arx seed dev` to get a fully-populated, playable game state.**
   This is what makes Arx II "open-source style" — zero-config onboarding for contributors and would-be hosts.
2. **Every game system has user-story integration tests that prove it works end-to-end.**
   Tests organized by player journey (not by code module) double as living documentation of the play loop.

The same factories drive both. Test setup and `arx seed dev` share one code path. If you can't seed it, you can't author it through the game either.

UI is the last-mile surface. Once all systems are seedable AND user-story-tested at the service layer, the UI just exposes what already works.

## Priority ordering

The phases below run in sequence:

1. **Phase 1 — Magic completeness.** Close magic-cluster gaps. Magic is the most-developed system; finishing it gives a model the rest of the work follows.
2. **Phase 2 — Integration test framework expansion.** Apply the same pattern to every other system. Pipeline tests become the source of truth for "does this work end-to-end?"
3. **Phase 3 — Seed for clone use.** Promote the integration-test seed orchestrators into a production-callable layer with `arx seed dev` as the entry point.

These can overlap at the boundaries — for example, the magic-cluster seed helpers built in Phase 1 are the prototype for Phase 3's promotion pattern. But the *priority* is firmly magic → tests → seeding.

## Foundational rules (apply to all phases)

- **Always factories, never fixtures.** Project rule, no exceptions.
- **Seed semantics: create-if-missing, never overwrite, never delete.** Use `get_or_create(natural_key, defaults={...})`, never `update_or_create`. Re-running on an edited DB preserves edits.
- **No hard-reset / `--force` flag.** Drop the database manually if you want to start fresh.
- **No engineering for seed-default propagation.** If a default changes, existing rows keep the old value. Don't add `seed_origin` flags or edit-detection.
- **Tests via `just test` or `arx test`.** No raw pytest.

---

## Phase 1 — Magic completeness

**Goal:** every magic user story is end-to-end tested, every magic singleton has a seed function, and the magic content needed for those tests is composed into a `seed_magic_dev()` orchestrator.

### Phase 1 tasks (in dependency order)

| Task | Unlocks |
|------|---------|
| ✅ **1.1** — `seed_magic_config()` orchestrator: lazy-create the 5 singletons (AnimaConfig, SoulfrayConfig, ResonanceGainConfig, CorruptionConfig, AudereThreshold) with sensible defaults. Includes IntensityTier reference rows (AudereThreshold's FK target) and MishapPoolTier rows. | `use_technique` no longer errors on cast. Anima daily regen actually fires. Soulfray accumulation works. Audere eligibility check has data to work with. |
| ✅ **1.2** — Seed canonical Rituals: "Rite of Imbuing" and "Rite of Atonement". Factories already exist (`ImbuingRitualFactory`, `AtonementRitualFactory`); just need an idempotent seed call. | Atonement flow can fire. Imbuing ritual dispatches. Both today silently fail because the service code looks them up by hardcoded name. |
| ✅ **1.3** — Seed `ThreadPullCost` rows for tiers 1, 2, 3. Also seeds `ThreadPullEffect` catalog (FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT) via `seed_thread_pull_catalog()`. | `spend_resonance_for_pull` no longer errors. Thread pulls become a real mechanic. |
| ✅ **1.4** — Pipeline test: `test_thread_pull_pipeline.py`. Resonance spend → CombatPull written → ThreadPullEffect resolved → effect applied (FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT). | Proves the entire Spec A thread system works in combat context. |
| ✅ **1.5** — Pipeline test: `test_anima_regen_pipeline.py`. Full daily regen tick: AnimaConfig + character with depleted anima + Soulfray-gated property → tick fires → anima restored unless gated. | Confirms the AnimaConfig + ConditionStage `blocks_anima_regen` property + tick scheduler all integrate correctly. |
| ✅ **1.6** — Pipeline test: `test_situation_pipeline.py`. SituationTemplate → SituationInstance → ChallengeInstance chain → resolution. | Situation system covered end-to-end. |
| ✅ **1.7** — Pipeline test: `test_corruption_per_cast_pipeline.py` covering the full per-cast hook landed in PR #403 — Audere caster takes corruption from non-Celestial cast, multiple resonances accrue per their involvement. | Per-cast corruption hook validated end-to-end. |
| ✅ **1.8** — Cantrip starter catalog via `seed_cantrip_starter_catalog()`: 5 TechniqueStyle rows, 6 EffectType rows, 25 Cantrip rows (5 styles × 5 archetypes), 5 PROSPECT Path rows. | CG magic stage works on a fresh dev install. New characters can pick a starter cantrip. |
| ✅ **1.9** — `seed_magic_dev()` master function in `integration_tests/game_content/magic.py` that calls 1.1, 1.2, 1.3, 1.8 plus `author_reference_corruption_content()` and `MagicContent.create_all()`. Two idempotency fixes: `_make_magical_endurance_check_type()` switched from factory to direct ORM (converges with seed_magic_config's row); `MagicContent.create_all()` switched to get_or_create (no duplicate Technique/ActionEnhancement rows on re-run). 7 new tests covering idempotency and convergence. | One call seeds the entire magic cluster. Ready to become the magic-cluster contribution to Phase 3's `seed_dev_database()`. |

### Phase 1 not in scope

- Soul Tether (Spec B) — separate spec/scope, builds on hooks already shipped in Scope #7.
- Tradition gameplay mechanics (what does belonging to a tradition *do* during play?) — design-incomplete; needs a brainstorm before seeding makes sense.
- Magical discovery during RP — design-incomplete.
- Aura farming via scene perception — design-incomplete on the perception side.

These get added to the magic roadmap as design tasks, not seed tasks.

### Phase 1 design decisions needed

None blocking. The math is settled, the models are stable, the factories exist. This phase is mechanical composition.

---

## Phase 2 — Integration test framework expansion

**Goal:** every L1 player user story has a passing pipeline test. The seed helpers needed by those tests get built as a side effect.

### Phase 2 — hard CG blockers

A new player cannot complete character creation today without these. Listed in dependency order — each batch must complete before the next batch starts.

| Batch | Tasks | Unlocks |
|-------|-------|---------|
| **2A — World scaffolding** | `Realm` rows; `Area` hierarchy; `Roster` rows ("Active"/"Available"/"Inactive"); `Family` rows; `OrganizationType` rows (6 standard) | Society creation. Character roster assignment. Beginnings family picker. Org membership. |
| **2B — Character lookups** | `Heritage` rows; `Gender` + `Pronouns` lookups; `Characteristic` + `CharacteristicValue` rows; `Species` (min: Human) + `Language` (min: Arvani); SpeciesStatBonus where applicable | CG Heritage stage. CG Appearance stage. Beginnings species/language M2M targets. |
| **2C — Forms catalog** | `HeightBand`, `Build`, `FormTrait`, `FormTraitOption`, `SpeciesFormTrait` rows | CG Appearance form has selectable options. |
| **2D — Origin scaffolding** | `StartingArea` rows; `Beginnings` rows (Normal Upbringing / Sleeper / Misbegotten); `CGPointBudget` row; `CGExplanation` lore strings | CG Origin stage. CG Heritage stage's heritage selector. CG copy text not blank. |
| **2E — Stat & skill spine** | 12 stat `Trait` rows; `TraitRankDescription` rows; `Skill` catalog; `SkillPointBudget` row | CG Attributes stage. CG Stage 5 skill allocation. Without `SkillPointBudget` row, Stage 5 validation **raises DoesNotExist**. |
| **2F — Resolution tables** | Tuned `PointConversionRange`, `CheckRank`, `ResultChart` + `ResultChartOutcome`, `CheckOutcome` rows | Every system using `perform_check` returns real outcomes. Today integration tests use placeholders; fresh DB has no rows. **Needs design pass on tuning curves first.** |
| **2G — Class & path** | `CharacterClass` rows; 5 PROSPECT `Path` rows (Steel/Whispers/Voice/Chosen/Tome); `Aspect` + `PathAspect` rows | CG Stage 5 path picker. `sheet.current_level`. Path-aspect check bonuses. |
| **2H — Distinctions starter** | `DistinctionCategory` (6 categories); ~20 `Distinction` rows for MVP; `DistinctionEffect` rows wiring to `ModifierTarget` | CG Distinctions stage. **Needs design pass on the starter catalog first.** |
| **2I — Naming ritual** | `TarotCard` deck (full 78 cards: 22 Major Arcana with Latin names + 56 Minor Arcana). Authorable from canonical reference, no design pass needed. | Naming ritual works for orphan/Misbegotten characters. |
| **2J — Relationships library** | Canonical `RelationshipTrack` rows (Trust/Respect/Romance/Antagonism); `RelationshipTier` milestones per track | First-impression flow. Track advancement. |
| **2K — Codex starter** | `CodexCategory` rows; `CodexSubject` rows; `CodexEntry` starter set; CG codex-grant tables (BeginningsCodexGrant, PathCodexGrant, DistinctionCodexGrant) referencing real entries | CG codex grants. Knowledge browser has content. Today CG grants FK to nothing → silent failures or FK violations. |

### Phase 2 — hard runtime blockers

Gameplay outside CG fails on a fresh install today without these.

| Task | Unlocks |
|------|---------|
| **2L** — `FlowDefinition` seed library (movement, look, speak minimum). The single most critical gap — known since project inception. | Any flow-wired command no longer raises DoesNotExist. The reactive layer becomes useable. |
| **2M** — Promote `ChallengeContent.create_all()` from test infrastructure into a real seed module. Includes CapabilityType (~19), Property (~27), Application (~44), ChallengeCategory (5), ChallengeTemplate (6), TraitCapabilityDerivation (11). | Capabilities, properties, applications, challenges all have authored content on fresh install. Action generation pipeline produces non-empty results. |
| **2N** — `StatDefinition` rows for stat-tracking system. | Achievement triggers no longer raise DoesNotExist when systems try to increment stats. |
| **2O** — 6 goal domain `ModifierTarget` rows + `goal` `ModifierCategory` + AP-related `ModifierTarget` rows (`ap_daily_regen`, `ap_weekly_regen`, `ap_maximum`). | Goals system functional. AP modifier system functional. Both today blocked by missing ModifierTarget rows. |
| **2P** — `CharacterVitalsFactory` (does not exist today) + include vitals row in character seed helpers. | Combat services no longer raise DoesNotExist for any character. Combat pipeline test becomes writable. |
| **2Q** — Canonical `CovenantRole` seed set (~6-8 rows: Vanguard/Sentinel/Arbiter for DURANCE; Battle equivalents). | Combat resolution order becomes meaningful. Today every PC defaults to NO_ROLE_SPEED_RANK=20. |
| **2R** — `GameClock` singleton row + verify `GameTickScript` creation runs at server start. | `get_ic_now()` returns a real time. All IC-time-dependent features (day/night, fatigue reset, condition expiry) become functional. |
| **2S** — `ActionPointConfig` row (singleton; has hardcoded fallback but should be staff-visible). | Staff can tune the AP economy from admin without knowing to create a row first. |

### Phase 2 — pipeline tests

Each test starts from a focused seed slice and walks an actor through a complete play loop.

| Test | Story | Enabled by |
|------|-------|-----------|
| **2T** — `test_character_creation_pipeline.py` | New player completes CG start to finish, character placed in starting Area, assigned to Roster | Tasks 2A through 2K |
| **2U** — `test_combat_pipeline.py` | Two PCs join combat, declare actions, NPCs select from threat pool, round resolves, damage applied | Tasks 2P, 2Q + new combat seed module (ThreatPool + ComboDefinition) |
| **2V** — `test_relationship_pipeline.py` | Character submits first-impression → track advances → tier crosses milestone | Task 2J |
| **2W** — `test_codex_pipeline.py` | CG codex grants apply at character creation; teaching offer accepted; codex progress tracked | Task 2K |
| **2X** — `test_journal_pipeline.py` | Character writes journal entry, peers praise, weekly XP awarded | None (zero-config system) — just needs the test |
| **2Y** — `test_progression_pipeline.py` | Character spends XP on a class-level unlock | Tasks 2G + XPCostChart/ClassXPCost seeding |
| **2Z** — `test_world_clock_pipeline.py` | Tick advances world clock → fatigue resets → conditions decay | Task 2R |

### Phase 2 design decisions needed (block specific tasks)

- **PointConversionRange / CheckRank / ResultChart tuning values** (blocks 2F). Integration test values are placeholders. Real game values need a design call on the conversion curve.
- **Distinction starter catalog** (~20 entries) (blocks 2H). Roadmap acknowledges "hundreds need authoring" — pick 20 covering 6 categories to unblock CG.
- **ClassLevelUnlock content** (blocks parts of 2Y). What does each class level give? No spec exists. Can be deferred — XP-spend can land without unlocks authored.

These three can run in parallel with the mechanical seeding work.

---

## Phase 3 — Seed for clone use

**Goal:** `git clone && arx seed dev` produces a playable game state. The integration-test seed helpers built in Phases 1-2 become a production-callable layer.

### Phase 3 tasks

| Task | Unlocks |
|------|---------|
| **3.1** — Choose seed module location. Suggested: `src/world/seeds/` with one module per cluster (magic, combat, character, narrative, infrastructure), or `src/seeds/` at top level. **Should NOT be under `integration_tests/`.** | A clear home for production-callable seed code. |
| **3.2** — Migrate content from `integration_tests/game_content/*` into the new home, preserving the test-callable surface so existing tests continue to work. | Single source of truth for seed orchestration. Test code and seed code share the same factories. |
| **3.3** — Add `arx seed dev` CLI command. Wraps a top-level `seed_dev_database()` orchestrator that calls every cluster's seed function. **Project-rule exception:** the "no management commands" rule has been overridden by user request for this specific command. | Anyone running `arx seed dev` gets a populated dev DB. |
| **3.4** — Enforce create-if-missing semantics across every seed function. Audit existing seed functions for `update_or_create` usage and replace with `get_or_create(natural_key, defaults={...})`. | Re-running on an edited DB preserves edits. Per project rule. |
| **3.5** — Add idempotency regression test: `arx seed dev` on a fresh DB succeeds; second run is a pure no-op (no DB writes). | Guarantee against accidental destructive seeds. |
| **3.6** — Add non-overwrite regression test: edit a seeded row via factory, re-run seed, verify edit is preserved. | Guarantee against accidental data loss. |
| **3.7** — Add a README section to project README explaining the clone-and-seed flow. | New contributors / clone hosts have onboarding docs. |
| **3.8** — Optional: extract per-cluster seed regression tests so each cluster's seed function is independently verified to not crash. | Catches regressions in seed orchestration when models change. |

### Phase 3 not in scope

- Production seed strategy. The dev seed is the foundation; production data lives in production's DB.
- Migration strategy for evolving seed defaults. Existing rows keep their values per agreed semantics.
- Frontend onboarding flow (how does a new clone host configure the admin?). UI work; downstream of this phase.

---

## What this work unlocks

Once Phase 3 lands:

- **Anyone can run an Arx clone.** `git clone && uv sync && arx manage migrate && arx seed dev` produces a playable game.
- **Every L1 user story is regression-tested.** Pipeline tests run in CI, catching breaks at the integration layer.
- **Backend gaps are discoverable.** When Phase C exposed "we can't write this test because the service doesn't exist," that became the next backend spec list. The same pattern continues.
- **The eventual config-admin UI has a data shape to expose.** The seed layer already knows what's tunable — the UI just surfaces it.
- **UI work becomes additive.** No more "we need UI to make this real" — every backend system is provably real before any UI ships.

## Tracking

Each phase task should land as its own PR, against this roadmap doc. Update the table cells with status markers (✅ done, 🟡 in progress, ❌ blocked) as work progresses. The audit doc (`docs/audits/2026-04-26-seed-and-integration-coverage-audit.md`) is the static record of where things stood at the start; this roadmap is the running record of execution.

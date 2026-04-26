# Seed-Data and Integration-Test Coverage Audit

**Date:** 2026-04-26
**Scope:** Every game-system app under `src/` audited against the new architectural target (factory-based seed mechanism + user-story integration tests, both built before any UI work).
**Output of:** Five parallel cluster audits saved at `.claude/scratch/audit-cluster-*.md`.

---

## Why this audit exists

The architectural target is concrete:

1. **Factory-based seed mechanism** — a `seed_dev_database()` orchestrator that someone can call (probably via `arx seed dev`) to populate a fresh-install dev database with sane defaults. Composes existing factories. Create-if-missing semantics, never overwrite, never delete.
2. **User-story integration tests** — `src/integration_tests/pipeline/` tests organized by player journey, each starting from a focused seed slice and walking actors through the play loop. Tests double as living documentation of how the game actually works.
3. **Same factories drive both.** Test setup and `arx seed dev` share one code path. If you can't seed it, you can't author it through the game either.
4. **UI is the last-mile surface** — once all systems are seedable AND user-story-tested at the service layer, the UI just exposes what already works. Eventually a config admin page surfaces the same data this seed populates.

The audit answers two questions per app:
- What authored content does this system need to function in a fresh install?
- Where on the spectrum (factory exists → seed function exists → user-story test exists) is each system today?

---

## Top-line finding

**The factory layer is in great shape across the entire codebase.** Every model that needs a factory has one. The patterns are consistent. The infrastructure is real.

**The seed-orchestration layer barely exists.** What exists today (`src/integration_tests/game_content/`) is six modules totalling ~1500 lines, focused on social actions and challenges. It has the right shape — but it covers maybe 15% of the systems that need seeding, and it's wired into test infrastructure rather than callable from a CLI.

**The user-story pipeline test layer is correspondingly thin.** Four pipeline tests exist (`test_alteration_pipeline`, `test_challenge_pipeline`, `test_social_pipeline`, `test_social_magic_pipeline`). Combat, character creation, and most narrative systems have **zero pipeline coverage** — only in-app unit tests.

The good news: the work is large but it's not architecturally hard. Every gap is "compose existing factories into a seed function" or "write a pipeline test that exercises an existing service." There's no design work blocking it.

---

## Hard CG blockers (a new player cannot complete character creation)

These items cause crashes or empty stages during character creation. None are optional. In rough dependency order:

| # | What | Where | Why it's a blocker |
|---|------|-------|---|
| 1 | `Realm` rows | `world.realms` | Every Society FK to Realm is non-nullable. StartingArea also FK. Without a Realm, neither societies nor starting areas can be created. |
| 2 | `Area` hierarchy | `world.areas` | StartingArea references Area. Without it, characters have no starting location. |
| 3 | `Roster` rows ("Active"/"Available"/"Inactive") | `world.roster` | New characters must be assigned to a Roster. CG submission fails without one. |
| 4 | `OrganizationType` rows (6 standard) | `world.societies` | Organization FK to OrganizationType is non-nullable. Any CG flow assigning org membership fails. |
| 5 | `Family` rows | `world.roster` | Beginnings picks a family. Empty list = empty picker. |
| 6 | `Heritage` / `Gender` / `Pronouns` / `Characteristic` lookups | `world.character_sheets` | All read by CG Heritage and Appearance stages. Empty = empty selectors. |
| 7 | `Species` rows + `Language` rows | `world.species` | `Beginnings.allowed_species` M2M empty → species picker empty. Languages M2M empty → no starting language assignment. |
| 8 | `HeightBand` / `Build` / `FormTrait` / `FormTraitOption` / `SpeciesFormTrait` | `world.forms` | CG Appearance form has no selectable options without these. |
| 9 | `StartingArea` + `Beginnings` rows | `world.character_creation` | Origin and Heritage stages blocked without rows. |
| 10 | `CGPointBudget` row | `world.character_creation` | Hardcoded fallback exists; should be staff-tunable from day one. |
| 11 | 12 stat `Trait` rows + `TraitRankDescription` | `world.traits` | CG Attributes stage cannot function without stat trait definitions. |
| 12 | `Skill` rows + `SkillPointBudget` | `world.skills` | **`SkillPointBudget.get_active_budget()` raises DoesNotExist** if no row. CG Stage 5 validation crashes. |
| 13 | 5 PROSPECT `Path` rows | `world.classes` | CG Stage 5 reads `Path.objects.filter(stage=PROSPECT)` for path picker. Empty = cannot submit CG. |
| 14 | `CharacterClass` rows | `world.classes` | `sheet.current_level` returns 0 everywhere without these. |
| 15 | `DistinctionCategory` (6) + starter `Distinction` catalog (~20) | `world.distinctions` | CG Distinctions stage is empty. Roadmap acknowledges "hundreds need authoring" — 20 minimum unblocks CG. |
| 16 | `TarotCard` deck (78 cards) | `world.tarot` | Naming ritual broken for orphan/Misbegotten characters. Deck is fully specced. |
| 17 | `RelationshipTrack` + `RelationshipTier` library | `world.relationships` | First-impression flow blocked without track FK options. |
| 18 | `CodexCategory` + `CodexEntry` starter set | `world.codex` | CG `BeginningsCodexGrant` / `PathCodexGrant` FK to CodexEntry. Empty → CG grants fail with FK violations. |

**Tuning content (needs design decision before authoring):**
- `PointConversionRange` / `CheckRank` / `ResultChart` / `ResultChartOutcome` / `CheckOutcome` — every check resolution depends on these. Integration test values are placeholders. Real game values need design sign-off on the conversion curve.

---

## Hard runtime blockers (gameplay outside CG fails on a fresh install)

These cause silent failures or crashes during normal gameplay after CG.

| # | What | Where | Why |
|---|------|-------|---|
| 1 | `FlowDefinition` rows | `src/flows` | Zero rows exist. Any command wired to a flow lookup raises DoesNotExist. **Per MEMORY.md: known gap since project inception.** |
| 2 | 5 magic singleton configs | `world.magic` | AnimaConfig, SoulfrayConfig, ResonanceGainConfig, CorruptionConfig, AudereThreshold — `use_technique` errors on cast without SoulfrayConfig. Anima daily regen no-ops without AnimaConfig. |
| 3 | `IntensityTier` reference rows | `world.magic` | Required before AudereThreshold can be seeded. AudereThreshold FKs IntensityTier. |
| 4 | `MishapPoolTier` rows | `world.magic` | Soulfray mishap path never fires without rows. |
| 5 | `GameClock` singleton row | `world.game_clock` | `get_ic_now()` returns None without row. All IC-time-dependent features (day/night, fatigue reset, condition expiry) blind. |
| 6 | `ActionPointConfig` row | `world.action_points` | Has hardcoded fallback so doesn't crash, but staff can't tune economy without knowing to create row. |
| 7 | `CovenantRole` rows (6-8 canonical) | `world.covenants` | All PCs default to NO_ROLE_SPEED_RANK=20 without rows. Combat resolution order meaningless. |
| 8 | Canonical `Ritual` rows ("Rite of Imbuing", "Rite of Atonement") | `world.magic` | Service code looks them up by hardcoded name. Atonement and imbuing flows silently fail without rows. |
| 9 | `CapabilityType` rows (~19) | `world.conditions` | Currently buried in `ChallengeContent.create_capability_types()`. Needed by both conditions (ConditionCapabilityEffect) and magic (TechniqueCapabilityGrant) — any system using capabilities breaks. |
| 10 | `StatDefinition` rows | `world.achievements` | `StatDefinition.objects.get(key=...)` raises DoesNotExist when systems try to increment stats. |
| 11 | 6 goal domain `ModifierTarget` rows + `goal` `ModifierCategory` | `world.mechanics` | CharacterGoal cannot be created without these (FK PROTECT). Shares mechanics app with AP modifier targets. |
| 12 | Resolution lookup tables (CheckRank/PointConversionRange/ResultChart) | `world.traits` | Currently buried in `SocialContent.create_all()`. Fresh install has no resolution tables → every check returns None rank → no consequences fire. |
| 13 | `Property` / `Application` / `ChallengeTemplate` library | `world.mechanics` | Currently buried in `ChallengeContent` test infrastructure. Without them no Application or Challenge can exist; `get_available_actions` returns empty. |
| 14 | `TraitCapabilityDerivation` rows (11) | `world.mechanics` | Trait values don't flow into derived capabilities without these. |
| 15 | `CharacterVitalsFactory` + vitals row in character seed | `world.vitals` | **No factory exists.** Combat services raise DoesNotExist for any character without vitals. |

---

## Per-cluster snapshot

Detailed audits saved to `.claude/scratch/audit-cluster-{magic,combat,character,narrative,actions-infra}.md`. One-paragraph summary each:

### Magic / Conditions / Mechanics / Checks
**Verdict: factories complete; seed orchestration absent.** Five magic singleton configs lazy-create themselves on first read but no `seed_magic_config()` ensures they exist with sensible defaults. `ChallengeContent.create_all()` is the most complete seed module in the codebase but lives in test infrastructure (won't get called by `arx seed dev`). Resolution lookup tables (CheckRank, ResultChart) are buried inside `SocialContent.create_all()` instead of standalone. Pipeline tests cover alteration, challenge, social-magic — solid. **Zero pipeline coverage for the Situation system, thread pull mechanic, or non-social check resolution.**

### Combat / Vitals / Covenants
**Verdict: 599 unit tests, ZERO pipeline integration tests.** Combat is mechanically complete through Phase 3 (REST API, full lifecycle, all combat modes scaffolded) but no test exercises a full encounter as a user story. The seed gap is acute: no `game_content/combat.py`, no ThreatPool/ComboDefinition seeding, **no `CharacterVitalsFactory` exists at all** (every test creates vitals inline). CovenantRole is explicitly an authored lookup table with zero rows on fresh install — combat resolution falls back to rank 20 for every PC.

### Character / Progression / Traits
**Verdict: largest seed-content gap in the codebase.** This cluster gates L1 viability — without character creation seed data, no one can play. Every CG stage has a hard blocker (see table above). The `BasicCharacteristicsSetupFactory` in `character_sheets/factories.py` is the closest existing thing to canonical content but is callable only from tests. Distinctions catalog needs a content-design pass (~20 for MVP, "hundreds" post-MVP per roadmap). PointConversionRange/CheckRank/ResultChart values need a tuning decision before authoring. `world/traits/factories.py` already has `CheckSystemSetupFactory` for a minimal 5-chart system — just needs promotion.

### Narrative / Social / World
**Verdict: middling — some apps zero-config, some entirely unseeded.** Scenes/journals/events/consent/instances/narrative are zero-config (per-player records, no library content). Stories needs TrustCategory + Era seed. Codex is **fully data-driven and completely unseeded** — biggest single content gap in this cluster. Roster + Realm + Area + OrganizationType form a four-link dependency chain that blocks CG entirely. Relationships need canonical track library before first-impression flow works. GM/staff_inbox/player_submissions are P3 (staff tooling).

### Actions / Items / Infrastructure
**Verdict: known-since-day-one gaps + critical infra holes.** FlowDefinition seed library is the single biggest gap — already documented in MEMORY.md as known. Forms catalog blocks CG. GameClock singleton blocks all IC-time features. ActionPointConfig has fallbacks but should still be seeded. Items not L1-blocking (entire service layer unbuilt — future work). Behaviors P3. Goals shares mechanics-app dependencies with AP.

---

## L1 player user-story map

The right way to drive this work is: define the user stories an L1 player must be able to do, then check whether each is currently end-to-end testable. Each story names what authored content it needs. An "❌" is a pipeline-test gap; the listed seed content is what blocks the test from being writable today.

| # | User story | Status | Authored content required |
|---|---|---|---|
| 1 | New player completes character creation start-to-finish | ❌ no pipeline test, ~17 hard CG blockers above | All CG-blocker rows in section above |
| 2 | New character is placed in their starting Area / Room | ❌ | Realm + Area hierarchy + at least one starting room |
| 3 | Two characters meet in a scene; one poses, the other endorses; resonance balance increments | ✅ partially covered | Spec C resonance gain content already seeded for tests |
| 4 | Character casts a tier-1 cantrip in a social context (Scope #4) | ✅ covered by `test_social_magic_pipeline` | Magic content + social check types — already seeded for test |
| 5 | Character casts an Abyssal cantrip; corruption_current/lifetime increment; CORRUPTION_WARNING fires at stage 3+ | ✅ covered by `test_corruption_flow` (just shipped in PR #403) | Reference corruption content seeded for test |
| 6 | Character takes Soulfray from overburn casting; aftermath aftermaths apply; treatment ritual stabilizes | ✅ covered by `test_soulfray_recovery_flow` | Soulfray content seeded for test |
| 7 | Character submits a first-impression to another character → relationship track advances → tier crosses milestone | ❌ no pipeline test | RelationshipTrack + RelationshipTier library |
| 8 | Character writes a journal entry, peers praise it, weekly XP awards | ❌ no pipeline test | None (zero-config) — just needs the test |
| 9 | Two PCs join a combat encounter, declare actions, NPCs select from threat pool, round resolves, damage applied | ❌ no pipeline test, NO combat pipeline tests at all | ThreatPool + ThreatPoolEntry + ComboDefinition + CovenantRole + CharacterVitalsFactory |
| 10 | Character spends XP on a class-level unlock | ❌ no pipeline test | XPCostChart + XPCostEntry + ClassXPCost + ClassLevelUnlock catalog |
| 11 | Character settles weekly endorsement pot at the weekly tick | ✅ covered by `test_resonance_gain_flow` | Already seeded |
| 12 | Player views their full magic state (anima/soulfray/corruption) via API | ❌ unknown — needs investigation whether status API exists | None (data exists; API surface uncertain) |
| 13 | Stage advances world clock; conditions decay; fatigue resets at dawn | ❌ no pipeline test | GameClock singleton + scheduled task records |
| 14 | Character receives a CodexEntry grant from CG choices | ❌ no pipeline test | CodexEntry catalog + CG codex-grant tables |
| 15 | New player accepts a teaching offer from a more experienced player and learns a Technique | ❌ no pipeline test | CodexTeachingOffer machinery seeded; needs test |

**Coverage today:** 5 of 15 user stories have meaningful pipeline coverage. **10 of 15 are blocked from testing by missing seed orchestration, missing factories, or both.**

---

## Recommended phased program

### Phase B-0: Foundations (one-week sprint)

The seed infrastructure itself, callable as `arx seed dev`. Doesn't add any new authored content yet — just builds the harness.

- Create `src/world/seeds/` (or similar) — the home for seed orchestration code. NOT under `integration_tests/` so it can be called from production code paths.
- Migrate `integration_tests/game_content/*` content into the new home, preserving the test-callable surface.
- Add `arx seed dev` command — gets the explicit project-rule exception (the user has authorized one management command for this purpose).
- Create-if-missing semantics enforced via `get_or_create(natural_key, defaults={...})`. Document the convention.
- Add a regression test: `arx seed dev` on a fresh DB succeeds and is idempotent (second run is a no-op).
- Add a regression test: `arx seed dev` on a DB with edited content does NOT overwrite edits.

### Phase B-1: Hard CG unblockers (week 1-2)

The 18 items in the "Hard CG blockers" table, in dependency order. Each gets a `seed_*` function. Some need a content-design decision first (PointConversionRange tuning, distinctions catalog ~20-30 entries).

Recommended order (each batch completes before next starts):
1. Realm + Area hierarchy
2. Roster + Family
3. OrganizationType (6 canonical)
4. Heritage + Gender + Pronouns + Characteristic lookups
5. Species (minimum: Human) + Language (minimum: Arvani)
6. HeightBand + Build + FormTrait + FormTraitOption + SpeciesFormTrait (forms catalog)
7. StartingArea + Beginnings + CGPointBudget + CGExplanation
8. 12 stat Trait rows + TraitRankDescription
9. Resolution tables (CheckRank/PointConversionRange/ResultChart) — needs tuning decision
10. Skill catalog + SkillPointBudget
11. PROSPECT Paths (5) + CharacterClass + Aspect + PathAspect
12. DistinctionCategory + Distinction starter (~20) — needs content-design pass
13. TarotCard deck (78 cards)
14. RelationshipTrack + RelationshipTier library
15. CodexCategory + CodexEntry starter

### Phase B-2: Hard runtime unblockers (week 2-3)

The 15 items in the "Hard runtime blockers" table:
1. FlowDefinition seed library (movement/look/speak minimum)
2. 5 magic singleton configs (AnimaConfig/SoulfrayConfig/ResonanceGainConfig/CorruptionConfig/AudereThreshold) + IntensityTier + MishapPoolTier
3. GameClock singleton + GameTickScript verification
4. CovenantRole canonical set
5. Canonical Rituals ("Rite of Imbuing"/"Rite of Atonement")
6. CapabilityType + Property + Application + ChallengeTemplate (promote `ChallengeContent` to real seed)
7. StatDefinition rows
8. 6 goal domain ModifierTargets + AP ModifierTargets
9. CharacterVitalsFactory + include vitals in character seed

### Phase C: User-story integration tests (weeks 3-5)

Write the 10 missing pipeline tests from the user-story map. Each test starts from a focused seed slice (or `seed_dev_database()`) and walks an actor through the play loop. Tests double as living documentation.

Priority order matches what's enabled by Phase B:
1. `test_character_creation_pipeline` — full CG submission → character placement
2. `test_combat_pipeline` — encounter lifecycle through round resolution
3. `test_relationship_pipeline` — first-impression → track → tier
4. `test_codex_pipeline` — CG codex grants + teaching-offer acceptance
5. `test_journal_pipeline` — write → praise → XP
6. `test_progression_pipeline` — XP earn → spend on class unlock
7. `test_world_clock_pipeline` — tick → fatigue reset + condition decay
8. `test_situation_pipeline` — Situation → Challenge → resolution
9. `test_thread_pull_pipeline` — resonance spend → effect application
10. `test_anima_regen_pipeline` — full daily regen tick

### Phase D: Backend gaps surfaced by Phase C

Phase C will reveal "we can't write this test because the service doesn't exist." That's the next backend spec list. Likely candidates based on cluster audits:
- ClassLevelUnlock content authoring (no spec exists)
- Audere Majora system (architecture planned, nothing built)
- Trainer system (planned, nothing built)
- Permanent wound pool (combat stub returning None)
- Player-facing "view my magic state" API (existence unknown)

### Phase E: UI

Once user stories work end-to-end at the service level, expose them through React. By this point the admin config page is half-written because the seed layer already knows the data shape.

---

## Cross-cutting observations

1. **The seed orchestration layer doesn't have a home yet.** `integration_tests/game_content/` is the prototype but it's test infrastructure. Phase B-0's first task is choosing the right module location. Suggestion: `src/world/seeds/` with one module per cluster, or `src/seeds/` at top level. Should NOT be under `integration_tests/`.

2. **Several authored-content items need a design pass before they can be seeded.** Distinctions catalog (the roadmap acknowledges this), tuned PointConversionRange/CheckRank/ResultChart values, ClassLevelUnlock content. Flag these as "needs spec before authoring" so they don't block Phase B-1.

3. **The "no management commands" project rule has been overridden by user request for `arx seed dev`.** This is a one-off exception; document it in the rule itself if/when revisited.

4. **Some "L1 blockers" are actually staff tooling.** TrustCategory and Era rows are P2 in the cluster reports — they unblock GM tooling, not player play. Consider whether to fold these into Phase B-1 (if you want a complete admin experience) or defer to a later phase.

5. **Pipeline test naming convention is inconsistent.** Existing tests are named `test_alteration_pipeline.py`, `test_challenge_pipeline.py`, etc. The new tests should follow the same convention. Worth documenting this convention explicitly.

6. **The `BasicCharacteristicsSetupFactory` and `CheckSystemSetupFactory` patterns are exactly the seed-function shape we want.** Use them as templates when promoting the seed orchestration layer.

---

## What this audit does NOT cover

- **Frontend seed needs.** Some frontend code probably reads from API surfaces that need real authored content (path picker reads `Path.objects.filter(stage=PROSPECT)`). The audit catches the backend side of this but not whether frontend stages are also blocked by missing data.
- **Production seed strategy.** This audit assumes "dev seed" — the production game would presumably extend the same seed mechanism with real content (full distinction catalog, all canonical resonances, etc.) but the dev seed is the foundation.
- **Migration strategy.** If we change a seed default later, existing dev DBs keep the old value (per agreed semantics). No migration concern, but worth flagging that the dev seed is not a "source of truth" for production data — production data lives in production's database.
- **Test execution time.** A `seed_dev_database()` call from every pipeline test setup might be slow. Consider per-test focused seeds (compose only what each test needs) vs. monolithic seed calls. Phase C will surface this.

---

## Next move

Phase B-0 (build the seed harness) is the right starting point. It's 3-5 days of work, unblocks everything else, and produces a tangible deliverable (`arx seed dev` works). Once that's in, Phase B-1 (hard CG unblockers) is largely mechanical — composing existing factories with canonical content values.

The one design pass needed before Phase B-1 starts in earnest: a tuning decision on PointConversionRange/CheckRank/ResultChart values and a content pass on the starter distinction catalog. Both can run in parallel with Phase B-0.

# Magic System — Playable-Loop Status

**Status:** engine essentially complete; blocked on onboarding/content, not mechanics.
**North star:** a player can **cast → see it posed into the scene → it's logged → it
resolves an outcome**, in a live RP scene in the web client.

This is the **status map** — the one place to answer "where are we / what's left." The
full scope-by-scope build record lives in
[`magic-build-history.md`](magic-build-history.md) (archive; consult it before designing
anything new, to avoid reinventing existing surfaces). When this doc and the archive
disagree, this doc and the code win.

**Capability tiers + MVP sequencing:** [`player-capability-ledger.md`](player-capability-ledger.md)
(DO / GROW / COMBINE pillars). **Gift/resonance economy decisions:** ADR-0050–0057 — Major/Minor
gifts (species abilities as Minor Gifts), gift-thread strength + resonance, XP-unlocks-gate-never-grant,
the one specialization engine, fall/redemption, Covenant of the Court.

## The playable loop, stage by stage

| Stage | Status | Where |
|-------|--------|-------|
| Cast initiation — REST `POST /api/action-requests/cast/`, WebSocket, `ActionPanel` UI | ✅ wired | `world/scenes/cast_services.py:request_technique_cast`; `frontend/src/scenes/actionQueries.ts:castTechnique` |
| Check resolution — anima, soulfray, mishap, corruption, environment | ✅ wired | `world/magic/services/techniques.py:use_technique` |
| Effects / outcome — conditions, combat damage, thread pulls, mage scars | ✅ wired | `world/combat/services.py`; `world/magic/services/` |
| Pose / narration into the scene | ✅ wired | `world/scenes/cast_services.py:create_cast_outcome_pose` → `world/magic/narration.py` |
| Logging — `SceneActionRequest` + `Interaction` + power ledger | ✅ wired | `world/scenes/action_models.py`; `cast_services.py:persist_power_ledger` |
| Resonance / progression feedback | ✅ by design | earned from RP perception (endorsements), **not** from casting — see "By design" below |
| Distinctions grant/shape resonance (standing + potency) | ✅ built | `#1834` — `DistinctionResonanceGrant` + `reconcile_distinction_resonance_grants`; see `magic-build-history.md` |
| **A real character actually being able to cast** | ✅ wired | `#1306` — shared template + per-character check; see below |

The backend cast→pose→log→outcome loop is fully wired and resolves end-to-end (verified
by tracing + a throwaway smoke test). The remaining frontier is **assembly, content, and
integration**, not engine mechanics.

## What's left (the real gaps)

Ordered by priority. These are the gaps between "the engine works" and "a player can do
magic." Each is a filed issue — work these, not micro-hardening tickets.

1. **✅ #1306 — RESOLVED: every technique is now castable** (`priority:now` → done).
   `create_technique` defaults `action_template` to the shared **Technique Cast**
   `ActionTemplate` seeded by `seeds_cast.ensure_technique_cast_content()`. Cast
   resolution rolls the **caster's own per-character magic check**
   (`ensure_character_magic_check_type` / `get_character_cast_check` in
   `seeds_checks.py` / `services/anima.py`); the same check is used by the anima ritual
   (wired via `provision_player_anima_ritual`). A graded **"Magic: Technique Cast"**
   `ConsequencePool` routes outcomes. No schema migration required.
   **Follow-ups from #1306:** the targeting model gaps (listed below) were closed by
   #1321; the technique-designer consequence-pool catalog was closed by #1320 (see
   below).

2. **✅ #1321 — RESOLVED: targeting model + behavior-consent + AoE + standalone condition
   application** (`priority:now` → done). Closed the four gaps deferred from #1306:
   - **Targeting validity enforcement:** `Technique.target_type` (new field,
     `ActionTargetType` choices: SELF/SINGLE/AREA/FILTERED_GROUP, default SINGLE) stores
     per-technique cardinality. `validate_cast_target` (`world/magic/services/targeting.py`)
     enforces cardinality and relationship rules, raising `InvalidCastTarget` on violation.
   - **Behavior-consent routing:** `ConditionCategory.alters_behavior` (new boolean, default
     False) marks behavior-altering categories (compulsion, charm, fear). The consent gate
     is now **behavior-based**: hostile → combat; benign + behavior-altering → PENDING
     consent; benign + capability/stat → resolves immediately (including on other PCs).
     `cast_requires_consent` in `targeting.py` implements this predicate.
   - **AoE expansion:** standalone AREA auto-expands via `resolve_targets` to all eligible
     personas in the scene (relationship-derived: SELF→caster only, ALLY/ENEMY→all others).
     Combat AoE uses the new `CombatRoundActionTarget` join table (`world/combat/models.py`);
     AREA auto-expands to all active opponents, FILTERED_GROUP uses the stored/supplied subset.
   - **Frontend target picker:** the existing `TargetPicker.tsx` (multi-select capable) is now
     driven by a technique's `target_spec`. `_target_spec_for_technique_action` in
     `actions/player_interface.py` builds the spec from `Technique.target_type` and
     `derive_target_relationship`. The `TargetSpec`/`TargetType`/`TargetKind`/`TargetFilters`
     model in `actions/` was **reused** (already existed and wired) — not reinvented.
   - **Standalone condition application:** `apply_technique_conditions`
     (`world/magic/services/condition_application.py`) extracted from combat's
     `_apply_conditions`. Standalone casts now apply technique-authored conditions to
     resolved targets. `AppliedConditionResult` still lives in `world/combat/types.py` as a
     known follow-up to relocate.

   **Still deferred (follow-ups):**
   - Resonance → aspect mapping (all magic checks still use the Arcana aspect).
   - Relocate `AppliedConditionResult` out of `world/combat/types.py`.
   - Standalone hostile/behavior-altering FILTERED_GROUP multi-consent state machine.
3. **🟠 #1307 — seed produces no playable character or scene** (`priority:next`). The
   "Big Button" (`world/seeds/database.py:seed_dev_database`, #651) seeds rules content
   only — 0 CharacterSheets / Personas / Scenes. Needs a playable-slice path (demo
   character via `create_character_with_sheet` + CG finalize, placed in a scene). Child
   of epic #1220.
4. **🟡 #1308 — the web cast loop is never tested live** (`priority:next`). Frontend cast
   tests mock `castTechnique`; backend tested only at service level. No test drives
   `POST /api/action-requests/cast/` against a seeded + CG'd character. Add one as the
   regression guard. Cross-refs #617.
5. **🟢 #1309 — frictionless scene start** (`priority:later`). Casting needs an active
   scene; a player should be able to start/auto-join one without staff setup (the
   "implicit scene start" intent).

## By design — do not re-file these as gaps

A code read flags these as "missing"; they are intentional. Verify against the design
before treating any as a bug:

- **Casting does not grant resonance.** Resonance is earned from *perception* — pose
  endorsements, scene entry, residence/outfit trickle (the four `grant_resonance`
  surfaces in Spec C, `docs/architecture/resonance-gain.md`). You earn it when others
  endorse your dramatic cast pose, not mechanically from the cast.
- **Non-combat casts deal no damage.** A hostile cast at a PC routes into combat
  (`seed_or_feed_encounter_from_cast`), where damage applies. Non-combat = benign / self
  / room. Consistent with the non-lethal-PvP invariant.
- **Non-combat thread pulls are passive-only** (VITAL_BONUS inactive outside combat) —
  Resonance Spec §7.4.

## Design resolution — #1306 (castability, RESOLVED)

**Was:** Is castability (the `action_template`) auto-provisioned per technique, shared
per effect-type/style, or authored staff content?

**Resolved:** A single shared **Technique Cast** `ActionTemplate` is seeded by
`seeds_cast.ensure_technique_cast_content()`. `create_technique` defaults `action_template`
to it; the per-technique FK remains as a staff-only override. Cast resolution rolls the
**caster's own per-character magic check** (synthesized from their stat + skill via
`ensure_character_magic_check_type`), not a technique-level authored check. Outcomes route
through a graded **"Magic: Technique Cast"** `ConsequencePool`. The anima ritual and
technique casts always share the same personal check (`provision_player_anima_ritual`
in `services/anima.py`).

Deferred to follow-up issues: optional resonance→aspect mapping for the per-character
check (today all magic checks use the Arcana aspect).

The targeting model gaps (validity enforcement, AoE, frontend picker, standalone condition
application) were resolved in #1321 — see the #1321 entry above. The consequence-pool
catalog (player/CG selects a flavor from a curated catalog built on
`ConsequencePool.parent`, instead of the single shared pool) was resolved in #1320 — see
`docs/systems/magic.md` and `src/world/magic/CLAUDE.md` for detail.

## Telnet technique-authoring workbench (#1496 — BUILT, staff/GM-only)

Closes the `#1328` telnet-coverage gap for technique authoring. Surfaces built:

- **`TechniqueDraft`** + three payload child models (`TechniqueDraftCapabilityGrant`,
  `TechniqueDraftDamageProfile`, `TechniqueDraftAppliedCondition`) in
  `src/world/magic/models/technique_draft.py`. Payload children inherit abstract bases
  (`AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` in
  `models/techniques.py`) shared with the committed `Technique*` rows.
- **Draft services** (`services/technique_draft.py`): `get_or_start_draft`, `discard_draft`,
  `set_draft_fields`, restriction + payload add/remove helpers, `draft_to_design`.
- **`validate_design_for_character`** (`services/technique_builder.py`) — gift-ownership
  gate extracted from the serializer; now the single gate for both telnet and web.
- **`AuthorTechniqueAction`** (key `"author_technique"`, category `"magic"`,
  `actions/definitions/technique_authoring.py`) — the single commit seam. Both the web
  `TechniqueViewSet.author` endpoint and `CmdTechnique` converge on `action.run()`.
- **Web convergence** — `TechniqueViewSet.author` now dispatches `AuthorTechniqueAction.run()`
  for the player path (HTTP contract preserved: 201/400/403). Staff-without-character retains
  a direct `author_staff_technique()` fallback.
- **`CmdTechnique`** (`commands/technique.py`, key `"technique"`, `cmd:perm(Builder)`) —
  staff/GM-only telnet workbench with subcommands:
  `draft show set restrict grant damage condition price author discard`.
  `author` dispatches `AuthorTechniqueAction` with `as_staff=True` (`StaffPolicy`, advisory
  budget, no `CharacterTechnique` binding).

**Deferred `needs-design` follow-up:** when and how ordinary players earn technique authoring
(CG design step, magical-research unlock, or other unlock mechanism — never on-demand).
The `PlayerPolicy` seam and web `author` endpoint are already wired; the player-tier gate
is a permissive `TODO` in `technique_builder.py`.

## Telnet resonance visibility (#2032 — BUILT)

Telnet players could earn and spend `CharacterResonance.balance` (thread pulls, imbuing,
sanctum weaving, entry flourishes, pose endorsements, ...) but had no telnet surface that
ever rendered it. Two read-only faces now expose it, both reading the same
handler/service the web uses — no parallel query pipeline:

- **`sheet/magic`** (`commands/account/sheet_sections.py`) gained a `Resonance:` block —
  every claimed resonance's balance + lifetime earned, from `_build_magic_resonances`
  (`world/character_sheets/serializers.py`), which reads `character.resonances`
  (`CharacterResonanceHandler`, the cached identity-mapped accessor). Folded into
  `MagicSection.resonances`, shared by telnet and the web Magic tab.
- **`resonance`** (`commands/resonance.py`, new command key) — bare `resonance` reuses the
  same builder for the balance listing; `resonance history [<name>]` shows the caller's
  last 10 `ResonanceGrant` rows (newest first, source label), optionally narrowed to one
  claimed resonance, via `resonance_grant_history_for_sheet`
  (`world/magic/services/gain.py`) — mirrors `ResonanceGrantViewSet`'s ordering.

## Ritual of the Durance (#1352 — BUILT)

The within-tier class-level advancement ceremony is complete. Magic's contribution:

- **`RitualLiturgy`** (`models/liturgy.py`) — OneToOne on `Ritual`; `opening_call` TextField
  holds the authored officiant invocation (public, non-spoiler).
- **`RitualOfTheDuranceFactory`** (`factories.py`) — seeds the `Ritual` row (SERVICE /
  INDUCTION, `service_function_path` → `world.progression.services.advancement.advance_class_level_via_session`,
  `min_participants=2`) and its companion `RitualLiturgy` via a `@post_generation` hook.
- `AudereMajoraCrossing` now inherits `AbstractClassLevelAdvancement` (from
  `world.progression.models.advancement`), sharing shape with `ClassLevelAdvancement`.
  `cross_threshold` calls `apply_class_level_advance` (the shared spine) instead of
  inlining a level write.

**Telnet Durance (#1700) — BUILT.** Telnet drivability of the Ritual of the Durance is now
complete. Both a live-officiant ceremony (`ritual draft` → inductee `ritual join` → `ritual fire`)
and a site-convened session (`durance convene` → inductee `ritual join`, auto-fires) are
supported. See `docs/roadmap/character-progression.md` and ADR-0065 for the full build record.

## CG magic acquisition — Path → Tradition → Gift → Technique (#2426 — BUILT)

CG no longer lets a player author a personal cantrip; it links a character to
staff-authored catalog content instead:

- **Tradition is a real mechanical layer.** Every character has exactly one
  Tradition, including the self-taught `Unbound` tradition (no NULL-tradition
  special-casing). `TraditionGiftGrant` (tradition × gift → signature technique
  extras) drives the CG gift list; `BeginningTradition.required_distinction`
  hard-gates non-Unbound traditions at tradition selection.
- **`PathGiftGrant.starter_techniques`** (unchanged schema) is reinterpreted as
  the CG *availability pool*, not an automatic grant — the same rows
  `grant_path_magic` mints from at the level-3 Durance semi-crossing (ADR-0063,
  unaffected). CG picks 1 + `Tradition Training` distinction rank from the
  pool ∪ the tradition's signature extras.
- **The Anima Check replaces a silent default.** CG's Gift stage now closes
  with an explicit stat + skill pick (`provision_player_anima_ritual` gained
  parameters instead of hardcoding Willpower + highest skill) and a ritual
  name — see the glossary entry (not "Signature"; ADR-0072 owns that term).
- **Removed:** `Cantrip` model + full stack, CG facet selection, custom gift
  name/description, and the CG Outcome Flavor pick.
- Rationale + rejected alternative: ADR-0136. Stage/flow detail:
  `docs/roadmap/character-creation.md`, `docs/systems/character_creation.md`,
  `docs/systems/magic.md`.

## Tradition sponsorship, Academy training, and the in-play loop (#2428/#2440/#2441/#2442 — BUILT)

The in-play training loop #2426's roadmap entries deferred as a follow-up is now real —
a character no longer needs to complete their starter Gift pool at CG; they finish it at
Shroudwatch Academy, or via a trainer of their own Tradition, in play.

**Content-dependency caveat.** The mechanical substrate below (Hares, obligations,
`OfferKind.TRAIN`/`SETTLE_OBLIGATION`, the availability gate) is dev-complete and
fully wired, but the *NPCRole* content that fronts it is not: real Academy trainer
curricula (which techniques, which tradition, how many, room prose) are lore-repo
authored content, not this cluster's job. What ships in this repo is a
dev-minimum seed — the Academy Registrar (settles the entrance debt) and one
ungated generalist trainer (teaches the shared starter pool) — just enough that a
freshly seeded DB can complete the loop end to end without lore-repo content
present. Staff/content replace or extend these seeded rows freely; the seeds
never overwrite a staff-adjusted row.

- **Golden Hares** (`currency.FavorTokenDetails`, ADR-0137) — a physical, tradeable,
  org-issued deed token (one Hare = one deed done for the issuing org), NOT an abstract
  ledger. Minted via `mint_favor_token` (GM adjudication `award_type="favor_token"`,
  #2428 Task 4), surrendered via `redeem_favor_token` (issuer-match enforced — a Hare
  only ever redeems to the org that issued it).
- **Academy sponsorship is a real spend, not a waiver.** `societies.OrganizationObligation`
  gives every CG-finalized character a Shroudwatch Academy entrance record: `OWED` one
  Hare for the Unbound (no Tradition to cover it), `SETTLED_BY_SPONSOR` for everyone else
  (the sponsor literally spent a Hare on the Prospect's behalf, lore-recorded at CG time).
  `settle_obligation` clears an `OWED` row by redeeming a real Hare later in play,
  reached through the Academy Registrar's `OfferKind.SETTLE_OBLIGATION` offer
  (`run_settle_obligation_offer`) — an ungated, always-visible NPCRole offer, since
  a Prospect who owes the debt must always be able to find someone to pay it to.
- **Academy training (#2440)** — `npc_services.OfferKind.TRAIN` teaches a technique for
  AP + coin + 1 Golden Hare, gated on the obligation above being settled and on the
  learner's own (Path × Gift) pool ∪ their active Tradition's signature list
  (`magic.services.cg_catalog.get_technique_options`). Delegates acquisition to the same
  `charge_and_learn` core player-to-player `TechniqueTeachingOffer` accepts use — one
  seam, two front doors. **Great Archive self-study** is the same TRAIN shape, gated on a
  quest-completion `Achievement`. It teaches the learner's own (Path × Gift) shared
  starter pool only — it does **not** restore an orphaned tradition's signature
  technique list; recovering a lost tradition's own curriculum is story content, not
  a mechanical unlock this seam provides. A second, ungated generalist trainer seeds
  the same shared-pool techniques without the achievement gate, so a fresh-DB
  Prospect always has ≥1 reachable TRAIN offer even before any quest content exists.
  **Level 2 requires knowing ≥3 techniques of the character's major Gift**
  (`progression.MajorGiftTechniqueRequirement`) — a count, not a completeness bar.
- **Tradition membership lifecycle (#2441)** — `CharacterTradition.left_at` makes
  membership history-preserving (mirrors `OrganizationMembership.left_at`).
  `join_tradition`/`leave_tradition` (`magic.services.tradition_membership`) switch
  membership; joining a tradition through its teaching org's membership-offer accept
  flow auto-sheds the Unbound/Orphaned-Tradition drawback. Learned techniques are never
  revoked on switch — only future signature-list access changes.
- **The Unbound penalty is TIME, not power (#2442).** The "unbound" drawback
  `Distinction` carries a +50% Action Point surcharge on magic-learning activities
  (`magic_learning_ap_cost` `ModifierTarget`) — self-taught mages develop just as
  strong, only slower. Resonance earning and spending are untouched (see ADR-0137 for
  the rejected resonance-halving alternative).
- Rationale + rejected alternatives: ADR-0137. Full model/service detail:
  `docs/systems/magic.md`, `docs/systems/societies.md`, `docs/systems/INDEX.md`
  ("NPC Services", "Currency", "Societies" entries).

## CG starter catalog rides the content pipeline, not a seed function (#2474 — BUILT, 2026-07-18)

The CG starter Gift/Technique catalog (`Resonance`/`Gift`/`Technique`/`PathGiftGrant`/
`TraditionGiftGrant`, including the "Unbound" `Tradition` itself) is now real
lore-repo content, not synthetic in-repo seed data — closing the gap left when
#2426 built the catalog *shape* but authored it via a temporary in-repo
`seed_starter_gift_catalog()` seed function.

- All five models gained `NaturalKeyMixin` and joined `CONTENT_MODELS`
  (`core_management/content_export.py`); `Technique`'s natural key is
  `(gift, name)` (`unique_technique_gift_name` — `name` alone collides across
  gifts, e.g. lore reuse or a player-crafted technique).
- `core_management.content_fixtures.load_entries` gained M2M natural-key
  resolution, stale-field tolerance (a fixture field naming a removed/renamed
  model field is skipped with a warning, not a crash), and fixed-point deferred
  retry (multiple passes until a pass makes no further progress — a multi-hop
  chain like a `Technique` naming a still-deferred `Gift` needs more than one
  retry).
- `world.seeds.database.seed_dev_database()` now sequences: resolve
  `CONTENT_REPO_PATH` (raise `ContentError` immediately if unset/missing) →
  seed config prerequisites the content fixtures FK by natural key
  (`ensure_technique_cast_content()`, since lore-repo `Technique` rows FK the
  shared "Technique Cast" `ActionTemplate`) → `load_world_content()` → the
  `CLUSTER_SEEDERS` loop. No cluster seeder authors catalog content anymore.
- The retired `seed_starter_gift_catalog()` + `StarterGiftCatalogResult` are
  replaced, for tests, by `MagicContent.create_starter_gift_catalog()`
  (`world/seeds/game_content/magic.py`, a synthetic factory-built stand-in) and
  an enriched `stub_content_root()` (`world/seeds/tests/content_stub.py`).
  NPC trainer seeds (`world/npc_services/seeds.py`) resolve their starter
  technique picks as gift-scoped `(gift_name, technique_name)` pairs and raise
  `ContentError` when none resolve — a missing/stale catalog fails loudly
  rather than silently seeding an empty trainer.
- Rationale + rejected alternative (a synthetic sample-content fallback baked
  into arxii seeds): ADR-0142. Full detail: `docs/systems/magic.md`'s "CG
  Starter Gift/Technique Catalog" + "Content-vs-config boundary" sections,
  `docs/systems/INDEX.md`'s "Content-repo load" entry.

---

## One-oracle merge — agency oracle reads technique grants (#2504 — BUILT, 2026-07-18)

Before #2504, a technique-granted `CapabilityType` only fed the **availability** oracle
(`get_capability_sources_for_character`, `world.mechanics.services` — "what could grant this
capability"); the **agency** oracle (`get_effective_capability_value`,
`world.conditions.services` — "can this character do X right now," consumed by requirement/gate
checks) did not know techniques existed, so a character whose only path to a capability was a
known technique failed requirement checks a condition or innate baseline would have passed.

- `world.conditions.services._technique_capability_values` folds the best (max) `prerequisite__isnull=True`
  `TechniqueCapabilityGrant` across a character's known techniques
  (`technique__character_grants__character=character_sheet`) into `get_effective_capability_value`,
  reusing `TechniqueCapabilityGrant.calculate_value()`. (`get_all_capability_values` deliberately keeps
  source-enumeration semantics with NO technique folding — the availability oracle's `_get_condition_sources`
  reads it, and folding there duplicated technique grants as phantom condition sources; caught by CI on this PR.)
- Zero per-consumer changes needed: `technique_performable` (`world/magic/services/capability_requirements.py`),
  mission `challenge_options_for_character` (`world/missions/services/challenge_options.py`), positioning +
  battle movement gates, predicates, and vitals awareness all now honor technique grants automatically —
  they already read through the agency oracle.
- Deliberate asymmetry (ratified, unchanged): `TraitCapabilityDerivation` stays availability-oracle-only.
- Rationale for MAX-not-sum + prerequisite-free-only: ADR-0144 (extends ADR-0034 individuation).
- Journey tests: `world/magic/tests/test_technique_requirements.py::TechniqueGrantSatisfiesRequirementTests`,
  `world/missions/tests/test_services_challenge_options.py::ChallengeOptionsTechniqueGrantTests`.
- Docs: `src/world/conditions/AGENT_GLOSSARY.md`'s "Agency oracle" entry; the "Technique - FK to
  ActionTemplate" box in `docs/architecture/action-template-pipeline.md` (was wrongly claiming
  availability-only).
- Follow-up noted, not filed (see `reference-capability-two-oracle-split` in project memory): the
  object-state→challenge bridge (#2503) is the remaining last mile for techniques feeding
  world-interaction end to end.

---

## Deeper design & history

- Scope-by-scope build record: [`magic-build-history.md`](magic-build-history.md)
- Architecture references: `docs/architecture/` (power-derivation, resonance-threads,
  resonance-gain, reactive-layer-foundation, magical-alteration, non-clash-casting, …)
- System reference: `docs/systems/magic.md`

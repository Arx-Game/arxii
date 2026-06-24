# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - proper domain models with optional ModifierTarget link
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity - proper domain models with FK to Affinity and optional ModifierTarget link
- **Motif**: Character-level magical aesthetic containing resonances and facets
- **Facet**: Hierarchical imagery/symbolism (Spider, Silk, Fire) assigned to resonances
- **Threads**: Per-character attachments anchored to a trait/technique/facet/
  relationship-track/relationship-capstone/covenant-role/sanctum. Each Thread
  channels a single Resonance (currency) and accrues `developed_points` → `level`
  via the Imbuing ritual. The legacy 5-axis Thread family was removed and replaced
  in Phase 4 of the resonance pivot.
- **Resonance currency**: `CharacterResonance.balance` is spendable currency
  earned via `grant_resonance` (Spec C surfaces will write here) and spent
  via `spend_resonance_for_imbuing` (advances Thread level) or
  `spend_resonance_for_pull` (low-level spend called by the pull helpers).
  `lifetime_earned` is monotonic audit. **Thread pulls are declaration modifiers**
  on `cast`/`clash` — the shared commit path lives in `world/combat/pull_helpers.py`:
  `commit_combat_pull` (combat contexts), `build_cast_pull_declaration`,
  `resolve_pull_from_kwargs`. Non-combat cast uses `request_technique_cast(cast_pull=…)`.
  Preview: `preview_resonance_pull` (`POST /api/magic/thread-pull-preview/`) — read-only,
  unchanged.
- **ThreadWeaving**: Acquisition layer. `ThreadWeavingUnlock` is the authored
  catalog (per anchor scope); `CharacterThreadWeavingUnlock` is the per-character
  purchase record; `ThreadWeavingTeachingOffer` is the teacher-facing offer
  (mirrors `CodexTeachingOffer`).
- **Ritual**: Authored magical procedures with four dispatch kinds —
  `execution_kind=SERVICE` invokes a registered service function path;
  `execution_kind=FLOW` invokes a `FlowDefinition`;
  `execution_kind=CEREMONY` creates a `PendingRitualEffect` that a finisher
  command (`weave`, `imbue`) later consumes to complete the ritual;
  `execution_kind=SCENE_ACTION` fires a check via `RitualCheckConfig`.
  The two canonical CEREMONY rituals are **Rite of Weaving** (finisher:
  `CmdWeaveThread` / `WeaveThreadAction`) and **Rite of Imbuing** (finisher:
  `CmdImbue` / `ImbueThreadAction`).
  Ritual *performance* is the `perform_ritual` `Action`
  (`actions/definitions/ritual.py`, key `"perform_ritual"`) — both telnet
  (`commands.ritual.CmdRitual`) and the web (`RitualPerformView`) converge on
  `PerformRitualAction.run()` (#1331). There is no standalone executor; the
  action catches the ritual-surface exceptions (`RitualComponentError`,
  `ResonanceInsufficient`, `AnchorCapExceeded`, `InvalidImbueAmount`,
  `XPInsufficient`) and returns a failure `ActionResult` whose `message` the
  view maps to HTTP 400.
- **PendingRitualEffect**: In-progress CEREMONY record. Created by
  `PerformRitualAction` when `execution_kind=CEREMONY`; unique per
  `(character, ritual)`. Consumed (deleted) by the finisher action on success.
  Fields: `character` (FK → `CharacterSheet`), `ritual` (FK → `Ritual`),
  `created_at`. If a finisher fires without a matching `PendingRitualEffect` the
  action returns a failure result — no side effects.

## Models

### Domain Models
- `Affinity` - Three magical affinities (Celestial, Primal, Abyssal) with optional OneToOne to ModifierTarget
- `Resonance` - Magical identity tags with FK to Affinity, optional opposite (self OneToOne), optional OneToOne to ModifierTarget

### Character State
- `CharacterAura` - Tracks a character's affinity percentages (celestial/primal/abyssal)
- `CharacterResonance` - Per-character per-resonance row. Identity anchor AND
  spendable currency bucket. Fields: `character_sheet` FK, `resonance` FK,
  `balance` (spendable), `lifetime_earned` (monotonic audit), `claimed_at`,
  `flavor_text`. Unified per Spec A §2.2 — the old `scope`/`strength`/`is_active`
  shape was dropped; row existence replaces `is_active`.
- `CharacterAnima` - Magical resource (anima) tracking

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (M2M to Resonance)
- `TechniqueStyle` - How magic manifests (Manifestation, Subtle, Performance, Prayer, Incantation) with `allowed_paths` M2M
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.)
- `IntensityTier` - Configurable thresholds for power intensity (Minor, Moderate, Major)
- `Technique` - Authored magical abilities with level, style, effect type (created via the budget builder or staff CRUD — see "Technique authoring" below)
- `CharacterGift` - Links characters to known Gifts
- `CharacterTechnique` - Links characters to known Techniques
- `TechniqueBudgetConfig` - Singleton (pk=1) of power-cost-per-unit knobs (intensity, control, payload, restriction refund multiplier). Lazy-created via `get_technique_budget_config()` in `services/technique_builder.py`.
- `TechniqueTierBudget` - Per-tier reference power budget + representative level stamped on techniques authored at that tier. Lazy-created via `get_technique_tier_budget(tier)`.
- `SoulTetherConfig` - Singleton (pk=1) of Soul Tether tuning knobs: sineating anima/fatigue costs per unit, per-scene caps, hollow-max multiplier, rescue strain thresholds, rescue resonance costs, rescue budget bases and multipliers. All fields are integers; multipliers encoded as integer-tenths or integer-hundredths. Lazy-created via `get_soul_tether_config()` in `services/soul_tether.py`.

### Technique authoring (budget builder)

`services/technique_builder.py` provides a three-layer authoring stack:

**Unrestricted core** — `build_technique(design, *, creator)` writes a `Technique` + payload rows (`TechniqueCapabilityGrant`, `TechniqueDamageProfile`, `TechniqueAppliedCondition`) + restriction attachments in one `transaction.atomic`. No gating, no character binding. `create_technique(...)` is the extracted low-level row writer shared with cantrip finalization. When `action_template` is omitted (the default), `create_technique` resolves it to the shared **Technique Cast** `ActionTemplate` seeded by `seeds_cast.py` via `get_standalone_cast_template()` — so every technique is castable standalone out of the box. Staff may pass an explicit template FK to override on a per-technique basis.

**Policy layer** — `price_design(design, *, config, budget)` is a pure function that itemizes power cost per dimension and subtracts restriction refunds, returning a `TechniqueCostBreakdown`. It always runs for every author — the breakdown is informational for staff and a gate for players. `AuthoringPolicy` subclasses answer three knobs:
- `StaffPolicy` — `enforced=False`; budget is advisory; any tier allowed.
- `PlayerPolicy` — `enforced=True`; budget is enforced; allowed tiers come from the research-unlock seam (permissive `TODO` today).
- `GMPolicy` — `enforced=True`; calibration is a staff-tunable `TODO` (no grounded GM-level concept yet).

`enforce_policy(design, policy, character)` always prices and returns the breakdown; raises `TechniqueBudgetExceeded(breakdown)` only when `policy.enforced and not within_budget`, or `TechniqueAuthoringNotPermitted` when the tier is disallowed.

**Context wrappers**:
- `author_technique(character, design)` — player path: `PlayerPolicy` (enforced) → build → bind `CharacterTechnique`.
- `author_staff_technique(design, *, creator=None)` — staff path: `StaffPolicy` (advisory) → build; no character binding.

**API endpoints** on `TechniqueViewSet` (`/api/magic/techniques/`):
- `POST .../author/` — resolves policy from the requesting user (staff → `StaffPolicy`; otherwise `PlayerPolicy`); returns 201 with `TechniqueSerializer` + breakdown, or 400 with breakdown when a player is over-budget.
- `POST .../price/` — dry-run; returns the `TechniqueCostBreakdown` for any author without creating rows.
- Base `create`/`update`/`destroy` are staff-only raw admin CRUD (`IsAdminUser` permission).

**Frontend** — `TechniqueBuilderForm` with `mode: "staff" | "player"`. Staff mode shows the budget meter informationally without blocking; player mode gates submit on `within_budget`. `usePriceTechnique` (debounced `POST .../price/`) drives the live budget meter; `useAuthorTechnique` handles submission.

### Anima Recovery
- `Ritual` (execution_kind=SCENE_ACTION) + `RitualCheckConfig` sidecar - Personalized recovery ritual (stat + skill + resonance + check_type)
- `AnimaRitualPerformance` - Historical record of ritual performances

**Note:** During character creation, the magic stage uses a simplified cantrip selection
system. Anima rituals are set up post-CG. The player-authored `Ritual` row (SCENE_ACTION)
carries check configuration via its `RitualCheckConfig` sidecar (stat, skill, resonance, check_type).

### Standalone Casting (#1306)

Every technique now carries an `action_template` FK (defaulted by `create_technique`) so
casting never hard-fails with "no template." The resolution chain:

- **Shared "Technique Cast" ActionTemplate** — seeded idempotently by
  `seeds_cast.ensure_technique_cast_content()`, called from the magic dev seed.
  Retrieved at runtime via `get_standalone_cast_template()`. Staff may override
  on a per-technique basis via the `action_template` FK; `None` (omit the kwarg)
  always resolves to this shared template.
- **Per-character magic check** — every caster rolls *their own* magic check, not a
  technique-level authored check. `ensure_character_magic_check_type(character_sheet, *, stat, skill)`
  (`seeds_checks.py`) synthesizes a `CheckType` named after the character (pattern
  `character_magic_check_type_name(character_sheet)`) that weights the character's
  personal stat + skill. `get_character_cast_check(character)` (`services/anima.py`)
  resolves this check type for use by the cast pipeline.
- **Anima ritual alignment** — `provision_player_anima_ritual` (`services/anima.py`)
  points the anima ritual's `RitualCheckConfig.check_type` at the same per-character
  check type, so the anima ritual and technique casts always roll the same personal check.
  Use `get_character_anima_ritual(character)` to retrieve the anima ritual row.
- **Graded consequence pool** — a single "Magic: Technique Cast" `ConsequencePool`
  (seeded by `seeds_cast.py`) routes graded outcomes (failure / partial success / success)
  through the shared consequence machinery. No per-technique pool is required.

Follow-ups deferred to later issues: technique designer (players pick a consequence pool
from a curated catalog), targeting model (targeting validity + AoE + per-technique target
constraints + frontend target picker), and the optional resonance→aspect mapping.

### Cantrips (Character Creation)
- `Cantrip` - Staff-curated technique templates for CG magic stage selection
- A cantrip IS a baby technique — at CG finalization it creates a real Technique
- Fields: archetype (display grouping), effect_type, style, base_intensity, base_control, base_anima_cost
- Mechanical fields are hidden from the player; they only see name/description/archetype/facets
- Cantrips are filtered by character's Path via `?path_id=` query param (style must be in Path's allowed_styles)
- New players see only their path's cantrips; returning players (advanced mode) see all cantrips
- 5 styles map 1:1 to 5 Prospect paths: Manifestation→Steel, Subtle→Whispers, Performance→Voice, Prayer→Chosen, Incantation→Tome

### Motif System

The Motif system is a **wired mechanical axis** — dressing in items whose styles match
a character's Motif bindings buffs that resonance's magic through the modifier pipeline.

- `Motif` - Character-level magical aesthetic (container for resonances + facets)
- `MotifResonance` - Resonances in a motif (from gifts or optional)
- `Facet` - Hierarchical imagery/symbolism (Category > Subcategory > Specific)
- `MotifResonanceLink` - Abstract base for per-resonance attachments. Declares
  NO fields; each concrete subclass declares its own `motif_resonance` FK.
  Provides `clean()`/`save()` cap-enforcement logic (Python-layer count check
  against `MAX_PER_RESONANCE`; no DB constraint). Two concrete subclasses:
  - `MotifResonanceAssociation` - Links a resonance to a facet in the motif
  - `MotifResonanceStyle` - Per-character style→resonance binding: each
    `MotifResonance` can hold up to 3 `MotifResonanceStyle` rows (cap enforced
    by `MotifResonanceLink.clean()`/`save()`, Python-layer). Each row binds one
    `Style` (from `world/items`, staff-curated vocabulary model sibling to
    `Facet`/`FashionStyle`) to the resonance.
    **Individualization core:** two characters can share the same `Style` name yet
    bind it to different resonances — so "Seductive" means different magic for a
    fire-resonant caster vs. a shadow-resonant caster.

**Coherence walker (`passive_motif_style_bonuses` in `world/mechanics/services.py`):**
Wired into `equipment_walk_total` → `get_modifier_total()`. For each `MotifResonanceStyle`
binding on the character's motif, checks which equipped items carry that style
(via `CharacterEquipmentHandler.item_styles_for`), aggregates their quality tiers via
`worn_quality_aggregate`, and applies a coherence bonus to the bound resonance's
`ModifierTarget`. The bonus magnitude and per-resonance cap come from the
`AestheticAxisConfig` singleton (`world/mechanics`, lazy-created by `get_aesthetic_config()`).

The per-resonance computation lives in `motif_coherence_bonus(sheet, resonance_id) -> int`
(decoupled from `ModifierTarget`); `passive_motif_style_bonuses` is a thin wrapper that
gates on `target.target_resonance_id` and delegates to it. The same helper is reused by the
thread survivability coherence amplifier (see below) — single source of truth, no parallel walk.

Two composition invariants are tested in `mechanics/tests/test_aesthetic_composition.py`:

- **Style × Facet coexistence:** An item carrying both an `ItemStyle` and an `ItemFacet`
  contributes to `passive_motif_style_bonuses` (style coherence) AND `passive_facet_bonuses`
  (facet resonance) independently and simultaneously. The two walkers operate on disjoint
  data paths and their results are summed by `equipment_walk_total`.

- **Dilution-only (unbound styles are inert):** The walker iterates only the character's
  `MotifResonanceStyle` bindings for the target resonance. Any worn `ItemStyle` not present
  in those bindings is invisible to the walker — it adds no coverage and applies no penalty.
  Characters may wear items tagged with arbitrary styles without degrading their coherence bonus.

**Admin authoring surface:** Standalone `MotifResonanceAdmin` (in `world/magic/admin.py`)
with a `MotifResonanceStyleInline` for the style bindings; `ItemStyle` inline on `ItemInstance`.

### Thread System (Resonance Pivot Spec A)

**Authored catalogs (lookup, SharedMemoryModel):**
- `ThreadPullCost` - Per-tier pull cost knobs (tier 1/2/3: `resonance_cost`,
  `anima_per_thread`, `label`). Tuning surface — values here are data; cost
  *shape* lives in `spend_resonance_for_pull`.
- `ThreadXPLockedLevel` - XP-locked boundary price list (`level` on the
  internal 10/20/30... scale, `xp_cost`). Mirrors skills' XP locks.
- `ThreadPullEffect` - Authored pull-effect template keyed
  `(target_kind, resonance, tier, min_thread_level)`. `effect_kind` chooses
  payload column: `FLAT_BONUS` / `INTENSITY_BUMP` / `VITAL_BONUS` (+ `vital_target`) /
  `CAPABILITY_GRANT` (FK to `CapabilityType`) / `NARRATIVE_ONLY`. Tier 0 is
  always-on passive; tiers 1–3 are paid pulls. `clean()` + CheckConstraints
  enforce payload/effect_kind shape.
- `ThreadSurvivabilityTuning` - Per-`VitalBonusTarget` tuning row for the
  universal thread survivability baseline (#1175). One row per target — five
  at launch: `MAX_HEALTH`, `DAMAGE_TAKEN_REDUCTION`, and the three threshold-save
  vectors `DEATH_SAVE` / `KNOCKOUT_RESIST` / `PERMANENT_WOUND_RESIST` (#1250).
  Fields: `vital_target` (unique choice), `coefficient` (linear multiplier on
  investment score S), `cap` (ceiling the baseline asymptotes toward),
  `half_saturation` (S at which baseline = cap/2), plus the coherence-amplifier
  knobs (#1252) `coherence_scale` (per-resonance coherence bonus that yields +1.0
  to a thread's depth multiplier; 0 disables amplification for this target) and
  `coherence_max_multiplier` (Decimal ceiling on the per-thread coherence factor;
  1.00 = inert). Formula: `round(cap × S / (S + half_saturation))` where
  `S = coefficient × Σ depth(t) × coherence_factor(t)` over all owned threads
  (see the baseline section below). Seeded idempotently via
  `seed_thread_survivability_tuning()` (called by the integration-test dev seed);
  inert until rows exist. Staff-tunable in admin.
- `ThreadWeavingUnlock` - Authored catalog of "you can weave threads on X"
  unlocks. Same discriminator + typed-FK pattern as Thread: `unlock_trait`,
  `unlock_gift`, `unlock_track`. `xp_cost` + M2M to `Path` (in-band) +
  `out_of_path_multiplier`. SANCTUM threads do not require a
  `ThreadWeavingUnlock` — the anchor cap (`sanctum.feature_instance.level × 10`)
  is the only gate at imbue time.
- `ImbuingProseTemplate` - Fallback prose for the Imbuing ritual keyed on
  `(resonance, target_kind)`. The row with both NULL is the universal fallback.
- `Ritual` - Authored magical procedure. Dispatch kinds: `SERVICE` →
  `service_function_path`; `FLOW` → FK to `FlowDefinition`; `CEREMONY` →
  creates `PendingRitualEffect` (finisher command completes the ritual);
  `SCENE_ACTION` → fires a check via `RitualCheckConfig`.
  `site_property` optionally gates where it can be performed.
- `RitualComponentRequirement` - FK to `Ritual` + FK to `ItemTemplate` with
  `quantity` and optional `min_quality_tier`. Consumed during ritual dispatch.
- `PendingRitualEffect` - In-progress CEREMONY record. Unique per
  `(character, ritual)`. Created by `PerformRitualAction` on CEREMONY invocation;
  consumed (deleted) by the finisher action (`WeaveThreadAction`, `ImbueThreadAction`)
  on success.

**Per-thread and per-character records:**
- `Thread` - The thread row. Discriminator (`target_kind`) + typed FKs:
  `target_trait`, `target_technique`, `target_facet`,
  `target_relationship_track`, `target_capstone`, `target_covenant_role`,
  `target_sanctum_details`. Fields: `owner` (FK CharacterSheet), `resonance`
  (FK Resonance), `name`, `description`, `developed_points`, `level`, timestamps,
  `retired_at` (soft-retire), `slot_kind` (required for SANCTUM threads —
  `SanctumSlotKind`: PERSONAL_OWN / COVENANT / HELPER). All typed FKs use
  `on_delete=PROTECT`. Three layers of integrity: `clean()`, per-kind
  CheckConstraints, per-kind partial UniqueConstraints.
  **SANCTUM anchor:** `Thread.target_sanctum_details` (FK to `SanctumDetails`).
  Anchor cap = `sanctum.feature_instance.level × 10`. The thread is pull-applicable
  ("in-sanctum boost") while the character is inside the Sanctum's room.
  **Bare ROOM `target_kind` removed** — use SANCTUM for room-anchored threads.
- `ThreadLevelUnlock` - Per-thread XP-locked-boundary receipt. Unique per
  `(thread, unlocked_level)`. Records that a thread paid XP to cross a
  specific boundary (20, 30, ...).
- `CharacterThreadWeavingUnlock` - Per-character purchase record linking a
  CharacterSheet to a ThreadWeavingUnlock. Captures actual `xp_spent`
  (in-band uses unlock.xp_cost; out-of-band multiplies by
  `out_of_path_multiplier`) and optional `teacher` (FK RosterTenure).
- `ThreadWeavingTeachingOffer` - Teacher-side offer. FK to RosterTenure +
  ThreadWeavingUnlock. Mirrors `CodexTeachingOffer` shape (pitch, gold_cost,
  banked_ap). Path multiplier computed at acceptance time, not stored.

**Universal survivability baseline (services/threads.py, #1175 / #1250 / #1251 / #1252):**

A character's breadth × depth of thread investment contributes a passive survivability
bonus across every vector likely to kill them — max-health, damage reduction, and the
death/knockout/permanent-wound threshold saves — independent of authored `VITAL_BONUS`
pull-effects. The baseline is amplified per-thread by the fashion/motif coherence of each
thread's own resonance (dress the part for the resonance you invested in → harder to kill).

- `seed_thread_survivability_tuning()` — idempotently creates the five default
  `ThreadSurvivabilityTuning` rows (DR: coeff=1, cap=20, half=8; MAX_HEALTH: coeff=1,
  cap=80, half=10; DEATH_SAVE / KNOCKOUT_RESIST / PERMANENT_WOUND_RESIST: coeff=1,
  cap=15, half=8). Called by the dev seed.
- `get_thread_survivability_tuning(vital_target) -> ThreadSurvivabilityTuning | None` —
  fetches the tuning row for a given `VitalBonusTarget`; returns `None` if not yet seeded
  (baseline is 0 when absent).
- `survivability_baseline(character, vital_target) -> int` — `round(cap × S / (S + half))`
  where `S = coefficient × Σ depth(t) × coherence_factor(t)` over owned (non-retired)
  threads, `depth(t) = max(1, thread.level // 10)`, and
  `coherence_factor(t) = min(coherence_max_multiplier, 1 + motif_coherence_bonus(sheet,
  thread.resonance) / coherence_scale)` (factor 1.0 when `coherence_scale` is 0). An
  uncoordinated wardrobe yields factor 1.0 — no penalty (dilution-only rule); a lone wolf
  (no threads) gets 0.
- `survivability_save_baselines(character) -> ThreadSurvivabilitySaves` — frozen dataclass
  (`wound`/`death`/`knockout`) bundling the three threshold-save baselines.

The baseline is injected at these call sites:

- `apply_damage_reduction_from_threads(character, damage_amount) -> int` — subtracts the
  DR baseline. Called from combat (`apply_damage_to_participant`) AND from the non-combat
  damage seams that previously bypassed it: `_deal_damage` (mechanics effect-handler;
  traps + consequence damage) and `_apply_round_tick_damage` (condition DoT) (#1251).
- `recompute_max_health_with_threads(character_sheet) -> int` — adds the MAX_HEALTH
  baseline to the base max-health figure. Called at weave and imbue time.
- `process_damage_consequences` (`world/vitals/services.py`) adds the matching save
  baseline to each tier's roll `extra_modifiers` (wound←PERMANENT_WOUND_RESIST,
  death←DEATH_SAVE, knockout←KNOCKOUT_RESIST) (#1250). Because all damage — combat, DoT,
  and traps — funnels its threshold rolls through this one function, hazard/DoT saves are
  covered for free.

**Combat-side models (live in `world/combat`, not magic):**
- `CombatPull` - Per-(participant, round) commit envelope for a thread pull.
  Unique per (participant, round_number). M2M to Thread for the threads
  pulled; `resonance_spent` / `anima_spent` for audit. Committed via
  `world/combat/pull_helpers.commit_combat_pull` (not called directly).
- `CombatPullResolvedEffect` - Frozen snapshot of one resolved effect from
  a pull. Captures `kind`, `authored_value`, `level_multiplier`, `scaled_value`,
  `vital_target`, `source_thread`, `source_thread_level`, `source_tier`,
  `granted_capability`, `narrative_snippet`. Cascades from CombatPull;
  edits to authoring or Thread.level mid-round cannot retroactively alter
  what a committed pull granted.

**Note:** Affinity and Resonance are proper domain models in this app, each with an
optional OneToOne FK back to ModifierTarget for modifier system integration.

### Resonance Gain Surfaces (Resonance Pivot Spec C)

**Models (new):**
- `ResonanceGainConfig` - Singleton tuning config (pk=1). Fields: `weekly_pot_per_character`,
  `scene_entry_grant`, `residence_daily_trickle_per_resonance`, etc. Lazy-created via
  `get_resonance_gain_config()`.
- `PoseEndorsement` - Unsettled endorsement of a pose; settles at weekly tick. FK to
  `endorser_sheet`, single `resonance` FK (PROTECT). Unique per `(endorser_sheet, interaction)`.
  Captures `persona_snapshot` (FK to `scenes.Persona`, SET_NULL) for masquerade audit. Fields:
  `created_at`, `settled_at` (NULL until weekly settlement).
- `SceneEntryEndorsement` - Immediate flat grant for endorsing a character's scene entry
  pose. FK `endorser_sheet`, FK `endorsee_sheet`, FK `scene`, single `resonance` FK (PROTECT).
  Captures `persona_snapshot` (FK to `scenes.Persona`, SET_NULL) for masquerade audit. Unique per
  `(endorser_sheet, endorsee_sheet, scene)`. Fires `grant_resonance` synchronously on creation.
- `ResonanceGrant` - Universal audit ledger. Discriminator `source` (TextChoice: POSE_ENDORSEMENT,
  SCENE_ENTRY, ROOM_RESIDENCE, OUTFIT_ITEM, STAFF_GRANT) + typed FKs: `source_room_profile`,
  `source_staff_account`, `source_pose_endorsement`, `source_scene_entry_endorsement`. FK
  `character_sheet`, FK `resonance`, `amount`. CheckConstraints enforce shape per source.
- **Room resonance data lives in the locations cascade.** What used to be tagged via
  the former `RoomAuraProfile` / `RoomResonance` models is now stored as
  `LocationValueModifier` rows with `key_type=RESONANCE`. See `world/locations/CLAUDE.md`
  and the `tag_room_resonance` / `get_residence_resonances` services in `services/gain.py`.

**Services (`services/gain.py` — new module):**
- `grant_resonance(sheet, resonance, amount, *, source, typed_fk_kwargs)` - Typed-FK signature.
  Writes CharacterResonance + ResonanceGrant atomically. `source` is a GainSource TextChoice.
  Matching typed FK kwarg required per source: ROOM_RESIDENCE → `room_profile=`,
  POSE_ENDORSEMENT → `pose_endorsement=`, SCENE_ENTRY → `scene_entry_endorsement=`,
  STAFF_GRANT → optional `staff_account=`, OUTFIT_ITEM reserved.
- `create_pose_endorsement(endorser_sheet, interaction, resonance)` - 8 preconditions
  (self, alt, whisper, private, participation, unclaimed resonance, duplicate). Raises
  `EndorsementValidationError` on failure.
- `create_scene_entry_endorsement(endorser_sheet, endorsee_sheet, scene, resonance)` -
  Immediate-grant sibling with participation + alt checks.
- `settle_weekly_pot(endorser_sheet)` - Settles all unsettled PoseEndorsement rows for one
  endorser. Distributes `ceil(weekly_pot_per_character / N)` resonance per endorsement.
  Idempotent.
- `residence_trickle_tick()` - Daily pass: for each sheet with residence, grant per matching
  (aura-tagged ∩ sheet-claimed) resonance. Per-character atomic.
- `resonance_daily_tick()` - Master daily tick (residence trickle + outfit stub).
- `resonance_weekly_settlement_tick()` - Master weekly tick (settle all endorsers).
- `tag_room_resonance(room_profile, resonance, set_by=None)` / `untag_room_resonance(room_profile, resonance)` -
  Idempotent room aura management.
- `set_residence(sheet, room_profile | None)` / `get_residence_resonances(sheet) -> set[Resonance]` -
  Residence declaration + resonance intersection query.
- `account_for_sheet(sheet) -> AccountDB | None` - Walks CharacterSheet → RosterEntry →
  current RosterTenure → PlayerData → Account. Single source of truth for alt-guard.
- `get_resonance_gain_config() -> ResonanceGainConfig` - Lazy-create singleton (pk=1).

**Ticks registered in `game_clock/tasks.py`:**
- `magic.resonance_daily` - 24h
- `magic.resonance_weekly_settlement` - 7d

**API surfaces (`views.py`):**
- `PoseEndorsementViewSet` - POST /api/magic/pose-endorsements/ + DELETE-if-unsettled
- `SceneEntryEndorsementViewSet` - POST-only (delete deferred with ResonanceGrantReversal)
- `ResonanceGrantViewSet` - Read-only, user-scoped. FilterSet on source/resonance/date range.

**Telnet surfaces (`commands/endorse.py`, `commands/fashion.py` — #1340):**
- `CmdPoses` (`poses <char>`) — lists endorseable poses in the current scene via
  `get_endorseable_poses_in_scene()`; respects WHISPER receiver and VERY_PRIVATE
  participation gates.
- `CmdEndorse` (`endorse pose/entry/style <char> resonance=<name>`) — two-phase pose
  endorsement (preview → confirm) + one-shot entry/style; converges on the same
  `PoseEndorseAction` / `SceneEntryEndorseAction` / `StylePresentationEndorseAction`
  the web serializers use. Active scene resolved from caller's room.
- `CmdJudgePresentation` (`judge <id>`) — fashion event judgement via
  `JudgePresentationAction` (now returns `endorsement` in `result.data`).

**Privacy rules (updated):**
- **WHISPER** poses: endorsable only by the direct recipient
  (`InteractionReceiver` row for endorser's account). Previously blanket-blocked.
- **VERY_PRIVATE** poses: endorsable by scene participants (SceneParticipation check).
  Previously blanket-blocked.

**New service:**
- `get_endorseable_poses_in_scene(endorser_sheet, endorsee_sheet, scene) → list[tuple[int, Interaction]]` —
  returns (stable-1-based-position, Interaction) pairs visible to the endorser.
  Batches whisper-receiver check to avoid per-row queries.

**Related changes:**
- `CharacterSheet.current_residence` FK to RoomProfile (narrative declaration; mechanical
  trickle fires only when the room has a positive cascade-row LocationValueModifier
  with key_type=RESONANCE matching a claimed resonance)
- `Interaction.pose_kind` CharField - STANDARD / ENTRY / DEPARTURE
- `GainSource` TextChoice - POSE_ENDORSEMENT / SCENE_ENTRY / ROOM_RESIDENCE / OUTFIT_ITEM / STAFF_GRANT

### Soul Tether (Resonance Pivot Spec B)

**Spec:** `docs/architecture/soul-tether.md`

Bond mechanic between two PCs (Sinner + Sineater) that mediates Corruption accrual from
non-Celestial casting. The Sinner's `RELATIONSHIP_CAPSTONE` Thread carries **the Hollow**
(a buffer that absorbs incoming corruption). The Sineater eats sins out of the Hollow
during Sineating actions, which refills the Hollow's capacity.

**New fields on existing models:**
- `Thread.hollow_current` — PositiveIntegerField; the Hollow's current refilled capacity.
  Drained by the redirect handler on Sinner casts; refilled by `resolve_sineating`.
- `CharacterResonance.lifetime_helped` — PositiveIntegerField (monotonic); increments on
  every accepted Sineating unit and every rescue ritual. Drives `CORRUPTION_RESISTANCE`
  passive benefit on the Sineater's Thread.

**New audit models (`models/soul_tether.py`):**
- `Sineating` — Audit row for each Sineating offer/accept/decline cycle. FKs to
  `sinner_sheet`, `sineater_sheet`, `relationship`, `scene` (nullable), `resonance`.
  Fields: `units_offered`, `units_accepted` (0 = declined), `anima_cost`, `fatigue_cost`.
- `SoulTetherRescue` — Audit row for stage-3+ rescue ritual. FKs to `sinner_sheet`,
  `sineater_sheet`, `relationship`, `scene` (nullable), `resonance`, `check_outcome`.
  Fields: `sinner_stage_at_start`, `sinner_stage_at_end`, `severity_reduced`,
  `sineater_strain_taken`.

**New constant / exception surface:**
- `ThreadPullEffect.EffectKind.CORRUPTION_RESISTANCE` — tier-0 passive effect kind for
  Sineater Thread; value derived from `lifetime_helped` at resolution time.
- `SoulTetherRole` TextChoices in `constants.py` (SINNER / SINEATER).
- Exception hierarchy in `exceptions.py`: `SoulTetherError` (base), `AffinityGateError`,
  `NoSoulTetherUnlockError`, `SoulTetherFormationError`, `SineatingValidationError`,
  `RescueValidationError`, `StageAdvanceBonusError`.
- `SOUL_TETHER_FORMED` / `SOUL_TETHER_DISSOLVED` event names in `flows/constants.py`.
  `SOUL_TETHER_DISSOLVED` is emitted by `dissolve_soul_tether` after the bond is torn.

**CharacterSheet integration:**
- `CharacterSheet.get_tether_strain_stage() -> int` — returns the Sineater's current
  Tether Strain stage for the character's active resonance. Used by `request_sineating`
  and `refresh_sineating_pending_offer` to populate `sineater_current_strain_stage` in
  the `SineatingOffer` payload so the Sineater can see their Strain level before deciding.
- `CharacterAnima` and `FatiguePool` are seeded at CG finalization so they exist for all
  finalized characters that Sineating cost-deduction can safely read from on first call.

**Authored content (factories, not migrations):**
- `TetherStrainTemplate` — ConditionTemplate applied to the Sineater at dramatic moments
  (opt-in stage-advance bonus, overflow commits). Only accrued via explicit opt-in.
- `SoulTetherActiveTemplate` — ConditionTemplate installed on the Sinner at formation.
  Carries two reactive trigger M2Ms (soul_tether_redirect, soul_tether_stage_advance_prompt).
- `accept_soul_tether` Ritual — SERVICE-dispatched formation capstone.
- `soul_tether_rescue` Ritual — SERVICE-dispatched stage-3+ rescue ritual.
- `soul_tether_redirect` TriggerDefinition — subscribes to `CORRUPTION_ACCRUING`.
- `soul_tether_stage_advance_prompt` TriggerDefinition — subscribes to
  `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`.

All wired via `wire_soul_tether_content()` in `factories.py`.

**Relationship side changes (`world/relationships/models.py`):**
- `RelationshipCapstone.is_ritual_capstone` — BooleanField (default False); marks capstones
  that gate a Ritual.
- `RelationshipCapstone.ritual` — nullable FK to `magic.Ritual`.

**Services (`services/soul_tether.py`):**
- `accept_soul_tether(sinner_sheet, sineater_sheet, scene, resonance, capstone)` — Formation
  ritual: affinity gate (Sineater must be non-Abyssal; Sinner must be non-Celestial), unlock
  gate (Sinner must have RELATIONSHIP_TRACK ThreadWeavingUnlock), idempotency check, Sinner
  Thread auto-weave (RELATIONSHIP_CAPSTONE), installs `SoulTetherActive` ConditionInstance
  and trigger rows on the Sinner.
- `dissolve_soul_tether(sinner_sheet, sineater_sheet)` — Tears bond: retires tether Threads,
  removes ConditionInstance + triggers, emits `SOUL_TETHER_DISSOLVED` event.
- `get_soul_tether_config() -> SoulTetherConfig` — Lazy-creates the singleton (pk=1).
  All rescue and sineating cost calculations read from this config rather than module
  constants, making them staff-tunable via admin without a code change.
- `request_sineating(sinner_sheet, scene, resonance, units_offered)` — Sinner-initiated offer;
  enforces per-scene cap and hollow-max; fires `PROMPT_PLAYER` to Sineater with
  `SineatingOffer` payload.
- `resolve_sineating(sinner_sheet, sineater_sheet, units_accepted, resonance, scene)` —
  Sineater `@reply` handler: atomically deducts Sineater anima/fatigue, increments
  `hollow_current` + `lifetime_helped`, writes `Sineating` audit row, fires achievement
  stats. Returns `SineatingResult` frozen dataclass.
- `perform_soul_tether_rescue(sineater_sheet, sinner_sheet, resonance, scene)` — Stage-3+
  rescue ritual: performs check roll, applies Strain cost, deducts resonance cost,
  calls `reduce_corruption` to pull severity back, writes `SoulTetherRescue` audit, fires
  achievement stats. Returns `RescueOutcome` frozen dataclass.
- `soul_tether_redirect_handler(*, payload)` — Reactive subscriber on `CORRUPTION_ACCRUING`.
  Drains `hollow_current` to absorb corruption; emits replacement events for overflow;
  cancels original event when fully absorbed.
- `soul_tether_stage_advance_prompt(*, payload)` — Reactive subscriber on
  `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`. Fires `PROMPT_PLAYER` to Sineater with
  `StageAdvanceBonusOffer` so they can opt-in to reservoir/Strain bonus.
- `resolve_stage_advance_prompt(sineater_sheet, sinner_sheet, resonance, commit_units, take_strain)` —
  Sineater `@reply` resolution for stage-advance prompt.

**`CORRUPTION_RESISTANCE` effect resolution** (in `services/corruption.py`):
Passive tier-0 `ThreadPullEffect` rows on Sineater's `RELATIONSHIP_CAPSTONE` Thread are
evaluated in `accrue_corruption` on the Sineater's own casting path. Value derived from
`lifetime_helped` for that resonance; reduces effective accrual before it writes.

**API endpoints (`views.py` + `urls.py`):**
- `POST /api/magic/soul-tether/accept/` — `SoulTetherAcceptView`
- `POST /api/magic/soul-tether/<id>/dissolve/` — `SoulTetherDissolveView`
- `POST /api/magic/soul-tether/<id>/sineat/request/` — `SineatingRequestView`
- `POST /api/magic/soul-tether/<id>/sineat/respond/` — `SineatingRespondView`
- `POST /api/magic/soul-tether/<id>/rescue/` — `SoulTetherRescueView`
- `GET /api/magic/soul-tether/<id>/detail/` — `SoulTetherDetailView`

**Types (`types/soul_tether.py`):**
- `SineatingOffer` — frozen dataclass with `units_offered`, `hollow_current`,
  `hollow_max`, per-unit `anima_cost`, `fatigue_cost`.
- `SineatingResult` — frozen dataclass with accepted units, costs, new `hollow_current`.
- `StageAdvanceBonusOffer` — frozen dataclass; `PROMPT_PLAYER` payload for stage-advance prompt.
- `StageAdvanceBonusResult` — outcome of the Sineater's stage-advance response.
- `RescueOutcome` — frozen dataclass; severity_reduced, stage_before/after, strain_taken.

### Dramatic Moment Tagging (#545 / #1139)

`models/dramatic_moment.py` — Staff-initiated scene moments that grant both resonance
and a renown award:

- `DramaticMomentType` (inherits `RenownAwardConfig`) — staff-authored lookup. Carries
  `label`, `description`, `resonance` (FK — the resonance granted), `resonance_amount`
  (flat units, default 15), and `per_scene_cap` (max awards per character per scene,
  default 1). Inherits `magnitude` / `risk` / `reach` / `archetypes` from
  `RenownAwardConfig` for the simultaneous renown leg.
- `DramaticMomentTag` — per-event record. FKs: `moment_type`, `character_sheet`,
  `scene` (nullable, `SET_NULL` — resilient to scene cleanup), `tagged_by` (AccountDB,
  `PROTECT` for provenance), `interaction` (optional pose anchor; `db_constraint=False`
  because `scenes_interaction` is a partitioned table with a composite PK),
  `interaction_timestamp` (denormalized from `interaction.timestamp` so the composite
  FK is navigable). `tagged_at` is auto-timestamped.

**Service (`services/gain.py`):**

`create_dramatic_moment_tag(*, character_sheet, moment_type, tagged_by, scene, interaction=None) -> DramaticMomentTag`

Validates that the character has claimed `moment_type.resonance` and that the
`per_scene_cap` for this `(moment_type, scene, sheet)` combination has not been
reached. On success, atomically:
1. Creates a `DramaticMomentTag` row (with `interaction_timestamp` denormalized when a
   pose is provided).
2. Calls `grant_resonance(..., source=GainSource.DRAMATIC_MOMENT, dramatic_moment=tag)`.
3. Calls `fire_renown_award` for the character's primary persona (skipped silently if no
   primary persona).

Raises `EndorsementValidationError` (unclaimed resonance) or `DramaticMomentCapExceeded`
(per-scene cap hit) — both carry `user_message` for safe 400 responses.

**REST API (`views.py`, `urls.py`, `serializers.py`):**

- `GET /api/magic/dramatic-moment-types/` — `DramaticMomentTypeViewSet` (read-only, no
  pagination; authenticated). Supplies the tag-picker dropdown in the GM control panel.
- `POST /api/magic/dramatic-moment-tags/` — create a tag; gated by
  `IsSceneGMOrOwnerOrStaff` (scene GMs, scene owners, and staff may tag — not
  restricted to staff-only). Body fields: `character_sheet`, `moment_type`,
  optional `scene`, optional `interaction`. Service errors map to HTTP 400
  with `user_message`. No `DELETE` endpoint — tags are immutable provenance records.
- `GET /api/magic/dramatic-moment-tags/` — list tags; filterable by `character_sheet`
  and `scene`; paginated.

**Django admin (`admin.py`):**

- `DramaticMomentTypeAdmin` — full CRUD for the authored catalog. Fields:
  `label`, `resonance`, `resonance_amount`, `per_scene_cap`, `magnitude`, `risk`.
  Staff author types here; no special approval workflow.
- `DramaticMomentTagAdmin` — read-only (no add/change permissions). All fields are
  readonly for provenance audit. Staff can inspect issued tags but cannot fabricate them.

**Scene/interaction context fields (scenes serializers):**

- `SceneDetailSerializer.viewer_can_gm` (SerializerMethodField, bool) — `True` when
  the requesting user is the scene's GM, owner, or a staff member. The frontend uses
  this flag to show or hide the GM tagging control per pose.
- `InteractionSerializer.dramatic_moment_tags` (SerializerMethodField, list) — tags
  anchored to this interaction (Prefetch `to_attr=cached_dramatic_moment_tags`).
  Drives the badge displayed on the pose in the scene log.
- `SceneParticipationSerializer.dramatic_moment_count` (SerializerMethodField, int) —
  count of tags for this participant in the scene, derived from a `dramatic_moment_counts`
  context dict built at scene-serialization time. Powers per-participant tallies.

**React frontend (`frontend/src/scenes/components/`):**

- Per-pose GM "Tag dramatic moment" control (visible only when `viewer_can_gm`).
- `DramaticMomentTagDialog.tsx` — modal dialog for type selection + confirmation.
- Badge displayed on tagged interactions in the scene log.

### Entry-Flourish Declaration (#1140)

On a **successful Entrance social action**, a poll-able offer is created so the entrant
declares which of their claimed resonances they broadcast. The pick resolves through
`create_entry_flourish` (actor self-grant), scoped to the room's active scene and
idempotent per scene. Mirrors the Audere offer pattern but is a **self-grant** —
not a reaction window (`react_to_window` hard-blocks self-reaction, so the #904
framework was evaluated and rejected for this; peer scene-entry endorsement is
the complementary half of the entrance moment).

**Model (`entry_flourish.py`):**
- `PendingEntryFlourishOffer` — poll-able offer; one per character (UniqueConstraint on
  `character_sheet`); nullable `scene` FK. Re-exported in `world/magic/models/__init__.py`.

**Model (`models/endorsement.py`):**
- `EntryFlourishRecord` — immutable receipt written by `create_entry_flourish`. FK
  `character_sheet`, FK `resonance`, nullable FK `scene`, `granted_amount`. Partial
  UniqueConstraint `(character_sheet, scene) WHERE scene IS NOT NULL` — per-scene
  uniqueness; scene-null grid-RP flourishes are unconstrained.

**Config tuning knob:**
- `ResonanceGainConfig.entry_flourish_grant` (default 10) — amount granted per flourish.

**Services:**
- `maybe_create_entry_flourish_offer(character, scene)` (`entry_flourish.py`) — called on
  Entrance success; skips if already flourished this scene or no claimed resonances.
- `resolve_entry_flourish_offer(offer: PendingEntryFlourishOffer, *, resonance: Resonance) -> EntryFlourishResult`
  (`entry_flourish.py`) — two-phase, mirrors `resolve_audere_offer`.
- `create_entry_flourish(sheet, resonance, *, scene, amount=None)` (`services/gain.py`) —
  checks claimed-resonance, creates `EntryFlourishRecord`, writes
  `ResonanceGrant(source=ENTRY_FLOURISH, entry_flourish=record)`. Skips gracefully on
  duplicate `(sheet, scene)`.

**Action wiring (`actions/definitions/social.py`):**
- `EntranceAction` calls `maybe_create_entry_flourish_offer` on success; gated by
  `ActionTemplate.grants_entry_flourish`. When an offer is created, the actor receives
  a telnet prompt: `"Use |wflourish <resonance>|n to declare your entrance."`
- `ResolveFlourishOfferAction` (key `"resolve_entry_flourish"`) — telnet + web converge
  here; calls `resolve_entry_flourish_offer(offer, resonance=resonance)` and stores the
  result under `ActionResult.data["entry_flourish_result"]`.

**Telnet commands (`commands/social/entrance_flourish.py`):**
- `CmdEnter` — thin telnet wrapper that dispatches `EntranceAction`.
- `CmdFlourish` — thin telnet wrapper that resolves a pending offer via
  `ResolveFlourishOfferAction`.

**REST endpoints (`/api/magic/entry-flourish/`):**
- `GET /api/magic/entry-flourish/pending/` + `GET .../pending/<id>/` —
  `PendingEntryFlourishOfferViewSet` (account-scoped, read-only).
- `POST /api/magic/entry-flourish/respond/` — `EntryFlourishRespondView`; body
  `{offer_id, resonance_id}`; dispatches through `ResolveFlourishOfferAction` (same
  seam as the telnet `flourish` command); picker data reuses `CharacterResonanceViewSet`.

**Exceptions (`exceptions.py`):**
- `EntryFlourishOfferError` (base), `EntryFlourishOfferNotFoundError`,
  `EntryFlourishOfferStaleError` — all carry `user_message` for safe 400 responses.

**Frontend:**
- `EntryFlourishOfferGate` + `EntryFlourishOfferDialog`
  (`frontend/src/magic/components/`) — gate polls `usePendingEntryFlourishOffers`;
  dialog opens once per offer id, lets the player pick a resonance and calls
  `useRespondToEntryFlourish`.
- Mounted in `frontend/src/scenes/pages/SceneDetailPage.tsx` (`isActive` guard).
- Hooks in `frontend/src/magic/queries.ts`: `usePendingEntryFlourishOffers`,
  `useRespondToEntryFlourish`.

**GainSource:** `ENTRY_FLOURISH` in `world/magic/constants.py` (`GainSource` TextChoices).

### Offer handler registry (`commands/offer_registry.py`)

System-initiated prompts (intensity surges, path crossings) are dispatched through
a registry of `OfferHandler` objects keyed by keyword string. Handlers live in
`world/magic/offer_handlers.py` and register in `MagicConfig.ready()`. The telnet
`accept`/`decline` commands route non-numeric first-token args through the registry.
To add a new handler: implement the `OfferHandler` protocol and call
`register_offer_handler()` in `ready()`.

### Audere & Audere Majora (#873, #543)

`audere.py` — Audere, the in-the-moment intensity surge: `AudereThreshold` (global
config), `PendingAudereOffer` (poll-able offer, one per character),
`check_audere_eligibility` (intensity tier + Soulfray stage + engagement),
`offer_audere`/`end_audere` lifecycle, `AbstractPendingOffer` (shared offer base).

`models/renown_config.py` — `RenownAwardConfig`: **abstract base** (SharedMemoryModel)
shared by `DramaticMomentType` and `AudereMajoraThreshold`. Carries four authored
knobs consumed by `fire_renown_award`: `magnitude`, `risk`, `reach` (nullable
override), and `archetypes` (M2M to `PhilosophicalArchetype`). Provides
`as_renown_award_kwargs() -> dict`. When `risk == NONE`, `fire_renown_award` creates
no `LegendEntry` — the invariant that gates deed creation.

`audere_majora.py` — Audere Majora / Crossing the Threshold, the unified tier-crossing
event:
- `AudereMajoraThreshold` — one authored row per boundary level (5/10/15/20).
  Inherits `RenownAwardConfig` (magnitude/risk/reach/archetypes). Additional fields:
  gate thresholds (`minimum_intensity_tier`, `minimum_warp_stage`,
  `requires_active_audere`) + ceremony content + `deed_title` (public, non-spoiler
  CharField; blank → generic composed title). **`vision_text`/`manifestation_text`
  are spoiler-private: authored in the DB only; factories/tests use placeholders;
  never commit real ceremony wording.** `deed_title` is the only ceremony-adjacent
  field that may appear in code and tests.
- `PendingAudereMajoraOffer` — poll-able Crossing offer (AbstractPendingOffer +
  threshold FK; one per character).
- `AudereMajoraCrossing` — irreversible receipt (unique per sheet+threshold;
  `chosen_path`, scene + declaration-interaction links, level_before/after,
  `legend_entry` OneToOneField → `societies.LegendEntry` with
  related_name `audere_majora_crossing`). The receipt is the single source of truth
  and points to the deed it minted; `legend_entry` is null when the threshold has
  `risk == NONE` or when the crossing sheet has no primary persona. Survives
  character death.
- Services: `check_audere_majora_eligibility` (8 gates),
  `eligible_paths_for_threshold` (current path's child paths at the target stage),
  `maybe_create_audere_majora_offer` (cast hook in `services/techniques.py`;
  manifestation EMIT broadcast on creation only), `resolve_audere_majora_offer`
  (two-phase staleness + spend guards + path validation),
  `cross_threshold` (atomic: declaration pose → level write → path history → receipt
  → Majora condition → **`_mint_crossing_deed`**), `end_audere_majora` (encounter
  cleanup calls it alongside `end_audere`).
- `_mint_crossing_deed(crossing)` — called by `cross_threshold` after writing the
  receipt. Resolves the sheet's primary persona, calls `fire_renown_award`
  (full renown event — fame/prestige/legend/society-reputation), records every
  persona present in the scene as `WITNESSED` via `grant_deed_knowledge` +
  `scene_witness_personas` (#916), and links the minted `LegendEntry` back onto
  `crossing.legend_entry`. Deed title/description use `threshold.deed_title` (if
  authored) or a generic public-fact composition; ceremony text is never used.
  No-ops silently if the sheet has no primary persona.
- API: `/api/magic/audere-majora/pending/` + `/respond/`; frontend
  `AudereMajoraOfferGate`/`AudereMajoraOfferDialog` (amber ceremony dialog with path
  choice + declaration composer) mounted in the combat panel.
- `PathIntent` (`world/progression`) — pre-declared next path; the offer serializer
  pre-selects it when eligible.

## Removed Models (deprecated)

The following models have been removed and replaced:
- `Power` - Replaced by `Technique` (player-created abilities)
- `CharacterPower` - Replaced by `CharacterTechnique`
- `AnimaRitualType` - Replaced by freeform stat+skill+resonance system
- `ResonanceAssociation` - Replaced by hierarchical `Facet` model
- `Thread` (legacy 5-axis model), `ThreadType`, `ThreadJournal`,
  `ThreadResonance` - Legacy 5-axis thread family. Replaced by the new
  `Thread` discriminator + typed-FK model and supporting catalogs
  (`ThreadPullCost` / `ThreadXPLockedLevel` / `ThreadPullEffect` /
  `ThreadWeavingUnlock` / `ThreadLevelUnlock` / `CharacterThreadWeavingUnlock` /
  `ThreadWeavingTeachingOffer`). See "Thread System (Resonance Pivot Spec A)"
  above.
- `CharacterResonanceTotal` - Aura recompute now reads `CharacterModifier` rows
  whose target category is `resonance` directly (no denormalized aggregate)

## Design Docs

- `docs/plans/2026-01-20-magic-system-design.md` - original system design
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` - cantrip/technique alignment + spell mechanics
- `docs/plans/2026-03-04-path-cantrip-filtering-design.md` - path-based cantrip filtering design
- `docs/architecture/resonance-threads.md` - Resonance Pivot Spec A (Threads + Currency + Rituals + Mage Scars rename)
- `docs/architecture/resonance-gain.md` - Resonance Pivot Spec C (Endorsements + Room Aura + Residence Trickle)
- `docs/architecture/soul-tether.md` - Resonance Pivot Spec B (Soul Tether bond mechanic)

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are proper models in this app, not ModifierTarget entries
- FKs to affinities/resonances point directly to Affinity/Resonance models (type-safe)
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierTarget)
- Technique has intensity (power) and control (safety/precision) as base stats
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
- Cantrip is a technique template — creates a real Technique at CG finalization
- No healing mechanics — shielding yes, restoration no (counter to tension design)

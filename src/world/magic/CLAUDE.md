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
  via `spend_resonance_for_imbuing` (advances Thread level — also charges a flat
  AP cost, with the Unbound +50% surcharge applying via the same
  `magic_learning_ap_cost` modifier as technique learning, #2467) or
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
- `ANIMA_BANDS` / `anima_band_for(current, maximum)` (`constants.py`, #1446) - Qualitative
  anima vocabulary (PLACEHOLDER labels pending Apostate rewrite) mirroring
  `vitals.constants.WOUND_DESCRIPTIONS`; `CharacterAnimaSerializer.band` surfaces it, shared
  by the web Status tab and the `sheet/status` telnet section

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (M2M to Resonance — the **supported set**: a weave constraint, not the cast-time value; the cast reads the character's GIFT-thread resonance via `gift_resonances_for`, ADR-0052). Carries a `kind` column (`GiftKind`: `MAJOR` = the one CG-chosen gift, `MINOR` = shared/acquirable — species abilities and in-play powers are delivered as Minor Gifts; ADR-0050, #1577)
- **Content pipeline (#2486):** the catalog (`Gift`/`Technique` + grant tables
  `PathGiftGrant`/`TraditionGiftGrant`/`species.SpeciesGiftGrant` + `Technique`'s payload
  rows) is lore-repo exportable via `CONTENT_MODELS` with natural keys —
  `Technique` is keyed `(gift, name)`, now DB-unique per gift
  (`unique_technique_gift_name`), so authoring a duplicate raises
  `DuplicateTechniqueName` (clean 400) instead of an `IntegrityError`. See
  `docs/systems/magic.md`'s "Content pipeline" section for the full model list.
- `TechniqueStyle` - How magic manifests (Manifestation, Subtle, Performance, Prayer, Incantation) with `allowed_paths` M2M
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.)
- `IntensityTier` - Configurable thresholds for power intensity (Minor, Moderate, Major)
- `Technique` - Authored magical abilities with level, style, effect type (created via the budget builder or staff CRUD — see "Technique authoring" below)
- `CharacterGift` - Links characters to known Gifts
- `CharacterTechnique` - Links characters to known Techniques
- `AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` — abstract bases
  (`models/techniques.py`) whose columns are shared by both the committed `Technique*` and the draft
  `TechniqueDraft*` payload rows; each concrete subclass adds only its owner FK.
- `TechniqueDraft` — one-per-`CharacterSheet` in-progress design workbench
  (`related_name="technique_draft"`). Created/returned by `get_or_start_draft`; deleted by
  `discard_draft`. No JSON; every field is a proper column.
- `TechniqueDraftCapabilityGrant` / `TechniqueDraftDamageProfile` / `TechniqueDraftAppliedCondition`
  — payload child rows for `TechniqueDraft`; inherit the abstract bases above.
- `TechniqueRemovedCondition` / `TechniqueDraftRemovedCondition` — dispel/cleanse payload rows
  (#1585). Subclass of `AbstractAppliedCondition` (sibling to `TechniqueAppliedCondition`); adds
  `remove_all_stacks` (bool, default True). The inherited severity/duration/stack knobs are inert
  for removal — `clean()` enforces they stay at defaults. Removal diverges from the apply path by
  authoring `target_kind` + `minimum_success_level` (dispel needs SELF/ALLY targeting the apply
  path hardcodes to ENEMY/1). See ADR-0064.
- `TechniqueBudgetConfig` - Singleton (pk=1) of power-cost-per-unit knobs (intensity, control, payload, restriction refund multiplier). Lazy-created via `get_technique_budget_config()` in `services/technique_builder.py`.
- `TechniqueTierBudget` - Per-tier reference power budget + representative level stamped on techniques authored at that tier. Lazy-created via `get_technique_tier_budget(tier)`.
- `SoulTetherConfig` - Singleton (pk=1) of Soul Tether tuning knobs: sineating anima/fatigue costs per unit, per-scene caps, hollow-max multiplier, rescue strain thresholds, rescue resonance costs, rescue budget bases and multipliers. All fields are integers; multipliers encoded as integer-tenths or integer-hundredths. Lazy-created via `get_soul_tether_config()` in `services/soul_tether.py`.
- `TouchstoneCastConfig` - Singleton (pk=1) of touchstone combat resonance tuning (#2023). `config_scale` (integer-tenths, default 10 = ×1.0) scales the per-tier cast bonus: `resonance_tier.tier_level × config_scale / 10`. Lazy-created via `get_touchstone_cast_config()` in `services/touchstone.py`. The touchstone power-term provider (`touchstone_power_term` in `services/power_terms.py`) scans equipped items for `template.tied_resonance` matches and folds the bonus into `_derive_power`'s TERM stage.

### Technique authoring (budget builder)

`services/technique_builder.py` provides a three-layer authoring stack:

**Unrestricted core** — `build_technique(design, *, creator)` writes a `Technique` + payload rows (`TechniqueCapabilityGrant`, `TechniqueDamageProfile`, `TechniqueAppliedCondition`) + restriction attachments in one `transaction.atomic`. No gating, no character binding. `create_technique(...)` is the extracted low-level row writer shared with the CG starter-gift catalog seed. When `action_template` is omitted (the default), `create_technique` resolves it to the shared **Technique Cast** `ActionTemplate` seeded by `seeds_cast.py` via `get_standalone_cast_template()` — so every technique is castable standalone out of the box. Staff may pass an explicit template FK to override on a per-technique basis.

**Policy layer** — `price_design(design, *, config, budget)` is a pure function that itemizes power cost per dimension and subtracts restriction refunds, returning a `TechniqueCostBreakdown`. It always runs for every author — the breakdown is informational for staff and a gate for players. `AuthoringPolicy` subclasses answer three knobs:
- `StaffPolicy` — `enforced=False`; budget is advisory; any tier allowed.
- `PlayerPolicy` — `enforced=True`; budget is enforced; allowed tiers come from the research-unlock seam (permissive `TODO` today).
- `GMPolicy` — `enforced=True`; calibration is a staff-tunable `TODO` (no grounded GM-level concept yet).

`enforce_policy(design, policy, character)` always prices and returns the breakdown; raises `TechniqueBudgetExceeded(breakdown)` only when `policy.enforced and not within_budget`, or `TechniqueAuthoringNotPermitted` when the tier is disallowed.

**Context wrappers**:
- `author_technique(character, design)` — player path: `PlayerPolicy` (enforced) → build → bind `CharacterTechnique`.
- `author_staff_technique(design, *, creator=None)` — staff path: `StaffPolicy` (advisory) → build; no character binding.

**Draft workbench** (`services/technique_draft.py`, `models/technique_draft.py`):

`TechniqueDraft` is the in-progress design row (one per `CharacterSheet`). Its payload children
inherit the abstract payload bases, so every payload column is identical between draft and committed
rows. Key service functions:
- `get_or_start_draft(character) -> TechniqueDraft` — creates or returns the active draft.
- `discard_draft(character)` — deletes the draft and all child payload rows.
- `set_draft_fields(draft, **fields)` — updates name/description/gift/style/effect_type/level/etc.
- `add_draft_restriction(draft, restriction)` / `remove_draft_restriction(draft, restriction)`
- `add_draft_capability_grant` / `add_draft_damage_profile` / `add_draft_applied_condition`
  and their `remove_*` counterparts — payload row management.
- `draft_to_design(draft) -> TechniqueDesignInput` — validates completeness and converts to the
  design input type; raises `TechniqueDraftIncomplete` on missing required fields.

`validate_design_for_character(design, policy, character)` in `services/technique_builder.py` is
the shared player-facing gift-ownership gate — the single source of truth for the gate. Call it
after `draft_to_design` when finalising from telnet or web. Raises
`GiftNotOwned` if the character doesn't own the design's gift.

Draft-specific exceptions (in `exceptions.py`): `NoActiveTechniqueDraft`,
`TechniqueDraftIncomplete`, `UnknownTechniqueVocab`, `UnknownGift`, `GiftNotOwned`.

**Action seam** — `AuthorTechniqueAction` (`actions/definitions/technique_authoring.py`,
key `"author_technique"`, category `"magic"`) is the single commit seam that both the web view
and the telnet workbench converge on. It calls `draft_to_design` → `validate_design_for_character`
→ the appropriate context wrapper, catching budget/permission/gift/draft exceptions and returning
a failure `ActionResult` whose `message` the web view maps to HTTP 400/403.

**API endpoints** on `TechniqueViewSet` (`/api/magic/techniques/`):
- `POST .../author/` — dispatches `AuthorTechniqueAction.run()` for the player path (HTTP contract
  preserved: 201/400/403). Staff-without-character uses `author_staff_technique()` directly (no
  `CharacterSheet` actor). Returns 201 with `TechniqueSerializer` + breakdown, or 400 with
  breakdown when a player is over-budget.
- `POST .../price/` — dry-run; returns the `TechniqueCostBreakdown` for any author without creating rows.
- Base `create`/`update`/`destroy` are staff-only raw admin CRUD (`IsAdminUser` permission).

**Frontend** — `TechniqueBuilderForm` with `mode: "staff" | "player"`. Staff mode shows the budget
meter informationally without blocking; player mode gates submit on `within_budget`. `usePriceTechnique`
(debounced `POST .../price/`) drives the live budget meter; `useAuthorTechnique` handles submission.

**Telnet workbench** — `CmdTechnique` (`commands/technique.py`, key `"technique"`, lock
`cmd:perm(Builder)` — staff/GM-only; not available to base players). Subcommands:
`draft` (create/show draft), `show` (print current draft), `set <key=value…>` (update fields
in-place), `restrict <name>` / `grant` / `damage` / `condition` (add payload rows),
`price` (dry-run breakdown), `author` (finalize via `AuthorTechniqueAction` with `as_staff=True`,
`StaffPolicy` — no `CharacterTechnique` binding), `discard` (delete draft). Registered in
`commands/default_cmdsets.py`.

**Exposure** — technique authoring is currently staff/GM-only. Player self-service (CG
technique-design step or a magical-research unlock — never on-demand) is a deferred
`needs-design` follow-up; the web `author` endpoint and `PlayerPolicy` seam are already wired.

### Anima Recovery
- `Ritual` (execution_kind=SCENE_ACTION) + `RitualCheckConfig` sidecar - Personalized recovery ritual (stat + skill + resonance + check_type)
- `AnimaRitualPerformance` - Historical record of ritual performances

**Note:** During character creation, the magic stage uses the starter Gift/Technique
catalog pick (see below). Anima rituals are set up post-CG. The player-authored `Ritual` row (SCENE_ACTION)
carries check configuration via its `RitualCheckConfig` sidecar (stat, skill, resonance, check_type).

**Anima/severity budget per outcome tier (#1207):** `anima._budget_for_outcome` reads
`AnimaRitualBudgetAward` (`world/magic/models/soulfray.py`) — a per-`CheckOutcome`-tier
authored row — instead of the old `SoulfrayConfig.ritual_budget_critical_success/_success/
_partial/_failure` fields. Every one of the 5 canonical tiers must have a row; a missing
one raises rather than silently granting 0 anima.

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
  resolves this check type for use by the cast pipeline. `resolve_cast_check_type(character,
  template)` (`services/anima.py`) is the single resolver every cast path calls: it
  returns the personal check when the caster is provisioned, else falls back to
  `template.check_type` (ADR-0096) — standalone casts, combat round casts, clash
  contributions, and battle technique resolution (`world/battles/resolution.py`)
  all go through it, so none of them can silently roll the shared template check
  for a provisioned caster.
- **Anima ritual alignment** — `provision_player_anima_ritual` (`services/anima.py`)
  points the anima ritual's `RitualCheckConfig.check_type` at the same per-character
  check type, so the anima ritual and technique casts always roll the same personal check.
  Use `get_character_anima_ritual(character)` to retrieve the anima ritual row.
- **Graded consequence pool** — a single "Magic: Technique Cast" `ConsequencePool`
  (seeded by `seeds_cast.py`) routes graded outcomes (failure / partial success / success)
  through the shared consequence machinery. No per-technique pool is required.
- **Consequence-pool catalog (#1320)** — a technique's author (web builder or telnet
  `technique set consequence_pool=<id>`; CG finalization does NOT expose this pick,
  #2426) may pick a "flavor" from a curated catalog instead of the shared graded
  pool. The catalog
  is `ConsequencePool.objects.filter(parent=<base pool>)` — single-depth children
  of the base pool seeded by `seeds_cast.ensure_technique_catalog_content()`. Each
  catalog entry has its own `ActionTemplate` (same `check_type`/`pipeline`/
  `target_type` as the shared template — only `consequence_pool` differs) so
  the flavor pick cannot affect the rolled check: **every** cast path (standalone,
  combat, clash, battle technique resolution in `world/battles/resolution.py`)
  resolves the check via `resolve_cast_check_type` (personal check first, template
  fallback — ADR-0096) — as does the combat availability descriptor
  (`actions/player_interface.py`), so the action-picker UI shows the same check
  the resolver rolls — and none of them read
  `technique.action_template.check_type` directly anymore. Resolution:
  `technique_builder.resolve_cast_action_template()`.

Follow-ups deferred to later issues: the optional resonance→aspect mapping. (The
targeting model — targeting validity + AoE + per-technique target constraints +
frontend target picker — was resolved in #1321; see "Targeting/hostility" below.)

**Property-gated targeting precondition (#1793):** `Technique.target_prerequisites`
(M2M to `mechanics.Prerequisite`) lets a technique require a target currently hold a
Property at or above a threshold. Enforced symmetrically in both cast paths: non-combat
(`validate_cast_target`/`resolve_targets`, `services/targeting.py`) and combat
(`resolve_combat_technique`, `world/combat/services.py`). In both, SINGLE/SELF raise
`InvalidCastTarget` pre-flight (SELF checks the caster directly, since a SELF cast
conventionally supplies no explicit target); AREA/FILTERED_GROUP get NO pre-flight
check at all and instead defer entirely to a silent per-target filter downstream
(`resolve_targets` non-combat, `_filter_by_target_prerequisites` combat) — an AoE cast
skips ineligible targets rather than hard-blocking the whole cast (ADR-0045). This is a
precondition layered on the existing target-resolution machinery — it does not build the
still-deferred general targeting model (AoE constraints, frontend target picker) noted above.

`Technique.properties` (M2M to `mechanics.Property`) carries neutral descriptive tags
on the technique itself (e.g. cursed) via `Technique.has_property(name)`; this is
separate from `Character.has_property`, which checks a *character's* Property
attachments (both the primary persona's authored identity tags and runtime
`ObjectProperty` rows, #1793) and backs the `has_property` reactive-trigger DSL op.
`Character.has_capability` is the capability-typed sibling — checks
`get_effective_capability_value(sheet, capability_type) > 0` — and backs the new
`has_capability` DSL op (both in `flows/filters/evaluator.py` /
`typeclasses/characters.py`).

### Dispel / Cleanse (#1585)

A technique carrying `TechniqueRemovedCondition` rows strips matching conditions from the
resolved target on cast. The removal sibling of `apply_technique_conditions` is
`remove_technique_conditions` (`services/condition_application.py`), wired into the same cast
seam — `request_technique_cast` (`world/scenes/cast_services.py`) for standalone and
`CombatTechniqueResolver._apply_conditions` (`world/combat/services.py`, returns
`(applied, removed)`) for combat. No-op when the technique has no `removed_conditions` rows.

Three independent gates per target, evaluated in order: (1) **cast-SL row gate** —
`success_level < row.minimum_success_level` skips the row (mirrors the apply path; a botched cast
removes nothing); (2) **`can_be_dispelled` hard gate** — a condition whose template has
`can_be_dispelled=False` is a no-op (never an error); (3) **opposed cure check** — when the
condition's `cure_check_type` is set, `perform_check(caster, cure_check_type, cure_difficulty)`
is rolled; removal succeeds iff `check_result.success_level > 0`, else resisted (no-op for that
target, cast continues). When `cure_check_type` is null, removal proceeds unconditionally
(uncontested dispel). Delegates to `world.conditions.services.remove_condition`
(`remove_all_stacks` forwarded → partial-stack decrement or full removal; reuses
`CONDITION_REMOVED` emission + deferred-death resolution).

**Targeting/hostility** (`services/hostility.py` + `services/targeting.py`): stripping an ENEMY's
buff is hostile; cleansing an ALLY's debuff resolves ALLY; a self-cleanse resolves SELF. Dispel
is **not** consent-gated — removing a behavior-altering condition (dispelling a charm) is
beneficial, so `removed_conditions` is intentionally NOT added to
`technique_alters_behavior`/`cast_requires_consent`.

**Authoring:** mirrors `applied_conditions` through the budget builder (`RemovedConditionSpec` →
`TechniqueDesignInput.removed_conditions` → `build_technique`; priced at flat
`payload_base_cost`), draft workbench (`add_draft_removed_condition` / `draft_to_design`),
serializer (`_RemovedConditionSpecSerializer`), admin (`TechniqueRemovedConditionInline`), telnet
(`technique dispel add|remove`), and frontend (`RemovedConditionsEditor` in
`TechniqueBuilderForm`). See ADR-0064 for why dispel is a payload row, not an `EffectKind`.

### Technique Acquisition (non-teaching) (#1732)

- `TechniqueGrant` — Authored sidecar (`models/technique_grant.py`) linking a
  `Technique` to an `ItemTemplate` (on-use delivery) or `Ritual` (SERVICE delivery).
  Exactly one vehicle enforced by `clean()` + partial UniqueConstraints.
- `learn_technique(learner, technique, *, source, ap_cost=0, xp_cost=0)` — shared
  commit seam in `services/technique_acquisition.py`. Runs gift-owned → path gate →
  cap → AP spend → mint → announce. Called by `UseItemAction` (item path) and
  `learn_technique_from_ritual` (ritual SERVICE path). `accept_technique_offer`
  delegates its mint step here.
- `can_learn_technique(learner, technique)` — shared path-style gate in
  `services/gift_acquisition.py`. Checks `technique.style.allowed_paths` against
  `current_path_for_character(learner.character)`.
- `GiftAcquisitionConfig.major_gift_ap_multiplier` — staff-tunable AP multiplier
  for MAJOR-gift techniques on the `has_gift` branch of `accept_technique_offer`.
- `GiftAcquisitionConfig.imbue_ap_cost` — staff-tunable flat AP cost per Rite of
  Imbuing (#2467). The Unbound +50% surcharge applies on top via
  `magic_learning_ap_cost_surcharge_percent`. Default 2 (cheaper than the
  technique-learning base of 5).
- `charge_and_learn(learner, technique, *, base_ap_cost, source, gold_cost=0,
  gold_treasury=None, teacher_tenure=None, teacher_banked_ap=0)`
  (`services/gift_acquisition.py`, #2440) — the shared charge+acquire core
  extracted from `accept_technique_offer`: duplicate/path-style gates →
  has-gift/major-gift AP multiplier → implicit gift acquisition → cap check →
  AP spend (+ teacher banked-AP consumption when `teacher_tenure` is set) →
  gold spend (learner purse → `gold_treasury`, when `gold_cost` > 0) → mint +
  announce via `learn_technique`. Two front doors: `accept_technique_offer`
  (player-to-player teaching, `teacher_tenure` set, no gold) and the Academy
  TRAIN offer handler (`world.npc_services.effects.run_train_offer`, AP + gold
  + a Golden Hare, no `teacher_tenure`) — one seam, never a forked acquisition
  path.
- `AccessChangeSource.TECHNIQUE_GRANT` — provenance value for non-teaching
  technique acquisition.
- Ritual SERVICE dispatch (`_dispatch_service` in `actions/definitions/ritual.py`)
  now forwards `ritual=ritual` to the service function, so technique-granting
  rituals can resolve their `TechniqueGrant` row.

### Starter Gift Catalog (CG Technique Picks, #2426; content pipeline #2474)

The pre-#2426 design used a staff-curated `Cantrip` starter-technique-template model
that CG finalization minted into a new `Technique`; that model and its API plumbing
were fully removed in #2426 Task 8. See below for the live mechanism.

The CG magic stage picks a staff-authored catalog `Gift` + `Technique`s directly — no
`Gift`/`Technique` row is minted at CG time; `finalize_magic_data` only *links* the
picks (see `services/cg_catalog.py` above).

**The catalog is content, not seed data (#2474).** `Resonance`, `Gift`, `Technique`
(natural key `(gift, name)`, `unique_technique_gift_name`), `PathGiftGrant`, and
`TraditionGiftGrant` all carry natural keys and ride the ordinary content pipeline —
`CONTENT_MODELS` (`core_management/content_export.py`) → arx2-lore fixtures →
`core_management.content_fixtures.load_world_content()`, called from
`world.seeds.database.seed_dev_database()` before any `CLUSTER_SEEDERS` entry runs.
The formerly in-repo `seed_starter_gift_catalog()` (`world/seeds/game_content/
magic.py`, called by `seed_magic_dev()`) — which authored 5 MAJOR `Gift` rows (one
per `TechniqueStyle`/PROSPECT-`Path` pair), 25 `Technique` rows, `PathGiftGrant`
per (path, gift), and the "Unbound" `Tradition` + its `TraditionGiftGrant` rows — is
retired; that shape now lives as lore-repo fixture content. `MagicContent
.create_starter_gift_catalog()` (same module) is the test-only factory-built
stand-in for suites that need an equivalent-shaped catalog without a real
content-repo checkout (see `world/seeds/tests/content_stub.py`'s `stub_content_root()`
for the enriched fixture-backed alternative). A fresh dev database now requires
`CONTENT_REPO_PATH` — `seed_dev_database()` raises `ContentError` if it's unset or
missing, before seeding anything (ADR-0142).

### Signature Motif Bonus (#1582 — ADR-0072)

A character may *sign* one of their TECHNIQUE-kind Threads by attaching a
`SignatureMotifBonus` (`models/signature.py`) — a staff-authored, Motif-gated ADDITIVE
bonus. It is NOT a `TechniqueVariant`, does NOT inherit `AbstractSpecializedVariant`, and
does NOT participate in `execute_crossing_ceremonies` (the crossing ceremony). Invariant: this
boundary must be preserved.

**Crossing gate (#1988):** signature selection requires `thread.level >= 3` (the first
PathStage crossing). `SignatureMotifBonus.min_crossing_level` (default 3, display-level
scale) gates which bonuses unlock at which thresholds — staff author higher-value bonuses
with `min_crossing_level=6` (or 11, 16, 21). `available_signature_bonuses` accepts an
optional `thread=` to filter by crossing level + resonance match. When a bonus with a
`discovery_achievement` is selected, `set_signature_bonus` fires `execute_ceremony_beat`
(gamewide first-ever or personal narrative). The `TechniqueCrossingHandler` fires a
narrative-only "you may now sign" beat at level 3; higher crossings produce no beat.

- **Catalog model:** `SignatureMotifBonus` (inherits `DiscoverableContent`) — `name`,
  `narrative_snippet`, `required_facet` FK (Facet, nullable), `required_resonance` FK
  (Resonance, nullable), `flat_intensity_delta`, `min_crossing_level` (default 3),
  `discovery_achievement` (nullable FK → `Achievement`, from `DiscoverableContent`).
  At least one gate required (`clean()`). AND semantics.
- **Payload child rows:** `SignatureMotifBonusCapabilityGrant` /
  `SignatureMotifBonusDamageProfile` / `SignatureMotifBonusAppliedCondition` — inherit the
  shared `Abstract*` bases from `models/techniques.py`.
- **Thread FK:** `Thread.signature_bonus` (nullable FK, TECHNIQUE-kind only — enforced by
  `clean()` + DB `CheckConstraint("thread_signature_bonus_technique_only")`). Migrations
  0066 + 0067.
- **Selection service** (`services/signature.py`): `available_signature_bonuses`,
  `set_signature_bonus`, `clear_signature_bonus`, `signature_bonus_for`.
- **Cast wiring** (`services/signature_effects.py`): `signature_intensity_delta` (folds
  into `use_technique(power_intensity_bonus=…)`) + `apply_signature_bonus_conditions`
  (uses shared `apply_technique_conditions` seam via `applied_condition_rows=` param added
  in #1582). Both cast paths (non-combat + combat) wired.
- **Consent (ADR-0024):** because a signature bonus lands its conditions on the resolved
  target, `technique_alters_behavior` / `cast_requires_consent`
  (`services/targeting.py`) take an optional `caster=` and fold in the caster's active
  signature bonus's `cached_condition_applications`. A benign technique signed with a
  bonus carrying a behavior-altering condition is consent-gated exactly as if the
  technique itself carried it; a non-behavior-altering signature condition (e.g.
  Entangled) stays consent-free. The non-combat cast routes (`world/scenes/cast_services.py`)
  pass `caster=initiator_persona.character_sheet.character` at all three consent gates.
- **Combat damage seam (#1728)** (`services/signature_effects.py`):
  `signature_damage_profiles(character, technique)` returns the signed bonus's
  `cached_damage_profiles` (or `[]` if unsigned); `CombatTechniqueResolver._apply_damage`
  (`world/combat/services.py`) appends these to the technique's own profiles before
  resolving damage — the bonus's authored damage now lands in combat.
- **Non-combat narration** (`narration.py`): `signature_clause(snippet)` builds the
  em-dash cosmetic line; folded into `render_cast_outcome_narration`.
- **Combat narration (#1728)**: `resolve_signature_snippet(character, technique)`
  (`services/signature_effects.py`) resolves the cosmetic clause (preferring
  `bonus.narrative_snippet`, falling back to the first Motif facet name), shared by the
  non-combat cast pose and the combat path — `render_action_outcome_narration` +
  `_record_and_broadcast_pc_action` (`world/combat/services.py`) now surface it.
- **Actions** (`actions/definitions/signature.py`): `SignatureSetAction` (key
  `"signature_set"`), `SignatureClearAction` (key `"signature_clear"`),
  `SignatureListAction` (key `"signature_list"`).
- **Telnet:** `CmdSignature` (`commands/signature.py`, key `"signature"`) — namespaced
  subverbs (`set`/`clear`/`list`) to avoid bare-key collisions.
- **Web (#1728):** `SignatureViewSet` (`views_signature.py`) dispatches the same
  Actions via the shared `PuppetActorMixin` (`views_actor.py`, also used by
  `SanctumViewSet`). Routes (`urls.py`, basename `signature`): `GET
  /api/magic/signatures/`, `POST /api/magic/signatures/set/`, `POST
  /api/magic/signatures/clear/`.
- **Admin:** `SignatureMotifBonusAdmin` with inlines for the three payload child models;
  each inline's `help_text` flags its wiring status (capability grants are inert — no
  cast seam yet).
- **Deferred (fast-follow):** the capability-grant cast seam — no technique/signature
  capability-grant cast seam exists anywhere yet, so `SignatureMotifBonusCapabilityGrant`
  rows remain inert.

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

**Audacity axis (#2029):** each matched binding's quality contribution is additionally
scaled by `world.items.services.styles.audacity_multiplier_for(binding.style)` before being
aggregated — a daring `Style` (higher `StyleAudacity` tier) contributes more coherence than
a restrained one wearing identically-tiered items. The multiplier itself comes from the
staff-tunable `items.AudacityTuning` singleton (defaults 0.75/1.00/1.35/1.75 for
UNDERSTATED/EXPRESSIVE/BOLD/OUTRAGEOUS). The peer style-presentation endorsement grant
(`create_style_presentation_endorsement`, `world/magic/services/gain.py`) applies the same
multiplier to `cfg.style_presentation_grant`, keyed on the *highest*-audacity worn style
that matches the endorsed resonance binding (an endorsee wearing multiple matching styles
is rewarded for the boldest one, not the first one found).

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

**Admin authoring surface (still present, no longer the only path):** Standalone
`MotifResonanceAdmin` (in `world/magic/admin.py`) with a `MotifResonanceStyleInline`
for the style bindings; `ItemStyle` inline on `ItemInstance`.

**Player-facing style-binding surface (#2030):** binding a `Style` to a claimed
resonance is now a normal player action, not an admin-only edit — telnet, web, and
admin all converge on the same service layer.

- **Service** (`services/motif_style.py`): `bind_motif_style(sheet, style, resonance)`
  (lazy-creates `Motif`/`MotifResonance` if absent, replace semantics — rebinding a
  style already bound elsewhere moves it; cap enforcement delegates to
  `MotifResonanceLink.clean()`, not reinvented), `unbind_motif_style(sheet, style)`,
  `motif_style_bindings(sheet)`. Exceptions: `StyleResonanceUnclaimed`,
  `StyleBindingCapExceeded`, `StyleNotBound` (`exceptions.py`).
- **Actions** (`actions/definitions/motif_style.py`, all REGISTRY, `category="magic"`,
  `target_type=SELF`): `BindMotifStyleAction` (key `"bind_motif_style"`),
  `UnbindMotifStyleAction` (`"unbind_motif_style"`), `ListMotifStylesAction`
  (`"list_motif_styles"`).
- **Telnet** (`commands/motif.py`, `CmdMotif`, key `"motif"`): namespaced subverbs —
  bare `motif` / `motif list` shows bindings, `motif bindstyle <style>=<resonance>`,
  `motif unbindstyle <style>` — mirroring `CmdSignature`/`CmdSanctum`'s namespacing to
  avoid bare-key collisions.
- **Web:** `MotifStyleViewSet` (`views_motif_style.py`, routes under
  `/api/magic/motif-styles/`) — `list`/`bind`/`unbind` dispatch the three Actions above.
  **Character scoping:** an `X-Character-ID` header is resolved via
  `web.api.mixins.CharacterContextMixin` (validated as owned by the requesting account)
  ahead of the caller's active puppet — the same header/ownership contract
  `PathIntentViewSet`/`CharacterGoalViewSet` use. This lets a player view/act on a
  specific owned character's bindings rather than always defaulting to whichever
  character they currently puppet; a header naming an unowned character 404s rather
  than silently falling back to the puppet. No header at all preserves the original
  puppet-only resolution. The Style catalog itself (for the bind picker) is a separate
  read-only endpoint, `StyleViewSet` at `/api/items/styles/` (`world/items/views.py`).
- **Frontend:** `MotifStylePanel` (`frontend/src/magic/components/`), mounted in the
  Spellbook tab below the read-only Motif card — see `frontend/src/magic/CLAUDE.md`
  for the wire contract.
- **Not built here:** the character-creation-time facet-binding flow floated in the
  original spec was ruled out against code (no CG magic-stage hook exists for it) —
  binding happens post-CG only, same as before.

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
  enforce payload/effect_kind shape. **Relationship pull content (#2021):**
  `ensure_relationship_pull_content()` seeds survivability-skewed rows for
  `RELATIONSHIP_TRACK` (one 4-tier chain per canonical resonance: Light/Sanctity/
  Radiance/Dissolution). Tier 0: VITAL_BONUS(DAMAGE_TAKEN_REDUCTION). Tier 1:
  VITAL_BONUS(DEATH_SAVE). Tier 2: RESISTANCE (all damage types). Tier 3:
  VITAL_BONUS(KNOCKOUT_RESIST). `apply_target_modulation` now handles
  `RELATIONSHIP_CAPSTONE` in addition to `RELATIONSHIP_TRACK` —
  `relationship_bond_modulation` generalized via `_thread_relationship_target`
  to resolve the threaded person from either FK.
- `RelationshipBondPullTuning` - Singleton (pk=1, `get_relationship_bond_pull_tuning()`)
  tuning surface for `relationship_bond_modulation` (`world/magic/services/
  pull_modulation_relationship.py`, #1849, ADR-0092), the RELATIONSHIP_TRACK sibling of
  Court's `court_regard_modulation`. Base term is sign-blind (keyed on the owner's own
  `CharacterRelationship.developed_absolute_value` bond to the thread's threaded person);
  two additive valence-aware terms (#2034, ADR-0110) sit on top, each with its own
  soft-cap columns on the same singleton: **fraught** (`fraught_coefficient/_cap/
  _half_saturation`, keyed on `min` of `CharacterRelationship.developed_signed_sums` —
  rewards a bond invested in both positive AND negative tracks at once) and **devotion**
  (`devotion_threshold/_coefficient/_cap/_half_saturation`, keyed on
  `max(0, developed_absolute_value - devotion_threshold)` — rewards raw depth past a
  threshold, no ritual/ceremony gate). All three terms reuse `_soft_cap`
  (`world/magic/services/threads.py`); see docs/systems/magic.md's "Relationship Bond
  Pull Modulation" section for the full formulas.
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
- `ThreadCrossingThreshold` - Authored gate at thread-level PathStage crossing
  levels (3, 6, 11, 16, 21). Keyed on `(target_kind, level)` so a level-3 GIFT
  crossing can require different things than a level-3 COVENANT_ROLE crossing.
  Requirements attach via the polymorphic `thread_crossing_threshold` FK on
  `AbstractUnlockRequirement` (the generalized base formerly
  `AbstractClassLevelRequirement`). Possession-only — items are never consumed
  (#1885, ADR-0090). Fail-open: no row for `(target_kind, level)` → no gate.
  The imbuing loop (`spend_resonance_for_imbuing`) checks for a threshold
  before advancing to a crossing level; if requirements are unmet, it sets
  `blocked_by="CROSSING_REQUIREMENT"` and stops. `is_crossing_level(level)`
  in `world/classes/services.py` is the single source of truth for crossing
  detection.
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
  `target_gift`, `target_mantle`, `target_sanctum_details`. Fields: `owner` (FK CharacterSheet), `resonance`
  (FK Resonance), `name`, `description`, `developed_points`, `level`, timestamps,
  `retired_at` (soft-retire), `slot_kind` (required for SANCTUM threads —
  `SanctumSlotKind`: PERSONAL_OWN / COVENANT / HELPER),
  `signature_bonus` (nullable FK → `SignatureMotifBonus`, PROTECT — only settable on
  TECHNIQUE-kind threads; enforced by `clean()` + DB CheckConstraint
  `"thread_signature_bonus_technique_only"`; #1582 ADR-0072).
  All typed FKs use `on_delete=PROTECT`. Three layers of integrity: `clean()`, per-kind
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
  threads, `depth(t) = thread_level_multiplier(thread.level)` (#1718 — `Decimal(level // 10)`
  unchanged for level ≥ 10, `Decimal(1)` at level 0, a linear ramp from 0.1 to 1.0 for
  levels 1-9), and
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

**Damage-type RESISTANCE pull-effect (#1580):** distinct from the damage-type-agnostic DR
above. `EffectKind.RESISTANCE` (+ `resistance_amount`, `resistance_damage_type` FK; null =
all types) is the species-gift thread's mitigation that offsets the species drawback's
negative `ConditionResistanceModifier` (a vulnerability). `gift_thread_resistance(character,
damage_type) -> int` (services/threads.py) returns the POSITIVE total — passive tier-0
(flat `resistance_amount`, gated by `min_thread_level`, via
`CharacterThreadHandler.passive_damage_type_resistance`) plus active paid-pull snapshots
(`scaled_value = resistance_amount × level_multiplier`, via
`CharacterCombatPullHandler.active_pull_resistance`). It is summed with
`character.conditions.resistance_modifier(damage_type)` into the SAME clamped subtraction in
`apply_damage_to_participant` (combat) — the one seam where the drawback vulnerability is
read — so drawback and gift resistance net. GIFT threads are pullable (added to
`_ALWAYS_IN_ACTION_KINDS`: a species gift is intrinsic, always in-action). The DoT/trap seams
apply neither condition resistance nor this gift resistance, so they stay byte-identical.

**Combat-side models (live in `world/combat`, not magic):**
- `CombatPull` - Per-(participant, round) commit envelope for a thread pull.
  Unique per (participant, round_number). M2M to Thread for the threads
  pulled; `resonance_spent` / `anima_spent` for audit. Committed via
  `world/combat/pull_helpers.commit_combat_pull` (not called directly).
- `CombatPullResolvedEffect` - Frozen snapshot of one resolved effect from
  a pull. Captures `kind`, `authored_value`, `level_multiplier`, `scaled_value`,
  `vital_target`, `resistance_damage_type` (RESISTANCE only; null = all types, #1580),
  `source_thread`, `source_thread_level`, `source_tier`,
  `granted_capability`, `narrative_snippet`. Cascades from CombatPull;
  edits to authoring or Thread.level mid-round cannot retroactively alter
  what a committed pull granted.

**Note:** Affinity and Resonance are proper domain models in this app, each with an
optional OneToOne FK back to ModifierTarget for modifier system integration.

### Specialization Engine (ADR-0055 — #1578)

A character's specialized techniques and capabilities are resolved by combining an
entity they hold — a **Gift**, **Path**, or **Covenant Role** — with their **resonance**
(and, where a thread is woven, that thread's level) through **one shared specialization
primitive**, not per-entity bespoke logic. The specialized form is **derived on read**
(ADR-0014): a resonance change instantly re-specializes every affected technique with no
regeneration step.

- `AbstractSpecializedVariant` — shared abstract base (SharedMemoryModel), the "one
  specialization engine." Carries the `matching_variant` selection predicate (highest
  `unlock_thread_level ≤ thread level` at the thread's resonance), the
  `newly_crossed_variants` discovery query, and the `discovery_narrative(is_first)`
  ceremony contract (`is_first=True` → gamewide recipients; `is_first=False` → `[]`,
  ceremony appends `[thread.owner]`).
- `TechniqueVariant` — concrete subclass. A resonance-specialized form of a parent
  `Technique` (`parent_technique` self-FK, `related_name="variants"`). Fields:
  `resonance`, `unlock_thread_level` (≥3 = variant), `name_override`,
  `intensity_delta`, `control_delta`, `discovery_achievement`, `codex_entry`. Unique per
  `(parent_technique, resonance, unlock_thread_level)`.
- `CovenantRole` — refactored to inherit `AbstractSpecializedVariant` (schema no-op;
  `parent_role` with `related_name="sub_roles"` is the variant parent).

**Resolver — `resolve_specialized_variant(*, entity, character)`**
(`world/magic/specialization/services.py`): the single specialization resolver.
`Technique` → `_ResolvedTechnique` value object (wraps parent + matching variant,
exposing `name`/`intensity`/`control` with deltas; raw parent `Technique` when no variant
matches). `CovenantRole` → the matching sub-role variant. Both paths read the active
thread through the cached `character.threads` handler (the same cached queryset the
passive bonuses read), never a fresh `Thread.objects.filter()`; a character with no
`CharacterSheet` degrades gracefully (returns the parent entity / supported set). The
GIFT-thread write-paths (`provision_latent_gift_thread`, `_weave_gift_thread`) call
`character.threads.invalidate()` after mutation, mirroring the covenant-role
invalidation contract. `_ResolvedTechnique`'s payload accessors
(`damage_profiles`/`capability_grants`/`condition_applications`) read their source's
single `cached_<payload>` list (on `Technique`/`TechniqueVariant`) rather than issuing a
`.exists()` + `.all()` pair. `resolve_effective_role` is now a one-line shim over this
resolver; no parallel specialization systems (ADR-0016).

**Crossing ceremony — `execute_crossing_ceremonies(*, thread, starting_level, new_level)`**
(`world/magic/crossing/ceremony.py`, ADR-0094): dispatches on `thread.target_kind` via a handler
registry so every `TargetKind` gets a ceremony at PathStage crossings (3, 6, 11, 16, 21).
GIFT/COVENANT_ROLE handlers wrap the existing variant-discovery logic
(`AbstractSpecializedVariant.newly_crossed_variants` → achievement + codex + narrative). The
other kinds use the `_CrossingChoiceHandler` base (player-choice buffs from the
`CrossingOption` catalog) or the `TechniqueCrossingHandler` (narrative-only beat). A shared
`execute_ceremony_beat` helper lets non-variant kinds fire the same beat without an
`AbstractSpecializedVariant`. Called from `spend_resonance_for_imbuing` on every thread advance;
also standalone-callable. (`world/covenants/discovery.py` re-exports it as
`fire_variant_discoveries` for backwards compatibility.)

**GIFT thread substrate:**
- `TargetKind.GIFT` + `Thread.target_gift` FK (PROTECT) — a thread anchored to a Gift. One
  active GIFT thread per `(owner, gift)` for now (multi-resonance chooser deferred).
- `provision_latent_gift_thread(sheet, gift, *, resonance)` — idempotent level-0 GIFT
  thread at CG finalization (`finalize_magic_data`), write-once on resonance. The
  resonance is chosen at the provisioning call (a frontend CG picker is deferred;
  the E2E test passes `resonance=` directly).
- `weave_thread(target_kind=GIFT)` — commits/chooses a resonance onto the existing latent
  thread rather than creating a new one (validates the resonance is in the gift's
  supported set, else `UnsupportedGiftResonanceError`, caught by `WeaveThreadAction`).
- `gift_resonances_for(character, gift) -> list[Resonance]` — the derive-on-read seam
  replacing `technique.gift.resonances.all()` at the four cast sites (`power_terms`,
  `techniques` ×2, `resonance_environment` ×2). Reads the active GIFT thread through the
  cached `character.threads` handler; returns `[thread.resonance]`, falling back to
  `gift.cached_resonances` (the authored supported set) when no thread or no sheet.
- `Gift.resonances` is repurposed to the **supported set** (weave constraint, not the
  cast-time value) per ADR-0052.

**GIFT anchor cap (#1580):** `compute_anchor_cap` now handles `TargetKind.GIFT`:
`_current_path_stage(thread.owner) × ANCHOR_CAP_GIFT_PER_STAGE` (=10). GIFT threads are
always in-action (`_ALWAYS_IN_ACTION_KINDS`; a species gift is intrinsic). The frontend CG
resonance picker remains a needs-design follow-up. Proven end-to-end by
`world/magic/tests/integration/test_gift_specialization_e2e.py` (#1578) and
`world/magic/tests/integration/test_species_gift_e2e.py` (#1580).
- **Species gift provisioning** — `SpeciesGiftGrant` (`world/species/models.py`; natural key
  `(species, gift)`) is the through-model linking a species to MINOR Gifts with an optional
  `drawback_condition` FK. `provision_species_gifts(sheet, *, resonance=None)`
  (`world/species/services.py`) is called from `finalize_magic_data` after the Major-gift
  block; mints the MINOR `CharacterGift`, calls `provision_latent_gift_thread`, applies any
  drawback idempotently. See ADR-0071.
- **Gift-specific pull-effect lookup** — `get_pull_effects_for_thread(thread, **filters)`
  (`world/magic/services/pull_effects.py`): for `TargetKind.GIFT` threads, tries rows where
  `target_gift == thread.target_gift` first, falls back to `target_gift IS NULL`; all other
  kinds get only `target_gift IS NULL` rows.

**Path-crossing grant — the (Gift × Path) base-technique-set leg (#1579, ADR-0055):**
#1578 built the *resonance* leg (how a known technique manifests); #1579 builds the
*(Gift × Path)* leg as an **acquisition** (which techniques you get):

- `PathGiftGrant` (`models/grants.py`, the `PathRitualGrant` through-model shape) authors,
  per `(path, gift)`, a curated `starter_techniques` M2M subset of *that gift's* techniques.
  The same authored Gift grants a different set per path (a warrior-line and a spy-line path
  both grant Pyromancy, but different techniques from it). `clean()` rejects a starter
  technique not belonging to the grant's gift; unique per `(path, gift)`.
- `grant_path_magic(sheet, path)` (`services/path_magic.py`, returns `PathMagicGrantResult`)
  mints, idempotently, `CharacterGift` + the latent GIFT thread (reusing
  `provision_latent_gift_thread`) + `CharacterTechnique` rows for the path's `PathGiftGrant`
  sets, then announces via `announce_access_change` (`AccessChangeSource.PATH_ADVANCEMENT`).
  Resonance for the latent thread = a claimed resonance in the gift's supported set, else the
  gift's first supported resonance (the player commits the real choice later via the Rite of
  Weaving). XP/advancement *gates* the crossing (ADR-0053); the grant is a consequence of path
  membership (ADR-0050), not an XP purchase.
- **Hook:** `cross_threshold` (`audere_majora.py`) calls `grant_path_magic(sheet, chosen_path)`
  right after writing `CharacterPathHistory` — so *which* levels grant is pure authored data
  (`AudereMajoraThreshold` rows). A POTENTIAL (level-3) "pre-crossing" reuses the identical
  machinery; its lesser-ceremony wording is authored on the threshold row.
- Proven end-to-end by `world/magic/tests/integration/test_path_crossing_grant_e2e.py`.

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
- `StylePresentationEndorsementViewSet` - POST /api/magic/style-presentation-endorsements/ +
  GET detail (create + retrieve only; immutable, no delete/settlement). Frontend caller
  (#2031): `EndorsementControl` (`kind='style'`, `frontend/src/scenes/components/`), mounted
  in `PoseUnit` alongside the pose/entry kinds. Endorsed-✓ has no persisted per-viewer flag on
  the `Interaction` payload (unlike entry's `entry_endorsed_by_me`), so the control derives it
  from the create-mutation's own `isSuccess` for the session.
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

**Residence declaration + room aura tagging, live end-to-end (#2036):** the daily
residence-trickle gate above was mechanically inert until #2036 wired every write path —
declaring a residence, tagging a room's aura, and reaching both without a manual step at CG.

- **Declare→tag→tick loop:** a player declares a residence via `SetPrimaryHomeAction`
  (`world.locations.services.set_primary_home` — telnet `room/home` / `home/set`, web "Set as
  Home"), which writes `CharacterSheet.current_residence` (via `set_residence` in this file)
  alongside Evennia `home`, and accepts org-derived owner/tenant standing (not only a direct
  `LocationTenancy` row) by minting a personal tenancy first — so a resident of a shared
  family/org/Academy-granted room can still declare their own home. A tenant or owner then tags
  the room's aura via `tag_room_resonance`/`untag_room_resonance` (telnet `room/aura <resonance>`
  / `room/aura clear <resonance>`, web `RoomAuraPicker`; gated by the owner-or-tenant
  `IsRoomTenantPrerequisite`, tagging additionally requires the caller has claimed that
  resonance). `residence_trickle_tick()` then grants resonance daily for the intersection of
  (aura-tagged resonances on `current_residence`) ∩ (the sheet's claimed resonances) —
  `get_residence_resonances()` above. `end_tenancy()` clears `current_residence` when the ended
  tenancy was the declared residence — a character shouldn't keep trickling from a room they no
  longer have standing in.
- **Zero-manual-step CG on-ramp:** `StartingArea.grants_residence_tenancy` (BooleanField, default
  True) — an authored per-area toggle — drives `_grant_cg_residence_tenancy()`
  (`world/character_creation/services.py`, called from `finalize_character`): grants a
  `LocationTenancy` at the starting room for areas that author it, which auto-defaults both
  Evennia `home` and `current_residence` via `maybe_default_residence()`. A new character can
  reach the trickle gate with zero manual player action (the "Academy auto-residence" story).
- **Intentional emergent synergy — sanctum Homecoming satisfies the same gate:** the Ritual of
  Homecoming (`perform_homecoming_ritual` → `apply_homecoming_gain`, `services/sanctum_rituals.py`
  / `services/sanctum_lvm.py`) grows a Sanctum's consecrated resonance by writing/incrementing a
  `LocationValueModifier(key_type=RESONANCE, resonance=sanctum.resonance_type,
  room_profile=sanctum's room)` row — the exact same row shape `tag_room_resonance` writes, just
  under a different `source` tag. `get_residence_resonances()` doesn't filter on `source`, so a
  character whose `current_residence` is a Sanctum room, with a claimed resonance matching the
  Sanctum's consecrated type, trickles daily for free as a side effect of ordinary Homecoming
  ritual growth — no extra wiring needed, and no code should special-case it.

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

All wired via `wire_soul_tether_content()` in `factories.py`, which `seed_magic_dev()` calls
(#2027) so this content exists in a real deploy, not only under test setup.
`seed_relationship_track_thread_unlock()` (`world/seeds/game_content/magic.py`) seeds the
paired RELATIONSHIP_TRACK `ThreadWeavingUnlock` (+ canonical "Devotion" `RelationshipTrack`)
that `accept_soul_tether`'s `_validate_unlock` gates on — `ThreadWeavingUnlock.unlock_track`
is a required FK and no `RelationshipTrack` catalog exists yet in production content, so this
seed also authors the one canonical track needed to make Soul Tether formation reachable.

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

### Covenant Lifecycle Content (#2114)

The full covenant lifecycle — formation, induction, banner-call rise, mentor bonding,
the mid-battle oath rite, and generic-org induction — is built session machinery
(`world.covenants.services` / `world.societies.membership_services`), but every
`Ritual` row a player would `ritual draft "<name>"` to trigger it previously existed
only in test factories. `wire_covenant_lifecycle_rituals()` in `factories.py`, which
`seed_magic_dev()` calls (#2114) right after `wire_soul_tether_content()`, seeds:

- **"Covenant Formation"** — `create_covenant_via_session` (DURANCE + BATTLE only;
  COURT formation is intentionally out of scope, per ADR-0057)
- **"Covenant Induction"** — `induct_member_via_session`
- **"Call the Banners"** — `rise_battle_covenant_via_session`
- **"Mentor's Vow"** — `establish_mentor_bond_via_session`
- **"Renew the Oath"** — `perform_covenant_rite`, seeded via the existing
  `wire_covenant_rite_content()` (`world.covenants.factories`) rather than the bare
  `RenewTheOathRitualFactory()` — `perform_covenant_rite` reads
  `session.ritual.covenant_rite`, a required `CovenantRite` sidecar the bare Ritual
  factory does not create, so the bare factory alone would seed a Ritual that crashes
  on fire. `wire_covenant_rite_content()` creates the Ritual + `CovenantRite` sidecar +
  role/level-band stat packages together.
- **"Organization Induction"** — `induct_organization_member_via_session`
  (`world.societies.membership_services`)

Also resets the `MentorBondConfig` singleton (pk=1) to its authored defaults via
`seed_mentor_bond_defaults()` — unlike the Ritual rows above (which preserve staff
edits via `django_get_or_create`), this is a pre-launch tuning-knob reset by design
(`update_or_create`), same treatment as other authored-defaults singletons.

Like Soul Tether, this content previously existed only under test setup — without it,
no player could ever found/join/grow a covenant, revive a dormant war covenant, form a
mentor bond, fire the mid-battle oath rite, or join an ordinary organization through
play; `covenant`/`org` (telnet)/REST could only manage state staff planted by hand.

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

**Telnet (#2227):**

- `moment tag <character>=<type>` — direct GM tagging from telnet; thin command
  calling `create_dramatic_moment_tag` directly (the same service the web serializer
  calls). Target resolved by name (`caller.search(global_search=True)`), type by
  `label__iexact`. GM-gated via `_account_can_gm_scene` on the caller's active scene.
- `moment tag list` — lists available `DramaticMomentType` rows (label + resonance +
  amount), same GM gate.

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

#### Dramatic Moment Suggestion — the technique-entrance recognition bridge (#2183)

A qualifying **Technique Entrance** (see "Technique Entrance" below) does not auto-tag a
Dramatic Moment — it surfaces a `DramaticMomentSuggestion` a GM later confirms or dismisses.
Recognition stays a human-adjudicated nudge, never a mechanical auto-grant (ADR-0113).

- `DramaticMomentType.suggest_on_technique_entrance` (bool) / `.suggestion_min_success_level`
  (`PositiveSmallIntegerField`) — opts a moment type into the bridge and sets the cast
  success-level floor (`>=`) that must be cleared.
- `DramaticMomentSuggestion` (`models/dramatic_moment.py`) — FKs `moment_type` (PROTECT),
  `character_sheet` (CASCADE), `scene` (nullable/SET_NULL), `interaction` (nullable/SET_NULL,
  `db_constraint=False` — the entrance pose), `interaction_timestamp` (denormalized).
  Fields: `success_level`, `status` (`SuggestionStatus`: PENDING/CONFIRMED/DISMISSED),
  `resolved_by` (AccountDB, PROTECT), `confirmed_tag` (OneToOne → `DramaticMomentTag`, the
  tag minted on confirmation). Unique per `(moment_type, character_sheet, scene)` while
  PENDING.
- **Services (`services/gain.py`):** `maybe_suggest_dramatic_moments(*, character_sheet,
  scene, success_level, interaction=None) -> list[DramaticMomentSuggestion]` — scans
  flagged `DramaticMomentType` rows meeting the success-level floor, skips unclaimed
  resonance / an already-spent `per_scene_cap`, `get_or_create`s idempotently.
  `resolve_dramatic_moment_suggestion(suggestion, *, resolver, confirm)` — confirm mints a
  real `DramaticMomentTag` via `create_dramatic_moment_tag`; dismiss closes it out with no
  reward. Raises `DramaticMomentSuggestionAlreadyResolved` on a non-PENDING suggestion.
- **Actions (`actions/definitions/dramatic_moments.py`):**
  `ConfirmDramaticMomentSuggestionAction` (key `"confirm_dramatic_moment_suggestion"`) /
  `DismissDramaticMomentSuggestionAction` (key `"dismiss_dramatic_moment_suggestion"`) —
  **account-authorized** (mirrors `actions/definitions/events.py`'s host-lifecycle
  actions: `actor=None`, `account=<resolver>`), gated on `_account_can_gm_scene` (staff,
  or `scene.is_gm(account)`, or `scene.is_owner(account)`).
- **Web:** `DramaticMomentSuggestionViewSet` (`views.py`) — `GET
  /api/magic/dramatic-moment-suggestions/?scene=<id>` (PENDING list, same GM/owner/staff
  gate); `POST .../{id}/confirm/` / `POST .../{id}/dismiss/` dispatch the actions above.
- **Telnet:** `CmdMoment` (`commands/dramatic_moments.py`, key `"moment"`) — `moment
  suggestions|confirm <id>|dismiss <id>`, account-authorized like the web surface.
- **Frontend:** `DramaticMomentSuggestionChip` (`frontend/src/scenes/components/`),
  mounted in `PoseUnit` for the caller's own entrance poses.
- **Seed content:** `ensure_dramatic_entrance_content()` (`factories.py`) seeds the "Grand
  Entrance" `DramaticMomentType` (self-contained — get-or-creates its own "Fervor"
  Resonance + "Celestial" Affinity) with `suggest_on_technique_entrance=True` /
  `suggestion_min_success_level=3`.

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
- **Technique-driven entrance (#2183):** `EntranceAction.execute` branches on a
  `technique_id` kwarg to `_execute_technique_entrance` instead of the plain
  ActionTemplate check path — see "Technique Entrance" below. The bare-entrance
  ActionTemplate path (this section) is unchanged and byte-identical when no
  technique is attached.

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

### Technique Entrance (#2183, ADR-0113)

A "make an entrance" whose check IS a technique cast — one roll, not two (ADR-0113): the
technique's own success level substitutes for the entrance's social check entirely and
drives every downstream consequence (flourish, disposition, the Dramatic Moment Suggestion
above). See `docs/systems/magic.md`'s "Technique Entrance" section for the full deferral
matrix table; the summary:

- **Dispatch:** telnet `enter <technique>[=<target>]` (`CmdEnter`,
  `commands/social/entrance_flourish.py`) and the web `EntranceTechniqueAttachment`
  popover both reach `EntranceAction._execute_technique_entrance`
  (`actions/definitions/social.py`) via `action.run()`. The web REST caller
  (`SceneActionRequestViewSet._create_technique_entrance`,
  `world/scenes/action_views.py`, #2183 Task 8 fold-in) dispatches the identical seam —
  **not** the generic technique-as-`ActionEnhancement` consent path
  `SceneActionRequestViewSet.create()` otherwise uses (that path has no
  `ActionEnhancement` row for `"entrance"` and always 400ed before this fix).
- **Deferral matrix** (why a success level isn't always known immediately): resolved
  inline → full hooks now; hostile → seeds/feeds combat, flourish only, suggestion
  deferred to combat round resolution (`from_entrance` marker, see
  `docs/systems/INDEX.md`'s Combat section); PENDING consent/risk-gated →
  `SceneActionRequest.originated_as_entrance` defers all hooks to
  `resolve_accepted_cast`; soulfray gate unconfirmed → a `PendingCast` carrying an
  `"entrance"` marker re-dispatches through the `"entrance"` REGISTRY action (not
  `"cast_technique"`) on `accept soulfray` (`world/magic/offer_handlers.py`
  `SoulfrayPendingHandler`).
- **Shared hook helper:** `run_entrance_success_hooks(actor, scene, *, success_level,
  target_persona_id, technique, interaction=None)` (`actions/definitions/social.py`) —
  one signature, three call sites (declaration-time inline/hostile branches,
  accept-time deferred hooks, combat round-resolution hook), no drift.

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

### Sanctum (#1497 — TELNET+WEB)

The sanctum subsystem is a 7-op surface shared by telnet (`CmdSanctum`) and web
(`SanctumViewSet` in `views_sanctum.py`); both converge on `action.run()`.

**Actions** (`actions/definitions/sanctum.py`, all REGISTRY, `target_type=SELF`, `category="magic"`):
- `sanctum_install` — Ritual of Sanctification: validate presence/ownership/founder-cap, create
  `RoomFeatureInstance` + `SanctumDetails`. Leader authorization
  (`_validate_sanctification_leader` in `services/sanctum_install.py`) branches on
  `owner_mode`: Personal requires the leader persona to be the room's direct owner;
  Covenant requires the room to be owned by a Covenant-type organization, that the
  Sanctum kind's authored owner-type catalog currently permits covenant ownership
  (`_covenant_ownership_allowed_for_sanctum()`, reading `RoomFeatureKindOwnerType` —
  staff can revoke covenant eligibility there), and that the leader holds an active
  (`left_at IS NULL`) `CharacterCovenantRole` whose `CovenantRank.can_lead_rituals` is
  `True` — mere active membership is no longer sufficient (#708). Also validates/consumes the
  Sanctification Ritual's `RitualComponentRequirement` rows (#707) via
  `resolve_and_consume_ritual_components` (`kwargs["components_provided"]`,
  `resonance_context=kwargs["resonance"]` — a touchstone must match THIS Sanctum's own founding
  Resonance) BEFORE calling `perform_sanctification`. This is the one Ritual that does NOT
  dispatch through the generic `PerformRitualAction` seam (`client_hosted=True`), so this Action
  calls the shared helper directly rather than relying on `PerformRitualAction`'s own wiring.
- `sanctum_homecoming` — Ritual of Homecoming: sacrifice resonance to grow the Sanctum's
  Homecoming reservoir (wraps `perform_homecoming_ritual`).
- `sanctum_purging` — Ritual of Purging: change the Sanctum's consecrated resonance type,
  draining grown resonance as the cost (wraps `perform_purging_ritual`).
- `sanctum_weave` — weave a SANCTUM-anchored `Thread` (`slot=personal|covenant|helper`).
- `sanctum_dissolve` — soft-delete the sanctum (see dissolution below).
- `sanctum_absorb` — drain the weaver's pending weaving/owner-bonus pool into spendable
  resonance currency; physical presence in the Sanctum's room required (wraps
  `absorb_sanctum_pool`).
- `sanctum_sever` — soft-retire a SANCTUM-anchored thread by name or id.

**Outcome-tier award tables (#1207):** Homecoming/Purging/Dissolution no longer key on the
deleted `ritual_checks.OutcomeTier` enum or hardcoded multiplier dicts — each looks up an
authored per-`CheckOutcome`-tier row via the shared `world.checks.models.OutcomeTierAward`
base (the pattern generalizes `world.societies.models.GangTurfReputationAward`):
`perform_homecoming_ritual` reads `SanctumHomecomingGainAward.gain_multiplier`,
`perform_purging_ritual` reads `SanctumPurgingRetentionAward.retention_modifier` (signed —
can reduce retention below the base value), and `perform_dissolution`
(`_dissolution_recovery_fraction`) reads `SanctumDissolutionRecoveryAward.recovery_fraction`
(all in `world/magic/models/sanctum.py`, consumed from `services/sanctum_rituals.py` and
`services/sanctum_install.py`). Sanctification itself doesn't use an award table — it was
ported to plain `success_level` comparisons against literal thresholds
(`MINIMUM_SANCTIFICATION_SUCCESS_LEVEL` / `SANCTIFICATION_CRIT_SUCCESS_LEVEL` /
`CRITICAL_FAILURE_SUCCESS_LEVEL` in `services/sanctum_install.py`).

Module helpers: `sanctum_in_room(location)` returns the active `SanctumDetails` for the
room (excludes dissolved); `room_profile_for_location(location)` resolves a `RoomProfile`.

**Telnet surface** (`commands/sanctum.py` — `CmdSanctum`, key `sanctum`): namespaced `sanctum
<subverb>` `DispatchCommand` routing the 7 subverbs through `dispatch_player_action`. Bare
`sanctum`/`sanctum status` = hub. No business logic in the command. `install`'s kwargs include
`components_provided=self._gather_components()` — auto-gathers every `ItemInstance` the caller
is physically carrying (mirrors `CmdRitual._gather_components`), since Sanctification now carries
real seeded `RitualComponentRequirement` rows (see "Seeded touchstone/reagent content" below).

**Web surface** (`views_sanctum.py` — `SanctumViewSet.install`): `SanctifyActionSerializer.components`
is an explicit `ListField` of the caller's own `ItemInstance` pks (mirrors
`RitualPerformRequestSerializer.components` in `serializers.py`) — `validate_components` resolves
them and checks each belongs to the requesting sheet's inventory (`ItemInstance
.holder_character_sheet`, not the account — items are body-scoped per #684). The view forwards the
resolved list as `components_provided=` to `SanctumInstallAction().run()`.

**Seeded touchstone/reagent content** (`seeds_touchstone_content.py`, #707): small,
framework-proving seed set — `ensure_resonance_tiers()` (Faint/Resonant/Profound, tier_level
1/2/3), `ensure_touchstone_content()` (one example touchstone `ItemTemplate`, a Praedari paw,
tier 1, plus 3 generic reagent templates: candle/salt/incense — self-contained, get-or-creates
its own "Praedari" Resonance + "Primal" Affinity by name rather than assuming some other seed ran
first, since no canonical Resonance/Affinity catalog exists yet in production seed code),
`ensure_sanctification_requirements(ritual)` (attaches 1x touchstone-mode + the 3 reagent
template-mode `RitualComponentRequirement` rows). `seeds_sanctum.ensure_sanctum_rituals()` calls
`ensure_sanctification_requirements()` for both the Personal and Covenant Sanctification rituals —
so every real "sanctum install" now requires a touchstone tied to the founding Resonance (tier ≥
Faint, attuned to the founder) plus one each of the three reagents. A full per-resonance/per-tier
content catalog is separate content-authoring work, not framework work.

**Dissolution soft-delete** (#1497): `perform_dissolution` sets `RoomFeatureInstance.dissolved_at`
(nullable `DateTimeField`) rather than deleting the row. `RoomFeatureInstance.active()` queryset
excludes dissolved instances. SANCTUM-anchored threads are soft-retired (`Thread.retired_at`) on
dissolution — never hard-deleted. The `one_personal_per_character_sheet` DB `UniqueConstraint`
on `SanctumDetails` was removed (cross-table partial-unique limitation); one-personal-per-founder
is enforced in the service layer, excluding dissolved rows. Re-sanctifying the same room after
dissolution is a deferred follow-up.

### Portal Travel (#2222, ADR-0121)

A character who knows a travel-mode `Technique` (`travel_anchor_kind` FK set) and stands in a
room carrying a matching active `PortalAnchor` can travel instantly to any other room whose
matching anchor is open-or-standing — `TravelAction.execute()`
(`actions/definitions/movement.py`) tries this branch FIRST, falling through to #2163's
walking pathfinder unchanged when ineligible. `PortalAnchorKind` (staff-authored medium
catalog — arrival/departure verbs) and `PortalAnchor` (stackable per-room install,
soft-deleted via `dissolved_at`, one active per `(room_profile, kind)`) live in
`models/portals.py`; deliberately NOT a `RoomFeatureInstance` (one-feature-per-room
cardinality) or a `RoomDecoration` (wrong domain — see ADR-0121). Services
(`services/portal_travel.py`): `travel_anchor_kinds_for` / `portal_destinations` /
`portal_route` / `perform_portal_travel` / `install_portal_anchor` /
`install_portal_anchor_as_staff` (#2451 — the staff-authoring counterpart called from the
world-builder canvas: no owner/tenant standing check, no currency cost) /
`dissolve_portal_anchor` — never consults `RoomProfile.is_public`. Install costs a flat
`settings.PORTAL_ANCHOR_INSTALL_COST` (default 5000 copper); actions
`portal_anchor_install`/`portal_anchor_dissolve` (`actions/definitions/portals.py`), telnet
`CmdPortalAnchor` (`portal/install <kind>=<name>` / `portal/dissolve [<kind>]`). `PortalAnchor`
also carries an optional nullable-unique `fixture_key` (#2451) for grid-bundle export/import —
see the "Grid content export/import" area of `docs/systems/INDEX.md`. Discovery
API lives in `world.locations` (not this app) alongside `ComfortViewSet`: `GET
/api/locations/portal-destinations/?character_id=<id>`. Seed:
`ensure_portal_travel_content()` (`world/seeds/game_content/magic.py`) — "Mirror" anchor
kind, "Mirrorwalking" Minor Gift + "Mirrorwalk" Technique, starter anchors in the seeded
magic-story cascade rooms. Full eligibility chain + API/frontend detail:
`docs/systems/magic.md`'s "Portal travel" section.

## Fall / Redemption: Asymmetric Resonance Conversion (#1583)

The Fall/Redemption system lets characters convert their affinity through
dramatic ceremony. **Falling gains power; Redemption is lossy** (ADR-0054,
ADR-0134). Compromising acts (combat kills, cruelty, malice) grant
spendable non-native resonance via `grant_resonance` with
`source=GainSource.COMPROMISE` — the existing `CharacterResonance` rows ARE
the drift tracker. `recompute_aura` shifts affinity percentages; the Fall
becomes available when the target affinity crosses
`FallRedemptionConfig.fall_threshold_percent`.

**Models (`models/fall_redemption.py`):**
- `CompromiseActType` — authored act category → (target_resonance, amount,
  is_cruelty). Staff author act types; mission/combat/social systems
  reference them.
- `ResonanceConversion` — authored mapping (source_resonance,
  target_affinity) → target_resonance. One row per path.
- `FallRedemptionConfig` — singleton (pk=1, `ArxSharedMemoryManager`) with
  conversion multipliers per path + penance exchange rate + fall threshold.
- `FallRedemptionRecord` — immutable audit of a full (irreversible) Fall
  or Redemption. `ConversionType` TextChoices: FALL / REDEMPTION.

**Services:**
- `services/conversion.py` — `convert_resonance()` shared engine for both
  partial (Atonement) and full (Fall) conversion. Transfers `balance` and
  `lifetime_earned` (scaled by multiplier) from source to target resonance.
  `lifetime_earned` is transferred, not decremented — the total is preserved
  modulo the multiplier, so `recompute_aura` shifts correctly. Full
  conversion re-anchors `Thread.resonance` FK (merging into existing
  target-resonance threads if needed, retiring duplicates). Partial
  conversion (Atonement) does NOT touch threads.
- `services/fall_redemption.py` — `grant_compromise_resonance()` (thin
  wrapper over `grant_resonance`), `perform_fall()` (the full ceremony,
  gated by aura threshold + irreversibility), `get_fall_redemption_config()`.

**Extended Rite of Atonement (`services/atonement.py`):**
The existing Rite of Atonement is extended to do BOTH:
1. **Corruption reduction** (existing) — `reduce_corruption` for stages 1–2.
   Stage 3+ still raises; stage 0 skips this effect.
2. **Resonance conversion** (new) — if the performer is Celestial-dominant
   with non-native `balance > 0`, converts it back to Celestial at the lossy
  `penance_exchange_rate` (default 0.5 = 2:1). No typed FK needed.
At least one effect must fire, or `AtonementNothingToAtone` is raised.
Repeatable (not a Fall); each conversion loses half the value.

**New `GainSource` values** (all `NON_ACCELERATED_GAIN_SOURCES`):
`COMPROMISE`, `PENANCE`, `FALL_CONVERSION`. No typed source FK
(MISSION_REPORT shape). Three new `ResonanceGrant` CheckConstraints.

**Seed content:** `wire_fall_redemption_content()` in `factories.py`,
called by `seed_magic_dev()`. Seeds the "Ritual of Falling" Ritual row
(SERVICE dispatch), the `FallRedemptionConfig` singleton, example
`CompromiseActType` rows, and example `ResonanceConversion` mappings.

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
- `CharacterResonanceTotal` - Superseded by `CharacterResonance.lifetime_earned`
  (monotonic, updated via `grant_resonance`); aura recompute reads that field via
  `recompute_aura`, not a `CharacterModifier`/resonance-category walk (#1836). Distinction
  effects targeting a resonance-category `ModifierTarget` no longer write a
  `CharacterModifier` row at all — they flow through
  `reconcile_distinction_resonance_grants` (the `DistinctionResonanceGrant` sidecar)
  instead (#1834). The `resonance` `ModifierCategory` itself is still live infrastructure
  for non-distinction sources — facet/mantle/motif-coherence passive bonuses
  (`equipment_walk_total` in `world/mechanics/services.py`) still read/write
  resonance-category `CharacterModifier` rows via `EQUIPMENT_RELEVANT_CATEGORIES`.

### Distinction Resonance Grants (standing/currency axis, #1834)

`DistinctionResonanceGrant` (`models/grants.py`) — sidecar authoring surface joining a
`distinctions.Distinction` to a `Resonance` with two rank-scaled currency knobs:
`flat_amount_per_rank` (seed) and `earn_rate_bonus_per_rank` (percent). Lives in
`world.magic` (not `world.distinctions`) per ADR-0010 — the general primitive
(`magic.Resonance`) must not import back into a dependent app.

- `reconcile_distinction_resonance_grants(character_distinction)`
  (`services/distinction_resonance.py`) — the grant-time consumer, called by both
  `create_distinction_modifiers` and `update_distinction_rank`
  (`world/mechanics/services.py`). For every `DistinctionResonanceGrant` on the
  distinction: establishes a `CharacterResonance` row (`get_or_create`), then tops off a
  rank-scaled flat seed via `grant_resonance(source=GainSource.DISTINCTION,
  source_character_distinction=...)`. Ledger-idempotent (sums this distinction's prior
  `DISTINCTION`-source grants for the resonance, grants only the shortfall); a rank-down
  never claws back.
- `distinction_earn_rate_for(character_sheet, resonance)` (`services/distinction_resonance.py`)
  — sums the earn-rate bonus across a character's distinctions for one resonance. Read by
  `grant_resonance` (`services/resonance.py`) to scale `amount` up before writing, but only
  when `source in ACCELERATED_GAIN_SOURCES` (ADR-0041 — perception/presence sources); the
  `DISTINCTION` seed itself is in `NON_ACCELERATED_GAIN_SOURCES` (accelerating it would be
  circular). A total-classification test asserts every `GainSource` lands in exactly one set.
- `GainSource.DISTINCTION` + `ResonanceGrant.source_character_distinction` — ledger
  discriminator + typed source FK for the seed grants above.
- Wired at both acquisition sites: gameplay grant/rank-up and character creation
  (`_create_distinction_modifiers_bulk` in `world/character_creation/services.py`, followed
  by `recompute_aura` once `CharacterAura` exists in `finalize_magic_data`).
- **Reverse direction (#2037):** `DistinctionResonanceRankThreshold` (`models/grants.py`,
  unique `(distinction, resonance, rank)` + `lifetime_earned_threshold`) authors "sustained
  investment in this Resonance ranks up that Distinction."
  `check_distinction_rank_thresholds(character_sheet, resonance)`
  (`services/distinction_resonance.py`) is the consumer, called by `grant_resonance` only
  when `source in ACCELERATED_GAIN_SOURCES` (never for `DISTINCTION` seeds — feedback-loop
  guard). Ranks up **held** distinctions only (threshold keyed to exactly
  `current_rank + 1`, which is also the re-fire guard), loops to a fully caught-up state per
  grant, routes through `grant_distinction(origin=ENDORSEMENT_THRESHOLD)`, catches/logs
  `DistinctionExclusionError`, and is failure-isolated in `grant_resonance` so the resonance
  grant always stands.

### Distinction Potency (POWER axis, #1834 Task 7)

A distinction expresses **potency** for a resonance — as opposed to the identity/currency
axis above — by authoring a normal `DistinctionEffect` whose `target` is a POWER-category
`ModifierTarget` gated by `target_resonance` (the same scope-gate seam
`motif_coherence_bonus` and tier-0 thread-pull FLAT_BONUS rows ride). `create_distinction_modifiers`
writes this as an ordinary `CharacterModifier` (POWER-category rows are unaffected by the
resonance-category skip above). Two consumers read it:

- **Casts** — already wired: `_partition_power_targets`/`_derive_power`'s FLAT stage
  (`world/magic/services/techniques.py`) scope-matches the target against the technique's
  gift-resonances and folds `get_modifier_breakdown(sheet, target)` into the power ledger.
- **Thread pulls** — `world.mechanics.services.power_flat_bonus_for_resonance(sheet,
  resonance_id)` mirrors cast scope semantics: sums POWER-category targets whose
  `target_resonance` is null (unscoped) or matches `resonance_id` (excluding the unscoped
  `power_multiplier` target) via `get_modifier_total`. `world.magic.services.resonance
  ._fold_distinction_pull_bonus` calls it once per pull (not per thread/tier, since every
  pulled thread shares one resonance) and appends a synthetic `FLAT_BONUS`
  `ResolvedPullEffect`; wired into both `spend_resonance_for_pull` (the charge/commit path —
  persists into `CombatPullResolvedEffect` for combat, returned ephemerally otherwise) and
  `preview_resonance_pull` (so the read-only preview matches the eventual commit).

**Not full parity with a cast.** A cast's FLAT stage (`_derive_power`) also sums
condition-sourced POWER contributions via `get_condition_modifier_breakdown` — the pull fold
only sums the `CharacterModifier` (distinction) side via `power_flat_bonus_for_resonance`. A
character with an active condition that boosts POWER for this resonance sees it in a cast but
not in a standalone pull.

## Design Docs

- `docs/plans/2026-01-20-magic-system-design.md` - original system design
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` - cantrip/technique alignment + spell mechanics
- `docs/plans/2026-03-04-path-cantrip-filtering-design.md` - path-based cantrip filtering design
- `docs/architecture/resonance-threads.md` - Resonance Pivot Spec A (Threads + Currency + Rituals + Mage Scars rename)
- `docs/architecture/resonance-gain.md` - Resonance Pivot Spec C (Endorsements + Room Aura + Residence Trickle)
- `docs/architecture/soul-tether.md` - Resonance Pivot Spec B (Soul Tether bond mechanic)
- `docs/adr/0134-resonance-as-drift-compromising-acts-grant-spendable-non-native-resonance.md` - Resonance-as-drift decision (#1583)

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are proper models in this app, not ModifierTarget entries
- FKs to affinities/resonances point directly to Affinity/Resonance models (type-safe)
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierTarget)
- Technique has intensity (power) and control (safety/precision) as base stats
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
- CG links a staff-authored catalog Gift + Techniques — it never mints new rows (#2426)
- No healing mechanics — shielding yes, restoration no (counter to tension design)

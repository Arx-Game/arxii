# Magic System

Power flows from identity and connection. Characters have auras (affinity balance),
resonances (style tags), gifts (power categories), and threads (magical relationships).
Techniques are the primary magical abilities, powered by intensity and control stats.

**Source:** `src/world/magic/`
**API Base:** `/api/magic/`
**How it works (start here):**
- `docs/architecture/technique-use-pipeline.md` — **How Magic Works**: the end-to-end
  cast lifecycle (entry paths → cost → resolution → consequences → narration), with diagram.
- `docs/architecture/power-derivation.md` — the power ledger (assembly phases) and the
  penetration-vs-resistance contest, with diagrams.

**Design Docs:**
- `docs/plans/2026-01-20-magic-system-design.md` (original system design)
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` (cantrip/technique alignment)
- `docs/architecture/resonance-threads.md` (Resonance Pivot Spec A — Threads + Currency + Rituals + Mage Scars rename)

---

## Enums (types.py + constants.py)

```python
from world.magic.types import (
    AffinityType,        # CELESTIAL, PRIMAL, ABYSSAL
    AnimaRitualCategory, # SOLITARY, COLLABORATIVE, ENVIRONMENTAL, CEREMONIAL
)

from world.magic.constants import (
    TargetKind,              # Thread discriminator: TRAIT, TECHNIQUE, FACET,
                             # RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE,
                             # COVENANT_ROLE, MANTLE, SANCTUM
    EffectKind,              # ThreadPullEffect payload: FLAT_BONUS,
                             # INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT,
                             # NARRATIVE_ONLY, ASSUME_ALTERNATE_SELF (drives
                             # transformation via target_form + depth band)
    VitalBonusTarget,        # MAX_HEALTH, DAMAGE_TAKEN_REDUCTION
    RitualExecutionKind,     # SERVICE, FLOW
    PendingAlterationStatus, # OPEN, RESOLVED, STAFF_CLEARED
    AlterationTier,
    ALTERATION_TIER_CAPS,
    THREADWEAVING_ITEM_TYPECLASSES,
)
```

Legacy enums `ResonanceScope`, `ResonanceStrength`, and `ThreadAxis` were
removed as part of Resonance Pivot Spec A — `CharacterResonance.scope/strength`
and the 5-axis Thread model no longer exist.

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `EffectType` | Types of magical effects (Attack, Defense, Movement) | `name`, `description`, `base_power`, `base_anima_cost`, `has_power_scaling` |
| `TechniqueStyle` | How magic manifests (Manifestation, Subtle, Prayer) | `name`, `description`, `allowed_paths` (M2M to `classes.Path`) |
| `IntensityTier` | Power effect thresholds | `name`, `threshold`, `control_modifier`, `description` |
| `Restriction` | Limitations that grant power bonuses | `name`, `description`, `power_bonus` |
| `Facet` | Hierarchical imagery/symbolism (Category > Subcategory > Specific) | `name`, `parent` (self-FK), `description` |
| `Gift` | Thematic collections of techniques | `name`, `description`, `resonances` (M2M to `Resonance` — the **supported set**: a weave constraint, not the cast-time value; the cast reads the character's GIFT-thread resonance via `gift_resonances_for`, ADR-0052), `creator` (FK to CharacterSheet), `kind` (`GiftKind`: `MAJOR` = the one CG-chosen gift, `MINOR` = shared/acquirable; ADR-0050) |
| `Affinity` | CELESTIAL / PRIMAL / ABYSSAL | `name`, optional OneToOne `modifier_target` |
| `Resonance` | Identity resonance tags | `name`, `affinity` FK, `opposite` self-OneToOne, optional `modifier_target` OneToOne |

**Note:** `Affinity` and `Resonance` are proper first-class domain models in
this app (each with an optional OneToOne link back to `mechanics.ModifierTarget`
for modifier-system integration). The old `ThreadType` lookup was deleted as
part of the Resonance Pivot — relationship flavor is now carried by
`relationships.RelationshipTrack`.

### Character State

| Model | Purpose | Key Fields | Relationship |
|-------|---------|------------|--------------|
| `CharacterAura` | Affinity percentages (must sum to 100) | `celestial`, `primal`, `abyssal` | OneToOne via `character.aura` |
| `CharacterResonance` | Per-character per-resonance identity + currency (Spec A §2.2) | `character_sheet` FK, `resonance` FK, `balance`, `lifetime_earned`, `claimed_at`, `flavor_text` | FK via `character_sheet.resonances` (unique_together: (character_sheet, resonance)) |
| `CharacterGift` | Acquired gifts | `gift`, `acquired_at` | FK via `character.character_gifts` |
| `CharacterTechnique` | Known techniques | `technique`, `acquired_at`, `source` (FK mechanics.ModifierSource, nullable — set for granted techniques) | FK via `character.character_techniques` |
| `CharacterAnima` | Magical energy pool | `current`, `maximum`, `last_recovery` | OneToOne via `character.anima` |
| `CharacterAnimaRitual` | Personalized recovery rituals | `stat`, `skill`, `resonance`, `personal_description`, `is_primary` | FK via `character.anima_rituals` |
| `CharacterAffinityTotal` | Cached affinity totals | `character`, `affinity`, `total` | FK via character |

**CharacterResonance reshape note.** Prior to Spec A, `CharacterResonance`
carried `scope`, `strength`, `is_active`, and FK'd `ObjectDB`. Those fields
were dropped (no readers beyond Mage Scars, which now uses
`character.resonances.most_recently_earned()`), `character` was re-FK'd to
`CharacterSheet`, and `balance` + `lifetime_earned` were added. Row existence
replaces the old `is_active` flag. `CharacterResonanceTotal` (denormalized
aggregate) was deleted — aura recompute now reads `CharacterModifier` rows
whose target category is `resonance` directly.

### Techniques (Player-Created Abilities)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Technique` | A specific magical ability within a Gift | `name`, `gift` (FK), `style` (FK to TechniqueStyle), `effect_type` (FK to EffectType), `restrictions` (M2M), `level`, `intensity`, `control`, `anima_cost`, `creator`, `target_type`, `reach` |

Key fields: `intensity` (base power), `control` (base safety/precision), `level` (progression
gate, derives tier), `target_type` (per-technique cardinality — see below).
Key property: `tier` (derived from level: 1-5=T1, 6-10=T2, etc.)

**`Technique.target_type`** (`actions.constants.ActionTargetType`, default `SINGLE`) stores the
cardinality of who this technique can target:
- `SELF` — affects only the caster.
- `SINGLE` — one target.
- `AREA` — auto-expands to all eligible personas in the scene (derived from relationship).
- `FILTERED_GROUP` — a player-supplied subset intersected with the eligible set.

The targeting *relationship* (who is eligible: SELF/ALLY/ENEMY) is **derived** from the
technique's authored condition `target_kind`s and hostility — it is not stored here.
See `derive_target_relationship` in `world/magic/services/targeting.py`.

**Intensity and Control:** These are base/static values on the technique. Runtime casting
values (after resonance bonuses, combat escalation, audere states) are tracked by a
separate casting handler. When intensity exceeds control at runtime, effects become
unpredictable and anima cost spikes. If anima cost exceeds the character's pool, the
excess deals damage to the caster.

### Technique Authoring Draft Workbench (#1496) [BUILT & WIRED]

The web frontend (`TechniqueViewSet.author`, player path) and the staff telnet command
(`CmdTechnique`) converge on `AuthorTechniqueAction.run()`
(`actions/definitions/technique_authoring.py`, key `"author_technique"`, category `"magic"`).
The action catches all budget/permission/gift/draft exceptions and returns a failure
`ActionResult`. (A staff account with no acting character has no `ObjectDB` actor to dispatch,
so that web case calls `author_staff_technique()` directly.)

**Abstract payload bases** (`models/techniques.py`) — shared by committed and draft rows:

| Model | Purpose |
|-------|---------|
| `AbstractCapabilityGrant` | Shared capability-grant columns; no owner FK |
| `AbstractDamageProfile` | Shared damage-profile columns; no owner FK |
| `AbstractAppliedCondition` | Shared applied-condition columns; no owner FK |

**Draft workbench models** (`models/technique_draft.py`):

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TechniqueDraft` | One-per-CharacterSheet in-progress design workbench | `character_sheet` FK (unique, `related_name="technique_draft"`), `name`, `description`, `gift` FK, `style` FK, `effect_type` FK, `intensity`, `control`, `anima_cost`, `level`, `target_type`, `reach`, `restrictions` M2M |
| `TechniqueDraftCapabilityGrant` | Draft payload — capability grant row (inherits `AbstractCapabilityGrant`) | `draft` FK |
| `TechniqueDraftDamageProfile` | Draft payload — damage profile row (inherits `AbstractDamageProfile`) | `draft` FK |
| `TechniqueDraftAppliedCondition` | Draft payload — applied condition row (inherits `AbstractAppliedCondition`) | `draft` FK |

**Draft services** (`services/technique_draft.py`):
- `get_or_start_draft(character) -> TechniqueDraft` — creates or returns the active draft.
- `discard_draft(character)` — deletes draft and all payload children.
- `set_draft_fields(draft, **fields)` — typed field updates (name, description, gift, style,
  effect_type, level, intensity, control, anima_cost, target_type, reach).
- `add_draft_restriction` / `remove_draft_restriction` — restriction M2M management.
- `add_draft_capability_grant` / `add_draft_damage_profile` / `add_draft_applied_condition`
  and `remove_*` counterparts — payload row management.
- `draft_to_design(draft) -> TechniqueDesignInput` — validates completeness; raises
  `TechniqueDraftIncomplete` on missing required fields.

**Shared validation gate** (`services/technique_builder.py`):
- `validate_design_for_character(design, policy, character)` — gift-ownership check; the single
  source of truth for the gate (telnet + web call it); raises `GiftNotOwned`.

**Exceptions** (in `exceptions.py`): `NoActiveTechniqueDraft`, `TechniqueDraftIncomplete`,
`UnknownTechniqueVocab`, `UnknownGift`, `GiftNotOwned`.

**Telnet workbench** — `CmdTechnique` (`commands/technique.py`, key `"technique"`,
`cmd:perm(Builder)` — staff/GM only). Subcommands: `draft`, `show`, `set`, `restrict`,
`grant`, `damage`, `condition`, `price`, `author` (dispatches `AuthorTechniqueAction` with
`StaffPolicy`), `discard`. Registered in `commands/default_cmdsets.py`.

**Exposure:** staff/GM-only. Player self-service is a deferred `needs-design` follow-up.

### Cantrips (CG Technique Templates)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Cantrip` | Staff-curated starter technique template | `name`, `description`, `archetype`, `effect_type` (FK), `style` (FK), `base_intensity`, `base_control`, `base_anima_cost`, `requires_facet`, `allowed_facets` (M2M) |

Cantrips are baby techniques. At CG finalization, a cantrip creates a real Technique
(intensity=base_intensity, control=base_control, etc.) in the character's Gift.
Mechanical fields are hidden from the player — they only see name, description,
archetype grouping, and optional facet selection. Filtered by Path (cantrip's style
must be in Path's allowed_styles).

### Standalone Casting — Shared Template + Per-Character Check (#1306) [BUILT & WIRED]

`create_technique` (`services/technique_builder.py`) defaults `action_template` to the
shared **Technique Cast** `ActionTemplate` seeded by `seeds_cast.ensure_technique_cast_content()`,
so every technique (including CG cantrips) is castable standalone. Staff may override
per-technique via the FK. Key surfaces:

| Surface | Location | Purpose |
|---------|----------|---------|
| `ensure_technique_cast_content()` | `seeds_cast.py` | Idempotent seed: shared ActionTemplate + fallback CheckType + "Magic: Technique Cast" ConsequencePool |
| `get_standalone_cast_template()` | `seeds_cast.py` | Retrieves the shared ActionTemplate; called by `create_technique` default |
| `ensure_character_magic_check_type(character_sheet, *, stat, skill)` | `seeds_checks.py` | Synthesizes a per-character `CheckType` (pattern: `character_magic_check_type_name()`) for that character's stat + skill |
| `get_character_cast_check(character)` | `services/anima.py` | Resolves the per-character check type for cast resolution |
| `get_character_anima_ritual(character)` | `services/anima.py` | Retrieves the character's personal SCENE_ACTION `Ritual` (their anima ritual) |
| `provision_player_anima_ritual(...)` | `services/anima.py` | Points `RitualCheckConfig.check_type` at the per-character check so ritual and technique casts share the same roll |

Cast resolution (`world/scenes/cast_services.py:_resolve_cast`) passes the caster's personal
check into `start_action_resolution` via the `check_type` override (optional kwarg added to
`src/actions/services.py`). No schema migration — all seeded via `ensure_technique_cast_content()`.

### Targeting Model (#1321) [BUILT & WIRED]

Standalone casts now validate targets, resolve AoE expansion, apply conditions, and route
consent based on behavioral impact rather than blanket benign/hostile.

**`ConditionCategory.alters_behavior`** (new boolean, default `False`) — marks behavior-altering
condition categories (compulsion, charm, fear) as distinct from capability/stat conditions.
Lives on `world/conditions/models.py:ConditionCategory`.

**Targeting services** (`world/magic/services/targeting.py`):

| Function | Purpose |
|----------|---------|
| `derive_target_relationship(technique) -> ConditionTargetKind` | ENEMY if hostile; ALLY if any condition has `target_kind=ALLY`; else SELF |
| `technique_alters_behavior(technique) -> bool` | True if any applied condition's `category.alters_behavior` is True |
| `cast_requires_consent(technique) -> bool` | True iff `technique_alters_behavior` — **behavior only**, not blanket benign |
| `validate_cast_target(*, technique, initiator_persona, target_personas)` | Raises `InvalidCastTarget` on cardinality or relationship violations |
| `resolve_targets(*, technique, initiator_persona, scene, supplied_personas) -> list[Persona]` | Expands target_type to concrete personas: SELF→caster; SINGLE→one; AREA→all eligible in scene; FILTERED_GROUP→supplied ∩ eligible |

**Consent routing** (in `world/scenes/cast_services.py:request_technique_cast`):
- Hostile → `seed_or_feed_encounter_from_cast` (combat).
- Benign + behavior-altering → PENDING `SceneActionRequest` (consent required).
- Benign + capability/stat → resolves immediately, including on other PCs.

**Shared condition application** (`world/magic/services/condition_application.py`):
`apply_technique_conditions(*, technique, success_level, eff_intensity, targets_by_kind, source_character)`
— extracted from combat's `_apply_conditions`; used by **both** combat and standalone
cast paths. Callers build `targets_by_kind` before calling; the service iterates
`TechniqueAppliedCondition` rows and batches them via `bulk_apply_conditions`.
(`AppliedConditionResult` lives in `world/conditions/types.py` — the neutral condition
layer both combat and magic depend on; no deferred import needed.)

**AoE — combat** (`world/combat/models.py:CombatRoundActionTarget`):
New join table. For AREA and FILTERED_GROUP techniques, each targeted `CombatOpponent`
gets one row. AREA auto-expands to all active opponents; FILTERED_GROUP uses the
stored/supplied subset. Per-target damage + condition expansion happens in
`CombatTechniqueResolver`. SINGLE/SELF techniques leave this table empty and continue
to read `CombatRoundAction.focused_opponent_target`.

**Frontend** — the existing `TargetPicker.tsx` (multi-select capable) is driven by each
technique's `target_spec`, built by `_target_spec_for_technique_action` in
`actions/player_interface.py`. `TargetSpec`/`TargetType`/`TargetKind`/`TargetFilters`
(all in `actions/types.py` and `actions/constants.py`) were **reused** — not reinvented.

**Scope notes:** standalone behavior-altering multi-target casts stay guarded by
`InvalidCastTarget` — per-target consent for multiple PCs is intentionally unsupported
(#1358 closed); hostile multi-target routes through combat's existing `CombatRoundActionTarget`
path. Magic checks use a single placeholder Arcana aspect; how `Aspect` should apply to
magic checks at all is an open design question (#1363).

### Motif System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Motif` | Character-level magical aesthetic | `character`, `name`, `description` |
| `MotifResonance` | Resonances in a motif | `motif`, `resonance` (FK to ModifierTarget) |
| `MotifResonanceAssociation` | Links resonances to facets in a motif | `motif_resonance`, `facet` |
| `CharacterFacet` | Links characters to facets | `character`, `facet`, `resonance` |

### Threads as Currency Consumers (Resonance Pivot Spec A §2.1)

The legacy 5-axis `Thread` / `ThreadType` / `ThreadJournal` / `ThreadResonance`
family was deleted in favor of a discriminator + typed-FK design. A Thread is
owned by a CharacterSheet, channels a single Resonance, and is anchored to
exactly one of: Trait / Technique / Facet / RelationshipTrackProgress /
RelationshipCapstone / CovenantRole / Mantle / SanctumDetails. The bare ROOM
`target_kind` was removed; SANCTUM is the leveled room anchor.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Thread` | Per-character attachment to one anchor that channels one Resonance | `owner` FK CharacterSheet, `resonance` FK, `target_kind`, `target_trait` / `target_technique` / `target_facet` / `target_relationship_track` / `target_capstone` / `target_covenant_role` / `target_gift` / `target_mantle` / `target_sanctum_details` (exactly one populated per kind), `name`, `description`, `developed_points`, `level`, `created_at`, `updated_at`, `retired_at` (soft-retire), `slot_kind` (SANCTUM only: PERSONAL_OWN / COVENANT / HELPER) |
| `ThreadLevelUnlock` | Per-thread XP-locked-boundary receipt | `thread` FK, `unlocked_level`, `xp_spent`, `acquired_at` (unique per (thread, unlocked_level)) |

**Integrity layers on Thread.** (1) `clean()` asserts exactly one `target_*`
FK is populated and matches `target_kind`, validates ITEM typeclass paths against
`THREADWEAVING_ITEM_TYPECLASSES`, and requires `slot_kind` for SANCTUM threads.
(2) Per-kind `CheckConstraint`s mirror the same rule at the DB layer. (3) Per-kind
partial `UniqueConstraint`s prevent duplicate threads for the same
(owner, resonance, target_kind, target_*) combination. All typed FKs use
`on_delete=PROTECT` — anchors cannot be deleted while threads reference them.
**SANCTUM anchor cap:** `sanctum.feature_instance.level × 10`; thread is
pull-applicable while the character is in the Sanctum's room (in-sanctum boost).

### Thread Lookup / Authoring Catalogs (Spec A §2.1 and §4.3)

All SharedMemoryModel lookups.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ThreadPullCost` | Per-tier pull pricing knobs | `tier` (unique: 1/2/3), `resonance_cost`, `anima_per_thread`, `label`. Cost *shape* lives in `spend_resonance_for_pull`; this table only holds the per-tier numbers |
| `ThreadXPLockedLevel` | XP-locked-boundary price list | `level` (unique; 20/30/40 on the internal scale), `xp_cost` |
| `SoulTetherConfig` | Singleton (pk=1) tuning surface for Soul Tether | sineating: `anima_cost_per_unit`, `fatigue_cost_per_unit`, `per_scene_cap_hard_max`, `per_scene_cap_level_mult`, `per_scene_cap_base`, `hollow_max_level_mult`. Rescue thresholds: `rescue_strain_stage3/4/5`. Rescue resonance costs: `rescue_resonance_stage3/4/5`. Rescue budget bases and multipliers (integer-encoded). Lazy-created via `get_soul_tether_config()`. |
| `ThreadPullEffect` | Authored pull-effect template | `target_kind`, `resonance` FK, `tier` (0..3), `min_thread_level`, `effect_kind`, + mutually-exclusive payload columns: `flat_bonus_amount`, `intensity_bump_amount`, `vital_bonus_amount` (+ `vital_target`), `capability_grant` FK to `CapabilityType`, `narrative_snippet`, `target_form` FK to `forms.CharacterForm` (nullable; set only for `ASSUME_ALTERNATE_SELF`, which names the form whose profiles to assume on cast), `resistance_amount` (+ `resistance_damage_type` FK to `conditions.DamageType`; null = all types — `RESISTANCE` effect kind, #1580). `target_gift` (nullable FK to `magic.Gift`) — when set, this pull-effect applies only to GIFT threads anchored to that specific gift (species-gift-specific tier-0 passives); null rows serve as the generic fallback for that kind. Tier 0 = passive always-on; tiers 1–3 = paid pulls. Unique per (target_kind, resonance, tier, min_thread_level) — with two partial `UniqueConstraint`s for GIFT kind (one with `target_gift` set, one without). CheckConstraints enforce payload/effect_kind alignment — `ASSUME_ALTERNATE_SELF` requires `target_form` set and all numeric/capability/snippet payload empty; `RESISTANCE` requires `resistance_amount` set and all other payload null; all other kinds require `target_form__isnull=True`. `get_pull_effects_for_thread(thread, **filters)` (`world/magic/services/pull_effects.py`) resolves the correct rows: for GIFT kind, tries `target_gift`-specific rows first, falls back to `target_gift IS NULL` |
| `ImbuingProseTemplate` | Fallback narrative prose for Imbuing | `resonance` FK (nullable), `target_kind` (nullable), `prose`. Row with both NULL = universal fallback |
| `Ritual` | Authored ritual procedure | `name`, `description`, `hedge_accessible`, `glimpse_eligible`, `narrative_prose`, `execution_kind` (SERVICE/FLOW), `service_function_path` (SERVICE), `flow` FK (FLOW), optional `site_property` FK. CheckConstraint: exactly one dispatch payload |
| `RitualComponentRequirement` | Items required to perform a Ritual | `ritual` FK, `item_template` FK, `quantity`, optional `min_quality_tier` FK, `authored_provenance` |

### ThreadWeaving Acquisition (Spec A §2.1 / §4.2)

How a character gains the *right* to weave threads on a given anchor scope.
Same discriminator + typed-FK pattern as `Thread`. Gifts and Paths are not
thread anchors — they appear here only as unlock dimensions.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ThreadWeavingUnlock` | Authored unlock catalog | `target_kind`, one of (`unlock_trait` FK Trait / `unlock_gift` FK Gift / `unlock_item_typeclass_path` str / `unlock_track` FK RelationshipTrack), `xp_cost`, `paths` M2M (in-band Paths), `out_of_path_multiplier` Decimal default 2.0. Per-kind partial unique constraints guarantee one unlock per anchor. CheckConstraints mirror the typed-FK rule; `target_kind=RELATIONSHIP_CAPSTONE` is forbidden (inherited from parent track). SANCTUM threads do not use this model — no unlock row needed. Has a derived `display_name` property |
| `CharacterThreadWeavingUnlock` | Per-character purchase record | `character` FK CharacterSheet, `unlock` FK, `acquired_at`, `xp_spent` (actual — in-Path=xp_cost, out-of-Path=xp_cost × multiplier), optional `teacher` FK RosterTenure. Unique per (character, unlock) |
| `ThreadWeavingTeachingOffer` | Teacher-side offer | `teacher` FK RosterTenure, `unlock` FK, `pitch`, `gold_cost`, `banked_ap`, `created_at`. Mirrors `CodexTeachingOffer` |

### Thread XP-Locked Boundaries

Thread levels hit authored `ThreadXPLockedLevel` boundaries (20/30/40 on the internal
scale) that must be purchased with XP before further development. The underlying spend is
`cross_thread_xp_lock(character_sheet, thread, target_level)`.

**Surfaces:**
- `POST /api/magic/threads/{id}/cross-xp-lock/` — legacy web-only action on the
  `ThreadViewSet`.
- `GET /api/progression/unlocks/` + `POST /api/progression/unlocks/purchase/` — shared
  Unlock Shop (web) that dispatches `PurchaseUnlockAction`
  (`registry_key="purchase_unlock"`).
- `progression unlock thread=<id> level=<n>` — telnet face of the shared Unlock Shop.

The shared seam is the TELNET+WEB path; the legacy thread endpoint remains usable from
web clients but does not run through `PurchaseUnlockAction`.

### Thread Pull — Declaration Modifier (#1455) [BUILT & WIRED]

A thread pull is a **modifier carried by a `cast` or `clash` declaration**, not a
standalone action. Both telnet and web converge on the same commit paths.

**Telnet surface:** `cast`/`clash` accept `pull=<thread>[,…] resonance=<name> [tier=<1-3>]`
parsed by the shared `_CombatCommandMixin` pull parser. The pull rides the declaration;
one pull per combat round (cap → `PULL_ALREADY_COMMITTED`).

**Web surface:**
- Non-combat cast: `CastPullRequestSerializer` nested inside the cast request body.
- Combat cast/clash: `pull_resonance_id` / `pull_tier` / `pull_thread_ids` in the dispatch
  kwargs (passed alongside the `ActionRef`).

**Shared commit paths (`world/combat/pull_helpers.py`):**
- `build_cast_pull_declaration(...)` — builds the pull declaration from kwargs.
- `resolve_pull_from_kwargs(...)` — resolves thread ids + resonance + tier from kwargs.
- `commit_combat_pull(...)` — the authoritative commit entry point for all combat contexts
  (combat cast and clash).
- Non-combat cast calls `request_technique_cast(cast_pull=…)`.

**Inert-effect rule:** effects that don't apply to the current context are applied as far
as they fit; the declaration is refused without charge only when none apply.

**Preview (kept):** `preview_resonance_pull` (`POST /api/magic/thread-pull-preview/`) is
the read-only preview endpoint; it is unchanged and remains the way to preview cost +
effects before committing.

**Models (live in `world/combat`):**

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CombatPull` | Per-round commit envelope for a thread pull | `participant` FK, `encounter` FK, `round_number`, `resonance` FK, `tier` (1/2/3), `threads` M2M, `resonance_spent`, `anima_spent`, `committed_at`. Unique per (participant, round_number); indexed on (encounter, round_number) |
| `CombatPullResolvedEffect` | Frozen snapshot of one resolved effect at pull commit | `pull` FK, `kind`, `authored_value`, `level_multiplier`, `scaled_value`, `vital_target`, `source_thread` FK, `source_thread_level`, `source_tier`, `granted_capability` FK, `narrative_snippet`. CheckConstraints mirror ThreadPullEffect payload rules |

A CombatPull is considered *active* while `round_number == encounter.round_number`
(canonical liveness check). `expire_pulls_for_round` (combat services) deletes
stale rows on round advance and invalidates the per-character
`CharacterCombatPullHandler` cache.

### Mage Scars (renamed from Magical Scars — §7.2)

Cosmetic rename only. Class names, table names, and migration code paths
unchanged. Verbose_names, CLI strings, API-visible labels, and documentation
now say "Mage Scars."

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `MagicalAlterationTemplate` | OneToOne on ConditionTemplate; magic-specific alteration metadata | `tier`, `origin_affinity`, `origin_resonance`, `is_library`, `visibility_required` |
| `PendingAlteration` | Queued unresolved Mage Scar | `character` FK, `status` (OPEN/RESOLVED/STAFF_CLEARED), `scene` FK, triggering-state snapshot fields |
| `MagicalAlterationEvent` | Immutable provenance audit log | `pending`, `event_type`, `data`, `created_at` |

### Specialization Engine (ADR-0055 — #1578)

A character's specialized techniques and capabilities are resolved by combining an
entity they hold — a **Gift**, **Path**, or **Covenant Role** — with their **resonance**
(and, where a thread is woven, that thread's level) through **one shared specialization
primitive**, not per-entity bespoke logic. The combination of (Gift × Path) sets the base
technique set; the character's resonance specializes how those techniques manifest —
exactly as (Covenant Role × anchored-thread resonance × thread level) already resolves a
specialized sub-role. The specialized form is **derived on read** (ADR-0014): a change of
resonance instantly re-specializes every affected technique with no regeneration step.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `AbstractSpecializedVariant` | Shared abstract base (SharedMemoryModel) — the "one specialization engine" | `parent` discriminator contract, `matching_variant` selection predicate (highest `unlock_thread_level ≤ thread level` at the thread's resonance), `newly_crossed_variants` discovery query, `discovery_narrative(is_first)` ceremony contract |
| `TechniqueVariant` | Concrete subclass — a resonance-specialized form of a parent `Technique` | `parent_technique` (self-FK, `related_name="variants"`), `resonance` FK, `unlock_thread_level` (≥3 = variant), `name_override`, `intensity_delta`, `control_delta`, `discovery_achievement` FK, `codex_entry` FK. Unique per `(parent_technique, resonance, unlock_thread_level)` |
| `CovenantRole` | Refactored to inherit `AbstractSpecializedVariant` (schema no-op) | existing sub-role fields; `parent_role` (`related_name="sub_roles"`) is the variant parent |

**Resolver — `resolve_specialized_variant(*, entity, character)`** (`world/magic/specialization/services.py`):
the single specialization resolver. For a `Technique` it finds the character's active GIFT
thread on the technique's gift, reads resonance + level, and returns a `_ResolvedTechnique`
value object wrapping the parent + matching variant (exposing `name`/`intensity`/`control`
with variant deltas applied), or the raw parent `Technique` when no variant matches. For a
`CovenantRole` it reads the cached `character.threads` handler (preserving the proven
`resolve_effective_role` cache coherence). `resolve_effective_role` is now a one-line shim
over this resolver — no parallel specialization systems (ADR-0016).

**Discovery ceremony — `fire_variant_discoveries(*, thread, starting_level, new_level)`**
(`world/covenants/discovery.py`): generalizes the covenant sub-role discovery beat to
dispatch on `thread.target_kind` — `COVENANT_ROLE` → the single parent role;
`GIFT` → iterate `gift.techniques.all()`. For each variant whose `unlock_thread_level`
falls in `(starting_level, new_level]` at the thread's resonance, it grants the
`discovery_achievement` (gamewide-first `Discovery` on the first crossing), unlocks the
`codex_entry`, and sends the `discovery_narrative`. Called from `spend_resonance_for_imbuing`
on every thread advance; also standalone-callable for ceremony-direct testing.

**GIFT thread substrate (#1578):**
- `TargetKind.GIFT` + `Thread.target_gift` FK (PROTECT) — a thread anchored to a Gift.
  One active GIFT thread per `(owner, gift)` for now (multi-resonance chooser is a deferred
  needs-design follow-up).
- **Latent provisioning at CG** — `provision_latent_gift_thread(sheet, gift, *, resonance)`
  (`world/magic/specialization/services.py`) creates the level-0 GIFT thread at
  character-creation finalization, idempotent on `(owner, gift)` and write-once on resonance.
  Wires from `finalize_magic_data` after `CharacterGift` creation, reading the chosen
  `selected_gift_resonance_id` from `draft.draft_data` (frontend picker is a deferred
  needs-design follow-up; falls back to `gift.resonances.first()`).
- **Weaving commits resonance** — `weave_thread(target_kind=GIFT)` commits/chooses a
  resonance onto the existing latent thread rather than creating a new one (validates the
  resonance is in the gift's supported set, else raises `UnsupportedGiftResonanceError`,
  which `WeaveThreadAction` catches into a failure `ActionResult`).
- **`gift_resonances_for(character, gift)`** — the derive-on-read seam replacing direct
  `technique.gift.resonances.all()` reads at the four cast sites (`power_terms`,
  `techniques` ×2, `resonance_environment` ×2). Returns the active GIFT thread's resonance;
  falls back to the authored `Gift.resonances` supported set when no thread exists.
- **`Gift.resonances`** is repurposed to the **supported set** (a weave constraint, not the
  cast-time value) per ADR-0052.

**GIFT anchor cap (#1580):** `compute_anchor_cap` now handles `TargetKind.GIFT`:
`_current_path_stage(thread.owner) × ANCHOR_CAP_GIFT_PER_STAGE` (=10,
`world/magic/services/threads.py`). GIFT threads are always in-action (intrinsic species
gift — added to `_ALWAYS_IN_ACTION_KINDS`). The frontend CG resonance picker remains a
needs-design follow-up.

Proven end-to-end by `world/magic/tests/integration/test_gift_specialization_e2e.py` (#1578):
CG provisioning → base resolve at level 0 → `gift_resonances_for` reads the thread's
resonance → advance past `unlock_thread_level=3` → variant resolve (name/intensity/control
deltas) → discovery beat fires (achievement + codex).

### Path-crossing grant — (Gift × Path) → base technique set (grants.py, services/path_magic.py — #1579)

The complement to the resonance engine above: #1578 specializes *how* a known technique
manifests; #1579 grants *which* techniques you get when you advance into a new Path. This is
ADR-0055's "(Gift × Path) sets the base technique set" leg, realized as an **acquisition** on
advancement (not a derive-on-read), honoring ADR-0053 (advancement *gates*; the grant is a
consequence of Path membership per ADR-0050, not an XP purchase).

| Surface | Role | Notes |
|---|---|---|
| `PathGiftGrant` (`models/grants.py`) | Authored `(path, gift)` → curated `starter_techniques` M2M | Mirrors the `PathRitualGrant` through-model shape. Same authored Gift, different set per path (warrior vs spy from one Pyromancy). A path may grant the character's *existing* gift (new techniques of it) AND a new gift. `clean()` rejects a technique not of the grant's gift; unique per `(path, gift)`. |
| `grant_path_magic(sheet, path) -> PathMagicGrantResult` (`services/path_magic.py`) | Idempotent grant | Mints `CharacterGift` + latent GIFT thread (via the shared `grant_gift_to_character` primitive) + `CharacterTechnique` rows; announces via `announce_access_change` (`AccessChangeSource.PATH_ADVANCEMENT`). Already-owned gifts/techniques are skipped (kept), so the character retains everything and only *gains*. |
| Path-change seam `cross_into_path(sheet, path)` (`world/progression/services/advancement.py`) | Wiring | Writes `CharacterPathHistory` + fires `grant_path_magic`. Used by **both** `cross_threshold` (Audere Majora, levels 5/10/15/20 → PUISSANT+) **and** the **Ritual of the Durance** when it advances into the POTENTIAL stage (level 3 — the "semi-crossing", no Audere Majora). So *which* levels grant is authored data; the level-3 rite reuses the identical grant machinery with no crossing ceremony. |

Proven end-to-end by `world/magic/tests/integration/test_path_crossing_grant_e2e.py`: the real
Audere Majora `resolve_audere_majora_offer → cross_threshold` into the warrior path grants only
the warrior technique set from a shared gift (spy set absent), keeps the character's prior
gift+techniques while deepening that existing gift and adding the new one, and the granted
technique resolves through the specialization path; plus the level-3 Durance semi-crossing
journey. **Out of scope → #1581:** the within-tier gift-thread *strength* growth (imbue-driven
more/stronger techniques) + per-target-kind cost tuning. (The GIFT anchor cap itself —
`path_stage × 10` — shipped in #1580.)

**Species gift extension (#1580) [BUILT & WIRED]:** `SpeciesGiftGrant` (`world/species/models.py`;
natural key `(species, gift)`) is the through-model that links a species to one or more MINOR
`Gift`s with an optional `drawback_condition` FK to `conditions.ConditionTemplate`.
`provision_species_gifts(sheet, *, resonance=None)` (`world/species/services.py`) is called
from `finalize_magic_data` after the Major-gift block; it mints the MINOR `CharacterGift`
(via the shared `grant_gift_to_character` primitive) and applies any drawback idempotently. The
gift's GIFT thread carries a tier-0 `ThreadPullEffect` with `effect_kind=RESISTANCE` that nets
against the drawback vulnerability at the combat-damage seam. `gift_thread_resistance(character,
damage_type) -> int` (services/threads.py) returns the aggregate resistance (passive +
active paid-pull snapshots). See ADR-0050, ADR-0062. E2E:
`world/magic/tests/integration/test_species_gift_e2e.py`.

### Entry-Flourish Declaration (entry_flourish.py, models/endorsement.py — #1140)

Poll-able offer created on a successful Entrance social action; the entrant picks one
claimed resonance to broadcast. Resolves through `create_entry_flourish` (actor self-grant
via the `ResonanceGrant` ledger), scoped to the active scene and idempotent per scene.
The #904 reaction-window framework was evaluated and rejected here — it is peer-only
(`react_to_window` hard-blocks self-reaction); entry flourish (actor self-grant) and
scene-entry endorsement (peer grant) are the two complementary halves of the entrance
moment.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `PendingEntryFlourishOffer` | Poll-able offer awaiting resonance pick; one per character | `character_sheet` FK, `scene` FK (nullable), `created_at`. UniqueConstraint on `character_sheet`. Re-exported from `world/magic/models/__init__.py` |
| `EntryFlourishRecord` | Immutable receipt written by `create_entry_flourish` | `character_sheet` FK, `resonance` FK, `scene` FK (nullable), `granted_amount`, `created_at`. Partial UniqueConstraint `(character_sheet, scene) WHERE scene IS NOT NULL` |

**Services:**
- `maybe_create_entry_flourish_offer(character, scene) -> PendingEntryFlourishOffer | None`
  — called on Entrance action success; skips if already flourished this scene or no
  claimed resonances.
- `resolve_entry_flourish_offer(offer_id, *, resonance_id) -> EntryFlourishResult` —
  two-phase staleness + ownership check then atomic grant + offer deletion.
- `create_entry_flourish(sheet, resonance, *, scene, amount=None) -> EntryFlourishRecord`
  — creates the record and fires `grant_resonance(source=ENTRY_FLOURISH)`; skips
  gracefully on a duplicate `(sheet, scene)`.

**API:**
- `GET /api/magic/entry-flourish/pending/` + `GET .../pending/<id>/` — account-scoped
  read-only inbox.
- `POST /api/magic/entry-flourish/respond/` — body `{offer_id, resonance_id}`.

**Frontend:** `EntryFlourishOfferGate` / `EntryFlourishOfferDialog`
(`frontend/src/magic/components/`), mounted in `SceneDetailPage`; hooks
`usePendingEntryFlourishOffers` / `useRespondToEntryFlourish` in `magic/queries.ts`.

**Config:** `ResonanceGainConfig.entry_flourish_grant` (default 10) — per-flourish amount.

**Exceptions:** `EntryFlourishOfferError`, `EntryFlourishOfferNotFoundError`,
`EntryFlourishOfferStaleError` (all in `exceptions.py`; carry `user_message`).

### Ritual Liturgy (models/liturgy.py — #1352)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `RitualLiturgy` | Player-facing authored words for a Ritual | `ritual` (OneToOne → `Ritual`), `opening_call` TextField |

`RitualLiturgy` holds the officiant's ceremonial language for a Ritual row. Each Ritual
has at most one `RitualLiturgy`. Content here is public and non-spoiler; spoiler-private
ceremony text (e.g. Audere Majora vision/manifestation wording) lives on
`AudereMajoraThreshold` and is kept denormalized from this model.

The Ritual of the Durance is seeded with a `RitualLiturgy` whose `opening_call`
carries the induction invocation. See "Ritual of the Durance" section below.

---

### Ritual of the Durance (#1352)

The **Ritual of the Durance** is the in-person, out-of-combat ceremony that marks
each **within-tier** class-level advance (1→2 … 4→5, 6→7 … 9→10, etc.). Narratively,
"the Durance" is a character's entire life arc; this ceremony is *one rite within it*.
Backend surfaces stay Class/Level-named; the narrative vocabulary is surface-only.

**Advancement gate.** The character must meet the authored `ClassLevelUnlock` requirements
for the next level. `LegendRequirement` + `ClassLevelUnlock` accumulate the character's
legend total and gate advancement — legend qualifies; **legend is never spent**, and there
is **no XP spend** for a within-tier advance.

**Tier-crossing refusal.** Steps that would cross a tier boundary (5→6, 10→11, 15→16,
20→21) are blocked by `TierBoundaryRequiresCrossing`. Those crossings are **Audere Majora**
territory only. The two advancement paths share `apply_class_level_advance` and
`AbstractClassLevelAdvancement` (see `docs/systems/progression.md`).

**Session mechanics.** The rite dispatches through the existing multi-participant
`RitualSession` machinery (`participation_rule=INDUCTION`). Flow:
`draft_session` → inductees `accept_session` → `fire_session` calls
`advance_class_level_via_session`. Several inductees may advance in one scene; each
receives its own `ClassLevelAdvancement` receipt, and the session records the **scene**
and the **declaration interaction** (the testament pose).

**Officiant.** Must be a higher-level character (`officiant_sheet.current_level > target_level`)
on the **same Path lineage** as the inductee (same Path, or the officiant evolved from the
inductee's current Path). PC or academy NPC. Validated by `assert_can_officiate`.

**Testament.** The inductee's `participant_kwargs["testament"]` string is their player-composed
oration. The service appends a citation of their qualifying `LegendEntry` deeds (up to 3,
by `base_value`) and posts the combined text as a POSE in the active scene via `_post_testament`.
**No `LegendEntry` is minted** for within-tier advances. No resonance plumbing is added
(a Ritual of the Durance is just a Scene → normal social-scene benefits apply). No boons are stacked on
the inductee.

**Factory.** `RitualOfTheDuranceFactory` (`src/world/magic/factories.py`) seeds the
`Ritual` row (SERVICE / INDUCTION, `min_participants=2`, no upper-bound). The `@post_generation`
hook creates the companion `RitualLiturgy` via `RitualLiturgyFactory`.

**Telnet follow-up (#1700).** `RitualSession` dispatch is REST-only today
(`POST /api/magic/ritual-sessions/draft/`, `accept/`, `fire/`). Telnet drivability — a
`CmdRitual` adapter for the Ritual of the Durance (mirroring the covenant adapters) — is
tracked in **#1700** (under the telnet-E2E umbrella #1328).

---

### Audere & Audere Majora (models/audere.py, audere_majora.py, models/renown_config.py)

**`RenownAwardConfig`** (`models/renown_config.py`) — abstract base (SharedMemoryModel)
shared by `DramaticMomentType` and `AudereMajoraThreshold`. Carries `magnitude`,
`risk`, `reach` (nullable override), and `archetypes` M2M to `societies.PhilosophicalArchetype`.
Provides `as_renown_award_kwargs() -> dict`. When `risk == NONE`, `fire_renown_award`
creates no `LegendEntry` — the invariant that gates deed creation.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `AudereMajoraThreshold` | One row per boundary level (5/10/15/20). Inherits `RenownAwardConfig`. | `boundary_level`, `target_stage`, `minimum_intensity_tier` FK, `minimum_warp_stage` FK, `requires_active_audere`, `deed_title` (public — non-spoiler), `vision_text`/`manifestation_text` (spoiler-private — DB-only) |
| `PendingAudereMajoraOffer` | Poll-able Crossing offer, one per character | `character_sheet` FK, `threshold` FK |
| `AudereMajoraCrossing` | Irreversible receipt of a completed crossing (inherits `AbstractClassLevelAdvancement`) | `character_sheet` FK, `threshold` FK, `chosen_path` FK, `scene` FK, `declaration_interaction` FK, `level_before`, `level_after`, `legend_entry` OneToOneField → `societies.LegendEntry` (related_name `audere_majora_crossing`; null when no deed was minted) |

**Deed minting.** `cross_threshold` calls `_mint_crossing_deed(crossing)` after writing
the receipt. This resolves the character's primary persona, calls `fire_renown_award`
(full renown event), records every persona present in the scene as `WITNESSED` via
`grant_deed_knowledge` + `scene_witness_personas`, and stores the resulting
`LegendEntry` on `crossing.legend_entry`. Deed title uses `threshold.deed_title` when
authored, falling back to a generic public-fact composition; ceremony text is never used.
No deed is created when `threshold.risk == NONE` or when the sheet has no primary
persona (`legend_entry` stays null).

### Dramatic Moment Tagging (#545 / #1139)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DramaticMomentType` | Staff-authored lookup inheriting `RenownAwardConfig`. Describes a taggable scene moment category. | `label`, `description`, `resonance` FK, `resonance_amount` (default 15), `per_scene_cap` (default 1), plus inherited `magnitude`/`risk`/`reach`/`archetypes` |
| `DramaticMomentTag` | Per-event record of a staff tag on a character in a scene | `moment_type` FK, `character_sheet` FK, `scene` FK (nullable/SET_NULL), `tagged_by` FK AccountDB (PROTECT), `interaction` FK (nullable/SET_NULL, `db_constraint=False` — partitioned table), `interaction_timestamp` (denormalized), `tagged_at` |

**Admin:** `DramaticMomentTypeAdmin` — full CRUD (staff author the catalog); `DramaticMomentTagAdmin` — read-only for provenance audit.

**Context fields on scenes serializers:** `SceneDetailSerializer.viewer_can_gm` (bool — True when the requesting user is the scene's GM, owner, or staff; controls GM control visibility); `InteractionSerializer.dramatic_moment_tags` (list — tags anchored to the pose; drives the interaction badge); `SceneParticipationSerializer.dramatic_moment_count` (int — per-participant tally in the scene).

### Other

| Model | Purpose |
|-------|---------|
| `AnimaRitualPerformance` | Historical record of ritual performances |
| `Reincarnation` | Tracks character reincarnation events |

### Effect Palette (#1584) [BUILT & PROVEN]

Nine castable effects seeded idempotently by `ensure_effect_palette_content()`
(`src/world/magic/effect_palette_content.py`). Each effect is a full technique +
condition + flow + trigger bundle wired via `get_or_create` throughout. The entry
point calls all nine sub-builders:

| Effect | Condition name | Handler / mechanism | Note |
|--------|---------------|---------------------|------|
| Summon Spirit | Summoning | `summon_ally_on_condition` adapter → `summon_ally` | CONDITION_APPLIED; creates an ALLY `CombatOpponent` (ADR-0059) |
| Aegis Field | Aegis Field | `absorb_pool` (priority 10) | DAMAGE_PRE_APPLY; mutation-only; overflow lands |
| Mirror Ward | Mirror Ward | `reflect_damage` (priority 20) | DAMAGE_PRE_APPLY; mutation-only; bounces via `bypass_pre_apply` |
| Phase Step | Phase Step | `blink_dodge` (priority 30) | DAMAGE_PRE_APPLY; mutation-only; moves bearer on success |
| Phase Jump | Phase Jump | `move_position_on_condition` adapter | CONDITION_APPLIED; placeholder destination (follow-up: #1584 note) |
| Barricade | Barricade | `create_obstacle_on_condition` adapter | CONDITION_APPLIED; placeholder destination (follow-up: #1584 note) |
| Ghostform | Ghostform | intangibility category only (`grants_intangibility=True`) | `ConditionCategory`; intangibility gate via `is_untargetable` |
| Earthmeld | Earthmeld | intangibility category only (1-round duration) | `ConditionCategory`; as Ghostform |
| Force Grip | Force Grip | `move_position_on_condition` adapter (ENEMY target) | CONDITION_APPLIED; placeholder destination (follow-up: #1584 note) |

**Placeholder-destination follow-up:** Phase Jump, Barricade, and Force Grip embed
`destination_position_id=0` at seed time; runtime destination selection (player
picks a position) is deferred to a follow-up issue.

**Handlers and adapters** (`src/world/magic/services/effect_handlers.py`):

| Function | Kind | Purpose |
|----------|------|---------|
| `move_position(*, payload)` | direct handler | Move bearer's `ObjectDB` to a target `Position` |
| `create_obstacle(*, payload)` | direct handler | Create a blocking `Obstacle` at a target `Position` |
| `absorb_pool(*, payload)` | reactive handler (prio 10) | Drain `absorb_remaining` buffer; sets `payload.amount=0` when fully absorbed; overflow lands |
| `reflect_damage(*, payload)` | reactive handler (prio 20) | Pay `reactive_anima_cost`; resolve attacker from `payload.source.ref`; bounce via `bypass_pre_apply`; set `payload.amount=0` |
| `blink_dodge(*, payload)` | reactive handler (prio 30) | Pay `reactive_anima_cost`; move bearer; set `payload.amount=0` |
| `summon_ally(*, payload)` | direct handler | Create a `CombatOpponent` with `allegiance=ALLY`, `summoned_by=caster` |
| `move_position_on_condition(*, payload, destination_position_id)` | CONDITION_APPLIED adapter | Thin wrapper → `move_position` |
| `create_obstacle_on_condition(*, payload, ...)` | CONDITION_APPLIED adapter | Thin wrapper → `create_obstacle` |
| `summon_ally_on_condition(*, payload, threat_pool_id, ...)` | CONDITION_APPLIED adapter | Bridges `ConditionAppliedPayload` (`.target` as bearer/caster) → `summon_ally` |
| `init_absorb_buffer(*, payload, buffer)` | CONDITION_APPLIED handler | Seeds `ConditionInstance.absorb_remaining` on Aegis Field application |

**Reactive interceptor cost pattern** (ADR-0060):

- `ConditionTemplate.reactive_anima_cost` — anima spent per fire; can't pay → fizzle,
  attack lands.
- `ConditionTemplate.upkeep_anima_per_round` — drained each round by
  `drain_reactive_upkeep` on `COMBAT_ROUND_STARTING`.
- All three reactive handlers are **mutation-only** (no `CANCEL_EVENT` child step).
  A `CANCEL_EVENT` child fires unconditionally — even on the fizzle path — so an
  unaffordable defense would still cancel the attack. That bug was caught and fixed
  by the reactive E2E tests (#1584 Task 16).

### Resonance-Environment Interaction (universal path — 2026-05-16)

**Design:** `docs/architecture/resonance-environment-universal-path.md`

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `AffinityInteraction` | 9 directed (caster, place) affinity pairing rows; tuning table | `source_affinity` FK, `environment_affinity` FK, `valence` (ALIGNED/OPPOSED), `kind` (AMPLIFY/REJECT/REPEL/CORRUPT), `severity`, `consequence_pool` FK (nullable — OPPOSED backfire pool) |
| `ResonanceEnvironmentConfig` | Singleton with scalar tuning coefficients | `backfire_base_difficulty`, `backfire_difficulty_per_magnitude` |
| `ResonanceAlignmentBoonTier` | Authored: which buff `ConditionTemplate` an ALIGNED pairing grants at or above a magnitude band | `affinity_interaction` FK (must be ALIGNED diagonal row), `min_magnitude`, `condition_template` FK. `UniqueConstraint(affinity_interaction, min_magnitude)`. `clean()` validates ALIGNED valence. Tier selection is Python `max()` over `interaction.cached_alignment_boon_tiers` — no `Meta.ordering` |

`AffinityInteraction.consequence_pool` (added migration `magic/0064`) is a nullable FK to
`actions.ConsequencePool`. `None` = inert (CORRUPT-deferred or no authored content yet).
The pool's `Consequence` rows carry `ConsequenceEffect(effect_type=APPLY_CONDITION)` entries
mapping `CheckOutcome` tiers to the existing Tempered Against Light / Singed / Burning /
Hallowed Burn / Cast Disrupted `ConditionTemplate`s.

Cached accessors (never query directly):
- `AffinityInteraction.objects.interaction_for(source, environment)` — loads all 9 rows into
  an in-memory map once; primitive carries the resolved row out as `effect.interaction`.
- `AffinityInteraction.cached_alignment_boon_tiers` — `cached_property` returning
  `list(self.alignment_boon_tiers.all())`.
- `ResonanceAlignmentBoonTier.objects.boon_condition_templates()` — cached set of distinct
  boon `ConditionTemplate`s; used by the movement service's clear step.
- `ConsequencePool.cached_consequences` — `cached_property` returning the resolved
  `Consequence` list; the OPPOSED service reads this, never `pool.entries.filter(...)`.

---

## Key Methods and Properties

### CharacterAura

```python
# Get a character's aura (OneToOne relationship)
aura = character.aura  # May raise DoesNotExist if not created

# Get dominant affinity
aura.dominant_affinity  # Returns AffinityType enum (CELESTIAL, PRIMAL, or ABYSSAL)

# Validation: percentages must sum to 100
aura.celestial = Decimal("50.00")
aura.primal = Decimal("30.00")
aura.abyssal = Decimal("20.00")
aura.save()  # Calls full_clean() automatically
```

### Thread (new Spec A model)

```python
# The populated FK, picked by target_kind
thread.target   # Returns the Trait / Technique / ObjectDB / RelationshipTrackProgress / RelationshipCapstone

# Resolved level cap (per Spec A §2.4)
from world.magic.services import (
    compute_anchor_cap,
    compute_path_cap,
    compute_effective_cap,
)
cap = compute_effective_cap(thread)   # min(path_cap, anchor_cap)
```

### Per-Character Handlers

```python
# character is a Character typeclass instance
threads = character.threads.all()                    # list[Thread] (cached, retired_at filtered)
threads_for_res = character.threads.by_resonance(resonance)
passive_hp = character.threads.passive_vital_bonuses("MAX_HEALTH")

balance = character.resonances.balance(resonance)    # int
lifetime = character.resonances.lifetime(resonance)  # int
cr = character.resonances.get_or_create(resonance)   # CharacterResonance (lazy create)
most_recent = character.resonances.most_recently_earned()   # used by Mage Scars

active_pulls = character.combat_pulls.active()       # list[CombatPull]
pulls_in_enc = character.combat_pulls.active_for_encounter(encounter)
pulled_hp = character.combat_pulls.active_pull_vital_bonuses("MAX_HEALTH")

# After any mutation that changes these collections, call:
character.threads.invalidate()
character.resonances.invalidate()
character.combat_pulls.invalidate()
```

### Technique

```python
technique.tier        # Derived from level: 1-5=T1, 6-10=T2, etc.
technique.intensity   # Base power stat
technique.control     # Base safety/precision stat
technique.anima_cost  # Base anima cost to activate
technique.target_type # ActionTargetType: SELF / SINGLE / AREA / FILTERED_GROUP (default SINGLE)
```

### Resonance-Environment Services

All three live in `world/magic/services/resonance_environment.py`.

```python
from world.magic.services.resonance_environment import (
    magical_profile,
    resonance_environment_for_cast,
    refresh_resonance_alignment,
    clear_resonance_alignment,
)

# Magic-capability gate — derived, never asserted or stored.
# Returns CharacterAura if the sheet's character has one (every finalized PC);
# returns None if Quiescent (NPC, not-yet-finalized character).
aura = magical_profile(character_sheet)   # CharacterAura | None

# OPPOSED backfire — called from the technique-use orchestrator ("Step 10",
# world/magic/services/techniques.py) immediately after accrue_corruption_for_cast.
# Gated by magical_profile. Resolves consequence pool → select_consequence_from_result
# → apply_resolution. Emits no event, runs no flow.
resonance_environment_for_cast(
    caster_sheet=sheet,     # CharacterSheet (extension model, not ObjectDB)
    room_profile=profile,   # RoomProfile (evennia_extensions)
    technique=technique,    # Technique | None
)

# ALIGNED presence buff — called from Character.at_post_move.
# Idempotently clears any prior alignment buff, evaluates presence-time resonance,
# and applies the highest matching ResonanceAlignmentBoonTier buff ConditionTemplate.
refresh_resonance_alignment(character_sheet=sheet)

# Explicit clear — called from at_pre_move(destination=None) and at_post_unpuppet.
clear_resonance_alignment(character_sheet=sheet)
```

**Integration points:**
- **Cast pipeline:** `resonance_environment_for_cast` is "Step 10" in
  `world/magic/services/techniques.py`, sibling of `accrue_corruption_for_cast`.
- **Movement pipeline:** `refresh_resonance_alignment` / `clear_resonance_alignment` are
  wired in `typeclasses/characters.py` via `Character.at_post_move`, `at_pre_move`, and
  `at_post_unpuppet`.

---

## Common Queries

### Check if character has a gift

```python
from world.magic.models import CharacterGift

# By gift name
has_pyromancy = CharacterGift.objects.filter(
    character=character,
    gift__name="Pyromancy"
).exists()

# Get all character's gifts
character_gifts = CharacterGift.objects.filter(character=character).select_related("gift")
```

### Get character's aura or create default

```python
from world.magic.models import CharacterAura

aura, created = CharacterAura.objects.get_or_create(
    character=character,
    defaults={
        "celestial": Decimal("0.00"),
        "primal": Decimal("80.00"),
        "abyssal": Decimal("20.00"),
    }
)
```

### Get character's techniques from a specific gift

```python
from world.magic.models import CharacterTechnique

techniques = CharacterTechnique.objects.filter(
    character=character,
    technique__gift__name="Shadow Majesty"
).select_related("technique", "technique__gift")
```

### Get all threads for a character

```python
# Preferred: use the cached handler (single query, select_related on all targets).
threads = character.threads.all()

# Direct ORM (bypasses the handler cache):
from world.magic.models import Thread

threads = Thread.objects.filter(
    owner=character_sheet,
    retired_at__isnull=True,
).select_related(
    "resonance__affinity",
    "target_trait",
    "target_technique",
    "target_facet",
    "target_relationship_track",
    "target_capstone",
    "target_covenant_role",
    "target_sanctum_details__feature_instance",
)
```

### Grant and spend resonance currency

```python
from world.magic.services import (
    grant_resonance,
    spend_resonance_for_imbuing,
    spend_resonance_for_pull,
    preview_resonance_pull,
    weave_thread,
    accept_thread_weaving_unlock,
    compute_thread_weaving_xp_cost,
)

# Earn (Spec C will author the gain surfaces that call this):
cr = grant_resonance(
    character_sheet=sheet,
    resonance=resonance,
    amount=3,
    source="social_scene_endorsement",
    source_ref=scene.pk,
)
assert cr.balance >= 3 and cr.lifetime_earned >= 3

# Imbue a Thread (greedy advancement through developed_points -> level):
result = spend_resonance_for_imbuing(
    character_sheet=sheet,
    thread=thread,
    amount=20,
)
# result is a ThreadImbueResult dataclass with the starting/ending level,
# dp remaining, and blocked_by reason if the bucket stopped early.

# Pay XP at an XP-locked boundary (level 20/30/40 on the internal scale):
from world.magic.services import cross_thread_xp_lock
cross_thread_xp_lock(character_sheet=sheet, thread=thread, level=20)

# Pull (combat or ephemeral):
pull_result = spend_resonance_for_pull(...)

# Weave a new thread (requires the unlock):
new_thread = weave_thread(
    character_sheet=sheet,
    resonance=resonance,
    target_kind="TRAIT",
    target=trait_instance,
    name="Grandfather's patience",
)

# Acquire a ThreadWeavingUnlock (in-band or out-of-band pricing):
cost = compute_thread_weaving_xp_cost(sheet, unlock)
accept_thread_weaving_unlock(character_sheet=sheet, unlock=unlock, teacher=tenure_or_none)
```

### Preview a pull without mutating state

```python
from world.magic.services import preview_resonance_pull

preview = preview_resonance_pull(
    character_sheet=sheet,
    resonance=resonance,
    tier=2,
    threads=[thread_a, thread_b],
    combat_encounter=encounter_or_none,
)
# preview.resonance_cost / preview.anima_cost / preview.affordable
# preview.resolved_effects — list of scaled per-effect snapshots
```

### UI helper queries

```python
from world.magic.services import (
    imbue_ready_threads,
    near_xp_lock_threads,
    threads_blocked_by_cap,
)

ready = imbue_ready_threads(sheet)      # threads whose bucket is near a level-up
near = near_xp_lock_threads(sheet)      # threads approaching an XP-locked boundary
capped = threads_blocked_by_cap(sheet)  # threads blocked by path or anchor cap
```

### Get intensity tier for a value

```python
from world.magic.models import IntensityTier

# Get the highest tier at or below the intensity value
tier = IntensityTier.objects.filter(
    threshold__lte=intensity_value
).order_by("-threshold").first()
```

---

## API Endpoints

All endpoints require authentication. Base URL: `/api/magic/`

### Lookup Tables (Read-Only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/styles/` | GET | List technique styles |
| `/effect-types/` | GET | List effect types |
| `/restrictions/` | GET | List restrictions |
| `/facets/` | GET | List facets (hierarchical) |
| `/gifts/` | GET | List all gifts |
| `/gifts/{id}/` | GET | Gift detail with nested techniques |

**Note:** The `/thread-types/` endpoint was removed as part of Spec A —
the legacy ThreadType lookup no longer exists.

### Character Data (Filtered to owned characters)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/character-auras/` | GET/POST | Character aura data |
| `/character-resonances/` | GET | Character resonances (balance + lifetime_earned per Spec A §2.2; create/delete via service functions, not REST mutations) |
| `/character-gifts/` | GET/POST/DELETE | Character's acquired gifts |
| `/character-anima/` | GET/POST/PATCH | Character anima pool |
| `/character-anima-rituals/` | GET/POST/PATCH/DELETE | Character's rituals |
| `/character-facets/` | GET/POST/PATCH/DELETE | Character facet assignments |
| `/techniques/` | GET/POST/PATCH | Character techniques |
| `/techniques/author/` | POST | Author a technique via `AuthorTechniqueAction`; 201/400/403 |
| `/techniques/price/` | POST | Dry-run budget breakdown (read-only) |

### Mage Scars (renamed from Magical Scars — §7.2 display-only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pending-alterations/` | GET | List open Mage Scars for the requesting account |
| `/pending-alterations/{id}/` | GET | Retrieve one Mage Scar |
| `/pending-alterations/{id}/resolve/` | POST | Resolve via library pick or author-from-scratch |
| `/pending-alterations/{id}/library/` | GET | Tier-matched library template list |

### Threads, Pull Preview, Rituals, ThreadWeaving (Spec A §4.5)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/threads/` | GET | List threads owned by requesting account (staff see all); excludes retired |
| `/threads/` | POST | Weave a new thread. Body must include `character_sheet_id`; serializer delegates to `weave_thread` |
| `/threads/{id}/` | GET | Thread detail with anchor + resonance |
| `/threads/{id}/` | DELETE | Soft-retire (stamps `retired_at`; row remains for historical references) |
| `/thread-pull-preview/` | POST | Read-only preview; body `{character_sheet_id, resonance_id, tier, thread_ids[], action_context?}`; returns resonance/anima cost + `affordable` + `resolved_effects[]` |
| `/rituals/perform/` | POST | Dispatch a Ritual via `PerformRitualAction.run()` (`actions/definitions/ritual.py`, key `perform_ritual`; shared with telnet `CmdRitual`, #1331). Body `{character_sheet_id, ritual_id, kwargs, components[]}`; Imbuing takes `{thread_id}` in kwargs (view resolves into Thread instance) |
| `/teaching-offers/` | GET | Read-only list of `ThreadWeavingTeachingOffer` records |

**API conventions.**
- All mutations that need a character context require an explicit
  `character_sheet_id` — no implicit first-sheet selection.
- Service functions raise typed exceptions with `user_message` properties
  (`AnchorCapExceeded`, `InvalidImbueAmount`, `ResonanceInsufficient`,
  `WeavingUnlockMissing`, `XPInsufficient`, `RitualComponentError`). Views
  surface those messages as HTTP 400 detail (never raw `str(exc)`).
- `ThreadViewSet` uses `IsThreadOwner` permission plus ownership filtering
  in `get_queryset()`; staff see all.

**Endpoints removed by Spec A.** `/thread-types/`, `/thread-journals/`,
`/thread-resonances/` — the underlying models were deleted. Journaling now
flows through relationships-app writeups for relationship-anchored threads,
and `JournalEntry.related_threads` M2M for all thread kinds.

### Dramatic Moment Tagging (#1139)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dramatic-moment-types/` | GET | Read-only catalog of authored `DramaticMomentType` rows; unpaginated; authenticated |
| `/dramatic-moment-tags/` | POST | Tag a character's dramatic moment (gated by `IsSceneGMOrOwnerOrStaff`); body: `character_sheet`, `moment_type`, optional `scene`, optional `interaction`; service errors → 400 with `user_message` |
| `/dramatic-moment-tags/` | GET | List tags; filterable by `character_sheet` and `scene`; paginated |

No `DELETE` — tags are immutable provenance records.

---

## Frontend Integration

### Types
`frontend/src/character-creation/types.ts`
- `Affinity`, `Resonance`, `Gift`, `GiftListItem`, `AnimaRitualType`
- `AFFINITY_TYPES` constant: `['celestial', 'primal', 'abyssal']`
- `AffinityType` type alias

### API Hooks
`frontend/src/character-creation/queries.ts`
```typescript
// Fetch all affinities
const { data: affinities } = useAffinities();

// Fetch all resonances
const { data: resonances } = useResonances();

// Fetch all gifts (list view)
const { data: gifts } = useGifts();

// Fetch anima ritual types
const { data: ritualTypes } = useAnimaRitualTypes();
```

### Components
- `MagicStage.tsx` - Character creation magic selection UI

---

## Integration Points

### With Traits System (Future)
Magic intensity calculations will factor in trait values:
```python
# Example pattern (not yet implemented)
from world.traits.services import get_trait_value
willpower = get_trait_value(character, "willpower")
modified_intensity = base_intensity + (willpower * modifier)
```

### With Flows (Future)
Magic effects will execute via the flow engine:
```python
# Example pattern (not yet implemented)
from flows.engine import execute_flow
execute_flow("cast_power", context={
    "caster": character,
    "power": power,
    "target": target,
    "intensity": effective_intensity,
})
```

---

## Notes

- **Aura validation** - CharacterAura enforces percentages sum to 100 via `clean()`
- **Thread uniqueness (Spec A)** - One thread per (owner, resonance, target_kind, target_*) combination, enforced via per-kind partial `UniqueConstraint`s. Soft-retired threads (retired_at set) don't block new ones at the uniqueness level but are filtered out of handler caches and API listings.
- **Thread PROTECT FKs** - All typed `target_*` FKs use `on_delete=PROTECT`. Anchors cannot be deleted while threads reference them. This is why `CharacterThreadHandler.passive_vital_bonuses` doesn't need an anchor-in-scope runtime filter.
- **SANCTUM room anchor** - `target_sanctum_details` (FK to `SanctumDetails`) is the leveled room anchor. Cap = `sanctum.feature_instance.level × 10`. Thread is pull-applicable (in-sanctum boost) while the character is in the Sanctum's room. Bare ROOM `target_kind` was removed.
- **Sanctum ops are TELNET+WEB** (#1497) — 7 REGISTRY Actions (`sanctum_install` / `sanctum_homecoming` / `sanctum_purging` / `sanctum_weave` / `sanctum_dissolve` / `sanctum_absorb` / `sanctum_sever`) in `actions/definitions/sanctum.py`. `CmdSanctum` (`commands/sanctum.py`) is the namespaced telnet face; the web `SanctumViewSet` dispatches the same Actions. Dissolution is a soft-delete: `RoomFeatureInstance.dissolved_at` marks dissolved sanctums; `.active()` excludes them; SANCTUM threads are soft-retired on dissolution. One-personal-per-founder enforced in service layer (excluding dissolved rows).
- **Currency has no cap** - `CharacterResonance.balance` grows freely; the strategic tension is over allocation, not over a ceiling.
- **Pull-cost tuning surface** - `ThreadPullCost` rows hold per-tier numbers; the cost *formula shape* lives in `spend_resonance_for_pull`. Both the model docstring and service docstring cross-reference this split.
- **SoulTetherConfig tuning** - `SoulTetherConfig` singleton (pk=1) holds all Soul Tether tuning knobs (sineating costs, rescue budgets/thresholds). Read via `get_soul_tether_config()`. Staff-tunable via admin.
- **SOUL_TETHER_DISSOLVED** - Emitted by `dissolve_soul_tether` in `flows/constants.py` after bond dissolution.
- **CharacterSheet.get_tether_strain_stage()** - Returns the Sineater's current Tether Strain stage. Used by sineating offer payloads.
- **SharedMemoryModel** - All lookup tables + identity rows use Evennia's identity-map cache
- **Affinity/Resonance are domain models** - First-class models in this app with optional OneToOne links to `ModifierTarget` for modifier integration
- **Techniques are player-created** - Unlike lookup tables, techniques are unique per character
- **Cantrips are technique templates** - Staff-curated, produce real Techniques at CG finalization
- **Intensity/Control** - Base stats on techniques. Runtime values modified by resonance, combat, audere, and thread pull effects
- **No healing** - Shielding yes, restoration no. Healing is counter to the escalation-based combat design
- **Technique.target_type** — cardinality field (SELF/SINGLE/AREA/FILTERED_GROUP). The *relationship*
  (who is eligible: SELF/ALLY/ENEMY) is derived at runtime by `derive_target_relationship`, not stored.
- **ConditionCategory.alters_behavior** — behavior-altering categories (compulsion, charm, fear) require
  the target's consent; capability/stat categories resolve immediately including on other PCs.
- **apply_technique_conditions** lives in `world/magic/services/condition_application.py` — shared by
  both combat and standalone cast paths. `AppliedConditionResult` (its return type) lives in
  `world/conditions/types.py`, the neutral condition layer both combat and magic import directly.
- **CombatRoundActionTarget** — new combat join table for AoE/multi-target technique actions (AREA and
  FILTERED_GROUP). SINGLE/SELF actions continue to use `CombatRoundAction.focused_opponent_target`.
- **TechniqueDraft** — in-progress design workbench (one per CharacterSheet). Draft child rows
  (`TechniqueDraftCapabilityGrant`, `TechniqueDraftDamageProfile`, `TechniqueDraftAppliedCondition`)
  share abstract payload bases with the committed `Technique*` rows — no JSON, all queryable columns.
- **AuthorTechniqueAction** (key `"author_technique"`) — the single author seam; telnet
  `CmdTechnique` and the web `POST .../author/` both converge on it. Staff-only via telnet today;
  player self-service is a deferred `needs-design` follow-up.

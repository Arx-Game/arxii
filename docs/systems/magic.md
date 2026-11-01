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
    AffinityShare,       # one affinity row + its percent
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
    VitalBonusTarget,        # MAX_HEALTH, DAMAGE_TAKEN_REDUCTION, DEATH_SAVE,
                             # KNOCKOUT_RESIST, PERMANENT_WOUND_RESIST — plus
                             # SHIP_HULL / SHIP_HANDLING / SHIP_ARMAMENT, which
                             # name a VESSEL's stats, not a person's, and are
                             # read only by world/ships/sanctum_bonus.py off
                             # TargetKind.SANCTUM rows (#2736, ADR-0188).
                             # SHIP_VITAL_BONUS_TARGETS is the membership set;
                             # passive_vital_bonuses returns 0 for them.
    RitualExecutionKind,     # SERVICE, FLOW
    PendingAlterationStatus, # OPEN, RESOLVED, STAFF_CLEARED
    MagicActivity,           # 20 kinds of magical roll that add staff-mapped
                             # skills (#4450): ANIMA_RITUAL, TECHNIQUE_LEARNING,
                             # RITUAL_WORKING, SUSTAINING_MAGIC, DISPELLING,
                             # MAGICAL_TREATMENT, SOULFRAY_RESILIENCE,
                             # RESISTING_LOSS_OF_SELF, SOUL_TETHER_RESCUE,
                             # COURT_PETITION, FURY_CONTROL, MOON_CONTROL,
                             # ENDURING_HOSTILE_RESONANCE, FEEDING_RESTRAINT,
                             # SENSING_MAGIC, WORSHIP_RITE, INVOCATION, CEREMONY,
                             # COMPANION_BINDING, DREAM_PERIL
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
| `TechniqueStyle` | How a **practitioner** works magic (Manifestation, Subtle, Prayer). A property of the caster's Path, not of the technique (#2700, ADR-0167) — the same catalog `Technique` is an Incantation cast by a Path of Tomes character and a Manifestation cast by a Path of Steel one. Reverse of `classes.Path.style` via `related_name="paths"`. `cast_concealment` (#2710, ADR-0170) is the style's difficulty floor for being noticed while casting — 0 (default) is overt and skips detection entirely; see "Cast observation" below. A Gift may set its own style (`Gift.style`), which wins over the caster's Path style for `cast_concealment` on that gift's techniques (capability gating still reads the caster's Path) (#2905, ADR-0199). | `name`, `description`, `cast_concealment` |
| `StyleCapabilityRequirement` | A capability the **caster** needs to work magic in this style (#2700) — e.g. Incantation requires `speech >= 1`. Caster-scoped sibling of `TechniqueCapabilityRequirement`; both are evaluated by `technique_performable` against `get_effective_capability_value`. | `style` FK, `capability` FK (`conditions.CapabilityType`), `minimum_value`. Natural key `(style, capability)` |
| `IntensityTier` | Power effect thresholds | `name`, `threshold`, `control_modifier` (0 or more: a tier only adds control, #4740), `description` |
| `Restriction` | Limitations that grant power bonuses (DESIGN kind) or a price a caster attaches to their own hold of a technique (PRICE kind, #4099, ADR-4099) | `name`, `description`, `power_bonus`, `kind` (`RestrictionKind`: DESIGN/PRICE), `creation_point_cost` (PRICE only, nullable; blank = not offered in creation), `cast_narration` (PRICE only; joins the cast narration) |
| `Facet` | Flat imagery/symbolism vocabulary — every facet is a peer (Wolf, Silk, Scythe, Red). The Category > Subcategory > Specific hierarchy and its `parent` self-FK were removed by #3776 (ADR-0289): depth made a node's mechanical reach uneven, so a facet's reach is now the same whichever one you pick. Owner-agnostic — characters bind facets via `Motif`, a `WorshippedBeing` via `worship.BeingFacet`, an `ItemTemplate` via `inherent_facets`, all from this one shared pool. Typed by many hands, so it drifts; three guards share one spelling rule, `services.facets.facet_key` (#4197, ADR-4197): a picker shows the near-matches (`GET /api/magic/facets/near/`) before it offers to create, `POST /api/magic/facets/` (staff) answers a spelling that already resolves with `matched: true` instead of a near-duplicate, and the admin action **Merge into...** (`merge_facets`) repoints every binding to a survivor and retires the losers as aliases. | `name` (unique), `description` |
| `FacetAlias` | Another spelling that routes to a facet (#4197): the names a merge retired, and any spelling staff add by hand. Resolved by the pickers' search and the create endpoint; never shown to a player. Content (`CONTENT_MODELS`, natural key `name`); cascades with its facet. | `name` (unique), `facet` FK |
| `FacetEffectBonus` | A facet's always-on bonus to one maneuver effect (#4815, slice 4 of #4783): the facet names the effect, whatever its thread's resonance ("Wolf: +2 Charge: damage"). Counted by `passive_facet_bonuses` while the character wears an item carrying the facet and has a FACET thread on it: `amount x item quality x attachment quality x max(1, shown thread level)` per worn item facet. Authored in the Facet admin's inline; `merge_facets` moves the rows. Content (`CONTENT_MODELS`, natural key `(facet, target)`). | `facet` FK (CASCADE), `target` FK `ModifierTarget` ("maneuver_effect" category only), `amount` (non-zero); unique per `(facet, target)` |
| `Gift` | Thematic collections of techniques | `name`, `description`, `resonances` (M2M to `Resonance` — the **supported set**: a weave constraint, not the cast-time value; the cast reads the character's GIFT-thread resonance via `gift_resonances_for`, ADR-0052), `creator` (FK to CharacterSheet), `kind` (`GiftKind`: `MAJOR` = the one CG-chosen gift, `MINOR` = shared/acquirable; ADR-0050), `parent` (self-FK, PROTECT, `related_name="children"` — the umbrella gift this one hangs beneath; see "Gift lineage" below, #2891, ADR-0192) |
| `Affinity` | Celestial / Primal / Abyssal rows; `Affinity.objects.get_celestial_affinity()` / `get_primal_affinity()` / `get_abyssal_affinity()` are the canonical getters | `name`, `corruption_coefficient` (integer tenths of corruption per cast tick), optional OneToOne `modifier_target`. Listed read-only at `GET /api/magic/affinities/` (`AffinityViewSet`) |
| `Resonance` | Identity resonance tags | `name`, `affinity` FK, `opposite` self-OneToOne, optional `modifier_target` OneToOne. Listed read-only, unpaginated, at `GET /api/magic/resonances/` (`ResonanceViewSet`, `ResonanceSerializer` with `affinity_name`; `?affinity=<pk>` filters): the CG Gift stage's Resonance picker reads it (#4665) |

**Note:** `Affinity` and `Resonance` are proper first-class domain models in
this app (each with an optional OneToOne link back to `mechanics.ModifierTarget`
for modifier-system integration). The old `ThreadType` lookup was deleted as
part of the Resonance Pivot — relationship flavor is now carried by
`relationships.RelationshipType` (the label catalogue; renamed from
`RelationshipTrack` in #3957).

### Character State

| Model | Purpose | Key Fields | Relationship |
|-------|---------|------------|--------------|
| `CharacterAura` | A character's aura. The percentages live in `CharacterAuraShare` rows (one per aura and affinity, `percent` 0-100, summing to 100; see `cached_shares`, `percent_for(affinity)`, `dominant_affinity`) | `character`, `glimpse_story`, `glimpse_state` | OneToOne via `character.aura` |
| `CharacterResonance` | Per-character per-resonance identity + currency (Spec A §2.2) | `character_sheet` FK, `resonance` FK, `balance`, `lifetime_earned`, `claimed_at`, `flavor_text` | FK via `character_sheet.resonances` (unique_together: (character_sheet, resonance)) |
| `CharacterGift` | Acquired gifts | `gift`, `acquired_at` | FK via `character.character_gifts` |
| `CharacterTechnique` | Known techniques; the character's hold carries their own personalization of it (#4099, ADR-4099) | `technique`, `acquired_at`, `source` (FK mechanics.ModifierSource, nullable — set for granted techniques), `custom_name` (display only, never a lookup key; blank = the catalog name), `custom_description` (blank = the catalog description), `price` (FK `Restriction`, PRICE kind only, nullable), `early_form` (FK `TechniqueVariant`, nullable; bought in creation before the gift thread reaches its level) | FK via `character.character_techniques` |
| `CharacterAnima` | Magical energy pool | `current`, `maximum`, `last_recovery` | OneToOne via `character.anima` |
| personal anima ritual (a `Ritual` of `execution_kind=SCENE_ACTION` + its `RitualCheckConfig`; the old `CharacterAnimaRitual` model is gone) | The character's recovery ritual: `author_account` is the player, `check_config` holds `check_type`, `target_difficulty`, `stat`, `skill`, `resonance` | `get_character_anima_ritual(character)` (`services/anima.py`) |

**Anima band vocabulary (#1446).** `ANIMA_BANDS` (`constants.py`) is a descending
`(min_ratio, label)` tuple (PLACEHOLDER labels pending Apostate rewrite — brimming /
vibrant / steady / dimmed / guttering / spent), mirroring `vitals.constants
.WOUND_DESCRIPTIONS`. `anima_band_for(current, maximum) -> str` resolves the qualitative
word (player-facing anima is narrative, never a raw number); `CharacterAnimaSerializer.band`
(a `SerializerMethodField`) surfaces it on `/character-anima/`, and the same helper backs
the web Status tab and the `sheet/status` telnet section.

**CharacterResonance reshape note.** Prior to Spec A, `CharacterResonance`
carried `scope`, `strength`, `is_active`, and FK'd `ObjectDB`. Those fields
were dropped (no readers beyond Mage Scars, which now uses
`character.resonances.most_recently_earned()`), `character` was re-FK'd to
`CharacterSheet`, and `balance` + `lifetime_earned` were added. Row existence
replaces the old `is_active` flag. `CharacterResonanceTotal` (denormalized
aggregate) was deleted — aura recompute (`recompute_aura`) reads
`CharacterResonance.lifetime_earned` grouped by affinity directly. Distinction
effects targeting a resonance-category `ModifierTarget` no longer write a
`CharacterModifier` row at all (#1834) — `create_distinction_modifiers` and
`update_distinction_rank` (`world/mechanics/services.py`) skip them and instead call
`reconcile_distinction_resonance_grants` (`world/magic/services/distinction_resonance.py`),
which reads the `DistinctionResonanceGrant` authoring sidecar and grants real
`CharacterResonance`/`ResonanceGrant` currency. The `resonance` `ModifierCategory` is
still live for non-distinction sources (facet/mantle/motif-coherence passive bonuses via
`equipment_walk_total`).

### Techniques (Player-Created Abilities)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Technique` | A specific magical ability within a Gift | `name`, `gift` (FK), `effect_type` (FK to EffectType), `restrictions` (M2M), `level`, `intensity`, `control`, `anima_cost`, `creator`, `target_type`, `reach`, `archetype_alignment` (#2529 — `RoleArchetype` choices, default CROWN, migration-seeded from `effect_type.category`: attack→sword, defense→shield, else→crown; which SWORD/SHIELD/CROWN blend axis of an engaged covenant role boosts this technique's cast). Natural key `(gift, name)`, backed by `unique_technique_gift_name` (#2474 — `name` alone is not globally unique; lore reuse or a player-crafted technique can share a name across gifts). Unique per `(gift, name)` |

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
See `derive_target_relationship` in `world/magic/services/targeting.py`, and
"Technique effect summary" below for the display-side block that reads it.

**Intensity and Control:** These are base/static values on the technique. Runtime casting
values (after resonance bonuses, combat escalation, audere states) are tracked by a
separate casting handler. When intensity exceeds control at runtime, effects become
unpredictable and anima cost spikes. If anima cost exceeds the character's pool, the
excess deals damage to the caster.

- **Authored outcome lines (#3554, ADR-0270):** `hit_narration` / `miss_narration`
  (`TextField`, blank = default sentence). `{actor}` and `{target}` are required and are
  filled by literal replacement. The authored text becomes the HEAD of the Narrator OUTCOME
  line; the damage figure, tail clauses and suffix clauses stay machine-appended
  (`render_action_outcome_narration(hit_text=, miss_text=)`). Admin-only authoring: the
  player builder (`TechniqueDesignSerializer`) does not accept them. Validated by
  `Technique.clean()` via `world.magic.narration.validate_outcome_narration`.

### Gift lineage — one thread reaches its ancestors' techniques (#2891, ADR-0192) [BUILT & WIRED]

`Gift.parent` (self-FK, `on_delete=PROTECT`, `related_name="children"`) hangs a gift
beneath an umbrella gift. **The invariant: holding a gift reaches the techniques of that
gift and of every ancestor, and the character's GIFT thread on the held gift is the thread
for all of them.** A Vulpi character holds ONE `CharacterGift` and threads ONE GIFT thread,
and that thread reaches both the Vulpi-specific techniques and the shared Khati ones.

The shape exists because the alternative — two `SpeciesGiftGrant` rows, the shipped
Vampire/Dhampir pattern (#2692) — gives the character two threads, and thread level rises
through the Rite of Imbuing, which charges AP per rite (`_charge_imbue_ap`,
`services/resonance.py`) plus XP at locked boundaries (`cross_thread_xp_lock`,
`services/threads.py`). Every Khati, Elf, Infernal and Vampire would pay twice for what a
Human pays once.

**`SpeciesGiftGrant.inheritable` is a different axis and stays.** `inheritable` walks the
*species* chain (`Species.parent`); `Gift.parent` walks the *gift* chain. `Dhampir.parent =
Vampire`, so Vampire's grant still propagates to Dhampir. Both are needed.

**Model surface** (`models/gifts.py`) — mirrors `Species.lineage` / `Species.codex_entries`
(`world/species/models.py`, PR #2897) rather than inventing a second walk:

| Property | Returns |
|---|---|
| `Gift.lineage` | This gift then every ancestor, nearest first. Cycle-safe via a seen-set (a `parent` cycle is a data defect, not a modelled state). |
| `Gift.lineage_ids` | `frozenset` of `lineage` pks — membership tests without re-walking. |
| `Gift.inherited_techniques` | Own techniques first, then each ancestor's, nearest first, de-duplicated by pk. **The pool read.** |
| `Gift.cached_techniques` | Unchanged: this gift's OWN techniques. It is the `Prefetch(to_attr="cached_techniques")` target for the gift API — do not widen it. |

**Resolver** — `resolve_owned_gift(sheet, gift) -> Gift | None`
(`services/gift_acquisition.py`) returns the gift the character actually holds that reaches
`gift`: `gift` itself when directly held, otherwise the held descendant whose lineage
contains it. It is the single answer to both "does the learner own this?" and "which gift's
thread and cap govern this technique?" — the two questions have the same answer and must not
drift apart.

**Lineage-aware call sites:**

| Site | Behaviour |
|---|---|
| `learn_technique` (`services/technique_acquisition.py`) | Ownership resolves through `resolve_owned_gift`; cap and count run against the *held* gift. |
| `charge_and_learn` (`services/gift_acquisition.py`) | Same. Critically, a child-gift holder is NOT treated as not-having-the-gift, so the teaching/Academy path demands no `GiftUnlock` receipt and mints no second `CharacterGift` or thread. |
| `count_techniques_for_gift` | Counts `technique__gift_id__in=gift.lineage_ids` — one thread, one cap; inherited techniques are not a second budget. |
| `get_technique_cap_for_gift` / `_gift_thread_depth` | Unchanged; always called with the held gift, whose thread exists. |
| `gift_threads_for(character, gift)` (`specialization/services.py`) | GIFT threads *covering* `gift` — on `gift` itself or on a descendant. A direct hold sorts first. |
| `gift_resonances_for` | Reads `gift_threads_for`, so an inherited technique manifests at the character's thread resonance instead of the ancestor's authored supported set. |
| `_resolve_technique_variant` | Reads `gift_threads_for` via `_gift_thread_for_variant`, so an inherited technique specializes at the child thread's level. |
| `crossing/handlers._parents_for` | GIFT branch returns `thread.target_gift.inherited_techniques` — variant discovery on a child thread sees the inherited techniques. |
| `societies/handlers.acquired_techniques_for` | A granted gift carries its ancestors' techniques with it. |

**Deliberately NOT lineage-aware** (verified against code, #2891):

- `cg_catalog.get_gift_options` / `get_technique_options` — availability comes from authored
  `PathGiftGrant.starter_techniques` rows (restricted by `TraditionGiftGrant.special_techniques`)
  at *technique* granularity, never from `gift.techniques`, so a child gift whose pool is
  authored inherited techniques is already included.

**A technique is offered only on its Paths; a Tradition's list restricts** (#4555,
ADR-4555-A). `PathGiftGrant.starter_techniques` is the list of techniques for that Path and
Gift. `TraditionGiftGrant.special_techniques` no longer adds to a pool: a technique no
Tradition grant lists is open to every Tradition, and one listed by one or more is open only
to those Traditions. The pool for Tradition T on Path P picking Gift G is the techniques on
P's list for G that no Tradition grant lists, or T's does (`get_technique_options` returns
the two halves as `pool` and `tradition`). `get_gift_options` offers every Major Gift G whose
pool holds a takeable technique; a grant row for (T, G) is not needed, since a row now marks a
Gift T favors rather than one it allows (#4659). The restriction half is
`cg_catalog.tradition_listings` / `offered_to_tradition`, shared with Academy training
(`_technique_available_to_learner`, through `get_technique_options`) and `grant_path_magic`,
which skips a technique the character's active Tradition may not take. The
`tradition-techniques-on-a-path` Required content row lists a technique a Tradition grant
lists that no Path's list holds, since it is offered nowhere.

**An empty path pool is missing content, not a design case** (ruled on #3682, ADR-0283).
Since #4555 a tradition special no longer carries a gift onto a path that offers nothing
for it; there will never be a gift a path offers nothing for, so the empty pool is an
authoring gap. The `path-gift-starter-pools`
required-content sentinel (`web/admin/tuning/required_content.py`, #3712) reports each
such `(path, gift)` pair and names the traditions it leaks through — 8 pairs across 17
combinations at the time it was added. A `TraditionGiftGrant` carrying no specials is
deliberately never reported: that is a legitimate authored state meaning "this tradition
favors this gift and adds no extras of its own" (#4659), and it creates no availability of
its own. The `cg-gift-pools-takeable` row lists each path and Major Gift no active tradition
can take there, and counts tradition and path pairings left with no Gift at all.

**"Non-empty" means a technique a player can take (#4545).** `cg_technique_queryset`
(`cg_catalog.py`) is the one CG readiness rule: never an ultimate, an `action_template`
set unless `include_unready`, no active requirement row when `exclude_gated`.
`cg_takeable_techniques()` is that rule as the technique picker applies it (ready,
ungated). `get_technique_options`, `get_species_technique_options` and `get_gift_options`
all filter through it, so a gift is offered only when its pool holds a technique the
picker will show (before #4545 `get_gift_options` checked only the template, and a pool of
gated techniques offered a gift with an empty picker behind it). The Required content
dashboard calls the same function: `path-gift-starter-pools` counts only takeable
starters, `cg-gift-pools-takeable` lists each (active tradition, active Prospect path,
gift) combination whose pool holds none (a path with no grant for the gift is an empty
pool, as `get_gift_options` reads it), and `cg-techniques-cast-effect` (Tuning) lists pooled techniques
`technique_is_underspecified` flags. On the 2026-10-21 production dump no technique had a
template, so every gift was hidden while the old starter-pool row read complete.
- `CharacterTechniqueHandler._state` (`handlers.py`) — reads explicit `CharacterTechnique`
  rows. Once an inherited technique is learned the row exists. Inheritance is an
  acquisition-eligibility concern, not an inventory one.
- `GiftSerializer.techniques` — still the gift's own techniques (paired with the annotated
  `technique_count`). Inert today because no authored gift has a parent yet; widening it is
  display work that belongs with the content PR that first makes a parented gift visible.

**Authoring:** `parent` is set in `GiftAdmin` (autocomplete) or by natural key in a lore
fixture (`"parent": ["Khati"]`). `magic.gift` is already in `CONTENT_MODELS` with
`NaturalKeyMixin(fields=["name"])`, so `parent` exports and loads with no new wiring — but a
self-FK natural key resolves at load time, so **the umbrella gift must appear before its
children in the fixture file.**

Content (#2764) authors the gifts, techniques and grant rows; this issue ships the mechanism
only.

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
| `TechniqueDraft` | One-per-CharacterSheet in-progress design workbench | `character_sheet` FK (unique, `related_name="technique_draft"`), `name`, `description`, `gift` FK, `effect_type` FK, `intensity`, `control`, `anima_cost`, `level`, `target_type`, `reach`, `restrictions` M2M |
| `TechniqueDraftCapabilityGrant` | Draft payload — capability grant row (inherits `AbstractCapabilityGrant`) | `draft` FK |
| `TechniqueDraftDamageProfile` | Draft payload — damage profile row (inherits `AbstractDamageProfile`) | `draft` FK |
| `TechniqueDraftAppliedCondition` | Draft payload — applied condition row (inherits `AbstractAppliedCondition`) | `draft` FK |

**Draft services** (`services/technique_draft.py`):
- `get_or_start_draft(character) -> TechniqueDraft` — creates or returns the active draft.
- `discard_draft(character)` — deletes draft and all payload children.
- `set_draft_fields(draft, **fields)` — typed field updates (name, description, gift,
  effect_type, level, intensity, control, anima_cost, target_type, reach).
- `add_draft_restriction` / `remove_draft_restriction` — restriction M2M management.
- `add_draft_capability_grant` / `add_draft_damage_profile` / `add_draft_applied_condition`
  and `remove_*` counterparts — payload row management.
- `draft_to_design(draft) -> TechniqueDesignInput` — validates completeness; raises
  `TechniqueDraftIncomplete` on missing required fields, and its subclass
  `TechniqueDraftMoraleRemovesNothing` when the draft's morale row removes no morale (#4619).

**Shared validation gate** (`services/technique_builder.py`):
- `validate_design_for_character(design, policy, character)` — gift-ownership check; the single
  source of truth for the gate (telnet + web call it); raises `GiftNotOwned`.

**Exceptions** (in `exceptions.py`): `NoActiveTechniqueDraft`, `TechniqueDraftIncomplete`,
`TechniqueDraftMoraleRemovesNothing`, `UnknownTechniqueVocab`, `UnknownGift`, `GiftNotOwned`.

**Telnet workbench** — `CmdTechnique` (`commands/technique.py`, key `"technique"`,
`cmd:perm(Builder)` — staff/GM only). Subcommands: `draft`, `show`, `set`, `restrict`,
`grant`, `damage`, `condition`, `price`, `author` (dispatches `AuthorTechniqueAction` with
`StaffPolicy`), `discard`. Registered in `commands/default_cmdsets.py`.

**Exposure:** staff/GM-only. Player self-service is a deferred `needs-design` follow-up.

### CG Starter Gift/Technique Catalog (#2426, content pipeline #2474)

The CG magic stage picks a staff-authored catalog `Gift` + `Technique`s directly
(`get_gift_options`/`get_technique_options`, `world/magic/services/cg_catalog.py`),
and `finalize_magic_data` only *links* them
(`world/character_creation/services.py:_finalize_gift_and_techniques`) — no `Gift`
or `Technique` row is created at CG time.

**The catalog is content, not seed data (#2474).** `Resonance`, `Gift`, `Technique`,
`PathGiftGrant`, and `TraditionGiftGrant` all carry natural keys (`magic.gift`,
`magic.pathgiftgrant`, etc. in `CONTENT_MODELS`, `core_management/content_export.py`)
and ship as arx2-lore fixtures, loaded by `core_management.content_fixtures
.load_world_content()` — the same pipeline that loads every other authored-content
model, not a bespoke seed function. `Technique`'s natural key is `(gift, name)`
(`unique_technique_gift_name`), since `name` alone is not globally unique across
gifts. The formerly-in-repo `seed_starter_gift_catalog()` /
`StarterGiftCatalogResult` (#2426 Task 7) are retired; a fresh dev database now
requires `CONTENT_REPO_PATH` to seed at all (`ContentError` if unset/missing — see
"Content-vs-config boundary" below and ADR-0142). Tests that need a catalog without
a real content-repo checkout use `MagicContent.create_starter_gift_catalog()`
(`world/seeds/game_content/magic.py`, a synthetic factory-built stand-in) or the
enriched `stub_content_root()` fixture (`world/seeds/tests/content_stub.py`).

The pre-#2426 design used a staff-curated `Cantrip` starter-technique-template
model that CG finalization minted into a new `Technique`; that model and its API
plumbing were fully removed in #2426 Task 8.

### Guided Glimpse Story (#2427) [BUILT & WIRED]

The Glimpse is the narrative of a character's first magical awakening
(`CharacterAura.glimpse_story`, prose). #2427 replaced the old always-visible
freeform textarea with a guided, tag-driven flow: pick authored tags across
five narrative axes, then write (or keep writing) the prose, with curated
distinction offers surfaced along the way. #2611 added the TRIGGER axis
(what *caused* the awakening) and path-gated tag filtering. #3675 retired the
tag's own `GlimpseTagDistinctionSuggestion` pairing table: a tag's distinctions are
now `world.character_creation.models.DistinctionOffer` rows (`chapter=glimpse`,
`glimpse_tag=<this tag>`), authored and read the same way every other CG chapter's
offers are (`world.character_creation.offers`, `docs/systems/character_creation.md`).

**A tag's offers are a self-healing cached property, fed cold via Prefetch, cleared
via related_cache_fields (ADR-0298).** `GlimpseTag.offers` is a `PrunedCachedProperty`
(`evennia_extensions/cached_property.py`, `models/glimpse.py`) returning a plain
`list[DistinctionOffer]` — active rows for the tag, ordered `sort_order, id`,
`select_related("distinction")`. Every reader (the CG API serializer's `get_offers`,
`GlimpseTagAdmin`'s change-form preview) reads `tag.offers` directly, no wrapper.
`CGGlimpseTagViewSet.get_queryset()` batches the whole page in one query via
`Prefetch("distinction_offers", ..., to_attr="offers")` — sanctioned onto a genuine
`cached_property` with explicit write-side invalidation wired (ADR-0298), unlike the former `GlimpseTagOffersHandler` wrapper this replaced (#3816 Task 9).
`DistinctionOffer.related_cache_fields = ["glimpse_tag", "origin_choice",
"schooling_line", "enemy_reason", "appearance_section"]` clears the property's cache
on every offer save/delete, for the offer's current and, when reassigned, previous
related objects as well.

**Models** (`models/glimpse.py`):

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `GlimpseTag` | Authored catalog choice, one per axis. Content model — `CONTENT_MODELS` (`magic.glimpsetag`), lore-repo authored, no factory-seeded catalog | `axis` (`GlimpseTagAxis`), `name`, `slug` (natural key), `description`, `example`, `sort_order`, `is_active`, `paths` (M2M to `classes.Path`, empty = all paths; #2611) |
| `CharacterGlimpseTag` | A character's chosen tag. Instance data — never exported | `aura` FK (`CharacterAura`, `related_name="glimpse_tags"`), `tag` FK (PROTECT); unique per `(aura, tag)` |

**Enums + config** (`constants.py`):

- `GlimpseTagAxis` — the five guided steps: `TRIGGER` (single-select, what
  caused the awakening; #2611), `TONE` (single-select), `CONSEQUENCE`
  (multi-select), `WITNESS` (Witness & Secrecy, multi-select), `SENSORY`
  (Sensory & Discovery, multi-select, renders as prose prompts rather than hard
  tags in the writing step — authored SENSORY tags remain possible).
- `GlimpseState` — `NOT_STARTED` / `TAGS_ONLY` (tags chosen, story unwritten) /
  `COMPLETE`. A cache of prose+tag truth, never written directly.
- `GLIMPSE_AXIS_CONFIG: dict[GlimpseTagAxis, GlimpseAxisRule]` — per-axis
  `multi`/`prose_prompt` rendering rule, keyed by `GlimpseTagAxis`.

**`CharacterAura.glimpse_state`** (`models/aura.py`) — a `GlimpseState` CharField,
default `NOT_STARTED`. A service-maintained cache of the prose+tag rows (mirrors
the `CharacterDistinction.secret` FK-presence precedent): never written directly
outside `world.magic.services.glimpse`.

**`CharacterDistinction.from_glimpse`** (`world/distinctions/models.py`) —
nullable FK to `CharacterAura`, `SET_NULL`. The FK's presence IS the
provenance state (mirrors `CharacterDistinction.secret`): when set, the
distinction was born in the character's Glimpse. Deleting the aura simply
drops the provenance, never the distinction.

**Services** (`services/glimpse.py`) — the single write path; every mutation
recomputes `glimpse_state` so it never drifts from the prose+tag truth:

- `refresh_glimpse_state(aura: CharacterAura) -> GlimpseState` — recomputes and
  persists `glimpse_state` from prose + tag rows (COMPLETE if prose is
  non-blank, else TAGS_ONLY if any tag row exists, else NOT_STARTED).
- `set_glimpse_tags(aura, tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis) -> None`
  — replaces the character's chosen tags for one axis (transactional). Enforces
  the axis's select-arity (`GLIMPSE_AXIS_CONFIG`) and that every tag belongs to
  `axis`; an empty `tags` clears the axis. Calls `refresh_glimpse_state`.
- `set_glimpse_prose(aura, text: str, *, edited_by=None) -> None` — writes
  `glimpse_story` through `character_sheets.services.update_profile_text`
  (`ProfileTextField.GLIMPSE`, #4224), so every rewrite keeps a `ProfileTextVersion` on the
  true profile, then calls `refresh_glimpse_state`.
- `link_distinction_to_glimpse(character_distinction: CharacterDistinction, aura: CharacterAura) -> None`
  — sets `from_glimpse`; raises `ValidationError` if the distinction and aura
  belong to different characters.
- `unlink_distinction_from_glimpse(character_distinction: CharacterDistinction) -> None`
  — clears `from_glimpse`.

**CG finalize wiring** (`world/character_creation/services.py`,
`finalize_magic_data`), after creating `CharacterAura`, two `draft_data` keys
are consumed through the glimpse services above (never written directly to the
aura/tag rows): `glimpse_tag_ids` (list of `GlimpseTag` ids, grouped by axis
and passed to `set_glimpse_tags` per axis), `glimpse_story` (passed to
`set_glimpse_prose`, defaults to `""`). Distinction-to-Glimpse provenance is no
longer read from a separate `glimpse_linked_distinction_ids` list (#3675): every
picked distinction whose `offer_ids` name a `DistinctionOffer` with
`glimpse_tag` set gets `link_distinction_to_glimpse` called on it, via one query
over `DistinctionOffer.objects.filter(pk__in=<picked offer ids>,
glimpse_tag__isnull=False)`. **Frontend note:** `GlimpseSection.tsx` never writes
`draft_data.glimpse_linked_distinction_ids` -- that key and its manual-link fallback
are retired; a Glimpse-chapter distinction pick syncs immediately through
`useSyncDistinctions` (see `ChapterOffers`/`GlimpseAxes`,
`frontend/src/character-creation/CLAUDE.md`), so `offer_ids` always carries the
`DistinctionOffer` provenance this backend read depends on.

**API surfaces:**

- **CG catalog** — `GET /api/character-creation/glimpse-tags/`
  (`CGGlimpseTagViewSet`, `world.character_creation.views`, read-only,
  unpaginated, filterable by `?axis=` and `?path_id=<N>`). The `path_id` filter
  (#2611) excludes tags whose `paths` M2M is non-empty and does not contain the
  given path, used by the CG flow to hide path-restricted trigger tags (e.g.
  "Patron Chose You" is Path of the Chosen only). Omitting `path_id` returns all
  tags (post-CG editor mode). Global authored catalog, not draft-dependent, so
  the same endpoint also backs the post-CG "finish your glimpse later" surface.
  Each row embeds its `offers` (prefetched `DistinctionOffer` rows opened by
  this tag, #3675) via `CGGlimpseTagSerializer`.
- **Aura actions** — four `@action`s on `CharacterAuraViewSet`
  (`world/magic/views.py`): `POST .../set-glimpse-tags/` (body
  `{axis, tag_ids[]}`, validates tags exist/are active before calling
  `set_glimpse_tags`), `POST .../set-glimpse-prose/` (body `{text}`),
  `POST .../link-glimpse-distinction/` and `POST .../unlink-glimpse-distinction/`
  (body `{character_distinction_id}`, scoped to the aura's own character).
  All four return the updated `CharacterAuraSerializer` payload; validation
  errors surface as HTTP 400 detail, never raw `str(exc)`.

**Sheet payload** (`world/character_sheets/`) — `AuraData` (`types.py`) gained
`glimpse_story`, `glimpse_state`, `glimpse_tags: list[GlimpseTagEntry]`, and
`can_finish_glimpse` (privileged-only — the "finish later" affordance, True
when the requester may edit this aura and `glimpse_state != COMPLETE`).
`DistinctionEntry` gained `is_from_glimpse` (`from_glimpse_id is not None`) so
the sheet can badge/link distinctions born in the Glimpse.

**Frontend** - one shared, purely presentational guided flow, and a folio-grammar CG
mount that no longer shares its markup (#3675 fix round 1; see
`frontend/src/magic/CLAUDE.md` and `frontend/src/character-creation/CLAUDE.md` for the
full contract):

- `GlimpseFlow` (`frontend/src/magic/components/glimpse/GlimpseFlow.tsx` +
  `glimpseTypes.ts`) - accordion of axis steps (TONE single-select,
  CONSEQUENCE/WITNESS multi-select; axes with zero catalog tags don't render a
  step), SENSORY as toggle chips inside the always-visible story textarea, and a
  manual link fallback for a character's *existing* `CharacterDistinction` rows
  (`GlimpseEditorDialog`'s own linking, unrelated to CG offer picks). No
  queries/mutations inside, purely props-in/callbacks-out. This is now the sheet's
  live-editor mount only; the CG mount stopped using it (#3675 fix round 1, a
  demo-fidelity defect: the single-open accordion hid two axes at a time).
- `GlimpseSection` (`frontend/src/character-creation/components/gift/GlimpseSection.tsx`)
  - the CG mount, a thin state binder: draft reads, `updateDraft` writes
  `draft_data.glimpse_tag_ids`, the "skip for now" deferral, and the copy query.
  Renders `GlimpseAxes` (`frontend/src/character-creation/components/gift/GlimpseAxes.tsx`),
  the folio-grammar per-axis layout (every axis visible at once, one `ChapterOffers`
  sub-block per chosen tag), which owns the distinction picks itself; they sync
  immediately through `useSyncDistinctions`, never through a `draft_data` list.
  Prose stays on `GiftStage`'s `register('glimpse_story')`.
- `GlimpseEditorDialog` (`frontend/src/magic/components/glimpse/GlimpseEditorDialog.tsx`)
  — the "finish later" editor on the own-character sheet, opened from
  `SpellbookTab`'s aura card, gated on `isMyCharacter && aura.can_finish_glimpse`.
  Writes through the four aura actions above.

**Out of scope (verified against code, not deferred by accident):** no
mechanics hooks off tag picks, no LLM involvement anywhere in the flow, no new
privacy axis beyond the existing WITNESS tags, and no authored `GlimpseTag`/
glimpse-chapter `DistinctionOffer` rows ship with this repo (lore-repo content,
authored later) — the flow renders gracefully with an empty catalog (axes with
no tags simply don't render a step).

### Content-vs-config boundary in the dev seed (#2474, ADR-0142; generalized #2724, ADR-0171)

`seed_dev_database()` (`world/seeds/database.py`) now sequences: (1) resolve
`CONTENT_REPO_PATH` via `core_management.content_repo.resolve_content_root()` —
raises `ContentError` immediately if unset/missing, before anything else runs; (2)
run every config prerequisite in `world.seeds.config_prerequisites
.CONFIG_PREREQUISITES` (`dict[str, Callable[[], None]]`, 12 entries as of #2724,
shaped like `world.seeds.clusters.CLUSTER_SEEDERS`) — rows the code names by string
literal, e.g. `world.magic.seeds_cast.ensure_technique_cast_content()`, since
lore-repo `Technique` fixtures FK the shared "Technique Cast" `ActionTemplate` and
the content load's own deferred-retry loop can't conjure a config row the
content/grid load itself never creates; (3) `load_world_content()`; (4) the
`CLUSTER_SEEDERS` loop. `technique_cast` runs FIRST inside the registry for exactly
that FK-by-natural-key reason; the other 11 entries (fatigue, fury, spread, vitals,
conditions, dreams, alterations, locations, combat_stats, projects, ships) cover
config rows other systems' service functions name by literal — see
`docs/adr/0171-code-required-content-rows-are-declared-config.md` for the full
rationale and the rejected alternatives (de-registering the model, a name-pattern
export filter, a `CONTENT_MODELS`-write linter). NPC trainer seeds
(`world/npc_services/seeds.py`) resolve their starter
technique picks as `(gift_name, technique_name)` pairs scoped by gift
(`Technique.objects.filter(gift__name=..., name=...)`, never a bare `name__in=`
lookup — see `Technique`'s natural key above) and raise `ContentError` when none of
the pairs resolve, so a missing/stale catalog fails loudly rather than silently
seeding an empty trainer. The admin seed view (`web/admin/seed_views.py`) catches
`ContentError` and surfaces it as a normal form error; the CLI (`arx manage seed`,
`core_management/management/commands/seed.py`) lets it traceback loudly by
design — no silent skip, no synthetic in-repo fallback catalog. See ADR-0142 for
the rationale and the rejected alternative.

### Standalone Casting — Shared Template + Per-Character Check (#1306) [BUILT & WIRED]

`create_technique` (`services/technique_builder.py`) defaults `action_template` to the
shared **Technique Cast** `ActionTemplate` seeded by `seeds_cast.ensure_technique_cast_content()`,
so every technique (including CG starter-catalog techniques) is castable standalone. Staff may override
per-technique via the FK. Key surfaces:

| Surface | Location | Purpose |
|---------|----------|---------|
| `ensure_technique_cast_content()` | `seeds_cast.py` | Idempotent seed: shared ActionTemplate + fallback CheckType + "Magic: Technique Cast" ConsequencePool |
| `get_standalone_cast_template()` | `seeds_cast.py` | Retrieves the shared ActionTemplate; called by `create_technique` default |
| `ensure_character_magic_check_type(character_sheet, *, stat, skill)` | `seeds_checks.py` | Synthesizes a per-character `CheckType` (pattern: `character_magic_check_type_name()`) for that character's stat + skill |
| `get_character_cast_check(character)` | `services/anima.py` | Resolves the per-character check type for cast resolution |
| `resolve_cast_check(character, technique)` | `services/magic_skills.py` | The one resolver every cast path calls (#4450, replaces `resolve_cast_check_type`): returns a `CastCheck(check_type, extra_traits)` or None. Check type precedence is unchanged (ADR-0096); `extra_traits` holds the technique skill term |
| `get_character_anima_ritual(character)` | `services/anima.py` | Retrieves the character's personal SCENE_ACTION `Ritual` (their anima ritual) |
| `perform_anima_ritual(character_sheet, scene)` | `services/anima.py` | The once-per-scene roll of the character's anima ritual plus `apply_anima_ritual_outcome` (Soulfray eased first, then anima by `AnimaRitualBudgetAward` tier). Reached by `PerformRitualAction`'s SCENE_ACTION branch (#4451) |
| `provision_player_anima_ritual(...)` | `services/anima.py` | Points `RitualCheckConfig.check_type` at the per-character check so ritual and technique casts share the same roll |
| `ensure_technique_catalog_content()` | `seeds_cast.py` | Idempotent seed: curated catalog of consequence-pool flavors (children of the base pool) + matching ActionTemplates |
| `resolve_cast_action_template()` | `services/technique_builder.py` | Resolves a chosen catalog pool id (or `None`) to the ActionTemplate a Technique's `action_template` should point at |

Cast resolution (`world/scenes/cast_services.py:_resolve_cast`) passes the caster's personal
check into `start_action_resolution` via the `check_type` override (optional kwarg added to
`src/actions/services.py`). No schema migration — all seeded via `ensure_technique_cast_content()`.

**Performing the anima ritual (#4451).** `PerformRitualAction.execute()` branches on
`execution_kind == SCENE_ACTION` before component and pool handling and calls
`_perform_anima_ritual`: the ritual must be the performer's own
(`get_character_anima_ritual`), the scene is the one at their location
(`get_active_scene`), and `perform_anima_ritual` does the roll and outcome. The four
`MagicError` refusals (`NoRitualConfigured`, `CharacterEngagedForRitual`,
`RitualScenePrerequisiteFailed`, `RitualAlreadyPerformedThisScene`) come back as a
failure `ActionResult` carrying their `user_message`. Web: the Perform button on the
SCENE_ACTION `RitualCard` posts `/api/magic/rituals/perform/`, whose response carries
`message` and `result {outcome, anima_recovered, severity_reduced, soulfray_resolved}` for
this kind. Telnet: `ritual anima` (or `ritual <the ritual's name>`; a SCENE_ACTION name
resolves only for its author). The scene-action-request resolver
(`anima_ritual_action.py`) is a second path to the same `apply_anima_ritual_outcome`.
Journey: `src/integration_tests/test_performing_the_anima_ritual_journeys.py`.

**Anima ritual name collisions are resolved silently, not surfaced (#2724).**
`provision_player_anima_ritual` defaults a player's anima ritual name to
`"<first name>'s Anima Ritual"`, and `Ritual.name` is `unique=True` — two characters
sharing a first name used to raise `IntegrityError` and roll back the entire CG
finalization. `_uniquify_ritual_name(base)` (`services/anima.py`) appends `" (2)"`,
`" (3)"`, etc. until the candidate is free (truncating the base so the suffixed
result still fits `max_length`); it does a plain `SELECT` and is NOT race-safe by
itself (a concurrent finalization can pass the check for the same candidate before
either commits). `provision_player_anima_ritual` closes that window with a bounded
retry: up to `_RITUAL_NAME_ATTEMPTS` (5) attempts, each in its own nested
`transaction.atomic()` savepoint so a losing `IntegrityError` rolls back only that
savepoint and leaves the surrounding `finalize_magic_data` atomic block usable for
the next attempt. Exhausting every attempt is deliberately left to raise rather than
silently skip ritual creation for the player.

**Consequence-pool catalog (#1320) [BUILT & WIRED]** — beyond the single shared "Magic: Technique Cast"
pool above, a curated **catalog** of pool "flavors" exists as single-depth children of
that base pool (`ConsequencePool.objects.filter(parent=<base pool>)`, seeded by
`ensure_technique_catalog_content()`). A technique's author may pick one instead of the
default: the web technique builder or telnet `technique set consequence_pool=<id>`. (CG
finalization does NOT expose this pick — every catalog technique already carries its own
authored `action_template`; see `src/world/character_creation/CLAUDE.md`'s "Magic
finalization" section, #2426.) `resolve_cast_action_template()` turns the
choice (or `None`) into the `ActionTemplate` the Technique's `action_template` FK is set
to; every catalog `ActionTemplate` shares the base template's `check_type`/`pipeline`/
`target_type`, so only the consequence pool actually varies.

**Combat offense catalog (#1995) [BUILT & WIRED]** — the PHYSICAL sibling of the catalog
above. `world.combat.seeds_offense` mirrors the same base-pool + curated-catalog shape for
the combat "Melee Attack" `ActionTemplate` (seeded by
`world.combat.factories.wire_melee_attack_action_template`, which now wires
`consequence_pool` onto the base "Combat: Melee Offense" pool instead of leaving it `None`):
`ensure_melee_offense_pool()` seeds the 3 canonical tiers; `ensure_combat_offense_catalog_content()`
seeds the curated flavors ("Brutal", "Precise") as children ActionTemplates ("Melee Attack:
Brutal" / "Melee Attack: Precise"). `resolve_cast_action_template(consequence_pool_id,
action_category=...)` now branches by category: PHYSICAL validates the chosen pool against
`get_combat_offense_catalog()`; every other category still validates against
`get_technique_cast_catalog()` — a magic flavor chosen for a PHYSICAL technique (or vice
versa) raises `InvalidConsequencePoolChoice`. The catalog listing endpoint
(`GET /api/magic/consequence-pool-catalog/`) returns both catalogs' entries in one flat list
(the picker doesn't filter by `action_category` client-side, so the listing doesn't either).
**This catalog applies to standalone casts only** — combat ROUND resolution never reads
`ActionTemplate.consequence_pool` (see "Combat" doc's note on `wire_melee_attack_action_template`
and ADR-0130).

**Beat-authoring parity (#3562) [BUILT & WIRED]** - the stories app's beat form needs
every authored `ConsequencePool`, not just the two curated technique-cast/combat-offense
catalogs above. `GET /api/magic/consequence-pool-catalog/?scope=beat`
(`ConsequencePoolCatalogFilter.filter_scope`, `ConsequencePoolScope` TextChoices in
`world.magic.constants`) widens the listing to every `ConsequencePool` in the game,
ordered by name; `?scope=technique` (also the default with no `scope` param) is a no-op -
the viewset's narrow-catalog `get_queryset` already applies. `GET
/api/magic/consequence-pool-catalog/{id}/` (`retrieve`) is always unfiltered - any pool,
catalog member or not - and routes through `ConsequencePoolDetailSerializer` instead of the
list row: `entries` is built from `resolve_pool_consequences` (parent inheritance plus the
pool's own entries minus exclusions), each with `outcome_tier`, `effect_types`, and
`character_loss`, so `ConsequencePoolPicker` (`frontend/src/stories/components/
ConsequencePoolPicker.tsx`) can preview what actually fires before a GM selects a pool for
a beat's success/failure/expired consequences.

### Magical skills (#4450, ADR-4450) [BUILT & WIRED]

Every magical roll adds skills that staff choose in admin; no skill is named in code. A roll keeps
its own check type as the base and passes the skills as `extra_traits` terms (see
`docs/systems/checks.md`, "extra_traits"). Terms add points, earn check-based development when the
roll passes an effort level, and count as involved traits for thread pulls. Where staff have set
nothing, the roll runs without the added skill; there is no placeholder data.

**Magic skills only (#4547).** These skills are bespoke Magic skills (trait category MAGIC) that
staff make and point each roll at. They are never skills a character picks anywhere else, so a
cast never counts one skill twice. The four pickers below share `limit_choices_to=MAGIC_SKILL_CHOICES`
(`world/magic/skill_choices.py`): the admin form and its autocomplete offer only Magic skills, and
`full_clean()` refuses any other with `MAGIC_SKILL_ERROR_MESSAGES` (`ForeignKey.validate` applies
the filter, so no separate `clean()` check). The filter follows the category, never a name, and
keeps an inactive Magic skill valid (it adds no term). `magic_category_skills()` reads the same
filter plus the active flag. A cross-table rule like this cannot be a database constraint, so
existing rows that point at another skill stay as they are until staff repoint them. No seeder
names, creates or weights a skill for magic: the magic check types (`seeds_checks.py`) and the
"Technique Cast" fallback (`seeds_cast.py`) weight their stat only, and the sanctum ritual
configs take their skill from the `RITUAL_WORKING` mapping, writing none while it is unmapped.

| Surface | Location | Purpose |
|---------|----------|---------|
| `MagicActivity` | `constants.py` | 20 `TextChoices` kinds of magical roll (see Enums) |
| `MagicActivitySkill` | `models/magic_activity.py` | `activity`, `skill` (FK Skill, PROTECT, Magic skills only), `weight` (default 1.00); unique on (activity, skill). One row adds one skill to every roll of that activity; an activity may map several |
| `Path.technique_skill` | `world/classes/models.py` | Nullable FK Skill (SET_NULL, Magic skills only): the skill every Major Gift technique cast by someone currently on this Path adds |
| `Gift.technique_skill` | `models/gifts.py` | Nullable FK Skill (SET_NULL, Magic skills only), Minor Gifts only: DB constraint `gift_technique_skill_minor_only` and a matching `clean()` message |
| `Technique.skill` | `models/techniques.py` | Nullable FK Skill (SET_NULL, Magic skills only): overrides the Path and Gift skill for this one technique |
| `ConditionCategory.adds_loss_of_self_skills` | `world/conditions/models.py` | Boolean (default False): resist and break-free rolls on conditions in the category add the `RESISTING_LOSS_OF_SELF` skills (staff tick it for corruption, atavism, possession) |
| `activity_skill_terms(activity)` | `services/magic_skills.py` | One `ExtraTraitTerm` per mapped row whose skill is active; empty when nothing is mapped |
| `technique_skill_term(character, technique)` | `services/magic_skills.py` | The technique skill as a term at weight 1.00, or None |
| `technique_skill_term_for_path(technique, path, own_paths=None)` | `services/magic_skills.py` | The same rule with the Path already read, for callers resolving many techniques for one caster; pass each technique's `own_paths` from one `technique_paths` call |
| `technique_paths(technique_ids)` / `skill_path(current_path, own_paths)` | `services/magic_skills.py` | A technique's own Paths (the `PathGiftGrant` lists that hold it, in Path order) and which Path's skill a cast adds (#4555) |
| `cast_check_type(personal_check, technique)` | `services/magic_skills.py` | The ADR-0096 check type precedence (personal check, else the action template's), shared by `resolve_cast_check` and the combat action picker |
| `resolve_cast_check(character, technique)` / `CastCheck` | `services/magic_skills.py`, `types/magic_skills.py` | Frozen `(check_type, extra_traits)` for a cast |
| `involved_trait_ids(check_type, extra_traits)` / `cast_involved_trait_ids(cast_check)` | `services/magic_skills.py` | Trait ids a roll or cast involves, for thread pulls |
| `magic_category_skills()` | `services/magic_skills.py` | The active skills whose trait category is MAGIC (#4457): the set a Tradition's schooling stance lifts at finalize, the points CG refuses, and the Anima Check filter's exclusion. Staff control the set by a skill's category, never by name |
| `loss_of_self_terms(template)` | `world/conditions/services.py` | The `RESISTING_LOSS_OF_SELF` terms for a condition template whose category is marked, else none |

**Technique skill resolution order.** The technique's own `skill`, if set; otherwise for a Major
Gift technique the `technique_skill` of the Path it is cast from (#4555, ADR-4555-A): the
technique's own Paths are those whose `PathGiftGrant.starter_techniques` lists it
(`technique_paths`, one query for many techniques; a single cast reads `Technique.cached_own_paths`, which the Path Gift Grant and Path admins clear on save through `invalidate_technique_own_paths`, so casting adds no query); `skill_path` takes the caster's current Path
(`current_path_for_character`) when it is one of them, otherwise the technique's first own Path in
Path order (stage, sort order, name, then pk), so a technique learned on the Path of Embers and cast after a
Crossing into the Path of Ash still adds the Embers skill. A Path never inherits its parent's
skill. A technique on no Path's list falls back to the caster's current Path, and a caster with no
Path then gets no Path skill. Otherwise for a Minor Gift technique the Gift's `technique_skill`. An
inactive skill gives no term.

**Which rolls add what.**
- Personal-check casts roll `CastCheck.check_type` and add the technique term: scene cast, combat
  round and joust, clash, technique interception, battle technique, ward penetration.
- A technique-enhanced social action and a standoff display cast keep their own check type (the
  template's, the approach's) and add the technique term only. A casting standoff approach
  carries one grade per display technique (`ApproachView.technique_grades`), each graded with that
  technique's term, so the grade shown is the grade rolled.
- A challenge met with a capability that comes from a technique (`CapabilitySourceType.TECHNIQUE`)
  keeps the approach's check type, or its action template's, and adds that technique's term; a
  trait, condition or equipment source adds none (`capability_skill_terms`,
  `world/mechanics/challenge_resolution.py`). The difficulty indicator shown when the approach is
  offered previews with the same terms.
- Activity rolls keep their check type and add `activity_skill_terms(<activity>)`: the anima
  ritual (`perform_anima_ritual`), technique learning (learner roll and teacher rating), sanctum
  rituals and the ritual pool shortfall (`RITUAL_WORKING`), sustaining magic, dispelling,
  magical treatment, Soulfray resilience, Soul Tether rescue, the Court emergency draw
  (`COURT_PETITION`), Fury control, moon control, hostile resonance ground, feeding restraint,
  noticing a cast or sensing a twisted ceremony or a loss of self (`SENSING_MAGIC`), worship rites,
  invocations and ceremonies; binding a summoned being as a companion (`promote_summon`,
  `COMPANION_BINDING`) and a dream's peril resist (`resolve_dream_peril_collapse`, `DREAM_PERIL`).
- A condition effect from a technique-enhanced action (`handle_apply_condition_on_check`,
  `handle_remove_condition_on_check` in `actions/effects/conditions.py`) adds that technique's
  term (`technique_skill_term`) when the effect's `ActionEnhancement` source is a technique
  (`config.enhancement.technique`); a distinction or condition source adds none.
- Resist rolls on application, on stage advance, on a peril condition's per-round resist and
  terminal-pool roll (Bleeding Out, Surrounded) and on Surrounded entry, and break-free rolls, add the `RESISTING_LOSS_OF_SELF` terms only for a
  condition in a marked category. A friend's
  Rally adds none; Reveal adds the `SENSING_MAGIC` terms for a marked category.
- Treatment is magical, and adds `MAGICAL_TREATMENT`, when a technique drives it or the template
  spends resonance or anima or requires a bond; zero-cost, bondless first aid is mundane. The
  one test is `conditions.services.is_magical_treatment`, which also decides whether the scene
  `treat` path heals at first aid's own mend fraction (#4600).

**Cast thread pulls.** `build_cast_applicable_threads` and `applicable_threads_for_cast` take the
`CastCheck`; the paid pull inside `use_technique` and combat's `commit_combat_pull` do too, so the
cast's stat, personal skill and technique skill are in `PullActionContext.involved_traits`. A TRAIT
thread on any of them joins the cast's applicable threads, both as a passive tier-0 effect and as
a declared pull. A social action passes its template check plus the technique term, because that
is what it rolls; its declared pull is charged by `_charge_social_pull` against the same traits.

**Character creation.** The Anima Check skill pick excludes skills whose trait category is MAGIC
(`compute_magic_errors` through `magic_category_skills()`, and the `AnimaCheckStep` options), so a
magic skill is never counted twice on a cast. Existing characters keep the skill they picked. Since
#4457 a schooled character also starts with the Magic skills themselves; see "Tradition training
and Academy skill courses" below.

**Required content dashboard** (TUNING tier, `src/web/admin/tuning/required_content.py`): three
probes list what staff have not set: activities with no `MagicActivitySkill` row, active Paths with
no `technique_skill`, and Minor Gifts with no `technique_skill`. A row or field whose skill is
inactive counts as unset, since the roll skips it. An activity staff leave unmapped on purpose
stays listed. Three more rows came with #4457 (below). A seventh, `check-types-weight-no-magic-skill`
(#4547), lists each check type with a trait row on a Magic-category SKILL trait, as
`check type: skills`, and links to the CheckType changelist filtered to exactly those
(`?id__in=`): a check type that weights a Magic skill itself counts it twice when the magic skill
settings add it too, so staff move it into those settings. It matches on the trait, so a Magic
skill trait with no `Skill` row or an inactive one is listed too.

**Admin.** `MagicActivitySkill` changelist (activity filter, skill autocomplete, weight editable in
the list); `technique_skill` on the Path and Gift forms, `skill` on the Technique form,
`adds_loss_of_self_skills` on the Condition category form.

**Not in this slice:** fixed-value magic that becomes a check, and resonance-flavoured thread
options. (Tradition skill grants came in #4457, next section.) See `docs/roadmap/magic.md`.

### Tradition training and Academy skill courses (#4457, ADR-4457-A) [BUILT & WIRED]

A Tradition's schooling stance gives a character magical training points to spend on Magic skills at
character creation; CG skill points never buy a Magic skill; a character who starts behind catches up
in play, fastest through an Academy course. Slice 1 above made rolls add skills; this slice gives a
schooled character those skills. Slice 2 of #4659 (ADR-4659-B) replaced the original fixed "floor"
(every Magic skill raised to one level) with a pool the player spends and a Tradition teaching fit
that grows the pool and eases Academy courses.

**Training points.** The stance's granted distinction carries a `DistinctionEffect` on the
`magic_training_points` `ModifierTarget` (category `character_creation`, seeded by
`wire_magic_training_points_target`). `CharacterDraft.magic_training_pool` sums those effects with the
fit bonuses below. `SchoolingLine.magic_skill_floor` and its check constraint were removed by
`0299_remove_schoolingline_magic_skill_floor` with no carry: production held no schooling lines
(dump arxii-20261025T033001Z, 0 rows), so the data disposition is "empty in production" (ADR-0237). The set of skills is
still every skill in `magic_category_skills()`, the same for every Tradition.

**Teaching fit.** Three authored inputs say how well a Tradition teaches a given student:

| Surface | Location | Purpose |
|---------|----------|---------|
| `TraditionGiftGrant` | `world/magic/models/grants.py` | A row now means a Gift the Tradition's teachers favor (ADR-4659-A); it no longer gates the Gift pick |
| `Tradition.favored_affinities` | `world/magic/models/gifts.py` | M2M to `Affinity`, blank; reverse name `favoring_traditions`. A student whose Gift resonance's affinity is one of these gets the affinity fit. Admin field on `TraditionAdmin` |
| `TraditionTeachingConfig` | `world/magic/models/teaching.py` | Singleton (pk=1, lazy-created): `gift_fit_training_bonus` (10), `affinity_fit_training_bonus` (10), `course_ease_gift_fit` (2), `course_ease_affinity_fit` (2). `clean()` requires the two training bonuses to be multiples of `SkillPointBudget.points_per_tier`. Kept apart from `GiftAcquisitionConfig`, which tunes technique acquisition |
| `teaching_fit(tradition, gift, affinity)` | `world/magic/services/teaching_fit.py` | The one resolver, returning a `TeachingFit` (`world/magic/types/teaching_fit.py`: `gift_fit`, `affinity_fit`, `favored_gift_name`, `favored_affinity_name`, `training_bonus(config)`, `course_ease(config)`). Gift fit is a `TraditionGiftGrant` for the pair; affinity fit is the given `Affinity` row being in `favored_affinities` (by pk, through foreign keys only, never names). No affinity or no Tradition never fits |
| `gift_affinity_for(sheet, gift)` / `student_traits(sheet)` | same file | The Academy's student: the Major Gift and the affinity of the resonance on the sheet's active GIFT thread for it (`specialization.services.gift_threads_for`), None without one. Character creation passes the picked Gift resonance's `affinity` directly. Fit by the character's aura is deferred to #4672 |
| `major_gift_for(sheet)` | same file | The sheet's Major Gift (first `CharacterGift` of kind MAJOR), None when it has none |
| `get_teaching_config()` | same file | Lazily creates and returns the `TraditionTeachingConfig` singleton |

Character creation and the Academy both go through `teaching_fit`, so the two places cannot
disagree. The fit gives bonuses and ease, never a gate.

| Surface | Location | Purpose |
|---------|----------|---------|
| `SCHOOLING_MAX_RANK_BY_STATE` / `schooling_max_rank(state)` | `world/character_creation/constants.py` | Which Tradition states open which stances: LIVING_MASTERS up to rank 2, TEACHERS_GONE up to rank 1, SELF_TAUGHT none. A game rule, not tuning; #4536 replaces it when the training level becomes its own fact. Read by the offers module and `TraditionSerializer.get_schooling` |
| `schooling_training_points(lines)` | `world/character_creation/offers.py` | The training points each stance gives keyed by rank: the granted distinction's `magic_training_points` effect at the stance's rank, 0 for rank 0 or a line that grants nothing. One query. Read by the Tradition serializer and the tradition slate page |
| `CharacterDraft.magic_training_pool` | `world/character_creation/models.py` | Property returning a `MagicTrainingPool` (`base`, `gift_bonus`, `affinity_bonus`, `total`, `required_spend`, `fit`, `sources`). Computed on every call, never memoised. See "The pool" below |
| `compute_magic_errors` / `_magic_skill_allocation_errors` | `world/character_creation/validators.py` | Gift-stage validation of `draft_data["magic_skills"]` |
| `_create_skill_values` | `world/character_creation/services.py` | At finalize, writes exactly the allocated `magic_skills` through `set_skill_values` (source `CHARACTER_CREATION`, caps off), one `CharacterTraitChange` each; a Magic skill with no allocation is not written |
| `_glimpse` | `world/character_creation/magic_writer.py` | A new `CharacterAura` starts with its 80 on the picked resonance's affinity (below) |
| `CharacterDraft._check_no_magic_points` | `world/character_creation/models.py` | Refuses points in a Magic skill or in a specialization whose parent is one, naming them (`MAGIC_SKILL_POINTS_REFUSAL`), from `validate_path_skills`. Magic skills are bought only from the training pool |
| `TraditionSerializer` | `world/character_creation/serializers.py` | Each Tradition row carries `favored_gift_names` and `favored_affinity_names` (one query each for the list, built in `TraditionViewSet.get_serializer_context`); each stance row carries `training_points` and `grants_distinction_name`. Gift options carry `favored` |
| `CharacterDraftSerializer.magic_training` | `world/character_creation/serializers.py` | Read-only breakdown on `GET /api/character-creation/drafts/<id>/`: `base_sources` (name, rank, points, `show_rank`: true only for a distinction whose `max_rank` is above 1), `gift_bonus`, `affinity_bonus`, `favored_gift_name`, `favored_affinity_name`, `total`, `required_spend`, `step` (the active `SkillPointBudget.points_per_tier`), `allocated`, and `skills` (id, name, value, max) |

**The pool.** `base` is the sum of the draft's `magic_training_points` distinction effects.
`total = base + gift bonus + affinity bonus`, where each bonus is the config value when that fit
holds and `base > 0` (a draft with no training gets nothing, even when it fits both), rounded down to
a multiple of `SkillPointBudget.points_per_tier`. A Magic skill value costs its own value in points
(10 per step, the ordinary skill price). `required_spend = min(total, active Magic skill count x
max_skill_value)`, so a pool larger than the skills can hold never blocks submission. Example with
Tradition Training rank 1 = 20, a Studious +10 distinction and both bonuses at 10: a draft that fits
both has 50 to spend, a Gift-only or affinity-only fit 40, no fit 30, no training distinction 0.

**Validation.** The Gift stage reads `draft_data["magic_skills"]` (skill id to value). It fails the
stage when the value is malformed, names a skill that is not an active Magic skill, holds a value
that is not a multiple of `points_per_tier` or exceeds `max_skill_value`, spends more than `total`,
or spends less than `required_spend`. Changing the Gift, Tradition, stance or resonance changes the
pool, so an allocation that no longer matches fails the stage and the draft cannot submit until it
is fixed. `_check_no_magic_points` stays.

**Starting aura.** A new character's `CharacterAura` starts at the model defaults; the Glimpse nudge
then applies as before. A starting aura that follows the picked resonance is deferred to #4672.

An orphaned Tradition's rank 1 carries Tradition Training's starting technique pick as a living
one does. A pick the state no longer opens (switching a rank 2 draft to a TEACHERS_GONE Tradition)
is dropped by the existing `reconcile_offer_picks`. A `DistinctionOffer` saved without its
schooling stance is never offered (the database does not require one). Joining a Tradition in play
grants nothing retroactively (#2441).

**Staff.** The tradition slate page has no training input on a stance: the points are the granted
distinction's `magic_training_points` effect, authored on the Distinction Builder. Under each rank 1
and 2 row it shows a read-only "grants <n> magical training points." (rank 0 reads "Rank 0 trains
none."). Favored Gifts are `TraditionGiftGrant` rows and favored affinities are the `favored_affinities`
field on the Tradition admin; the tuning numbers are on the `TraditionTeachingConfig` admin page.
The Required content dashboard has these rows (`required_content.py`; all TUNING):

| Key | Lists | Consumer |
|-----|-------|----------|
| `schooling-magic-skill-floors` | Schooling ranks 1 and above that give no training points: no granted distinction, no `magic_training_points` effect, or one worth 0 or less at the rank, read through `schooling_training_points()` (key kept so the dashboard row is stable) | `schooling_training_points()` |
| `magic-skill-courses` | Active Magic skills with no `SKILL_COURSE` offer on an active role that has a `faction_affiliation` (an inactive role's offers are never shown) | `run_skill_course_offer()` |
| `path-suggestions-name-magic-skills` | `PathSkillSuggestion` rows naming a Magic skill (CG cannot take them) | `PathSkillSuggestionViewSet` |

**Frontend.** The Gift stage has its own training step after the Resonance step, shown once both
the Gift and the resonance are picked (its Gift bonus depends on the Gift, its affinity bonus on the
resonance): `MagicTrainingBlock` lists the pool lines (each source, with its rank when `show_rank`;
the Gift and affinity bonuses; the total), the remaining count, and a row per Magic skill stepping
by the payload's `step`; an overspend or an
underspend is flagged and the step stays open until `allocated` equals `required_spend`. Tradition
and Gift cards carry "Teaches well" tags from `favored_gift_names`, `favored_affinity_names` and
`favored`. `SchoolingStances` shows each stance's training points. `SkillsSection` hides Magic skills
from the point groups and shows the allocation as a read-only Magic group; Path suggestions naming
a Magic skill and Magic ids loaded from an older draft are dropped.

#### Academy skill courses

`OfferKind.SKILL_COURSE` is an Academy teacher's course in one skill (staff choose the skill on each
offer; the dashboard row above keeps one per Magic skill). It reuses the trainer menu and the Academy
gates TRAIN uses, and is not a TRAIN offer: TRAIN teaches a technique through the training meter.

| Model / function | Location | Purpose |
|------------------|----------|---------|
| `SkillCourseOfferDetails` | `world/npc_services/models.py` | 1:1 with the offer: `skill`, `total_development`, `session_development` (check constraints `course_session_within_total`, `course_total_development_positive`, `course_session_development_positive`), `session_ap_cost`, `coin_cost` (coppers, 0 is a free course), `check_type`, `check_difficulty`. No field has a default. `clean()` requires `NPCServiceOffer.ap_cost == 0` |
| `SkillCourseEnrollment` | `world/npc_services/models.py` | A sheet's place in one course: `development_remaining`, `last_session_week` (FK `GameWeek`), `enrolled_at`, `completed_at`. At most one open enrollment per sheet and course (`one_open_enrollment_per_course`); a finished course may be taken again |
| `run_skill_course_offer(offer, persona)` | `world/npc_services/effects.py` | The handler. Registered in `OFFER_EFFECT_HANDLERS` |
| `_academy_for(offer, sheet, kind)` | `world/npc_services/effects.py` | Shared by TRAIN, the course and settle-obligation: the role's `faction_affiliation` (an authoring error message when none), and the owed-entrance-obligation refusal (skipped for settle-obligation, whose job is paying it) |
| `AcademyOfferApCostError` | `world/npc_services/effects.py` | Replaces `TrainOfferMisconfiguredError`. Raised when a TRAIN or SKILL_COURSE offer has a nonzero `ap_cost`, which the generic pre-dispatch charge would take on top of the handler's own AP |

*How acceptance works.* The first acceptance enrolls: it pays the coin (skipped when 0) to the
Academy's treasury and redeems one Golden Hare, once for the course, then runs the first session.
Each later acceptance of the same offer is a session costing `session_ap_cost` AP, rolled with
`perform_check_with_modifiers` against the course's `check_type` and `check_difficulty`. The
development is `floor(session_development x multiplier)`, where the multiplier is the
`TrainingOutcomeAward` row for the roll's outcome (the table technique training reads; no row or no
outcome teaches nothing), capped at `development_remaining`. It is applied through
`train_skill(..., stop_at_boundary=True)`: development that would run past an XP boundary stays in
the course, because the course was paid for up front, and the session after a breakthrough
continues it. A skill the character has no row for starts at 10 (`DP_BASE_LEVEL`). The enrollment is
stamped complete when `development_remaining` reaches 0. The AP is spent on any rolled outcome,
including a botch that teaches nothing.

*Teaching fit (slice 2 of #4659).* When the offer's role has `teaches_tradition`, `_course_ease`
(`effects.py`) resolves `student_fit(tradition, student_traits(sheet))` (the sheet's Major Gift and
the affinity of the resonance on its active GIFT thread for that Gift, then `teaching_fit`) and subtracts `course_ease(config)` from `check_difficulty` before the roll, with no floor. The fit
changes the check only: the roll's outcome still decides the development gained. A role with no
Tradition is neutral. The menu price (`OfferPrice`) carries two lines for such a course:
`teaching_line` ("Taught in the manner of <Tradition>") and, when the learner fits,
`fit_line` ("Fits your <Gift> and its <Affinity> affinity. Sessions are easier for you.", or just the part
that fits; omitted when the fit's `course_ease` is 0, so staff zeroing both eases removes the claim).
The menu (`serialize_npc_session_state`) reads the student's traits once and resolves one fit per
teaching Tradition (`_menu_teaching_fits`, a local dict passed down), not one per offer. Both
ride `OfferPriceSerializer`, `NPCInteractionDialog` shows them and telnet `hire` prints them.

*Refusals charge nothing.* Every refusal is checked before anything is charged, in this order:
debt or no Academy (`_academy_for`), then (under the AP pool lock) already trained in this course
this game week, the skill parked at an XP boundary (19, 29, 39, 49), short of AP, and when enrolling
short of coin (the same `enforce_can_afford_training` check TRAIN uses) or of a Hare. One session per
course per game week, across enrollments (a course finished this week and retaken waits for the next
week); the week is recorded on the enrollment (`last_session_week`) rather than as an offer
cooldown, because `resolve_offer` writes a cooldown even when the handler refuses. The Unbound
drawback's +50% surcharge on magic learning is not read: a character without formal training never
pays more to train.

*Trainer menu price line.* `InteractionOfferSerializer.price` (`OfferPriceSerializer`: `ap`,
`coppers`, `golden_hares`, `per_session_ap`, `development_remaining`, `development_total`,
`training_points`, `display`) is built per offer by `_offer_price` into the frozen `OfferPrice`
dataclass (`world/npc_services/types.py`), and `format_offer_price` writes the one line the web menu
(`NPCInteractionDialog`) and telnet `hire` both print. It is null for every kind but SKILL_COURSE and
TRAIN. A course not yet taken reads "Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one
now"; once enrolled, "Next session · 6 AP · 1200 of 1500 left", or "Next session next week · 6 AP ·
1200 of 1500 left" when her open enrollment's `last_session_week` is the current game week (read with
`GameWeek.get_current()`, never bootstrapped by a menu read; the flag is `OfferPrice
.next_session_next_week` and only changes `display`). TRAIN reads "2g 5s · 1 Golden Hare ·
5 points of training or more, paid in AP": TRAIN charges no AP on acceptance, and
`TrainOfferDetails.learn_ap_cost` is the training meter's base (the gift multipliers in
`charge_and_learn` can raise it), not AP charged at acceptance.

*Admin.* `SkillCourseOfferDetailsAdmin` draws the fields in the demo's order (Offer, Skill, Sold by,
Total development, Session development, Session AP cost, Coin cost (coppers), Check type, Check
difficulty) with two read-only derived rows: the skill's category beside Skill ("Derived,
read-only: category Magic.") and Sold by, the offer's role and its house ("Academy Trainer, for
Shroudwatch Academy.", or "(no house)"). Any skill may be picked. `NPCServiceOffer.ap_cost`'s help
says it must stay 0 on TRAIN and Skill Course offers. A read-only `SkillCourseEnrollmentAdmin` lists
who is taking which course.

*Verified by.* `src/integration_tests/test_tradition_training_journeys.py` (the Tradition list, the
stance sync, the draft detail, refused Magic points, finalize to the sheet, a schooled character's
cast rolling her Path's Magic skill at the floor beside a self-taught one's at 0) and
`src/integration_tests/test_academy_skill_course_journeys.py` (enrolling, refusals that charge
nothing, sessions per outcome, boundaries, the trainer menu over telnet and the web); rows in
`docs/testing/journeys.md`.

### Covenant-Role Blend Power Term (#2529, ADR-0149) [BUILT & WIRED]

`_derive_power` (cast power resolution) sums a list of independent power-term providers
registered in `world.magic.services.power_terms._PROVIDERS`, each `(PowerTermContext) ->
int`. `covenant_role_blend_power_term` is the always-on **Layer 1** baseline for
`covenants`' four-layer vow-power model (see `docs/systems/covenants.md`'s "Vow power,
four-layer model" and ADR-0149): for every `character.covenant_roles.currently_engaged_roles()`
row, it adds `total_thread_level_across_all_kinds(sheet) × role.blend_weight_for(technique.archetype_alignment)
× CovenantRoleBlendConfig.multiplier_tenths / 10`, floored at 0 when the technique or
character has no engaged role. `total_thread_level_across_all_kinds(sheet)` (`world.magic.services.threads`)
sums raw `thread.level` across **every** thread kind the character has (TECHNIQUE, GIFT,
COVENANT_ROLE, SANCTUM, ...) — not the bucketed `thread_level_multiplier`
`survivability_baseline` uses. `CovenantRoleBlendConfig` (pk=1 singleton,
`get_covenant_role_blend_config()`, lazy-created) holds the tunable
`multiplier_tenths` (default 10 = ×1.0). Kept as its own provider (not folded into an
existing term) so the contribution stays attributable in cast breakdowns — Layer 4's
presentation contract (#2536 slice 1, ADR-0151, now built — see "Vow Situational Power
Term" below) shows "this much came from your vow" as a distinct announced line.

### Covenant-Role Technique Specialty Power Term (#2443, ADR-0149 amendment) [BUILT & WIRED]

`covenant_role_specialty_power_term` is another always-on `_PROVIDERS` entry — **Layer
2** of `covenants`' four-layer vow-power model (see `docs/systems/covenants.md`'s "Vow
power, four-layer model" and ADR-0149's 2026-07-20 amendment). It rewards a vow for
casting techniques that match what the role specializes in, keyed on the shared
`TechniqueFunction` vocabulary (`constants.py`, 15-value `TextChoices`, `STRIKE` and `MEND`
added by #4581, also consumed by Layer 4's situational perks, #2536, and by vow added
effects, #4581) rather than the coarser SWORD/SHIELD/CROWN axis
Layer 1 reads.

For each of `character.covenant_roles.currently_engaged_roles()`, the term collects
`covenants.CovenantRoleTechniqueSpecialty` rows from the anchor role **plus** the
resolved sub-role's own rows when it differs (both role ids go into one lookup), filtered
to functions the cast technique carries (`technique.cached_function_tags`), and sums
`total_thread_level_across_all_kinds(sheet) × row.multiplier_tenths / 10` per matching
row. Returns 0 when the technique carries no `TechniqueFunctionTag`, no role is engaged,
or no specialty row matches. **Sub-role rows ADD to the anchor's — they are never
normalized away** — the opposite of the anchor-only rule
the blend weights use; a promoted (specialized) member reads as
strictly more specialized than an unpromoted one.

### Vow Situational Power Term (#2536 slices 1 & 3, ADR-0151/ADR-0153) [BUILT & WIRED]

`vow_situational_power_term` is a conditional `_PROVIDERS` entry — **Layer 4** of
`covenants`' four-layer vow-power model ("the point of vows", see
`docs/systems/covenants.md`'s "Layer 4: Situational Perks" and ADR-0151). Unlike Layers
1-2 (always-on), this term is 0 unless a `POWER_BONUS` `VowSituationalPerk` actually fires
for the cast — see `world.covenants.perks.services.applicable_perks` for the full
beneficiary/situation resolution.

`PowerTermContext` gained two optional fields for this term (both defaulted so every
existing constructor is unaffected): `situation_ctx` (the live resolution context — a
`CombatRoundContext`, `world/combat/round_context.py`, when the cast resolves inside
combat; `None` for a standalone/non-combat cast) and `target_sheet` (the cast's primary
target's `CharacterSheet`, resolved by `world.combat.services._resolve_primary_target_sheet`
on the combat round path — `None` for a targetless cast, an NPC-only opponent with no
linked `CharacterSheet`, or a non-combat cast). `situation_ctx` is threaded from the combat
cast path (`resolve_combat_technique`) and from clash (`commit_to_clash`); `target_sheet`
is threaded from the combat round path only (clash contributions have no explicit target
concept yet, so target-keyed situations correctly read `False` there, same as any other
targetless cast).

Guards: no technique → 0 (perks are cast-scoped); no engaged covenant role on the caster →
0 (a cheap exit that never skips a case `applicable_perks` would otherwise have fired,
since `applicable_perks`'s own ally-candidate path also requires the subject to hold at
least one engaged role before a mate's group-beneficiary perk can reach them). When perks
fire, the term sums, per firing, `total_thread_level_across_all_kinds(sheet) ×
magnitude_tenths / 10` (int-truncated after summing in `Decimal` — the same arithmetic
Layers 1-2 use) and calls `announce_fired_perks` (the presentation-contract seam, see
`docs/systems/covenants.md`) exactly once, since `_derive_power` calls this provider
exactly once per real cast resolution (`use_technique`'s single orchestration call).

**Attributability gap (documented, not fixed this slice):** the ledger's TERM-stage label
for this provider is the same static function-name-derived string every other
multi-source provider in this file gets (`_derive_power`'s TERM loop labels once per
provider, not once per return value) — a cast boosted by two different firing perks shows
one summed "vow situational power" line, not two named lines. The per-perk name reaches
the player through `announce_fired_perks`'s dual-dispatch line instead, which is where
ruling 1's "loud, visible moment" actually needs to land. See ADR-0151 for the reasoning.

`CHECK_BONUS`'s parallel seam lives in `world.checks.services._situational_perk_check_bonus`
(`docs/systems/covenants.md` covers the shared delivery contract) — `perform_check` gains
an optional keyword-only `situation_ctx` parameter, `None` by default (byte-identical to
every pre-#2536 call site; existing checks tests pass unmodified as the proof), scoped by
each fired perk's `check_type` (null = any check).

**Slice 3 additions (ADR-0153):** the fired set is filtered through `perk_scope_matches`
before scaling — `battle_action_kind` is `POWER_BONUS`'s only valid scope column
(`mission_category`/`mission_template` are `CHECK_BONUS`-only, `clean()`-enforced), read off
`ctx.situation_ctx.battle_action_kind` via an `isinstance(ctx.situation_ctx, SituationContext)`
type check — an ordinary combat `CombatRoundContext` (or `None`) is not a `SituationContext`, so
every battle_action_kind scope column simply no-ops outside a Battle warfare cast (the only
caller that threads a real `SituationContext` through as `PowerTermContext.situation_ctx`, via
`BattleTechniqueResolver`/`resolve_battle_technique`, `world/battles/resolution.py`). This
provider also runs one **dormant pass** (`dormant_perk_firings`/`announce_dormant_perks`, ruling
2's "loud OFF state") BEFORE the "subject has an engaged role" early-exit above — a subject
whose entire vow is disengaged has no engaged role at all, which is exactly the case the dormant
pass exists to catch; it reads the same cached `covenant_roles` handler list that guard does, so
running it first costs no extra query either way.

### The Damage Identity — Bounded Team-% Lane, Vow-Keyed Stacking, Smooth Execute (#2643, ADR-0158) [BUILT & WIRED]

The ratified composition (lore repo `design/covenant-vows-consolidated.md` §5): team
damage = Strike's bases (execute-scaled) × Uplift's team-wide % × Undermine's
enemy-side %. This slice builds the two percent lanes' bound + pricing + stacking and
the execute ramp; Strike's own base-damage/intensity-coefficient authoring is unchanged.

**The bounded team-damage-percent lane — the ONLY buff-multiplier lane, forever
(ADR-0158, the EQ2 lane guard).** A dedicated `mechanics.ModifierTarget` row named
`team_damage_percent` (same `"power"` category as the legacy `power_multiplier`
target, so `_get_power_targets()` picks it up for free; seeded idempotently via
`world.mechanics.factories.ensure_team_damage_percent_target()`, called from
`seed_magic_dev()`) is read as its own SEPARATE lane inside
`_apply_power_multiplier_stage` (`world/magic/services/techniques.py`). The lane's
summed delta runs through vow-keyed diminishing returns (below), clamps to
`±magic.constants.TEAM_BUFF_LANE_CAP_PERCENT` (default 50), and is folded into the
SAME single `builder.multiply` call as the legacy `power_multiplier` aggregate —
`total_delta = lane_delta_clamped + legacy_delta` — never a second multiplicative
stage. Pre-existing `power_multiplier` sources (Audere/Audere Majora, #636) are
intentionally left OUTSIDE the band for this issue's scope; folding them into the
bounded lane is flagged future within-lane tuning, not a #2643 requirement.

**Power buys the percentage, priced against the buffed/debuffed target's level.**
A lane condition is authored `ConditionModifierEffect(modifier_target=
team_damage_percent, value=1, scales_with_severity=True)`. At apply time (both cast
paths, via the shared `world.magic.services.condition_application
.apply_technique_conditions` seam) `world.conditions.services.priced_percent_severity`
computes `severity = clamp(round(eff_intensity * PCT_PER_POWER_TENTHS / 10 /
max(1, target_level)), 1, TEAM_BUFF_LANE_CAP_PERCENT)` and that becomes the
`ConditionInstance.severity` — overriding the row's own authored severity formula for
that one row. `target_level` resolves generically for whoever the condition lands on
(the lane works for an ally BUFF as easily as an enemy DEBUFF — Undermine can author
a `value=-1` row targeting ENEMY): a PC target reads `CharacterSheet.current_level`;
a `CombatOpponent` target reads its pseudo-level from `combat.constants
.OPPONENT_TIER_LEVEL` (SWARM 1 / MOOK 2 / ELITE 4 / BOSS 6 / HERO_KILLER 8 —
flagged judgment-call seeds, not measured content); an unresolvable target defaults
to level 1.

**Vow-keyed stacking (diminishing returns within a vow, full stacking across vows).**
`conditions.ConditionInstance.source_vow` (nullable FK → `covenants.CovenantRole`,
`SET_NULL`) is stamped once per apply-time batch from the applier's engaged-vow
anchor: the FIRST of `character.covenant_roles.currently_engaged_roles()`, resolved
to its ANCHOR (`parent_role` when the engaged role resolved to a sub-role, else the
role itself — never the resolved sub-role). Resolution helper:
`world.conditions.services._resolve_source_vow_anchor`; wired into both
`apply_condition` and `bulk_apply_conditions`. The lane's read
(`world.magic.services.techniques._team_lane_delta`, backed by
`conditions.services.get_condition_modifier_vow_contributions`) groups per-instance
contributions by `source_vow_id` (a `None` group — no engaged role at apply time — is
its own group like any named vow) and runs them through the pure function
`world.magic.services.techniques.vow_keyed_diminished_total`: within one vow,
contributions sort descending and weight 100% / 50% / 25% / 25%...(4th+ all ×0.25,
no further decay); distinct vow groups stack FULLY against each other — the
mechanical reward for multi-vow synergy over one-vow spam. `ConditionInstance
.source_vow` is surfaced to the UI as `source_vow_name` on `ConditionInstanceSerializer`
(`world/conditions/serializers.py`) — an armed team-damage-percent buff's vow
provenance is visible on an ally before casting.

**Enemy-side bound (Undermine's other expression).** The pre-existing
condition-driven `ConditionDamageInteraction.damage_modifier_percent` lane —
summed across every matching row in `process_damage_interactions` and applied as a
final percentage multiplier in `world.combat.services
._apply_condition_damage_interactions` — is clamped to
`±combat.constants.ENEMY_LANE_CAP_PERCENT` (default 50) before it multiplies net
damage. The clamp bounds only the live damage APPLICATION; an individual authored row
may itself exceed the band, and the unclamped sum still reports on the raw
`DamageInteractionResult`.

**Defense piercing (#4575).** `AbstractDamageProfile` shares three authored
controls across technique, draft, variant, signature, miracle and vow-added-effect damage rows:
`ignores_soak` (false), `resistance_shift` (nonnegative points, 0) and
`bypasses_wards` (false). The builder API and draft publication preserve them.
Soak piercing skips armor-like protection without granting an unarmored damage
bonus. A typed hit subtracts its shift from signed resistance, crossing zero and
deepening vulnerability without mutating the target. Any effective profile's ward
flag bypasses the cast-wide barrier contest, so damage and associated conditions
pass together. Other success checks still apply. Effect summaries show the authored
per-hit properties and whole-technique ward scope. See
[Combat Defense Composition](COMBAT_DEFENSES.md#authored-defense-piercing-4575).

**Smooth execute.** `AbstractDamageProfile.execute_missing_health_multiplier`
(Decimal, default 0 — a no-op on every technique unless authored otherwise) scales a
landing hit's damage by `1 + multiplier * missing_health_fraction`, computed off the
TARGET's PRE-hit health (never the post-hit value — no recursion, and a second hit in
the same exchange correctly compounds off whatever the first hit left behind). Applied
at both `world.combat.services.apply_damage_to_opponent` and
`apply_damage_to_participant` via the shared `_apply_execute_multiplier` helper — the
opponent seam is threaded from a live caller (`CombatTechniqueResolver
._apply_profiles_to_target`, where the resolving damage profile is already in hand,
mirroring how `damage_intensity_multiplier` reaches `compute_damage_budget`); the
participant seam accepts the same kwarg and is unit-tested directly, since combat
technique damage in this codebase currently only ever resolves against
`CombatOpponent` targets, not PC `CombatParticipant`s — ready for PC-vs-PC technique
damage whenever that's wired.

### Sized technique buffs: a buff's level and size (#4594, ADR-4594-A) [BUILT & WIRED]

A technique's buff or debuff carries a **level** (from its cast) and a **size** (authored), and its
check modifiers read the check lane's value table (`docs/systems/checks.md`, "Modifier value
table"). Only the check lane is wired; cast power, damage and the other lanes in #4551's
inventory join later.

- **Size** — `TechniqueAppliedCondition.modifier_size` (nullable `ModifierSize`; blank keeps the
  condition's flat check modifiers) and `narrow_use` (bool). `clean()` refuses Paramount (only a
  vow's size step reaches it). The other applied-condition families (variants, drafts, signature
  bonuses, vow added conditions) stay unsized.
- **Level** — `CastPowerLevel(min_power unique, level)` and
  `CastOutcomeLevelShift(success_level unique, level_shift)` (`models/modifier_level.py`, admin
  pages beside the power configs). `services/modifier_sizing.py`: `load_cast_level_table()` (two
  queries) returns a `CastLevelTable` whose `level_for(effective_power=, success_level=)` takes the
  highest power row at or below the cast, adds the outcome shift, and never goes below 1; a cast
  weaker than every row resolves no level. `sized_modifier_level(row, ...)` returns the (level,
  size) for one row, (None, None) unless it is a sized `TechniqueAppliedCondition`.
- **Stamping** — `apply_technique_conditions` loads the table only when a row is sized and
  `_build_bulk_applications_for_row` puts `modifier_level` / `modifier_size` on each
  `BulkConditionApplication`; `bulk_apply_conditions` stamps them on the `ConditionInstance`.
  Passive techniques (`combat/services/damage/passive_techniques.py`) are not casts and stay
  unsized. The target's level is never read.
- **Vow size step (#4747, ADR-4747-A)** - when a row is sized, `apply_technique_conditions` also
  calls `caster_vow_step(source_character, technique) -> VowStep | None` once per cast. Its
  vow is her first engaged role (the one `_resolve_source_vow_anchor` stamps as `source_vow`);
  it steps when that role, its resolved sub-role or its anchor has a
  `CovenantRoleTechniqueSpecialty` for one of the technique's function tags. `VowStep.level`
  is the shown level of her COVENANT_ROLE thread on the anchor, never capped by the buff's own
  level, so a weak cast from a deep vow steps at the vow's depth. `VowStep.tenths` is the
  matching row's `multiplier_tenths` (the larger when two rows match), times
  `SecondaryVowConfig.potency_tenths / 10` (rounded half up) for a secondary vow. None when
  there is no match, thread, level or share. The pair rides `BulkConditionApplication` onto
  `ConditionInstance.modifier_vow_level` / `modifier_vow_tenths` through
  `_stamp_modifier_sizing` (a re-application keeps the stronger pair, by level then tenths).
  Each modifier of the instance then adds the scaled size step as an untapered `vow_part`
  (`docs/systems/checks.md`). Points only: no outcome floors or ceilings. Note the specialty's
  multiplier also adds cast power (`covenant_role_specialty_power_term`), so a vowed buff
  usually lands at a higher `modifier_level` too.
- **Admin size check** — `applied_condition_size_warnings(technique)` returns plain warnings, shown
  by `TechniqueAdmin.save_related` as admin messages (never a refusal): a technique whose only
  payload is the buff should size it Large; one with other payload rows (damage, other
  conditions, capability grants, removals, treatments) at most Moderate; `narrow_use` allows one
  step more, up to Exceptional; and a sized condition with no `ConditionCheckModifier` warns that
  its size has nothing to act on yet.
- **Tuning** — the Checks panel of the tuning dashboard has a modifier pile: N equal buffs of a
  level and size on a character at the level baseline, plain and tapered, with ranks and
  whole-rank odds (`web/admin/tuning/checks_analytics.py` `compute_modifier_pile`). Required
  content lists the five tables as TUNING rows.

### Targeting Model (#1321) [BUILT & WIRED]

Standalone casts now validate targets, resolve AoE expansion, apply conditions, and route
consent based on behavioral impact rather than blanket benign/hostile.

**`ConditionCategory.alters_behavior`** (new boolean, default `False`) — marks behavior-altering
condition categories (compulsion, charm, fear) as distinct from capability/stat conditions.
Lives on `world/conditions/models.py:ConditionCategory`.

**Targeting services** (`world/magic/services/targeting.py`):

| Function | Purpose |
|----------|---------|
| `derive_target_relationship(technique) -> ConditionTargetKind` | ENEMY if hostile (damage, an ENEMY condition or removal, or a morale row, #4619; it only lands on opposing combatants); ALLY if any applied, removed or **treatment** row has `target_kind=ALLY`; ENEMY if a treatment row targets an enemy (stabilising a downed foe is aimed at an adversary without being hostile); else SELF. Treatments joined in #3682 - a technique whose only payload was an ALLY treatment derived SELF, and the SELF branch of `_check_relationship` then refused to let the authored heal name its ally. Reads the technique's `cached_*` payload lists rather than its own `.filter().exists()` queries (#2898). Exactly one relationship comes back, so a technique whose payload rows disagree gets a guess - see `technique_relationship_is_ambiguous` below. |
| `technique_alters_behavior(technique) -> bool` | True if any applied condition's `category.alters_behavior` is True |
| `cast_requires_consent(technique) -> bool` | True iff `technique_alters_behavior` — **behavior only**, not blanket benign |
| `validate_cast_target(*, technique, initiator_persona, target_personas)` | Raises `InvalidCastTarget` on cardinality or relationship violations |
| `resolve_targets(*, technique, initiator_persona, scene, supplied_personas) -> list[Persona]` | Expands target_type to concrete personas: SELF→caster; SINGLE→one; AREA→all eligible in scene; FILTERED_GROUP→supplied ∩ eligible |
| `protective_condition_and_flavor(technique) -> tuple[ConditionTemplate, str] \| None` (#2207) | Classifies a technique's reactive-trigger handler into `barrier`/`blink`/`redirect` by walking `condition_applications → condition.reactive_triggers → flow_definition.steps` (one batched Prefetch query); returns the matched `ConditionTemplate` too, since combat's guardian resolution needs its `reactive_anima_cost`. No new authored field — derives from the existing effect-palette data. |
| `protective_flavor(technique) -> str \| None` (#2207) | Thin wrapper over `protective_condition_and_flavor` returning only the flavor string; used by `declare_interpose`'s declaration-time gate (combat, `world/combat/services/`) |

**`PlayerAction.reactive_anima_cost` / `CastableTechniqueSerializer.reactive_anima_cost`** (#3573)
both carry the protective condition's flat fee (`ConditionTemplate.reactive_anima_cost`), resolved
from the same `protective_condition_and_flavor(technique)` call `protective_flavor` and the
guardian resolution already make (`actions/player_interface.py`'s `_combat_actions` for
`PlayerAction`; `world/scenes/action_serializers.py`'s `CastableTechniqueSerializer.
get_reactive_anima_cost`, one call per row, for the standalone-cast list) - `None` when the
technique carries no protective handler. `AvailableEnhancement` does NOT carry this field: the
technique-enhancement commit path (`create_action_request` -> `_resolve_enhanced_action` ->
`use_technique`) never calls `apply_technique_conditions`, so an enhancement can never mint the
condition a ward consent would attach to (tried and reverted in #3573's Task 6 fix round).

Three consent surfaces read `reactive_anima_cost` before offering "hold this ward into Soulfray"
(consent must ALWAYS be available, not gated behind an active Soulfray warning):
- **Guard control** (`YourTurn.tsx`, combat) - `guard-soulfray-toggle`, fee + current anima shown;
  `useGuardMutation`'s `confirmSoulfrayRisk` rides straight into `InterposeAction.execute`'s
  `confirm_soulfray_risk`, which Task 4's `declare_interpose`/guardian resolution reads directly.
- **Focused cast card** (`YourTurn.tsx`, combat) - `cast-ward-soulfray-toggle`, shown only when no
  active Soulfray warning already surfaces `SoulfrayAcceptGate` (whose acceptance covers both).
- **Standalone cast panel** (`ActionPanel.tsx`'s `castableTechniques` list, out of combat) -
  `cast-ward-soulfray-toggle`, sends `soulfray_consented: true` via `castTechnique` ->
  `TechniqueCastCreateSerializer.soulfray_consented` (`world/scenes/action_serializers.py`) ->
  `SceneActionRequestViewSet.cast` -> `request_technique_cast`'s `soulfray_consented` kwarg,
  threaded explicitly through `_route_immediate_cast`/`_route_filtered_group_cast`/
  `_route_other_pc_cast` into `_resolve_and_pose_cast`. This is the REAL integration point for a
  standalone ward cast (e.g. party wards): unlike the enhancement path, it does apply conditions.

**Web cast consent is explicit, not derived** (#3573 fix round): `request_technique_cast`'s
`confirm_soulfray_risk` defaults `True` on the web path (the telnet-only soulfray halt/accept
offer, `world.magic.offer_handlers.SoulfrayPendingHandler`, must never block a web cast), and
`_resolve_and_pose_cast` derives `soulfray_consented` from `confirm_soulfray_risk` when
`soulfray_consented` is left `None`. Before this fix, `SceneActionRequestViewSet.cast` never
passed `soulfray_consented` at all, so EVERY web-cast ward was silently stamped consented. The
view now reads `soulfray_consented` from the serializer (`default=False`) and always passes it
explicitly, bypassing the derivation on the web path only - every other caller (telnet's
`CastTechniqueAction`, `offer_handlers.py`'s accept-soulfray re-dispatch, `berserk_compulsion.py`,
`clash.py`, `battles/resolution.py`) still omits it and keeps the old derived behavior unchanged.

**Telnet** (`commands/combat.py`'s `CmdDeclareTechnique`) - a trailing `soulfray` keyword on
`cast`/`declare` (mirrors `combat interpose ... soulfray`, #3573 Task 1) sets
`confirm_soulfray_risk=True` via `_inject_cast_mode_kwargs`, pre-consenting and skipping the
separate "accept soulfray"/"decline soulfray" offer prompt that would otherwise gate a cast made
while the caster has an active Soulfray stage.

**Reactive protections and Soulfray (#3573).** Consent is captured before a reaction ever
fires, never at fire time, since a reaction fires inside someone else's resolution:
`declare_interpose`'s `confirm_soulfray_risk` for a declared technique-guardian interpose
(`CombatRoundAction.confirm_soulfray_risk`), or `ConditionInstance.soulfray_consented`
stamped at cast time (via `bulk_apply_conditions` -> `_ApplyConditionParams` ->
`_create_instance_from_context`, from both `apply_technique_conditions` and
`apply_signature_bonus_conditions`) for a standing ward. Three seams read that consent and
branch on it - unconsented is unchanged (fizzle or lapse); consented debits through
`deduct_anima(lethal=encounter.is_lethal)` (glut-first, deficit-capable) and accrues
through `world.magic.services.soulfray.accumulate_soulfray`, the SAME function
`use_technique`'s step 7 calls, so a guardian or ward-holder running dry accrues Soulfray
the way a caster does: `_try_technique_interpose` (declared interpose fire),
`_try_spend_reactive` (a Barrier/other reactive-condition fire, `effect_handlers.py`), and
`drain_reactive_upkeep` (per-round upkeep drain, via `_debit_ally_paid_upkeep`/
`_pay_upkeep`). `_try_technique_interpose` and `drain_reactive_upkeep` always run
inside a known `CombatEncounter`, so their lethal clamp is just `encounter.is_lethal`.
`_try_spend_reactive` can fire with no encounter in scope at all (a standing ward held
outside combat), so it derives lethal from the bearer's own live COMBAT engagement via
`active_combat_engagement_for` instead - `None` (no live COMBAT engagement) now falls
through to `lethal=False` (#4098 fix round 2, owner ruling: Soulfray can kill only in a
combat encounter). Before #4098 the no-engagement case fell through to `lethal=True`,
exactly backwards: it let a reactive fire with no combat at all draw a life-force
deficit. A consented deficit
fire narrates distinctly (`_broadcast_commitment_line`): "tears at their own soul to hold
the line over {ally}" for an interpose, "bleeds soul to keep the ward on {bearer}" for
upkeep. See ADR-0255 (amends ADR-0118).

**Consent routing** (in `world/scenes/cast_services.py:request_technique_cast`):
- Hostile → `seed_or_feed_encounter_from_cast` (combat).
- Benign + behavior-altering → PENDING `SceneActionRequest` (consent required).
- Benign + capability/stat → resolves immediately, including on other PCs.
- **Allegiance renewal is a cast, never a fight (#4091, ADR-4091 Decision 9).** A pure
  allegiance technique (charm/turn/calm: no damage profile, no removed conditions, every
  applied condition sets allegiance) re-cast on a target the caster already holds routes
  through the ordinary immediate-cast path (`is_allegiance_renewal`,
  `world.magic.services.hostility`) even though the same technique aimed at a fresh target is
  hostile (its condition rows target `ENEMY`). Striking first on a fresh target still opens a
  fight as usual; renewal only applies when the caster's own active hold on that exact target
  is already there.
- **Any benign cast that affects an ACTIVE combatant** seats the caster in
  that combatant's encounter (#2226, ADR-0119) — via
  `seat_caster_for_benign_intervention`, called post-resolution on both the
  immediate and consent-accept paths. Risk acknowledgement is automatic.

### Technique effect summary (#2898)

Every mechanical difference between one technique and another lives in four sibling
tables, and until #2898 none of them reached any player-facing surface. All four
technique payloads stopped at the `Technique` row — which is where the *least*
differentiation lives, since the authored catalog is near-uniform on `level`,
`intensity`, `control`, `anima_cost`, `reach` and `target_type`.

**The derivation** — `summarize_technique_effects(technique) -> TechniqueEffectPayload`
(`world/magic/services/technique_effects.py`; wire shapes in
`world/magic/types/technique_effects.py`). It reads `cached_capability_grants` /
`cached_condition_applications` / `cached_damage_profiles` / `cached_removed_conditions` /
`cached_treatments` (the fifth joined in #3682 - see below) and `cached_morale_effect` (#4619)
and **composes the two derivations that already existed** — `is_technique_hostile`
(`services/hostility.py`) and `derive_target_relationship` (`services/targeting.py`) —
rather than restating them. No model field is added: `Technique.target_type`'s own help
text records that relationship is derived, never stored.

The payload carries `relationship` / `hostile` / `target_type` / `reach` / `reach_hops` /
`arena` (`action_category`) / `anima_cost`, the five effect lists, `is_underspecified`,
and `summary` — the plain-words line, e.g. *"Cast on an ally, anywhere in the room, in the
physical arena. Costs 5 anima. Applies Guarded."* The sentence is authored server-side and
is byte-identical on the web and over telnet; clients render it, never re-derive it.

**Treatments and grants say what they are (#3682).** `TechniqueTreatment` was authorable
from #2668 and read by no display surface, no relationship derivation and no gap check, so
a technique whose only authored effect was a treatment described itself as having none —
it is the fifth list (`treatments`) and its own clause, *"Treats Bleeding."* A capability
grant is **standing possession**, not a cast effect (ADR-0248): knowing the technique is
what confers it, and the cast deliberately does nothing extra with the row. The clause
reads *"Knowing it grants flight."* and the frontend chip is labelled `Known:` — before
#3682 both sat unqualified among the cast clauses and told the player a lie about when the
capability arrives.

**Ordering is authoring order.** The four payload models carry `Meta.ordering = ["pk"]`, so
a multi-condition clause reads in the order staff attached the rows — "Applies Burning,
Blinded and Slowed", every time. Without it the queryset is unordered and the same technique
renders a different sentence between two requests, which also makes any test asserting the
clause pass only by luck. Damage-type names are additionally sorted inside the damage clause.

**Caching.** `Technique.cached_effect_summary` holds the built payload on the row, so a
technique fetched by pk anywhere in the process answers every surface from the identity
map after one build. The same rule made three query-per-call derivations read the cached
lists instead: `is_technique_hostile` (3 queries, called up to 6× per cast path),
`derive_target_relationship` (2), and `Technique.is_lock_applying` (1). The `cached_*`
lists `select_related` their `condition` / `damage_type` / `capability` FKs so the display
walk costs nothing further. **Any path that writes payload rows must call
`invalidate_technique_payload_caches(technique)`** — `build_technique` and
`TechniqueAdmin.save_related` do.

**One serialized shape.** `TechniqueEffectSummarySerializer` (`world/magic/serializers.py`)
is embedded as `effect_summary` by all four surfaces, which keep only their own extras:

| Surface | Serializer | Also gained |
|---|---|---|
| Magic API | `TechniqueSerializer` | `action_category` |
| Character creation | `CGTechniqueOptionSerializer` | — (the block carries cost / reach / targeting / hostility, every one of CG's gaps) |
| In-scene cast list | `CastableTechniqueSerializer` | **`description`** — the list previously shipped numbers and no prose |
| Character sheet (web + telnet) | `TechniqueEntry` via `_build_magic_gifts` | — |

`CastableTechniqueSerializer.hostile` reads off the same summary, so the top-level flag
and the block cannot disagree.

**Telnet.** Bare `cast` is the cast list (it raised a usage error before);
`sheet/magic` prints the summary line under each technique. Both, and the web
`castable-techniques` endpoint, read `castable_techniques_for_sheet`
(`world/scenes/cast_services.py`) so the two faces of "what can I cast" can't diverge.

**Authoring gaps are reported, not guessed at.** A technique whose authored condition is a
*side effect* rather than its point derives the wrong relationship — a self-teleport that
applies Flanked to an enemy derives as enemy-targeted, silently, and looks correct (found
while authoring #2764). Authored data carries no signal separating the point of a technique
from a side effect, so an override would mean the stored field this system rules out, and a
heuristic would be a second silent guess. Instead:

- `technique_relationship_is_ambiguous(technique)` — the applied + removed + treatment
  rows carry more than one distinct `target_kind`, so the single derived relationship is a
  guess.
- `technique_is_underspecified(technique)` — no condition, no removal, no damage profile,
  no treatment, so relationship isn't derivable at all. Display renders this as "effects
  not yet catalogued" rather than a blank; 86 of 272 authored techniques were in this
  state. Capability grants deliberately do **not** clear the flag: a grant is standing
  possession (ADR-0248), so a grant-only technique genuinely does nothing on cast.
- `technique_is_not_castable_standalone(technique)` (#3682) — the technique carries no
  `action_template`, so `request_technique_cast` refuses it ("not castable standalone")
  and `castable_technique_links_for_sheet` filters it out of both the web and telnet cast
  lists, while `get_technique_options` still offers it as a valid CG pick and
  `compute_magic_errors` still accepts it. **A fact, not a verdict** — whether a technique
  is meant to be castable at all is an authoring decision, and no readiness policy is
  enforced off the back of it. All 306 authored techniques were in this state when it was
  added, which is exactly why it is *not* a `TechniqueAuthoringGap` member: folding it in
  would make gap membership mean "every technique" and bury the two gaps that are about
  unreadable authored data. `TechniqueAdmin` filters it in SQL
  (`action_template__isnull=True`) and shows it in the `Gap` column.

`technique_effect_authoring_gaps()` collects the first two; `TechniqueAdmin` surfaces all
three as the `Targets` / `Gap` columns and an "authoring gap" filter.
`derive_target_relationship`'s own answers are deliberately unchanged — it gates live cast
targeting.

**Shared condition application** (`world/magic/services/condition_application.py`):
`apply_technique_conditions(*, technique, success_level, eff_intensity, targets_by_kind, source_character, applied_condition_rows=None)`
— extracted from combat's `_apply_conditions`; used by **both** combat and standalone
cast paths. Callers build `targets_by_kind` before calling; the service iterates
`TechniqueAppliedCondition` rows and batches them via `bulk_apply_conditions`.
The optional `applied_condition_rows=` override was added in #1582 for the signature-bonus
seam: when provided, those rows are applied instead of the technique's own condition rows;
when `None` (default), all existing callers are byte-identical.
`compute_severity` / `compute_duration_rounds` were relocated from `TechniqueAppliedCondition`
to `AbstractAppliedCondition` (pure upward move, no behavior change) so `SignatureMotifBonusAppliedCondition`
rows can be passed through the same seam.
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

### Language comprehension effects are not combat power (#4090)

The DE (damage-equivalent) pricing pipeline (`world/magic/services/technique_power_eval.py` and
its standalone siblings `condition_power_eval.py`/`capability_power_eval.py`, sharing the
row/technique-independent formula core in `de_valuation.py`, #3390, ADR-0239; see INDEX.md's
"Game Tuning & Game Ops Dashboards" for the full evaluator writeup) prices a
`ConditionModifierEffect` as a bonus on the 1-100 combat roll. A language-comprehension bonus
(a `ModifierTarget` whose `target_trait.trait_type` is `LANGUAGE`) is not that, so it is excluded
rather than mispriced:

- `de_valuation.modifier_effect_shift(condition, *, severity)` excludes any effect whose
  `modifier_target.target_trait.trait_type == TraitType.LANGUAGE`, alongside the pre-existing
  team-damage-percent-lane exclusion.
- `de_valuation.has_language_modifier_effects(condition, *, language_condition_ids=None)`
  reports whether a condition carries a language effect at all, including one authored on a
  STAGE, which `modifier_effect_shift`'s condition-level-only query would miss, so a staged
  understanding condition still reports "not combat power" rather than a silent zero.
  `condition_ids_with_language_effects(condition_ids)` is its batch sibling: one query up front
  for every condition id a loop will check, never one `has_language_modifier_effects` call per
  row (the #4090 review finding the batch form exists to fix).
- When a condition carries a language effect, `de_valuation.not_combat_power_valuation(condition)`
  reports the explicit `PayloadValuation(value=0.0,
  provenance=ValuationProvenance.NOT_COMBAT_POWER)` row instead of a silent gap, and the standalone
  condition evaluator (`condition_power_eval.py`) appends the `FLAG_NOT_COMBAT_POWER`
  (`"not_combat_power"`) flag. `technique_power_eval.py` appends the same flag to a technique's
  report whenever any of its valuations carries `ValuationProvenance.NOT_COMBAT_POWER`.

### Motif System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Motif` | Character-level magical aesthetic; one per character, shared across all Gifts | `character` (O2O CharacterSheet), `description` |
| `MotifResonance` | Resonances in a motif | `motif`, `resonance` (FK to `Resonance`), `is_from_gift` |
| `MotifResonanceAssociation` | Links resonances to facets in a motif (cap 5 per resonance, `MotifResonanceLink.clean()`-enforced) | `motif_resonance`, `facet` |
| `MotifResonanceStyle` | Player binding of a `Style` to one of the character's motif resonances (cap 3 per resonance, `MotifResonanceLink.clean()`-enforced) | `motif_resonance`, `style` (FK to `items.Style`) |

`CharacterFacet` **[ABSENT]** — this table used to list it as "links characters to facets".
No such model or table exists; it was dropped in favour of Thread-on-Facet (see
`docs/architecture/items-fashion-mantles.md`), and a character's facets are reached through
`Motif → MotifResonance → MotifResonanceAssociation`. Verified against code 2026-09-11.

**Player-facing style binding (#2030) [BUILT & WIRED]:** binding a `Style` to a
claimed resonance is a normal player action, not admin-only. Service
(`services/motif_style.py`): `bind_motif_style(sheet, style, resonance)` (lazily
creates `Motif`/`MotifResonance` if absent; replace semantics on rebind; cap
enforcement delegates to `MotifResonanceLink.clean()`), `unbind_motif_style`,
`motif_style_bindings`. Exceptions (`exceptions.py`): `StyleResonanceUnclaimed`,
`StyleBindingCapExceeded`, `StyleNotBound`. Actions (`actions/definitions/
motif_style.py`, REGISTRY, `category="magic"`): `BindMotifStyleAction` /
`UnbindMotifStyleAction` / `ListMotifStylesAction`. Telnet: `CmdMotif`
(`commands/motif.py`, key `"motif"`, `motif bindstyle <style>=<resonance>` /
`motif unbindstyle <style>` / bare `motif`). Web: `MotifStyleViewSet`
(`views_motif_style.py`, `/api/magic/motif-styles/`), scoped to a specific owned
character via an optional `X-Character-ID` header (`CharacterContextMixin`); falls
back to the caller's active puppet when absent. The Style catalog itself is a
separate read-only endpoint, `StyleViewSet` at `/api/items/styles/`
(`world/items/views.py`). This binding is what the coherence walker
(`passive_motif_style_bonuses` in `world/mechanics/services.py`, wired into
`equipment_walk_total`) and the peer style-presentation endorsement
(`create_style_presentation_endorsement` in `services/gain.py`) already read —
#2030 only added the authoring surface; the consumer-side wiring predates it. See
`src/world/magic/CLAUDE.md`'s "Motif System" section for the full coherence-walker
detail.

### Signature Motif Bonus (#1582 — ADR-0072) [BUILT & WIRED]

A **`SignatureMotifBonus`** is a staff-authored, facet/resonance-gated additive bonus
that a player may attach to a TECHNIQUE-kind Thread. Signing a technique applies the
character's Motif to that one technique above its Gift baseline — a cosmetic +
mechanical flourish, NOT a `TechniqueVariant` and NOT a resonance divergence.

**Design boundary:** `SignatureMotifBonus` must NOT inherit `AbstractSpecializedVariant`
and must NOT participate in `fire_variant_discoveries`. It is an additive flourish; it
never changes the technique's identity.

**Catalog model** (`models/signature.py`):

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SignatureMotifBonus` | Staff-authored bonus gated on the character's Motif | `name`, `narrative_snippet`, `required_facet` FK (Facet, nullable), `required_resonance` FK (Resonance, nullable), `flat_intensity_delta` (SmallInt, additive to effective intensity), `min_crossing_level` (default 3; the only gate on which thread depth unlocks this bonus, #4099), `creation_point_cost` (nullable; character-creation points to weave this flourish at creation, blank = not offered in creation, #4099). At least one of `required_facet`/`required_resonance` must be set (`clean()` enforces). AND semantics when both gates set. |
| `SignatureMotifBonusDamageProfile` | Damage profile for a bonus (inherits `AbstractDamageProfile`) | `signature_bonus` FK |
| `SignatureMotifBonusAppliedCondition` | Applied condition for a bonus (inherits `AbstractAppliedCondition`) | `signature_bonus` FK |

**Gradual unlock (#4099, ADR-4099):** `min_crossing_level` is the only gate on which
thread depth unlocks a flourish, now that the old hard `thread.level >= 3` floor on
`set_signature_bonus` is gone. Staff may author a bonus below level 3 for an earlier
flourish, or above 3 for a deeper one; `next_signature_bonus(thread, catalog)`
(`services/signature.py`) returns the nearest not-yet-reached flourish for a "keep
imbuing" progress display.

**Gate predicate** — `SignatureMotifBonus.qualifies_for(character_sheet) -> bool`: checks
the character's `Motif` against `required_resonance` (via `MotifResonance`) and
`required_facet` (via `MotifResonanceAssociation`). Returns `False` when no Motif exists.

**Thread FK** — `Thread.signature_bonus` (nullable FK to `SignatureMotifBonus`, PROTECT).
Only settable when `thread.target_kind == TargetKind.TECHNIQUE` — enforced by `clean()`
and DB `CheckConstraint("thread_signature_bonus_technique_only")`. Migrations: 0066 +
0067.

**Selection service** (`services/signature.py`):

| Function | Purpose |
|----------|---------|
| `available_signature_bonuses(character_sheet)` | Full catalog filtered by `qualifies_for` |
| `set_signature_bonus(thread, bonus)` | Attach bonus; guards: TECHNIQUE-kind, qualifies, owner knows technique. Invalidates `character.threads` cache. |
| `clear_signature_bonus(thread)` | Set `signature_bonus=None`; idempotent. Invalidates cache. |
| `signature_bonus_for(character, technique) -> SignatureMotifBonus | None` | Cast-wiring read — finds the active TECHNIQUE thread for the technique via cached handler; returns its bonus or None. |

**Cast wiring** (`services/signature_effects.py`):

| Function | Purpose |
|----------|---------|
| `signature_intensity_delta(character, technique) -> int` | Returns `bonus.flat_intensity_delta` or 0; added to `use_technique(power_intensity_bonus=…)` on both cast paths |
| `apply_signature_bonus_conditions(*, character, technique, success_level, eff_intensity, targets_by_kind, source_character)` | Applies `bonus.cached_condition_applications` through the SHARED `apply_technique_conditions` seam (`applied_condition_rows=` param) — NO parallel apply path |
| `signature_damage_profiles(character, technique) -> list` | (#1728) Returns `bonus.cached_damage_profiles` or `[]`; `CombatTechniqueResolver._apply_damage` (`world/combat/services/`) appends these to the technique's own profiles before resolving damage |
| `resolve_signature_snippet(character, technique) -> str \| None` | (#1728) Resolves the cosmetic clause — prefers `bonus.narrative_snippet`, falls back to the first Motif facet name; shared by the non-combat cast pose and the combat OUTCOME narration |

`apply_technique_conditions` gained an optional `applied_condition_rows` param (default
`None` = use the technique's own rows; when provided, applies those rows instead). This
keeps all existing callers byte-identical while enabling the signature seam.
`compute_severity` / `compute_duration_rounds` were relocated from
`TechniqueAppliedCondition` to `AbstractAppliedCondition` (pure upward move — no
behavior change).

**Non-combat narration** (`narration.py`): `signature_clause(snippet) -> str` builds a
cosmetic em-dash clause from the bonus's `narrative_snippet`. Used in
`render_cast_outcome_narration` (standalone cast pose) via the `signature_snippet=`
param. (#1728) Combat-path cosmetic narration now shares the same snippet resolution via
`resolve_signature_snippet` (`services/signature_effects.py`), surfaced in
`render_action_outcome_narration` + `_record_and_broadcast_pc_action`
(`world/combat/services/`).

**Web surface (#1728)** (`views_signature.py`): `SignatureViewSet` dispatches
`SignatureListAction` / `SignatureSetAction` / `SignatureClearAction` through the shared
`PuppetActorMixin` (`views_actor.py`, also used by `SanctumViewSet`). Routes (`urls.py`,
basename `signature`): `GET /api/magic/signatures/`, `POST
/api/magic/signatures/set/`, `POST /api/magic/signatures/clear/`.

**Admin:** `SignatureMotifBonusAdmin` (`admin.py`) with inlines for the three payload
child models; each inline's `help_text` flags wiring status (capability grants are
inert — no cast seam yet).

**Actions** (`actions/definitions/signature.py`, REGISTRY, `category="magic"`):
- `SignatureSetAction` (key `"signature_set"`) — attach a bonus to a thread.
- `SignatureClearAction` (key `"signature_clear"`) — remove the current bonus.
- `SignatureListAction` (key `"signature_list"`) — list available bonuses + current settings.

**Telnet command** — `CmdSignature` (`commands/signature.py`, key `"signature"`, `locks
"cmd:all()"`): routes `signature set technique=<name> bonus=<name>` / `signature clear
technique=<name>` / bare `signature` or `signature list` through `dispatch_player_action`.
Namespaced to avoid broad one-word key collisions (same reasoning as `CmdSanctum`).

**E2E test:** `world/magic/tests/integration/test_signature_motif_e2e.py` — full journey:
Motif → weave TECHNIQUE thread → select bonus → cast → assert cosmetic snippet in pose
Interaction, intensity delta applied, condition lands on caster. Also tests rejection
(`SignatureBonusNotAvailable` / `TechniqueNotOwned`) and bonus portability between threads.

**Resolved (ADR-0248, #3449):** no capability-grant cast seam will be built — grants
mean standing possession, and cast-time capability boosts are authored as applied
conditions (`ConditionCapabilityEffect`, outcome-scaled via `compute_severity`). The
formerly-inert `SignatureMotifBonusCapabilityGrant` family was stripped.

**Shipped in #1728** (see `docs/adr/0072-...` addendum): the `damage_profiles` combat
cast seam, combat cosmetic narration, and the web `SignatureViewSet`.

### Technique personalization (#4099, ADR-4099) [BUILT & WIRED]

A character personalizes a technique on their own hold of it (`CharacterTechnique`),
never on the shared catalog `Technique`. Personalization is creation-only (owner ruling,
2026-10-01): a player sets it while building the character, and nothing in play lets them
rename or re-price a technique they already hold. Three pieces, each optional and each
costed separately in CG points:

- a free **name and description** (`custom_name`/`custom_description`, display only, never
  a lookup key);
- a **price** (`CharacterTechnique.price`, a `Restriction` of `kind=PRICE`, offered in
  creation when its `creation_point_cost` is set). A price costs something real: it may
  consume carried items on each cast that pays it (`PriceComponentRequirement` rows:
  `item_template`, `quantity`, optional `min_quality_tier`; the sibling of
  `RitualComponentRequirement`) and may inflict an authored condition on the caster
  (`Restriction.inflicted_condition`). Both are PRICE-only (`clean()` on both models, DB
  constraint `restriction_inflicted_condition_price_only`). A cast that **pays** the price
  gets its `power_bonus` as a power-ledger term and its `cast_narration` in the cast line,
  spends the components and takes the condition. A caster who lacks a component still
  casts, without the price: no bonus, no clause, no condition, nothing spent;
- an **early form** (`CharacterTechnique.early_form`, a `TechniqueVariant` bought before
  the gift thread reaches its level). Honored by the variant resolver only for its buyer,
  only when the cast's resolved resonance matches the form's own authored resonance (a hold
  carries no resonance of its own), and never for a role-granted hold.

**Services** (`src/world/magic/services/technique_personalization.py`, the hold-reading
seam used everywhere a technique's own name/price appears):

| Function | Purpose |
|----------|---------|
| `clean_custom_technique_name(value) -> str` | Hygiene for a player-typed name: collapses whitespace, then REJECTS (raises, does not strip) an em/en-dash, `\|` markup, or a control character, and enforces the length cap. Raises `InvalidPersonalText`. The web client strips those characters client-side before submit (`sanitizeCustomName`, `PersonalizationPanel.tsx`), so this server check is normally unreachable from the UI, but it is what actually rejects a request that skips the client (API/telnet). |
| `clean_custom_technique_description(value) -> str` | Same hygiene for the description (newlines allowed). |
| `hold_display_name(hold, *, fallback) -> str` | `hold.custom_name` if set, else `fallback`. |
| `technique_display_name(character, technique, *, fallback=None) -> str` | Reads the caster's own hold (via the cached handler) and returns its display name, else the catalog name. |
| `technique_price_for(character, technique) -> Restriction \| None` | The hold's price for this technique, or `None` (also `None` once staff re-kind the row away from PRICE). Read by `price_paid_for_cast`; says nothing about whether a cast pays. |
| `price_paid_for_cast(character, technique) -> PricePayment \| None` | **The one decision** whether this cast pays the price. A price with no components always pays; otherwise it pays only when `gather_consumable_pks` finds every component in `character.carried_items`, and the allocation rides the returned `PricePayment` (`types/personalization.py`). Called once, inside `use_technique`. |
| `settle_price_payment(*, character, technique, payment) -> None` | Spends a paid price after the cast resolves: `consume_materials` on the decision's allocation, then `apply_condition` for the inflicted condition. No-op for `None`. |
| `paid_price_snippet(price) -> str \| None` | The narration clause (`cast_narration`, else name) of the price a cast PAID (`TechniqueUseResult.price_paid`), never the hold's. |
| `price_components_by_price(price_ids) -> dict[int, list[PriceComponentRequirement]]` | One bulk read of each price's components (none for no ids), used by the CG options payload and the sheet. |
| `price_consumes_payload(components)` / `price_inflicts_name(price)` | Display shapes for a price's cost: `[{name, quantity}]` from authored template names, and the authored condition name or `None`. |
| `seed_motif_from_gift_resonance(sheet, resonance) -> MotifResonance` | Seeds a `Motif`/`MotifResonance` for a brand-new character at finalize, so a flourish (resonance-gated via `required_resonance`; a price carries no resonance of its own) can qualify once the gift resonance resolves. |

**Creation services** (`src/world/magic/services/creation_personalization.py`, the
draft-time half):

| Function | Purpose |
|----------|---------|
| `parse_personalization_picks(raw, *, technique_ids) -> list[TechniquePersonalizationPick]` | Reads `draft_data["technique_personalizations"]` (keyed by technique id, a string); drops entries for a deselected technique. |
| `creation_personalization_options(techniques, *, resonance_id) -> list[PersonalizationOptionSet]` | What creation offers (flourishes/forms/prices with a `creation_point_cost`) for each chosen technique at the draft's gift resonance. Backs `GET /drafts/{id}/personalization-options/`. |
| `personalization_pick_errors(...) -> list[str]` | Validation: an unoffered option, a flourish/form at the wrong resonance, a malformed pick. |
| `priced_personalization_lines(picks, *, techniques_by_id) -> list[PricedPersonalizationLine]` | One CG-points breakdown line per priced pick, read by `CharacterDraft.calculate_cg_points_breakdown`. |
| `apply_creation_personalizations(...)` | Finalize-time write: sets the hold's name/description/price/early_form and, for a flourish pick, calls `weave_creation_technique_thread`. |

**Gradual flourish** (`src/world/magic/services/threads.py`,
`src/world/magic/services/signature.py`):

- `weave_creation_technique_thread(character_sheet, technique, resonance, *, level) ->
  Thread` weaves a TECHNIQUE thread at a starting level during creation, paid for in CG
  points. Raises `CreationThreadLevelTooHigh` above `CREATION_PERSONALIZATION_MAX_LEVEL`
  (1), because a new character is level 1 and a thread never exceeds its character's
  level (#4585); that also keeps creation below the first crossing (level 3).
- `next_signature_bonus(thread, catalog) -> SignatureMotifBonus | None` returns the
  nearest flourish the thread has not yet reached, for a "keep imbuing" display. See
  "Gradual unlock" above: `min_crossing_level` is the only gate on when a flourish
  unlocks, not a hard level-3 floor.

**Price at cast** (`src/world/magic/services/techniques.py` `use_technique`, the seam
every cast path shares: scene cast, social enhanced action, combat round, clash, battle).
After the Soulfray gate, `use_technique` calls `price_paid_for_cast` exactly once. The
resulting `PricePayment` (or `None`) threads to: `_derive_power(price_payment=...)` →
`PowerTermContext.price_payment` → `price_power_term` (`services/power_terms.py`), which
adds the paid price's `power_bonus` in raw cast-power units, never through the builder's
refund multiplier, and never re-reads the hold; `settle_price_payment`, called right after
`resolve_fn` inside `transaction.atomic()` (opened only for a paid cast), so a cast
refused by the Soulfray gate or cancelled at `TECHNIQUE_PRE_CAST` consumes nothing and a
cast that fails while resolving rolls its consumption back; and
`TechniqueUseResult.price_paid`, which the scene cast pose
(`create_cast_outcome_pose`), the combat outcome narration
(`_record_and_broadcast_pc_action`) and the clash contribution's ACTION interaction
(`commit_to_clash`) read through `paid_price_snippet`. Combat calls `use_technique` when the
round resolves, so the component is checked at resolution, not at declaration. Neither
declaration label (`render_action_declaration_label`, `render_clash_contribution_label`)
carries a price clause, since nothing is decided yet when they render.

**Showing the cost.** The CG option payload (`CGPersonalizationOptionSerializer`) carries
`consumes` (`[{name, quantity}]`) and `inflicts` (condition name or null) on every option
(always empty/null for a flourish or form), and `PersonalizationPanel.tsx` shows them on
the price rows and the collapsed price summary. The sheet's `TechniquePricePayload` carries
the same two fields, rendered by `SpellbookTab.tsx` and the telnet `sheet/magic` price
line (`Consumes:` / `Inflicts:`). Staff author both on the Restriction admin
(`PriceComponentRequirementInline`, `inflicted_condition` autocomplete). The TUNING
Required-content row `price-components-active` lists any price component whose item
template is inactive (no new ones can be made, so the price eventually stops being paid).

**Early form resolution** (`world/magic/specialization/services.py`,
`_resolve_technique_variant`): after the ordinary thread-derived variant match, checks the
caster's own hold for an `early_form` whose OWN authored resonance equals the cast's
resolved resonance (a hold carries no resonance of its own — only the `TechniqueVariant`
row does). Applies only when the hold is not role-granted (`role_source_id is None`); a
role-granted hold's `early_form` never leaks to the role-holder. A naturally-reached
higher-level form still beats an early pick once the thread catches up (compared by
`unlock_thread_level`); `TechniqueFormSerializer.is_early` marks a payload row bought this
way.

**Exceptions** (`exceptions.py`): `CreationThreadLevelTooHigh` (raised by
`weave_creation_technique_thread`). `InvalidPersonalText` (raised by the name/description
hygiene functions). The old `SignatureBelowCrossing` exception and its hard `thread.level <
3` guard are removed; `min_crossing_level` is the only remaining gate.

**Endpoint:** `GET /api/character-creation/drafts/{id}/personalization-options/` (see
`docs/systems/character_creation.md`'s "Magic" API section).

**Visibility (leak table):**

| Surface | Who sees it | What it shows | Contained by |
|---|---|---|---|
| Sheet magic section (web and `sheet/magic` telnet) | owner; others per `magic_visibility` tier (#1271) | custom name, custom description, price, next flourish | the existing section gate; the description shows only where the technique itself is visible |
| Castable list (web), bare `cast` (telnet), combat technique picker | owner only | custom name plus the catalog name, as `Name (Catalog name)` | these endpoints serve only the caster |
| Cast narration (scene and combat) | room/encounter audience | custom name plus the price's narration clause, never the description — **except when a specialized form applies: the form's own name wins over the custom name, since it describes what actually happened in THIS cast** (ruled 2026-10-02, fixing #4110 CI; `_resolve_and_pose_cast` in `world/scenes/cast_services.py`) | the technique's name was already in this line; a concealed tier names neither |
| Combo planning panel | party | catalog name only | a shared coordination vocabulary other players read |

### Threads as Currency Consumers (Resonance Pivot Spec A §2.1)

The legacy 5-axis `Thread` / `ThreadType` / `ThreadJournal` / `ThreadResonance`
family was deleted in favor of a discriminator + typed-FK design. A Thread is
owned by a CharacterSheet, channels a single Resonance, and is anchored to
exactly one of: Trait / Technique / Facet / CharacterRelationship (one SIDE of a
tie since #3957) / RelationshipCapstone / CovenantRole / Mantle / SanctumDetails. The bare ROOM
`target_kind` was removed; SANCTUM is the leveled room anchor.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Thread` | Per-character attachment to one anchor that channels one Resonance | `owner` FK CharacterSheet, `resonance` FK, `target_kind`, `target_trait` / `target_technique` / `target_facet` / `target_relationship` / `target_capstone` / `target_covenant_role` / `target_gift` / `target_mantle` / `target_sanctum_details` (exactly one populated per kind), `name`, `description`, `developed_points`, `level`, `created_at`, `updated_at`, `retired_at` (soft-retire), `slot_kind` (SANCTUM only: PERSONAL_OWN / COVENANT / HELPER), `signature_bonus` (nullable FK to `SignatureMotifBonus`, PROTECT — only settable on TECHNIQUE-kind threads, enforced by `clean()` + `CheckConstraint`, #1582 ADR-0072) |
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
| `ThreadPullEffect` | Authored pull-effect template | `target_kind`, `resonance` FK, `tier` (0..3), `min_thread_level`, `effect_kind`, + mutually-exclusive payload columns: `flat_bonus_amount`, `intensity_bump_amount`, `vital_bonus_amount` (+ `vital_target`), `capability_grant` FK to `CapabilityType`, `narrative_snippet`, `target_form` FK to `forms.CharacterForm` (nullable; set only for `ASSUME_ALTERNATE_SELF`, which names the form whose profiles to assume on cast), `resistance_amount` (+ `resistance_damage_type` FK to `conditions.DamageType`; null = all types — `RESISTANCE` effect kind, #1580). `target_gift` (nullable FK to `magic.Gift`) — when set, this pull-effect applies only to GIFT threads anchored to that specific gift (species-gift-specific tier-0 passives); null rows serve as the generic fallback for that kind. `regard_polarity` (`RegardPolarity`: OFFENSIVE / PROTECTIVE / NEUTRAL, default NEUTRAL, #1831) — how Court-role (COVENANT_ROLE) pull modulation responds to the Court leader's signed regard for the live target; ignored for every other `target_kind`. Tier 0 = passive always-on; tiers 1–3 = paid pulls. Unique per (target_kind, resonance, tier, min_thread_level) — with two partial `UniqueConstraint`s for GIFT kind (one with `target_gift` set, one without). CheckConstraints enforce payload/effect_kind alignment — `ASSUME_ALTERNATE_SELF` requires `target_form` set and all numeric/capability/snippet payload empty; `RESISTANCE` requires `resistance_amount` set and all other payload null; all other kinds require `target_form__isnull=True`. `get_pull_effects_for_thread(thread, **filters)` (`world/magic/services/pull_effects.py`) resolves the correct rows: for GIFT kind, tries `target_gift`-specific rows first, falls back to `target_gift IS NULL` |
| `ImbuingProseTemplate` | Fallback narrative prose for Imbuing | `resonance` FK (nullable), `target_kind` (nullable), `prose`. Row with both NULL = universal fallback |
| `Ritual` | Authored ritual procedure | `name`, `description`, `hedge_accessible`, `glimpse_eligible`, `narrative_prose`, `execution_kind` (SERVICE/FLOW), `service_function_path` (SERVICE), `flow` FK (FLOW), optional `site_property` FK. CheckConstraint: exactly one dispatch payload |
| `RitualComponentRequirement` | Items required to perform a Ritual | `ritual` FK; exactly one of three modes (`CheckConstraint` `ritualcomponentrequirement_exactly_one_mode`): `item_template` FK (template-mode), `min_touchstone_tier` FK to `ResonanceTier` (touchstone-mode), or `matches_target_resonance` (target-resonance mode, #4733: an item tied to the resonance being converted toward, an item with a motif facet tied to it, or an item at or over `min_item_meaning`, which only this mode may set and blank turns off); `quantity`, optional `min_quality_tier` FK, `authored_provenance` |
| `ResonanceTier` | Ordered potency tier for resonance-tied items/touchstones (independent of `items.QualityTier` — potency and crafting quality are orthogonal axes) | `name` (unique), `tier_level` (unique, ordering/threshold value), `description` |

**Touchstones + reagents (#707 — ADR-0087).** `ItemTemplate.tied_resonance` (FK to `Resonance`) +
`ItemTemplate.resonance_tier` (FK to `ResonanceTier`) mark a template as a *touchstone* —
a resonance-tied item a character personally attunes to. `ItemInstance.attuned_to_character_sheet`
+ `attuned_at` record that binding, set by `attune_touchstone()` (`services/touchstones.py`,
dispatched by the seeded "Rite of Attunement" `Ritual`, `seeds_touchstones.py`). A
`RitualComponentRequirement` row in touchstone-mode (`min_touchstone_tier` set, `item_template`
null) is satisfied by any `ItemInstance` attuned to the performer whose template's
`resonance_tier.tier_level` meets the requirement and whose `tied_resonance` matches either the
ritual's `resonance_context` (when given, e.g. Sanctification's founding Resonance) or any
Resonance the performer has claimed. The shared validate/consume helper
`resolve_and_consume_ritual_components(ritual, components, performer_sheet, resonance_context=None)`
(`services/ritual_components.py`) partitions a ritual's requirements into template-mode and
touchstone-mode, resolves both against a caller-supplied `components` list of carried
`ItemInstance` rows, and atomically consumes the matched set — all-or-nothing (raises
`RitualComponentError` and consumes nothing if any requirement is unsatisfied). Used by both
`PerformRitualAction` (the generic ritual seam — telnet `CmdRitual`/`_gather_components` auto-
gathers everything carried; web `RitualPerformRequestSerializer.components` is an explicit
item-id list) and, independently, `SanctumInstallAction` (Ritual of Sanctification does not
dispatch through `PerformRitualAction` — see the Sanctum section below). `seeds_touchstone_content.py`
seeds a small framework-proving catalog (three `ResonanceTier` rows, one example Praedari-paw
touchstone template, three generic reagent templates) and attaches requirements to both
Sanctification rituals; a full per-resonance/per-tier catalog is separate content-authoring work.
Attunement itself (binding, not consuming) is the seeded **Rite of Attunement** `Ritual`
(SERVICE, `seeds_touchstones.py`) dispatching `attune_touchstone()`
(`services/touchstones.py`) through the *generic* `PerformRitualAction` seam — unlike
Sanctification, this one genuinely goes through `CmdRitual`/`RitualPerformView`. It sets
`ItemInstance.attuned_to_character_sheet` + `attuned_at`, raising `RitualComponentError` if the
item isn't resonance-tied, isn't held by the performer, is already attuned, or the performer
hasn't claimed the item's `tied_resonance`. Narrative acquisition of touchstones/reagents
themselves (no shop system exists) is documented in `docs/systems/items.md`
(`grant_touchstone_item_to_character`). See ADR-0087 for the extension-vs-parallel-model
decision and the `client_hosted` dispatch discovery.

### Ritual anima pools & the blood economy (#3001, ADR-0205) [BUILT & WIRED]

Rituals are the home of generalized magic — there is deliberately **no Gifted-gate in the
ritual framework**; the price is the gate. Anima itself is a level-scaled economy: maximum
= `AnimaConfig.level_zero_maximum` (10) at level 0, else `maximum_per_level` (100) × level
(recomputed on both level-write spines — `apply_class_level_advance` and
`set_primary_class_level` — plus CG finalize, via `recompute_max_anima`). Regen is a flat
`AnimaConfig.daily_regen_amount` (1)/day; appetite holders never regen naturally (their
delta is the `AppetiteUpkeep` drain — blood daily −1 floor ceil(10%), shade daily −1 floor
0, essence 0). `deduct_anima` draws `glut` first (#2853's documented-but-inert rule, now
real).

- **`Ritual.anima_requirement`** (0 = folk rite) is powered by a pool of
  `RitualAnimaContribution` rows (`models/ritual_pool.py` — audit rows that outlive their
  session via SET_NULL). Contribution routes (`services/ritual_pool.py`):
  `contribute_channel` (own anima, glut-first), `contribute_prick` (1 anima, trivial
  damage), `contribute_gash` ((1d6+1) × level, a real wound + fatigue),
  `contribute_sacrifice` (victim drained wholesale; reuses `feed_anima`'s kill guards).
- **Death harvest:** a killing drain — feeding gorge or ritual sacrifice — yields
  `AnimaConfig.death_harvest_multiplier` (20) × the victim's full maximum (feeder overflow
  lands in `glut`; ritual harvests pour into the pool). Fires the murder taint.
- **Blood taints:** extraction is affinity-neutral; the METHOD taints, via authored
  `CompromiseActType` rows chosen by their `feeding_taint_role` field (`FeedingTaintRole`:
  murder, seduction by deception, seduction by predation), never by name (`grant_blood_taint`
  in `services/feeding.py`, log-skip when unauthored). Staff must set `feeding_taint_role` on
  each authored act, or the taint never fires: the murder act (+5 Praedari) and both
  seduction acts (+1 Insidia, +1 Praedari) on every essence-kind feed.
- **Pool gate** (`resolve_pool_gate`): met → as authored; ≥2× → spectacular tier
  (stashed into `session_kwargs["anima_pool"]` for requirement-bearing session rituals;
  `ActionResult.data["spectacular"]` for solo performs); underfilled → the ritual's own
  `RitualCheckConfig` check at a deficit-bumped difficulty, failure = fizzle that
  **consumes** the session and pool (`RitualFizzledError`). Enforced at both dispatch
  lanes: `fire_session` and `PerformRitualAction` (which auto-channels the solo performer
  toward the requirement — never via kwargs, which would block sustained declaration).
- **Hedge access:** `ritual_visible_to(sheet, ritual)` = `hedge_accessible` OR
  `magical_profile(sheet)` — one predicate for browse (`RitualViewSet.get_queryset`) and
  perform (`PerformRitualAction`). Session drafting is deliberately ungated (Durance/
  covenant/induction rites gate in their own service functions).
- **Contribute endpoint:** `POST /api/magic/ritual-sessions/{id}/contribute/`
  (`{kind, amount?, victim_sheet_id?, lethal?}`; initiator or ACCEPTED participant;
  NPC-only PLACEHOLDER consent rail on sacrifice victims). Session detail carries
  `anima_requirement` + `anima_pool_total`.

### Sustained rituals — conducting a ritual under fire (#2705, ADR-0190)

`RitualCheckConfig.sustained_rounds` (PositiveSmallInt, default 0) marks a ritual as
conductable across combat rounds rather than firing the instant it's invoked — 0 (the
default) is today's fire-immediately behavior, unchanged for every existing ritual. This
is the PC-side sibling of `world.combat`'s telegraphed-wind-up mechanism (ADR-0161): the
combat-domain model (`world.combat.models.SustainedAction`) and its declaration/erosion/
maturation machinery are documented in full in `docs/systems/INDEX.md`'s combat section
and `docs/architecture/combat-resolution-loop.md` — this entry covers only the ritual-side
seam.

- **The dispatch switch is extracted, not duplicated.** `dispatch_ritual(*, ritual,
  performer_sheet, **kwargs)` (`world/magic/services/ritual_dispatch.py`) is the
  SERVICE/FLOW/CEREMONY switch pulled verbatim out of `PerformRitualAction`
  (`actions/definitions/ritual.py`) so a ritual dispatched at maturation — several
  rounds after the components were consumed — shares the exact same switch the
  synchronous non-combat path uses, instead of a second copy drifting out of sync.
  `PerformRitualAction.execute()` now calls `dispatch_ritual(...)` where it used to
  branch inline; behavior-preserving (the pre-existing ritual action/service tests are
  the oracle — none of them changed).
- **The deferral gate.** `try_declare_sustained_ritual(*, sheet, ritual, kwargs)`
  (`world.combat.services`) is called from `PerformRitualAction.execute()` after
  `_validate_components` (components are consumed there — a broken sustained ritual is
  genuinely spent, never refunded) and before `dispatch_ritual`. Returns `None` — "not
  sustained, dispatch immediately as today" — unless the performer resolves to an
  ACTIVE `CombatParticipant` in a DECLARING encounter, `ritual.check_config_or_none
  .sustained_rounds > 0`, `kwargs` is empty, and the performer isn't already holding an
  earlier round's commitment. When it fires, it rolls the absorption budget (the same
  Concentration-check helper the TECHNIQUE side uses — see INDEX.md), creates a
  `SustainedAction(sustained_kind=RITUAL, declared_action=None)` — null because a
  ritual is invoked through `PerformRitualAction`, not the combat round-declaration
  seam a TECHNIQUE commitment clones from — and returns a success `ActionResult`
  ("You begin `<ritual>`, holding it together.") instead of the ritual's normal result.
- **The ADR-0007 kwargs guard.** A `SustainedAction` is a fixed-column DB row; a ritual
  invoked with non-empty `kwargs` (e.g. a `thread` target) cannot be deferred, because
  persisting an arbitrary per-cast kwargs dict to replay at maturation would need a
  JSON field, which ADR-0007 forbids. Such a ritual dispatches immediately, exactly as
  it would outside combat — rituals authored with `sustained_rounds > 0` are expected
  to be no-kwargs SERVICE/FLOW calls for this reason. Not raised, not blocked: this is
  a silent fall-through, the same as every other "not sustained" case.
  `try_declare_sustained_ritual`'s already-holding check also does not raise (unlike
  the TECHNIQUE-side `declare_action` guard) — a ritual invocation is not the
  round-declaration seam, so blocking outright would strand the components already
  consumed inside the same atomic transaction.
- **Maturation.** At `resolves_round`, `_mature_sustained_ritual` (`world.combat
  .services`) calls `dispatch_ritual(ritual=sustained.ritual,
  performer_sheet=sustained.participant.character_sheet)`, catching only the same
  ritual-surface exceptions `PerformRitualAction` itself catches
  (`RitualComponentError`/`ResonanceInsufficient`/`AnchorCapExceeded`/
  `InvalidImbueAmount`/`XPInsufficient`/`GhostTutorError`) — a content-authoring gap in
  one participant's ritual must not abort round resolution for every other combatant.
  A caught failure still deletes the `SustainedAction` with no refund (components were
  already spent at declaration).

### ThreadWeaving Acquisition (Spec A §2.1 / §4.2)

How a character gains the *right* to weave threads on a given anchor scope.
Same discriminator + typed-FK pattern as `Thread`. Gifts and Paths are not
thread anchors — they appear here only as unlock dimensions.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ThreadWeavingUnlock` | Authored unlock catalog | `target_kind`, one of (`unlock_trait` FK Trait / `unlock_gift` FK Gift / `unlock_item_typeclass_path` str / `unlock_type` FK RelationshipType), `xp_cost`, `paths` M2M (in-band Paths), `out_of_path_multiplier` Decimal default 2.0. Per-kind partial unique constraints guarantee one unlock per anchor. CheckConstraints mirror the typed-FK rule; `target_kind=RELATIONSHIP_CAPSTONE` is forbidden (inherited from the parent RELATIONSHIP_TRACK unlock). SANCTUM threads do not use this model — no unlock row needed. Has a derived `display_name` property |
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
| `CombatPullResolvedEffect` | Frozen snapshot of one resolved effect at pull commit | `pull` FK, `kind`, `authored_value`, `level_multiplier`, `scaled_value`, `vital_target`, `source_thread` FK, `source_thread_level`, `source_tier`, `granted_capability` FK, `capability_grant_value` (frozen curved magnitude for CAPABILITY_GRANT, #2730/ADR-0173), `narrative_snippet`. CheckConstraints mirror ThreadPullEffect payload rules |

A CombatPull is considered *active* while `round_number == encounter.round_number`
(canonical liveness check). `expire_pulls_for_round` (combat services) deletes
stale rows on round advance and invalidates the per-character
`CharacterCombatPullHandler` cache.

### Non-Combat Ephemeral Pull CAPABILITY_GRANT (#2840) [BUILT & WIRED]

Non-combat (ephemeral) thread pulls that resolve a `CAPABILITY_GRANT` effect
confer capabilities for the duration of the scene, using the standard condition
capability path — the same `ConditionCapabilityEffect` → `get_capability_status`
→ `get_effective_capability_value` path that any condition can use.

**Mechanism:** when `spend_resonance_for_pull` runs in non-combat context and
the resolved effects contain at least one `CAPABILITY_GRANT`, it calls
`_apply_non_combat_capability_grants` (`world/magic/services/resonance.py`)
which:
1. Gets the "Thread Surge" `ConditionTemplate` (SCENE duration, non-stackable,
   dispellable — seeded by `ensure_thread_surge_content()`).
2. Ensures the template has a `ConditionCapabilityEffect(value=1,
   scales_with_severity=True)` row for each capability being granted (idempotent
   `get_or_create`).
3. Applies the condition with `severity = MAX frozen curved value` across the
   pull's CAPABILITY_GRANT effects. The oracle computes
   `int(1 * effective_severity)` = the frozen value.

This is fully generalized: the Thread Surge is just a condition that grants
capabilities through the standard path. Any condition with
`ConditionCapabilityEffect` rows can do the same — no custom oracle path, no
sidecar model.

**Known limitation:** all capabilities from one pull share the same severity
(the MAX across effects). This is exact for the common case (one capability per
pull) and a minor inaccuracy when a single pull grants multiple capabilities
with different curved values.

**Cleanup:** zero new code. `expire_scene_scoped_conditions` (called from
`finish_scene_full`) already sweeps SCENE-duration conditions.

**Dispel:** the Thread Surge condition has `can_be_dispelled=True`; a dispel
technique can end the surge early via the existing `remove_condition` path.

### Burning Resonance as a Strain Option (#4736, slice 7 of #4672) [BUILT & WIRED]

A character who pulls a thread may also **burn** resonance from that thread's resonance to
push the cast harder. The burn rides the pull: no pull, no burn (`ResonanceBurnNeedsPull`,
`ActionDispatchError.BURN_NEEDS_PULL`). Code: `world/magic/services/burn.py`, types in
`world/magic/types/burn.py`.

- **Ceiling.** `burn_ceiling(runtime_intensity, config)` = floor(runtime intensity x
  `StrainConfig.burn_per_intensity`, default 0.50). A request is capped by the ceiling and by
  the balance left once the pull's own cost is paid.
- **Strain check and reach.** If anything is left to burn, `resolve_resonance_burn` rolls
  `StrainConfig.strain_check_type` (target difficulty `StrainConfig.strain_check_difficulty`,
  default 0) with the `MagicActivity.PUSHING_HARD` skill terms. The outcome tier selects a
  `StrainBurnReach` row (`world/combat/models.py`, an `OutcomeTierAward`): `reach_percent` of the
  capped request is what she **reaches** and the only amount debited. `clean()` enforces that a
  better tier never reaches less than a worse one. A tier with no row reaches 0%; the Required
  content page lists the missing tiers. A zero cap rolls nothing (`check_result` is None).
- **Strain units.** Reached points become strain units at the burned resonance's
  `Affinity.burn_value` (default 1.00), added to the anima strain before the one diminishing
  curve (`strain_to_intensity`) in `use_technique`. Anima strain stays deterministic; only the
  burn is rolled.
- **Hasty fall.** A caster whose acting aura (`acting_aura`) is dominantly Abyssal who burns
  resonance of any other affinity falls hastily: the points are first converted at the Fall pair
  rate (`conversion_pair(source, abyssal).conversion_multiplier`) and valued at the Abyssal
  `burn_value`. With no Fall pair authored the burn is refused (`BURN_NO_FALL_RATE`, "No Fall
  rate is set up for burning that resonance."). Corruption for the fallen points accrues on the
  burned resonance at the Abyssal coefficient times `CorruptionConfig.hasty_fall_multiplier`
  (integer tenths, default 20 = 2.0x), even when the burned resonance's own affinity (Celestial)
  has coefficient 0. It does not move to a mapped Abyssal resonance. Every other pairing burns
  raw.
- **Corruption.** `_build_resonance_involvements` counts the active combat pulls and the
  non-combat cast pull plus burned points (`_PullSpend.add_burn` in
  `world/magic/services/techniques.py`, `hasty_fall_points`), which also closes a gap: a non-combat pull's resonance spend never
  reached corruption before. A pull on a resonance outside the gift's set still involves that
  resonance. Celestial's coefficient 0 means no corruption.
- **Engagement share.** After every cast whose strain bonus is above 0 (anima-only strain
  included), `_share_strain_with_engagement` adds
  `StrainConfig.engagement_share_percent` (default 50) of the bonus, floored, to
  `CharacterEngagement.intensity_modifier` under a row lock (`select_for_update`). Out of an
  engagement nothing is added. #4738 reuses it.
- **One burn per declared action.** A combat burn is resolved, valued and debited at
  declaration (`commit_combat_pull` -> `_resolve_combat_burn`), stored on `CombatPull`
  (`resonance_burned`, `burn_valued_points`, `burn_strain_units`, `burn_hasty_fall`, `burned_for`
  = `PullBurnAction` CAST or CLASH) and read back at resolution without re-valuing. Only the
  action it was declared with (`use_technique(combat_burn_for=)`) gets its strain units and burn
  corruption, so a focused cast plus a clash contribution in one round is strained once; the
  engagement share follows it once. The pull's own cost still counts toward corruption for every
  cast in the round, as before. A non-combat cast resolves the burn inside `use_technique`,
  after the Soulfray gate; a pending (consent-gated) scene cast stores it on
  `SceneActionPullDeclaration.burn`. Both strain checks read situational perks: the combat burn
  passes a `SituationContext` with the live `CombatRoundContext`; the non-combat burn
  (`_resolve_cast_burn`) passes the cast's own `situation_ctx` when one was threaded, else a
  `SituationContext` for the caster with no target and `resolution=None` (no round to read, so
  combat-positioning situations never hold there).
- **One pull per round, one job per pull.** A `CombatPull` is unique per (participant, round).
  The web client sends the pull and its burn on exactly one dispatch: the clash contribution
  when a clash is chosen, the focused cast otherwise (`YourTurn` `buildFocusedJob` /
  `buildClashJob`). Sending it on both made the second commit refuse with "You have already
  pulled a thread this round." `burned_for` is recorded whenever a burn was asked for, even one
  that reached nothing, and is blank when none was.
- **Idempotent resubmit.** A submit is several dispatches; when a later one fails, the player
  submits again. `_commit_focused_pull` first checks this round's committed pull
  (`_focused_pull_already_committed`): the same resonance, tier and threads, with
  `burned_for` CAST when a burn is asked (blank when not) and a stored reach no more than the
  request, is a no-op (no second charge, no second burn line); any other pull is refused with
  `PULL_ALREADY_COMMITTED`. The client also leaves the pull off a retried submit once the job
  carrying it succeeded (`pullCommitted` in `YourTurn`'s round state). The clash path has no
  such check; the client guard covers it.
- **Refusals.** No strain check type designated: `ResonanceBurnUnavailable` /
  `BURN_UNAVAILABLE` (a pending cast refused at accept time degrades to the pull-fizzle path).
  Bad web value (non-integer, bool, negative, above `MAX_RESONANCE_BURN` = 2**31-1):
  `BURN_INVALID` / `ResonanceBurnInvalid`, "A burn must be a whole number of resonance, 0 or
  more." Balance below cost plus burn: `spend_resonance_for_pull(burn=)` refuses under the same
  lock and debits nothing. A web focused pull with a Soulfray warning and no
  `confirm_soulfray_risk` is refused (`PULL_NEEDS_SOULFRAY_CONSENT`) before anything is charged;
  telnet instead holds the declaration for `accept soulfray`.
- **Telling her.** `announce_burn` sends, on commit, "You burn {reached} of {requested}
  {Resonance} resonance." (a hasty fall adds "; it falls at the pair rate to {valued}."). A burn
  that reached nothing says why: "You burn none of the {requested} {Resonance} resonance you
  asked for: " then "your burn ceiling is 0 at this intensity", "you have no {Resonance}
  resonance left once the pull is paid", or "your strain check reached none of it".
- **Surfaces.** Telnet `cast` and `clash` take `burn=<n>`, valid only beside `pull=`. Web combat
  dispatch takes `pull_burn` beside `pull_resonance_id` / `pull_tier` / `pull_thread_ids`
  (`_parse_pull_burn` in `world/combat/pull_helpers.py`). Web scene cast
  `POST /api/action-requests/cast/` takes `pull.burn` (`CastPullWithBurnRequestSerializer`); the
  social action endpoint takes none. The pull preview (`POST /api/magic/thread-pull-preview/`)
  takes an optional `technique_id` (only a technique she knows, `CharacterTechnique`; another
  is a 404) and returns `burn` = `{ceiling, strain_units_per_point, hasty_fall, available,
  resonance_name, off_affinity, corruption_affinity_name, ceiling_tier_name}` (null without a
  technique); `ceiling` is already capped by the balance left after the pull's cost, and
  `available` is False when no strain check is designated or the hasty fall has no Fall pair.
  `off_affinity` is True when the resonance is not of the caster's acting-aura affinity;
  `corruption_affinity_name` is the affinity whose corruption the burn leaves (the Abyssal on a
  hasty fall, the resonance's own when its coefficient is above 0, else null);
  `ceiling_tier_name` is the `IntensityTier` her runtime intensity has reached.
- **Web Strain area.** The burn is entered in the Strain area, not the pull dialog: in combat,
  `ActionDeclarationCard`'s Strain block under the anima strain slider (`strainBurn` prop, fed
  by `YourTurn` from `usePullBurnPreview`); on the scene cast, which has no anima strain
  control, a Strain block of its own under the pull picker (`ActionPanel`,
  `useCastPullSelection`). `PullBurnInput` labels the row "{Resonance} (yours)" or
  "(off-affinity)", shows "Burn ceiling at {tier name}: N resonance" (falling back to the pull
  tier), and once something is burned: "Strain check on submit. Degrees decide how much of the
  N you reach.", the combat power of anima strain plus burn on the client mirror of the strain
  curve ("up to +N power", `strainPowerBonus` with `burnStrainUnits` from `magic/burn.ts`), and
  the warnings "Burning {Resonance} raw. It leaves {Affinity} corruption you will need
  cleansed." or "Hasty fall. No rite, so it leaves extra {Affinity} corruption." The burn resets
  when the pull or the technique changes. The demo's "intensity after" and "anima cost"
  projection rows are not built (they need a server projection of the spiral).
- **Authored numbers.** `StrainConfig.burn_per_intensity`, `engagement_share_percent`,
  `strain_check_type`, `strain_check_difficulty`; `StrainBurnReach` rows; `Affinity.burn_value`;
  `CorruptionConfig.hasty_fall_multiplier`; and for digging deep (#4738)
  `dig_deep_fatigue_category`, `dig_deep_fatigue_cost`, `free_dig_deeps_per_encouragement`.
  Migrations 0314 (fields, `CombatPull` burn columns) and 0315 (`SceneActionPullDeclaration.burn`).
- **Web combat fix.** `CombatRoundContext._record_combat_declaration` used to drop the web
  declaration card's `pull_*` kwargs, so a pull declared from the web focused cast was never
  committed (only the telnet registry path and clash committed pulls). It now commits the
  focused slot's pull, with its burn, through `_commit_focused_pull`.

Journeys: `src/integration_tests/test_resonance_strain_journeys.py`.

### Fury: surrendering control for intensity (#4738 part B, #4727 decision 5) [BUILT & WIRED]

Fury is a chosen trade, not a per-cast bonus. A character declares a `FuryTier` and an anchor
(a character she has a tie toward) with a technique cast; the tier is a preset amount of control
she surrenders for the rest of her engagement, and her control roll's outcome picks how much
intensity that buys. Code: `world/magic/services/fury.py`, models in `world/magic/models/fury.py`.

- **Models.** `FuryTier`: `name`, `depth`, `control_surrendered`, `base_check_difficulty`,
  `berserk_severity`. `FuryConfig` (singleton): `check_trait`, `provocation_cap_per_tier`,
  `bonus_scale_per_cap_point`, `cap_ease_per_point`, `default_berserk_duration_rounds`,
  `berserk_condition`. `FuryDegreeShare` (an `OutcomeTierAward`): `intensity_percent` per
  outcome tier; `clean()` enforces that a better outcome never buys a smaller percent.
  `StrainConfig.intensity_per_control_surrendered` (Decimal, default 0) is the rate.
  `CharacterEngagement.fury_control_surrendered` tallies what was surrendered, for display.
  Migration 0327 (`control_penalty` renamed to `control_surrendered`; `intensity_bonus` and
  `lucid_grade_floor` removed, empty in production).
- **Cap.** The anchor caps the depth: `provocation_cap` = her own side's relationship tier
  toward the anchor // `provocation_cap_per_tier`; `clamp_tier` drops a deeper declaration to
  the deepest tier within the cap. Each cap point also eases the control roll by
  `cap_ease_per_point` and scales the trade up by `bonus_scale_per_cap_point` percent.
- **The trade.** `fury_intensity_for(tier, cap, outcome)` = floor(`control_surrendered` x
  `intensity_per_control_surrendered` x (100 + `bonus_scale_per_cap_point` x cap) / 100 x
  `intensity_percent` / 100), Decimal math floored once. An outcome with no `FuryDegreeShare`
  row buys nothing; the control is still surrendered.
- **Where it lands.** Each path builds a `FuryCast` (`fury_cast_for`) and hands it to
  `use_technique(fury=...)`, which drives it. Once the Soulfray gate has passed,
  `FuryCast.surrender()` rolls the control check (`FuryConfig.check_trait` plus the
  `FURY_CONTROL` magic-skill terms, difficulty `base_check_difficulty` minus the ease) and writes
  her `CharacterEngagement` (any engagement type) under a row lock:
  `intensity_modifier += intensity_gained`, `control_modifier -= control_surrendered`,
  `fury_control_surrendered += control_surrendered`. `use_technique` then re-reads her runtime
  stats, so the cast Fury was declared with channels the trade, and every later cast in the
  engagement does too. A `TECHNIQUE_PRE_CAST` cancel calls `withdraw()`, which takes the trade
  back off (the roll stands). A cast that proceeds calls `settle()`: the caster alone is told
  "You surrender N control: intensity +M." on commit, and Berserk is applied for a Berserk tier.
  A cast stopped at the Soulfray gate surrenders nothing and tells her nothing. With no
  engagement, or when the anchor's tie clamps the tier to nothing, nothing is rolled and nothing
  changes. Fury may be declared again each round, and each declaration surrenders and buys again.
  `get_runtime_technique_stats` floors runtime control at 0, so repeated surrenders cannot push
  the anima cost up without limit (the stored `control_modifier` is not floored).
- **Berserk is chosen.** A tier with `berserk_severity` above 0 is a Berserk tier: choosing it
  applies Berserk (`FuryConfig.berserk_condition`) at that severity whatever the roll. No roll
  ever causes Berserk. Declaring Fury while already Berserk is allowed.
- **Callers.** Combat (`resolve_combat_technique`), scene cast (`cast_services._resolve_cast`)
  and technique-enhanced scene actions (`action_services`) each pass `fury=` to
  `use_technique` and read `FuryCast.realized_tier` back for the audit. None passes a Fury power
  term; `use_technique`'s `control_penalty` parameter is gone.
- **Validation.** `_cap_fury_by_provocation` (scene action and cast serializers) refuses Fury
  without a technique, without an anchor, above the cap, and with no engagement ("Fury needs
  something at stake: you are not engaged."). A combat cast declaration (web or telnet) refuses a
  tier deeper than the anchor's cap with the same message (`fury_over_cap_message`, from
  `CastTechniqueAction._combat_fury_cap_refusal` in `round_declaration`); nothing is recorded or
  charged. Resolution still clamps, for a tie that lapsed after declaring.
- **Required content.** `fury-degree-shares` lists every `CheckOutcome` (matched by FK) with no
  `FuryDegreeShare`; `fury-intensity-per-control` is absent while the rate is 0.
- **Surfaces.** The cast picker (`FuryTierOption`) carries `control_surrendered`, `is_berserk`
  and `full_intensity` (`full_trade_intensities`: the trade at the highest authored
  `FuryDegreeShare.intensity_percent`, 0 when none exists, with no anchor scaling); each
  `AnchorOption` carries `tier_full_intensities`, the same figure under that anchor's cap. The web `FuryDeclaration` ("Surrender control") lists tiers as "Seething:
  surrender 6 control" (`(Berserk)` on a Berserk tier) and previews "6 control -> up to +10
  intensity, by your roll" from those server figures. The participant payload carries
  `fury_control_surrendered` beside `intensity_modifier` / `control_modifier`; the
  `Pressure` rail section (`frontend/src/combat/sections/Pressure.tsx`) shows them, with a
  "Fury: surrendered N control" chip once N > 0, read from her engagement whatever its type.
  `FuryCast.settle` tells the caster alone, on commit, "You surrender N control: intensity +M." (`fury_trade_message`), so all three
  resolution paths say it. Telnet: bare `combat` lists the tiers (`fury_tier_label`), the
  declared tier and a `Pressure:` line.
- **Berserk penalises, it does not refuse (#4738 part B).** A Berserk character may declare
  flee and parley; both roll through `collect_check_modifiers`, so any
  `ConditionCheckModifier` staff author on the Berserk template (template or stage level)
  against `FleeConfig.check_type` or `SocialManeuverConfig.parley_check_type` lands on the
  roll. Only `leave_encounter` is refused (`reject_leave_if_berserk`: "The rage will not
  walk away. You can still try to flee."). Required content `berserk-disengage-penalty`
  lists a Berserk with no penalty against either check: a negative modifier authored on the
  check type or on its category, at template or stage level. Journeys:
  `src/integration_tests/test_berserk_disengage_journeys.py`.

Journeys: `src/integration_tests/test_surrendering_control_to_fury_journeys.py`.

### Target-Aware Pulls — Court Regard Modulation (#1831 — ADR-0086) [BUILT & WIRED]

Thread pulls are **target-aware**: the live target the pull's action is directed at
flows into `resolve_pull_effects(threads, tier, *, in_combat, target=...)`
(`world/magic/services/resonance.py`) as an `ObjectDB | None`. `None` for
ephemeral/untargeted pulls (existing behavior, byte-identical). The target is
threaded through `world.magic.types.pull.PullActionContext.target` — populated by
`commit_combat_pull` (`world/combat/pull_helpers.py`, combat cast/clash, reading
`CombatParticipant`'s focused target) and by `use_technique`'s `pull_target` kwarg
(`world/magic/services/techniques.py`, non-combat cast; defaults to the cast's
first resolved target when not supplied explicitly).

**Modulation seam** — `apply_target_modulation(thread, target, effect_row,
base_scaled)` (`world/magic/services/pull_modulation.py`) is the single dispatch
point on `thread.target_kind` for numeric-payload pull effects, called from inside
`resolve_pull_effects` for every row with a numeric payload. It is a no-op (returns
`base_scaled` unchanged) when there is no numeric payload, no target, or the
thread's `target_kind` has no registered rule — so every existing (untargeted or
unrelated-kind) pull stays byte-identical. Two rules are registered today: Court
(COVENANT_ROLE, below) and Relationship Bond (RELATIONSHIP_TRACK, below).

**Court rule (COVENANT_ROLE)** — `court_regard_modulation(thread, target,
effect_row, base_scaled)` (`world/magic/services/pull_modulation_court.py`) fires
for `TargetKind.COVENANT_ROLE` threads. It resolves the Court leader's primary
persona for the servant's engaged Court membership anchored on the thread's
`target_covenant_role`, reads the leader's signed `NpcRegard` for the target
persona (`world.npc_services.regard.get_regard`, #1717), and empowers the pull
only when `ThreadPullEffect.regard_polarity` matches the sign of that regard:
`OFFENSIVE` ⇒ empowered by negative regard (a disfavored target), `PROTECTIVE` ⇒
empowered by positive regard (a favored target), `NEUTRAL` ⇒ empowered by either
nonzero sign. When empowered: `base_scaled + round(base_scaled × (abs(regard) /
REGARD_MAX) × COURT_REGARD_PULL_K)` — `COURT_REGARD_PULL_K` (`world/magic/constants.py`,
currently `1.0`) is a flagged tuning placeholder for playtest. No-op (returns
`base_scaled` unchanged) when no Court leader is resolvable, the target has no
`CharacterSheet`, regard is 0, or the polarity doesn't match.

**Picker signal** — `compute_thread_applicability` (`world/magic/services/pull_applicability.py`,
the `POST /api/magic/applicable-pulls/` combat-UI picker; this module's own
`PullActionContext` is a distinct, caller-supplied dataclass from
`world.magic.types.pull.PullActionContext` above — same name, different shape and
purpose) reports `InapplicabilityReason.COURT_LEADER_NO_STAKE` for a COVENANT_ROLE
thread when a `target_persona_id` is supplied in context and no candidate
`ThreadPullEffect` on the thread would ever be empowered against that persona
(leader indifferent, or every candidate effect's `regard_polarity` mismatches the
regard's sign) — so the player isn't offered a pull that won't actually do
anything extra. No-op (thread stays applicable) when no Court leader is
resolvable at all — the base pull is simply unmodulated in that case.

### Relationship Bond Pull Modulation (#1849 — ADR-0092) [BUILT & WIRED]

The `RELATIONSHIP_TRACK` sibling rule, `relationship_bond_modulation(thread,
target, effect_row, base_scaled)` (`world/magic/services/pull_modulation_relationship.py`).
Fires when the live target IS the thread's threaded person
(`thread.target_relationship.target` — the side row the thread anchors to since
#3957), or holds an active side toward them whose `conflict` exceeds its
`affection` (hostile — "threatening"). Each side is independent: no reciprocity
is required. The
shared `_relationship_pull_would_trigger(x_sheet, y_sheet)` helper decides this
for both the resolution path and the picker, mirroring
`_regard_polarity_matches`'s role for Court modulation.

Unlike Court modulation, there is **no polarity gate** — `ThreadPullEffect.regard_polarity`
is not consulted at all. This is a deliberate divergence (ADR-0092): Court modulates
an NPC master's preference (narrative consistency demands sign-matching), while
this rule rewards any PC-to-PC relationship investment unconditionally (rival or
lover alike).

Magnitude: `bonus = round(cap × S / (S + half_saturation))` where `S = coefficient
× CharacterRelationship(source=owner, target=threaded_person).pair_depth()`
(#3957 — the tie's depth pooled across both sides)
— a saturating curve (reusing `_soft_cap` from `world/magic/services/threads.py`,
the same formula shape `ThreadSurvivabilityTuning` uses) rather than Court's fixed
ratio, since `CharacterRelationship` values grow unbounded (unlike `NpcRegard`'s
`0..REGARD_MAX`). Tuning lives in the `RelationshipBondPullTuning` singleton
(pk=1, staff-tunable in admin).

The picker surfaces `InapplicabilityReason.RELATIONSHIP_NO_STAKE` via
`_relationship_pull_would_have_effect`, gated by the same `can_perceive` privacy
check `_court_pull_would_have_effect` uses (a hostile third party's relationship
to the threaded person must not leak to the owner via an observable tell when the
owner can't perceive that third party).

**Fraught + devotion differential terms (#2034, ADR-0110) [BUILT & WIRED]** — Two
additive, valence-aware terms sit on top of the sign-blind base bonus above:

- **Fraught** — `fraught_bonus = round(fraught_cap × S / (S + fraught_half_saturation))`
  where `S = fraught_coefficient × min(bond.affection, bond.conflict)` (#3957 — the
  two unsigned gauges on the side row, both moved only by play). Rewards a bond that
  play has moved in BOTH directions at once (a love/hate dynamic); a bond lopsided
  entirely in one direction earns nothing here, no matter how large.
- **Devotion** — `devotion_bonus = round(devotion_cap × S / (S + devotion_half_saturation))`
  where `S = devotion_coefficient × max(0, pair_depth() - devotion_threshold)`.
  Rewards a bond so overwhelmingly deep it clears a threshold well past the base curve's
  own half-saturation point; depth alone gates it, deliberately — no ritual/ceremony
  requirement (Tehom, 2026-07-06).

Both terms reuse `_soft_cap` and are computed unconditionally alongside the base bonus in
`relationship_bond_modulation` (`base_scaled + bonus + fraught_bonus + devotion_bonus`);
their tuning columns (`fraught_coefficient`/`fraught_cap`/`fraught_half_saturation`,
`devotion_threshold`/`devotion_coefficient`/`devotion_cap`/`devotion_half_saturation`) live
on the same `RelationshipBondPullTuning` singleton as the base curve's `coefficient`/`cap`/
`half_saturation`. Defaults are conservative: both new caps are 10 (half the base `cap` of
20); `devotion_threshold` is 60 (2× the base `half_saturation` of 30 — the point where the
generic curve is already ≥⅔ saturated). Because both terms live inside the one modulation
function, they surface in `preview_resonance_pull` automatically alongside the base bonus —
no separate wiring — since preview and commit share the one `apply_target_modulation` seam
(#2035). See ADR-0110 for the rejected alternatives (hybrid-combo-type-driven
bonuses, sign-flip transition detection) and the cross-link to #1991 (the expression half —
a ceremony beat at RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE thread crossings; this feature
is the power half only).

### Mage Scars (renamed from Magical Scars — §7.2)

Cosmetic rename only. Class names, table names, and migration code paths
unchanged. Verbose_names, CLI strings, API-visible labels, and documentation
now say "Mage Scars."

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `MagicalAlterationTemplate` | OneToOne on ConditionTemplate; magic-specific alteration metadata. `NaturalKeyMixin`, `CONTENT_MODELS` (`magic.magicalalterationtemplate`, #3034) — NK `["condition_template"]` (already DB-unique). Only staff/system rows (`authored_by` NULL) export; a player's "author from scratch" row is filtered via `EXPORT_FILTERS` | `tier`, `origin_affinity`, `origin_resonance`, `is_library`, `visibility_required` |
| `PendingAlteration` | Queued unresolved Mage Scar | `character` FK, `status` (OPEN/RESOLVED/STAFF_CLEARED), `scene` FK, triggering-state snapshot fields, `is_cosmetic` (#4501) |
| `MagicalAlterationEvent` | Immutable provenance audit log | `pending`, `event_type`, `data`, `created_at` |

**Cosmetic Mage Scars (#4501, spec #4343).** `PendingAlteration.is_cosmetic` marks a reward scar:
no drawbacks and no wait on advancement. A trial's Success or Critical Success route queues one
through `MAGICAL_SCARS` with `ConsequenceEffect.scar_is_cosmetic`; the handler passes it to
`create_pending_alteration(..., is_cosmetic=)`. Rules, all in `world/magic/services/alterations.py`:
`has_pending_alterations` (so `enforce_advancement_gate`, the XP dashboard and every spend site)
ignores cosmetic rows; `validate_alteration_resolution(..., is_cosmetic=)` requires every
magnitude and the weakness damage type to be 0 on the scratch path and accepts only a
drawback-free library entry (three magnitudes 0 and no `ConditionOrStageEffect` row on its
condition) on the library path; the same-scene merge in `create_pending_alteration` pairs only
scars of the same `is_cosmetic`, so a reward never raises a cost's tier. The serializer returns
zeroed drawback caps for a cosmetic row, which hides the form's magnitude pickers; the site
banner and the XP page's gate alert skip it. It is never a trial's cost. Not tier 1 "Cosmetic
Touch", which still gates advancement.

**Trial training (#4501).** `AcquisitionOrigin.TRIAL` / `AccessChangeSource.TRIAL` ("enduring a
trial") mark techniques and meters a trial produced. The `TECHNIQUE_TRAINING` consequence effect
(`world/mechanics/effect_handlers.py`, `_technique_training`) never skips a gate: "grant outright"
(Critical Success only) is `learn_technique(sheet, technique, source=TRIAL, ap_cost=0,
origin=TRIAL)`, which still runs `enforce_technique_prerequisites` (only `GM_GRANT` skips it);
points create a meter with `learn_technique(..., ap_cost=training_meter_size)` when the character
has none, then `credit_technique_progress(meter, points)`. A refusal (`GiftNotOwned`,
`TechniqueRequirementsNotMet`, `TechniqueCapExceeded`) mints nothing, credits nothing and tells
the player why; the codex entry, the cost and any cosmetic scar still apply. Below Success the
unmet requirements are not named (they could name the entry the trial did not grant).

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
| `TechniqueVariant` | Concrete subclass — a resonance-specialized form of a parent `Technique`. `NaturalKeyMixin`, `CONTENT_MODELS` (`magic.techniquevariant`, #3034) — NK `(parent_technique, resonance, unlock_thread_level)`, the same triple the `UniqueConstraint` already enforces | `parent_technique` (self-FK, `related_name="variants"`), `resonance` FK, `unlock_thread_level` (≥3 = variant), `name_override`, `intensity_delta`, `control_delta`, `discovery_achievement` FK, `codex_entry` FK. Unique per `(parent_technique, resonance, unlock_thread_level)` |
| `CovenantRole` | Refactored to inherit `AbstractSpecializedVariant` (schema no-op) | existing sub-role fields; `parent_role` (`related_name="sub_roles"`) is the variant parent |

**Resolver — `resolve_specialized_variant(*, entity, character)`** (`world/magic/specialization/services.py`):
the single specialization resolver. For a `Technique` it finds the character's active GIFT
thread on the technique's gift, reads resonance + level, and returns a `_ResolvedTechnique`
value object wrapping the parent + matching variant (exposing `name`/`intensity`/`control`
with variant deltas applied), or the raw parent `Technique` when no variant matches. For a
`CovenantRole` it reads the cached `character.threads` handler (preserving the proven
`resolve_effective_role` cache coherence). `resolve_effective_role` is now a one-line shim
over this resolver — no parallel specialization systems (ADR-0016).

### Per-caster technique forms (#2901)

The specialization engine above answers *which* variant applies to a cast. It does
not answer the question the two per-character display surfaces need: **which forms
of this technique can this caster work at all.** A variant does not replace a
technique — it makes an alternate version available, and `cast <tech> base` /
`cast <tech> variant=<resonance>` both stay reachable — so a display that collapsed
to one resolved form would misreport what the character can do. Until #2901 nothing
anywhere enumerated a caster's forms: `Technique.cached_variants` had no display
caller, and a player could pass `base` or `variant=` without any surface having told
them those forms existed.

`available_technique_forms(character, technique, *, character_technique=None,
sheet=None) -> list[TechniqueFormPayload]` (`world/magic/services/technique_forms.py`)
returns, in order:

1. **The base form** — always present, `variant_id=None`.
2. **Each unlocked specialized form** — at most one per GIFT-thread resonance,
   because `matching_variant` picks the *highest* qualifying `unlock_thread_level`
   per resonance and shadows the rest. A multi-resonance caster (#1619) gets one
   entry per thread; a role-granted technique (#2022) resolves through its
   COVENANT_ROLE thread instead.
3. **The next locked form per resonance** — the lowest `unlock_thread_level`
   strictly above the thread's current level, carried with `is_locked=True` so the
   deepening reads as a goal. One step ahead, not the whole ladder.

`technique_signature_payload(character, technique) -> TechniqueSignaturePayload | None`
returns the signature flourish *beside* the list. A signature is an additive
modifier on whichever form is chosen, never a sibling form (ADR-0072).

**Three invariants hold this together.**

*One resolver, never a second selection rule.* Each entry is produced by calling
`resolve_specialized_variant` once per candidate resonance. Re-deriving
`matching_variant`'s predicate in a display service would drift from the cast the
first time either side changed (ADR-0055/ADR-0016).

*The `is_default` marker comes from the resolver too.* A bare `cast <tech>` resolves
with `preferred_resonance=None`, a path that folds in the active alt-self resonance
override (`_active_alt_self_resonance`). A display assuming "default = the thread's
own resonance" would mislabel a shifted character.

*No per-caster cache exists or is needed.* A resolved form is fully determined by
`(parent_technique, variant)` — no caster input reaches it — so each form's effect
summary caches on `TechniqueVariant.cached_effect_summary` exactly as the base one
caches on the `Technique` row. Invalidate with `invalidate_variant_payload_caches`
(shorter than the technique's list: a variant has no `removed_conditions` relation).
The only per-caster work is deciding which forms are reachable, and that reads two
already-cached lists (`character.threads`, `technique.cached_variants`).

**The `cached_*` alias fix.** Every payload *reader* —
`summarize_technique_effects`, `is_technique_hostile`, `derive_target_relationship` —
reads the `cached_<payload>` names, but `_ResolvedTechnique` originally exposed only
the bare `damage_profiles` / `capability_grants` / `condition_applications`. Its
`__getattr__` forwarded the `cached_` reads straight to the parent `Technique`, so a
variant that swapped its damage rows summarised as the **base** form under the
variant's name and nothing failed. `_ResolvedTechnique` now declares all four
`cached_*` names; `cached_removed_conditions` is declared explicitly to make the
asymmetry visible — there is no `TechniqueVariantRemovedCondition` model, so a
variant can never override which conditions a technique strips.

**Surfaces.** The sheet describes, the scene does:

| Surface | Carries |
|---|---|
| `sheet/magic` (telnet) + web Magic tab (`SpellbookTab`) | The full catalogue: every unlocked form with its own effect summary and intensity/control, the next locked form, and the signature line. Silent when only the base form is reachable. |
| bare `cast` (telnet) + web castable list (`ActionPanel`) | A compact `Forms: base \| Cinder (Ashfall Lash) (default)` affordance plus the structured `forms` payload driving the web picker. Locked forms omitted. |

**The web could not choose a form at all before this.** `CastRequestSerializer`
carried `use_base_form` (#1581) but no `preferred_resonance_id`, so telnet's
`variant=<resonance>` (#1619) had no web counterpart; the Action kwarg
(`actions/definitions/cast.py`) already existed, only the wire field was missing.
#2901 adds it and forwards it from `SceneActionRequestViewSet.cast`.

**Query cost.** Both read paths prefetch `technique__variants`
(`select_related("resonance")`) and make one read of the cached threads handler.
Both are fixed regardless of how many techniques or variants are involved: the
character sheet went 37 → 39 queries, the telnet cast listing 5 → 7.

**Cast-time variant wiring [BUILT & WIRED, #1581]:** `resolve_specialized_variant` is called
at two cast seams so unlocked variants shape every cast automatically: (1)
`get_runtime_technique_stats` (`world/magic/services/techniques.py`) — combat runtime stats;
variant `intensity`/`control` deltas reach the power ledger. (2) `_resolve_and_pose_cast`
(`world/scenes/cast_services.py`) — the non-combat standalone-cast path; variant form drives
cost, narration, and outcome. Both seams are gated on `unlock_thread_level`: below the
threshold the parent technique is returned unchanged. `MagicContent.create_all()`
(`world/seeds/game_content/magic.py`) builds starter `TechniqueVariant` rows so a suite
has variants to exercise, but it is a test-fixture builder only — it left the production
`seed_magic_dev()` path in #2973, so a fresh dev environment has none until the lore repo
authors them. `TechniqueVariant` joined `CONTENT_MODELS` in #3034 (NK `(parent_technique,
resonance, unlock_thread_level)`), so that authoring path now exists — it did not before.
The
gift-thread confers the standard always-in-action thread bonus (passive `ThreadPullEffect`
tier-0 rows; `_ALWAYS_IN_ACTION_KINDS` — already wired in #1580); cast-time variant
resolution is the new addition in #1581.

**`apply_variant` flag on `get_runtime_technique_stats` (#1581 Task 7):** the function
signature is `get_runtime_technique_stats(technique, character, *, apply_variant: bool = True)`.
Pass `apply_variant=False` to obtain the raw base-form `RuntimeTechniqueStats` (no variant
delta applied), used internally by `use_technique` for the strict-bonus cost clamp (see below).
All external callers use the default (`apply_variant=True`).

**Strict-bonus cost clamp in `use_technique` (#1581 Task 7):** a gift-technique variant is
always a benefit at cast time, never a penalty. After computing `variant_cost` (with
`apply_variant=True`), `use_technique` computes `base_form_cost` (with `apply_variant=False`)
and applies `cost = min(variant_cost, base_form_cost)`. This enforces "never punish
achievement": a character pays no more anima for the variant than they would for the plain
base form, regardless of the variant's `intensity_delta`.

**Base-form opt-out (#1581 Task 8):** the variant is the **default** at cast time, but a
player may cast the base form explicitly when the resonance-tied character of the variant is
situationally unwanted. Surfaces:

- `request_technique_cast(..., use_base_form: bool = False)` — the primary seam in
  `world/scenes/cast_services.py`; passes `apply_variant=False` to both
  `_resolve_and_pose_cast` and `use_technique` when `True`.
- Telnet: `cast <technique> base` — the `base` standalone trailing keyword in
  `CmdDeclareTechnique` (`src/commands/combat.py`); sets `use_base_form=True` in
  the dispatch kwargs forwarded to `CastTechniqueAction`.
- Web cast payload: `use_base_form` boolean field on the cast request body.
- Combat opt-out and a React toggle UI are deferred follow-ups.

**Crossing ceremony — `execute_crossing_ceremonies(*, thread, starting_level, new_level)`**
(`world/magic/crossing/ceremony.py`, ADR-0094): dispatches on `thread.target_kind` via a
handler registry so **every** `TargetKind` gets a ceremony at PathStage crossing levels (3, 6,
11, 16, 21), not just GIFT and COVENANT_ROLE. GIFT/COVENANT_ROLE handlers wrap the existing
variant-discovery logic (`AbstractSpecializedVariant.newly_crossed_variants` → achievement +
codex + narrative). The other seven kinds (TECHNIQUE, TRAIT, FACET,
RELATIONSHIP_TRACK/CAPSTONE, MANTLE, SANCTUM) have stub handlers that log a debug no-op,
replaced with real logic in #1988–#1993. A shared `execute_ceremony_beat` helper lets non-variant
kinds fire the same achievement + codex + narrative beat without an `AbstractSpecializedVariant`.
Called from `spend_resonance_for_imbuing` on every thread advance; also standalone-callable for
ceremony-direct testing. (`world/covenants/discovery.py` re-exports it as
`fire_variant_discoveries` for backwards compatibility.)

**GIFT thread substrate (#1578):**
- `TargetKind.GIFT` + `Thread.target_gift` FK (PROTECT) — a thread anchored to a Gift.
  One active GIFT thread per `(owner, gift)` for now (multi-resonance chooser is a deferred
  needs-design follow-up).
- **Grant-time resonance resolution (#2971, ADR-0203)** — `grant_gift_to_character(sheet,
  gift, *, resonance=None)` (`world/magic/specialization/services.py`) is the shared
  gift-acquisition primitive every grant call site uses: CG's `_finalize_gift_and_techniques`
  (reading `selected_gift_resonance_id` from `draft.draft_data` — frontend picker built #1620,
  the `GiftStage` funnel writes the key, #2426 Task 10; `compute_magic_errors` requires it and,
  as of #2971, also rejects a stale pick pointing at a deleted `Resonance`), the path-crossing
  grant (`grant_path_magic`), species-gift provisioning (`provision_species_gifts`), and
  `charge_and_learn`'s implicit gift acquisition. It mints the `CharacterGift` link and
  **always** provisions the gift's latent level-0 GIFT thread — resonance is resolved by
  `_resolve_grant_resonance` *before* the `CharacterGift` row is minted, so a raise leaves no
  partial state (a `CharacterGift` with no thread — the exact corrupted state #2971 eliminates —
  can never be created). Resolution order: the caller's explicit pick (when the gift's
  supported set is empty or contains it) → an existing active GIFT thread already covering the
  gift (lineage-aware, via `gift_threads_for` — makes a re-grant a true no-op) → the supported
  set's claimed-or-first member → the character's own earliest GIFT thread's resonance → their
  highest-`lifetime_earned` claimed resonance → the anima-ritual resonance. Raises
  `GiftResonanceUnresolvable` when none of those resolves — an empty `Gift.resonances` (the
  "unrestricted" weave-gate meaning, ADR-0052/#2967) no longer means "skip provisioning the
  thread"; a fresh CG character with nothing else resolved is exactly the case CG guards
  against by also always supplying a `selected_gift_resonance_id`.
  `provision_latent_gift_thread(sheet, gift, *, resonance)` is the idempotent level-0 GIFT
  thread writer `grant_gift_to_character` calls once resonance is resolved (write-once on
  resonance) — no grant call site invokes it directly anymore.
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

**GIFT anchor cap (#1580, #4585):** `compute_anchor_cap` handles `TargetKind.GIFT` by
returning `compute_level_cap(thread.owner)` (character level × 10,
`world/magic/services/threads.py`): a gift has no cap value of its own. GIFT threads are always in-action (intrinsic species
gift — added to `_ALWAYS_IN_ACTION_KINDS`). The frontend CG resonance picker is built (#1620).

Proven end-to-end by `world/magic/tests/integration/test_gift_specialization_e2e.py` (#1578):
CG provisioning → base resolve at level 0 → `gift_resonances_for` reads the thread's
resonance → advance past `unlock_thread_level=3` → variant resolve (name/intensity/control
deltas) → discovery beat fires (achievement + codex).

**The anima ritual records the same CG pick too (#2971).** `_finalize_anima_ritual`
(`world.character_creation.services`) resolves `selected_gift_resonance_id` the same way
`_finalize_gift_and_techniques` does and passes it to `provision_player_anima_ritual(...,
resonance=...)`, which writes it onto the created `RitualCheckConfig.resonance` — the anima
ritual IS the character's magical identity, so CG now populates it there instead of leaving it
`None` until a post-CG edit. `world.magic.services.gain.anima_ritual_resonance(sheet)` — one of
`_resolve_grant_resonance`'s own fallback rungs above — resolves for every freshly finalized
character as a result, instead of always returning `None` at CG time.

### Path-crossing grant — (Gift × Path) → base technique set (grants.py, services/path_magic.py — #1579)

The complement to the resonance engine above: #1578 specializes *how* a known technique
manifests; #1579 grants *which* techniques you get when you advance into a new Path. This is
ADR-0055's "(Gift × Path) sets the base technique set" leg, realized as an **acquisition** on
advancement (not a derive-on-read), honoring ADR-0053 (advancement *gates*; the grant is a
consequence of Path membership per ADR-0050, not an XP purchase).

| Surface | Role | Notes |
|---|---|---|
| `PathGiftGrant` (`models/grants.py`) | Authored `(path, gift)` → curated `starter_techniques` M2M | Mirrors the `PathRitualGrant` through-model shape. Same authored Gift, different set per path (warrior vs spy from one Pyromancy). A path may grant the character's *existing* gift (new techniques of it) AND a new gift. `clean()` rejects a technique not of the grant's gift; unique per `(path, gift)`. **Authorable since #3712**: a standalone `PathGiftGrantAdmin` (`filter_horizontal` on `starter_techniques`, which is where a pool is composed) plus a `PathAdmin` inline as the way in from the path. Until then only the tradition half of the CG menu had a page, so the 76 authored path pools were fixture-loaded and uneditable. |
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
(via the shared `grant_gift_to_character` primitive) and applies any drawback idempotently.
`resonance=None` (the common case — species gifts have no CG-picker field of their own) lets
`_resolve_grant_resonance` (#2971, ADR-0203) anchor the Minor Gift's thread to the character's
Major-gift thread resonance, since that thread already exists by the time species gifts
provision — never "no thread provisioned" the way an empty `Gift.resonances` set used to mean.
The gift's GIFT thread carries a tier-0 `ThreadPullEffect` with `effect_kind=RESISTANCE` that nets
against the drawback vulnerability at the combat-damage seam. `gift_thread_resistance(character,
damage_type) -> int` (services/threads.py) returns the aggregate resistance (passive +
active paid-pull snapshots). See ADR-0050, ADR-0071. E2E:
`world/magic/tests/integration/test_species_gift_e2e.py`.

### Player-facing gift/technique/thread-weaving acquisition surface (#1587, #2116) [BUILT & WIRED]

`spend_xp_on_gift_unlock` + `accept_technique_offer` (`services/gift_acquisition.py`) were
complete and tested but had zero non-test callers until #2116 wired a player-facing surface —
one telnet namespace + matching web endpoints, both thin `Action`s over the existing services
(mirrors the `sanctum.py` shape).

| Surface | Role | Notes |
|---|---|---|
| `PurchaseGiftUnlockAction` (`actions/definitions/gift_acquisition.py`, key `purchase_gift_unlock`) | XP gate — buy a `CharacterGiftUnlock` receipt | Wraps `spend_xp_on_gift_unlock`. Does not acquire the gift; kwargs `gift_unlock_id`, optional `teacher_tenure_id`. |
| `AcceptTechniqueOfferAction` (key `accept_technique_offer`) | Acquisition step — accept a `TechniqueTeachingOffer` | Wraps `accept_technique_offer`. Implicitly acquires the gift on the first technique learned from it (requires the `CharacterGiftUnlock` receipt above). Kwarg `offer_id`. |
| `AcceptThreadWeavingOfferAction` (key `accept_thread_weaving_offer`) | Telnet parity for thread-weaving teaching offers | Wraps `accept_thread_weaving_unlock` (`services/threads.py`). The web `ThreadWeavingTeachingOfferViewSet.accept` (`AcceptTeachingOfferSerializer.create()`) now dispatches through this same Action — one seam, not three shapes. Kwarg `offer_id`. |
| `CmdLearn` (`commands/gift_learning.py`, key `learn`) | Telnet namespace | Bare `learn`/`learn status` — hub listing open `GiftUnlock` rows (XP cost + purchased/missing) and open teaching offers (pitch/cost/teacher) for both techniques and thread-weaving. `learn gift <id>` / `learn technique <id>` / `learn thread <id>` dispatch the three Actions above via `dispatch_player_action`. |
| Web endpoints | `POST /api/magic/gift-unlocks/purchase/`, `POST /api/magic/technique-offers/accept/` | New; both `APIView`s resolving the acting `CharacterSheet` via the alt-guard helper (`_resolve_actor_sheet`) then dispatching the matching Action. `POST /api/magic/teaching-offers/{id}/accept/` (thread-weaving) is pre-existing, now re-pointed through `AcceptThreadWeavingOfferAction`. |

Both `GiftUnlock`/`TechniqueTeachingOffer` rows are broadcast/open (no `learner` FK) — anyone can
purchase/accept; teaching offers are not consumed on acceptance (multiple learners may accept the
same offer). Proven end-to-end by
`world/magic/tests/integration/test_gift_acquisition_action_e2e.py` (purchase → accept →
`CharacterTechnique` minted; thread-weaving parity).

**`GiftUnlock` is authored content, not seed data (#2967).** `magic.giftunlock` is registered in
`CONTENT_MODELS` with natural key `["gift"]` (one row per gift, now a DB constraint), so the lore
repo authors which Minor Gifts are acquirable and at what price. This was the missing link: without
a row here nobody can *learn* a Minor Gift at all, since `charge_and_learn` raises
`GiftUnlockMissing` for a learner's first technique from a gift they don't own, and an authored
Minor Gift with no `GiftUnlock` is reachable only by a Species/Tradition/Path grant handing it over
outright. Leaving `paths` blank is the open-to-everyone shape — every path treats the unlock as
in-band at full `xp_cost`; populate it only to make the gift cheaper for some paths. Corollary of
the `CONTENT_MODELS` registration: **no seeder may create a `GiftUnlock` row.**

**Second front door — Academy TRAIN offers (#2440):** `accept_technique_offer`'s charge+acquire
core is extracted into `charge_and_learn(learner, technique, *, base_ap_cost, source,
gold_cost=0, gold_treasury=None, teacher_tenure=None, teacher_banked_ap=0)`
(`services/gift_acquisition.py`) — one seam, two front doors. `accept_technique_offer` delegates
to it (`teacher_tenure=offer.teacher`, no gold); `world.npc_services.effects.run_train_offer`
(the `OfferKind.TRAIN` effect handler) is the second caller — AP + coin (learner purse → the
Academy's `OrganizationTreasury`) + exactly one unredeemed Golden Hare
(`currency.FavorTokenDetails`, #2428) redeemed to the Academy as venue, no player `teacher_tenure`.
See `docs/systems/INDEX.md`'s "NPC Services" entry (and
`world/npc_services/AGENT_GLOSSARY.md`) for the full TRAIN-offer flow (obligation gate,
tradition-signature members-only availability, `NPCRole.teaches_tradition`).

**A short purse is refused by cause, before anything is charged (#4523):** when `gold_cost > 0`,
`charge_and_learn` first calls `enforce_can_afford_training(sheet, gold_cost)`, which locks the
learner's `CharacterPurse` row and raises `TrainingFundsInsufficient` (a `MagicError`;
`user_message` "This training costs 2g 5s and you have 9s.", built with `format_coppers`) when the
balance is short. `run_train_offer` returns that message through its existing `except MagicError`
branch with AP, coin, the Hare and `TechniqueProgress` untouched, so its `except ValidationError`
branch ("Someone else called in that Hare before you finished.") now means only a lost Hare race.
The purse lock is held until `transfer` takes the same row, so a concurrent debit cannot slip
between the check and the charge. `accept_technique_offer` passes no coin (`gold_cost=0`), so the
check returns at once for it. Journey: `integration_tests/test_academy_training_journeys.py`.

**Unbound magic-learning AP surcharge (#2442):** `charge_and_learn` applies one more scale
after the has-gift/major-gift multiplier: `ap_cost = ceil(ap_cost × (100 + surcharge%) / 100)`,
where `surcharge%` is the learner's live `magic_learning_ap_cost` modifier total
(`_magic_learning_ap_cost_surcharge_percent`, resolved via `world.mechanics.services
.get_modifier_total` — the post-CG `CharacterModifier` path, not the CG-draft
`CharacterDraft._get_distinction_bonus` helper used during character creation). TIME, not
power — resonance earning/spending is untouched; a self-taught mage develops just as strong,
only slower. The "Unbound" drawback `Distinction` (slug `unbound`, seeded by
`world.seeds.character_creation.ensure_unbound_drawback_distinction`) is the sole authored
source today: a +50 `DistinctionEffect` on the `magic_learning_ap_cost` `ModifierTarget`
(category `magic`, seeded by `wire_magic_learning_ap_cost_target`). Applies identically to
both `charge_and_learn` front doors (accept + TRAIN) — one read, no duplication. Every seeded
Unbound `BeginningTradition` row reads `state=TraditionState.SELF_TAUGHT`
(`seed_beginning_traditions`, #3675; was a `required_distinction=<Unbound drawback>` FK
pre-#3675); the SELF_TAUGHT `TraditionStateLine` carries the drawback (`carries` FK,
`world.character_creation.offers.self_taught_drawback()`), and `select_tradition`
(`world.character_creation.views`) applies it to the draft via the generic
`reconcile_offer_picks` call every tradition pick already runs, not a name-matched special
case (Orphaned Tradition/Metallic Order carry theirs the same way, via TEACHERS_GONE). Shed
automatically via `world.magic.services.tradition_membership.join_tradition` (checks
`_tradition_is_orphaned`, now a `BeginningTradition.state == TEACHERS_GONE` read) and
re-applied by `leave_tradition` (`self_taught_drawback()`, #2441 Task 8/9, #3675); the
underlying `CharacterModifier` row cascade-deletes with the `CharacterDistinction` row
(`ModifierSource.character_distinction` is `on_delete=CASCADE`), so the surcharge disappears
the moment the drawback is shed, no separate cleanup needed.

### Technique Prerequisites, the learning gate (#4097) [BUILT & WIRED]

A `Technique` can carry authored requirements of its own, gating whether a character
is allowed to *learn* it at all. This is distinct from the Path/thread-crossing/
path-entry gates documented in `docs/systems/progression.md`. `AbstractUnlockRequirement`
(that doc's "Requirements" section) grew a fourth polymorphic target, `technique`, so
any existing requirement type (`TraitRequirement`, `RelationshipRequirement`, and so
on) can be authored against a `Technique` as well as a `ClassLevelUnlock`,
`ThreadCrossingThreshold`, or `Path`. Two new requirement types exist specifically for
gating technique acquisition:

- `GiftHeldRequirement`: the character must hold a gift. Named means that gift
  (lineage-aware via `resolve_owned_gift`); blank means any held gift.
- `TechniqueKnownRequirement`: the character must already know a named technique.
  This is also the row `world.magic.services.technique_prerequisites
  .prerequisite_technique_ids` walks to build the transitive prerequisite closure
  consumed by thread carry (see "Thread Carry Through Technique Prerequisites" below).

`LegendRequirement` and `ItemRequirement` deliberately reject the `technique` (and
`path`) target; they only ever gate `class_level_unlock`/`thread_crossing_threshold`.

**Gate wiring:** `check_requirements_for_technique(character, technique)`
(`world.progression.services.spends`) mirrors the Path/thread-crossing/unlock
checkers, failing open (`(True, [])`) when the technique carries no active
requirement. `enforce_technique_prerequisites(sheet, technique)`
(`world.magic.services.gift_acquisition`) wraps it, raising
`TechniqueRequirementsNotMet` (`world.magic.exceptions`) on failure. Every
technique-acquisition route calls it: `charge_and_learn`
(`world.magic.services.gift_acquisition`) — the shared charge+acquire core behind
both teaching front doors, `accept_technique_offer` (player-to-player teaching) and
the Academy TRAIN offer handler (`world.npc_services.effects.run_train_offer`) —
calls it immediately after the duplicate-knowledge check and before gift-ownership/
cap logic; and `learn_technique` (`world.magic.services.technique_acquisition`) — the
third route, the shared commit seam behind item-scroll `TechniqueGrant` delivery
(`actions/definitions/items.py`), ritual `TechniqueGrant` delivery
(`learn_technique_from_ritual`), and `GMAwardAction`'s story-grant action
(`actions/definitions/gm_adjudication.py`) — calls the same helper right after its
own duplicate-knowledge check, in both its immediate-mint (`ap_cost == 0`) and
meter-creation (`ap_cost > 0`) branches. `learn_technique` skips the check in two
cases: `origin=AcquisitionOrigin.GM_GRANT` (a GM award is deliberate fiat) and
`completing_progress=True` (the meter-fill call `contribute_to_technique_progress`
makes — the check already ran when that meter was created, whichever route created
it). The item-scroll route additionally runs `check_requirements_for_technique`
as a pre-flight check *before* `use_item()` consumes the item's charge, since
`use_item()` is its own committed transaction a post-use refusal can't roll back —
a gated scroll is refused without being spent.

**CG pick list exclusion:** a character-creation draft has no `CharacterSheet` yet,
so `check_requirements_for_technique` cannot be evaluated against it. Instead,
`world.magic.services.cg_catalog.get_technique_options(..., exclude_gated=True)`
excludes every technique carrying at least one active requirement row outright, one
query per concrete requirement type (via `concrete_requirement_types()`), never one
per technique. Only call sites that model "what a brand-new character can pick" pass
`exclude_gated=True`: `world.character_creation.validators` and `.views`, and the
starting-kit analytics report (`web/admin/tuning/technique_analytics.py`). Every
in-play caller, today just Academy TRAIN's own eligibility check, keeps the default
`exclude_gated=False`, because an in-play learner may already satisfy the
prerequisite and `charge_and_learn`'s own per-character check is the correct gate
for them, not a blanket catalog exclusion.

**Discovery, not a hardcoded list:** `concrete_requirement_types()`
(`world.progression.services.spends`) replaces the former hand-maintained list of
requirement types that every `_check_requirements` caller consulted, where a type
omitted from that list silently never evaluated. It now returns every concrete
`AbstractUnlockRequirement` subclass Django has registered (`apps.get_models()`),
so a new requirement type is live the moment its model is defined.

### Thread Carry Through Technique Prerequisites (#4097) [BUILT & WIRED]

A thread woven into a technique also empowers every technique that technique is a
prerequisite for, at the thread's full level, transitively, including a hidden
ultimate several `TechniqueKnownRequirement` hops downstream. Early investment in a
foundational technique is never wasted once a character learns what it unlocks.

- `prerequisite_technique_ids(technique_ids)`
  (`world.magic.services.technique_prerequisites`): a breadth-first walk over active
  `TechniqueKnownRequirement` rows (`technique=X, required_technique=Y` means "X
  requires Y"), one batched query per depth level, cycle-safe. Returns only the
  *discovered* prerequisites, excluding the input ids themselves (even one
  rediscovered through a cycle).
- `PullActionContext.involved_technique_closure` (`world.magic.types.pull`): a
  `cached_property` unioning `involved_techniques` with
  `prerequisite_technique_ids(involved_techniques)`. Memoizing is safe here because
  `PullActionContext` is a per-call frozen dataclass value object, not a
  `SharedMemoryModel`, so the cache lives exactly as long as one pull resolution.
- `_anchor_in_action` (`world.magic.services.resonance`): the TECHNIQUE branch
  tests thread membership against `involved_technique_closure` instead of the bare
  `involved_techniques` tuple. This is the one caller that needed widening: both
  casts and paid combat/non-combat pulls resolve through it, so the carry applies
  identically to both.

**Deliberately unchanged:** the ambient capability sweep
(`_anchor_ambiently_active`, "Capability magnitude curve" below) still tests the
bare involved technique, not the closure. Ambient/passive contribution demands
demonstrable real state, and a prerequisite's thread is not itself in active use
just because something it unlocked is being cast.

See `docs/adr/adr-4097-threads-carry-through-technique-prerequisites.md` for the
decision record and rejected alternatives (moving/copying thread investment, a
stored carried total).

### Acquisition provenance — `CharacterTechnique.origin` / `CharacterGift.origin` (#3055) [BUILT & WIRED]

Both link models carry an `origin` field (`AcquisitionOrigin` TextChoices,
`world/magic/constants.py`) recording how the row was acquired — the
`distinctions.DistinctionOrigin` pattern generalized to the two magic-acquisition
models that lacked any discriminator. One shared enum (not one per model), since
neither model is expected to use every value:

| Value | Set by | Notes |
|---|---|---|
| `CHARACTER_CREATION` | CG finalize (`_finalize_gift_and_techniques`) | Default value; covers pre-#3055 rows. |
| `PATH_GRANT` | `grant_path_magic` | Path-crossing grant. |
| `SPECIES_GRANT` | `provision_species_gifts` | Gift-only — no site grants a `CharacterTechnique` for a species today. |
| `TRAINED` | `learn_technique`'s mint seam (ritual `TechniqueGrant` or a completed `TechniqueProgress` meter); `charge_and_learn`'s implicit first-gift acquisition | The "acquired via training/teaching investment" family for both models. |
| `ROLE_GRANT` | `_grant_role_gifts_and_techniques` (`world/covenants/services.py`) | Auto-revoked on disengage (technique side, via `role_source`). |
| `ORGANIZATION_GRANT` | Weaving an `ORGANIZATION` thread (`services/threads.py`) | Technique-only. |
| `ALTERNATE_SELF_GRANT` | An alt-self's ability-suite grant (`world/forms/services`) | Technique-only; tied to a `ModifierSource`, revoked on revert. |
| `AUTHORED` | `author_technique` (technique-authoring budget builder) | Technique-only. |
| `GM_GRANT` | `GMAwardAction`'s `award_type="technique"` branch (#3055 slice 1c) | Technique-only — passed as `learn_technique(..., origin=AcquisitionOrigin.GM_GRANT)`, `ap_cost=0` for an immediate mint. |
| `TRIAL` | The `TECHNIQUE_TRAINING` effect's "grant outright" (#4501) | Technique-only. Unlike `GM_GRANT` it does NOT skip `enforce_technique_prerequisites`. |

`grant_gift_to_character` (the shared gift-acquisition primitive) takes an `origin=`
kwarg (default `CHARACTER_CREATION`), stamped only on a freshly-minted `CharacterGift`
— an already-owned gift keeps its original provenance on re-grant. See the sibling
acquisition-provenance record for in-place trait/skill value mutation,
`traits.CharacterTraitChange`, in `docs/systems/INDEX.md`'s Traits entry.

### Check-Based Training Session Trigger (#2739) [BUILT & WIRED]

`resolve_training_check()` (`services/technique_training.py`, #2727) wraps
`contribute_to_technique_progress` with a learning check — the learner rolls
intellect, plus the skills staff map to `TECHNIQUE_LEARNING`, against a difficulty derived from the technique's tier,
the learner's level, and any teacher's skill bonus (self-study takes a flat
penalty) — but shipped with no production caller: nothing dispatched it from telnet
or the web. #2739 is that trigger, one seam for both surfaces:

**Content dependency, loud failure (#3043).** The check rolled is the "Technique
Training" `CheckType`, resolved by exact name. That row (which weights intellect only;
the seed stopped inventing an "Arcane Theory" skill for it in #4547) is authored content, not seeded — as of 2026-08-07 it does not
exist in any shipped content bundle (tracked in ArxII-lore#72). `resolve_training_check`
used to fall back to `CheckType.objects.first()` on `DoesNotExist` — an arbitrary,
unrelated check silently rolled in training's place on any deploy missing the row.
It now raises `TechniqueTrainingNotConfigured` (`world/magic/exceptions.py`)
instead, whose `user_message` ("Technique training is not configured on this
server yet.") is what `TrainTechniqueAction`'s existing `except (…, MagicError)`
clause surfaces — a clean failure `ActionResult` on telnet, HTTP 400 `{"detail": …}`
on the web endpoint below. No player-facing string carries an em-dash.

- **Action** — `TrainTechniqueAction` (`actions/definitions/technique_training.py`,
  key `train_technique`, REGISTRY, `category="magic"`, `target_type=SELF`). Kwargs:
  `technique_id` (the `Technique` pk — resolved against the learner's own open
  `TechniqueProgress` meter; no meter is a clean failure naming the two front doors
  that create one — accepting a teaching offer, or an Academy TRAIN offer, both
  covered above), `ap_to_invest` (defaults to 1 — no base-session-cost constant
  exists yet on `GiftAcquisitionConfig` or the seam itself; a supplied value ≤ 0 is
  rejected). Resolves a co-present teacher: `progress.teacher_tenure` counts only
  when that tenure's live character shares the learner's room *at session time* —
  never a location hard-block (Decision 3a), true for both PC-teacher meters and
  Academy TRAIN meters; a teacher out of the room silently drops to self-study
  rates for that session. `resolve_training_check`'s own `WeeklyTrainingCapExceeded`
  / `MagicError` raises map to failure `ActionResult`s; a bare `ValueError` from
  `learn_technique` (reached on meter completion) — raised when the learner already
  holds the `CharacterTechnique`, e.g. a stale meter left open after the technique
  arrived by another route (a staff grant, a `TechniqueGrant` item) — maps to a
  failure the same way rather than escaping as a traceback. On success, `data`
  carries `{technique_id, outcome_name, points_before, points_after,
  total_required, technique_acquired, self_study}`.
- **Telnet** — `CmdTrain` (`commands/training.py`, key `train`). `train <technique>
  [=<ap>]` resolves the technique by name and dispatches the action; bare `train`
  lists the caller's open `TechniqueProgress` meters (name, progress/total,
  teacher-or-dash) with no dispatch — a read path, not an action.
- **Web** — `TechniqueProgressViewSet` (`world/magic/views_technique_progress.py`,
  routed at `/api/magic/technique-progress/`). `list` returns the scoped
  character's own meters via `TechniqueProgressSerializer` (technique id/name,
  `points_accumulated`/`total_required`, teacher name-or-null via
  `RosterTenure.display_name`, `source_label` from
  `TechniqueProgress.get_source_display()`, and a batched-query
  `weekly_remaining` — one `GameWeek` lookup + one config lookup + one query over
  the listed meters' technique ids, never per-row). `POST
  <technique_id>/train/` (`TrainTechniqueRequestSerializer`, body
  `{ap_to_invest?}`) dispatches the action, mapping a failure `ActionResult` to
  HTTP 400 with its message. `<technique_id>` is the `Technique` pk (matching the
  action's own kwarg), not the `TechniqueProgress` row's pk, so a technique with
  no meter surfaces the action's own "you aren't training that" failure as a clean
  400 rather than a router-level 404. Character scoping mirrors
  `MotifStyleViewSet` (#2030): an `X-Character-ID` header, validated as owned, takes
  precedence over the caller's active puppet.
- **Frontend** — `TechniqueProgressPanel` (`frontend/src/magic/components/`),
  mounted in `SpellbookTab` below `MotifStylePanel`, own-view only. One card per
  meter: a progress bar/fraction, a "Taught by `<name>`"/"Self-study" badge, weekly
  remaining (when the server supplies it), an optional AP-to-invest number input,
  and a Train button. The session outcome (or the server's 400 message) renders
  inline per row; the mutation invalidates the meter query so the refetched
  figures reflect the session immediately. See `frontend/src/magic/CLAUDE.md` for
  the query/mutation wire contract.

This closes the same "built but unreachable" gap the acquisition surface above
closed for `spend_xp_on_gift_unlock`/`accept_technique_offer` — `resolve_training_check`
now has exactly one production caller, shared by both client surfaces.

The entrance itself (which pose is the entry pose, the threshold before it, the acclaim
window opened on it) is described in `docs/systems/scenes.md`'s "The entrance" (#3867).

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

**Origin scene (#2159).** `RitualSession.scene` (nullable FK → `scenes.Scene`, `SET_NULL`)
captures the initiator's active scene at draft time via the canonical `get_active_scene`
resolver — never client-supplied. `RitualSessionFilterSet` exposes a `?scene=` `NumberFilter`
(field `scene_id`) on the sessions list endpoint so a scene can surface its own
PENDING/READY sessions (the web `RitualProposedChip` on `/game` and `/scenes/:id`, see
`frontend/src/rituals/CLAUDE.md`). Like the other `RitualSessionFilterSet` filters
(`as_invitee`/`as_initiator`/`ritual`/`participation_rule`), `?scene=` doesn't appear in the
generated OpenAPI schema — drf-spectacular can't introspect this viewset's request-dependent
filterset (pre-existing gap).

---

### Soulfray (world/magic/services/soulfray.py, #4089, #4122)

**Soulfray is the condition template `SoulfrayConfig.condition` names (#4122).** The
game never matches the template by name, so staff can rename it in admin and nothing
changes. `soulfray_condition_id()` / `get_soulfray_template()` read the field through the
config singleton; accrual (`_handle_soulfray_accumulation`), the non-lethal cap, the safety
checkpoint warning (`get_soulfray_warning`), Audere and Audere Majora eligibility, the
anima ritual's severity paydown, the boss break-bar floor, the Soulfray Stage Builder and
the Required-content probes all go through those helpers or `soulfray_stages()`. With the
field unset every read finds no Soulfray (a stage list is empty, no instance matches) and
the first accrual raises `ConditionTemplate.DoesNotExist`; the Required-content row
`soulfray-condition` flags it. The bootstrap seed (`seed_magic_config`) and the test
factories (`SoulfrayTemplateFactory`, `SoulfrayContentFactory`) create the template under
`world.magic.constants.SOULFRAY_SEED_TEMPLATE_NAME` and set the field; game logic never
reads that constant.

**The ladder summary is the one read every Soulfray surface shares.**
`soulfray_ladder_summary() -> list[SoulfrayStageSummary]` walks every `ConditionStage`
of the Soulfray template in ladder order and resolves each one's EFFECTIVE
consequences - its own pool entries merged with its shared parent's, the same
single-depth merge `actions.services.merge_pool_entries`/`get_effective_consequences`
use for an ordinary consequence pool draw - in two queries total regardless of ladder
size. `SoulfrayStageSummary.can_kill` is true when any of those effective consequences
carries `character_loss`; `consequence_count` and `shared_consequence_ids` (ids the
stage's own pool also draws from its parent) round out what the Soulfray Stage Builder's
ladder, rail and Required-content probes all read from one call. `soulfray_stages()`
(exact `condition__name` match, ladder-ordered) and `is_soulfray_stage(stage)` are the
shared lookups every Soulfray consumer in this module uses, including the `ConditionStage`
admin's "Open in Soulfray Stage Builder" object-tool link (`web/admin/authoring/links.py`)
and the `AudereMajoraThreshold.minimum_warp_stage` picker below.

**The non-lethal cap and the checkpoint's death warning now read inherited lethal rows
(#4089 Task 2).** `nonlethal_ceiling_for(summaries)` is a pure function over an
already-built ladder summary: `(lowest severity_threshold among stages that can kill) -
1`, floored at 0, or `None` when no threshold-bearing stage can kill. It is read both by
`nonlethal_severity_ceiling()` (wraps it over a fresh `soulfray_ladder_summary()` call;
`calculate_soulfray_severity(..., lethal=False)` bounds its result below this ceiling)
and by the Soulfray Stage Builder's Danger rail, so the game and the authoring page agree
on the same number. Before #4089, `nonlethal_severity_ceiling()`'s cap and
`get_soulfray_warning()`'s `has_death_risk` flag (the safety checkpoint's death warning)
each read a stage's own pool entries only; a `character_loss` row a stage's pool inherited
from a shared parent pool was drawn by a lethal cast but never capped for a non-lethal
one, and the checkpoint never warned of it. Both now read `get_effective_consequences`
(`get_soulfray_warning`) or `soulfray_ladder_summary()` (`nonlethal_severity_ceiling`),
which merge in the inherited rows the same way the draw itself does.

**The anima-0 stage (#4740, #4727 decision 7).** `SoulfrayConfig.anima_zero_stage`
(nullable FK to a Soulfray `ConditionStage`, PROTECT; `clean()` requires a stage of
`condition` with a `severity_threshold`, and the admin picker offers Soulfray stages only)
is the stage the dangerous part of the ladder starts at. While she has anima left after a
cast's deduction, `_handle_soulfray_accumulation` keeps the cumulative severity at or below
`anima_zero_ceiling(current) = anima_zero_stage.severity_threshold - 1`, on both the
first-creation and the advance branch, through the same bound the non-lethal cap uses
(`_bounded_advance`); when both caps apply, the lower wins. At anima 0, or with the field
unset, there is no anima cap. `accumulate_soulfray` passes the refreshed `anima.current`;
a direct caller that passes none gets no anima cap.

**Authoring path.** A Soulfray stage's own fields, its on-entry conditions, its
resilience-check penalty, its consequence pool (own rows and an optional one-level-deep
shared parent) and each own row's effects are authored on the **Soulfray Stage Builder**
(`web/admin/soulfray_builder/`), the single page that replaces hand-editing the stage's
admin change form plus its pool's and consequences' separate pages. A row the stage
inherits from its shared parent is drop/reweight only there (spec story 7, ruling RF-1):
its wording, Can kill, Spin the wheel and effects belong to the parent pool, so the page
shows them read-only and the save writes only the stage's child entry for it. Two Required-content
rows ("Soulfray stage consequence pools", "Some Soulfray stage can kill") flag a stage
with nothing to draw or a ladder with no lethal stage, linking straight into the builder.
Full detail: `src/web/admin/CLAUDE.md`'s "Soulfray Stage Builder" section.

**A dramatic stage draw spins the #924 outcome wheel (#4089 Task 7).** Stage-consequence
resolution now produces `SoulfrayReveal` (`title`, `stage_label`, `faces`, `selected`)
whenever the drawn tier is dramatic (`should_emit_theater`: any face is ticked
`theater` or can kill) - the same per-result rule every other check-outcome wheel in the
game uses (ADR-4089-B). `_soulfray_reveal` builds its `faces` from the drawn tier's
UNFILTERED effective consequences (`consequence_pool_faces(..., min_faces=1)`, a lone
candidate still spins): a `character_loss` row a non-lethal cast's own filter removed from
the actual draw still shows as a face the wheel spins past, and neither the screen nor the
payload reveals that it was filtered - the draw's `selected` face is always one the
filtered draw actually picked. `accumulate_soulfray(..., defer_reveal=False)` sends the
reveal to the caster on commit (`transaction.on_commit`, so a rolled-back cast never
spins a wheel) via `deliver_soulfray_reveal` (the existing `maybe_emit_resolution_theater`
emitter, web-only: telnet has no `roulette_result` output). The scene-action path
(`world.scenes.action_services`) instead calls `use_technique(..., defer_soulfray_reveal=
True)` and plays the held reveal itself, through `_schedule_check_outcome_theater`'s
`soulfray_reveal` kwarg, AFTER the action's own wheel(s) and to the caster only - a
Soulfray stage draw is the caster's own backlash, not something the rest of the scene's
audience watches. See `world/checks/CLAUDE.md`'s "#924 theater" section and ADR-4089-B.

---

### Audere & Audere Majora (models/audere.py, audere_majora.py)

**Found by designation (#4739) [BUILT & WIRED].** The Audere and Audere Majora conditions are
`AudereThreshold.audere_condition` / `audere_majora_condition`, read through
`audere_condition_id()` / `audere_majora_condition_id()`; eligibility, `offer_audere`,
`end_audere`, `cross_threshold`, `end_audere_majora`, the mid-crossing check, the check-level
bonus, `_character_is_in_audere`, `active_ceremony` and encounter cleanup all compare ids,
never names. Unset: no offer, nothing applied (the dashboard lists it). The combat participant
payload carries `audere_state` (`audere` | `audere_majora` | null) for the web Audere strip.
Berserk likewise is `FuryConfig.berserk_condition` (`get_berserk_template()`,
`berserk_condition_id()`), read by fury, moon-sensitivity, the rampage compulsion's
`is_berserk` and the combat status line (the fury declaration serializer no longer reads it,
#4738).

**High control opens Audere earlier (#4740, #4727 decision 6).**
`AudereThreshold.control_per_stage_earlier` (PositiveSmallIntegerField, default 0 = off):
each full step of runtime control steps the Soulfray stage the plain Audere offer needs back
one stage along the actual Soulfray ladder (stage orders need not be contiguous: on a
10/20/30 ladder one step from 30 is 20), never below the first Soulfray stage.
`required_stage_order(threshold, runtime_control)` (`world/magic/audere.py`) computes it;
negative control lowers nothing, and the ladder is read (one query) only when control
lowers the requirement. `stages_lowered_by_control(threshold, runtime_control)` counts the
stages taken off; `PendingAudereOfferSerializer.stages_lowered_by_control` exposes it from
the offer's `fired_control`, the web offer dialog renders "Your control lets you break
through one Soulfray stage earlier than usual." (or "N Soulfray stages") when it is above
0, and the telnet `accept` listing appends the same line (`control_lowered_line`). `_evaluate_audere_gates`,
`check_audere_eligibility(character, runtime_intensity, runtime_control=0)` and
`maybe_create_audere_offer(character, runtime_intensity, *, runtime_control=0, sheet=None)`
take the control; the cast hook in `use_technique` passes `stats.control` (the control as
cast, after any control surrendered to Fury). `PendingAudereOffer.fired_control` stores it so
`resolve_audere_offer`'s stale re-check asks for the same stage the cast did. Audere Majora's
own `minimum_warp_stage` gate is unchanged (by default it also requires an active Audere).

**Intensity tiers never lower control (#4740, #4727 decisions 5 and 13).**
`IntensityTier.control_modifier` has `MinValueValidator(0)` (the admin refuses a negative
value), the bootstrap seed sets Moderate and Major to 0, and the Required content row
`intensity-tiers-never-lower-control` lists any tier still below 0 (rows authored before the
rule are not migrated; staff fix them).

**Audere check level bonus (#4147).** `AudereThreshold.check_level_bonus` and
`AudereMajoraThreshold.check_level_bonus` (PositiveSmallIntegerField, default 0) are the
extra effective levels every check the character makes counts while in Audere or Audere
Majora (each level is 5 points, ADR-0166). `audere_check_level_bonus(character)`
(`world/magic/audere.py`) reads it: Audere Majora's own bonus replaces Audere's while the
Majora condition holds, using the threshold with the highest `boundary_level` at or below
the character's path level; with Majora held but no threshold at or below that level, it
falls back to Audere's bonus; zero when neither condition is held. `perform_check`
(`world/checks/services.py`) adds it to the resolved path level only when no
`level_override` is given; an override is used as given. Spectacle's level comparison adds
the same bonus to the caster's level.

**An ultimate never fails (#4147).** `floor_ultimate_check(result, technique)`
(`world/magic/services/ultimates.py`) raises a failed outcome to the lowest
`CheckOutcome` with `success_level >= 1`; points are left as rolled, and a result already
at success or better, or a technique that is not an ultimate, passes through unchanged. It
is applied in the combat technique path and the standoff display cast. An ultimate also
skips the control mishap in `_complete_technique_cast`, which covers every cast path. The
scene-cast path (`world/scenes/cast_services.py`) does not floor the roll, because
`start_action_resolution` has no roll hook and Audere arises only in combat in practice.

**Audere entry and a Crossing shake witnesses (#4147).** `shake_witnesses(character, kind,
display_name=...)` (`world/magic/audere.py`) finds the character's encounter through its
COMBAT engagement and, on `transaction.on_commit(robust=True)`, applies and delivers a
spectacle (see `docs/systems/INDEX.md`, Spectacle). It is a no-op with no sheet or no combat
engagement. `offer_audere` calls it with `AUDERE_ENTRY` after an accepted offer;
`cross_threshold` calls it with `CROSSING` after the crossing's own broadcast. Deferring to
commit means a rolled-back acceptance posts nothing, and `robust=True` means a failure in
the rider is logged without undoing what already committed.

**Surge broadcast on accept (#3451).** `AudereThreshold.surge_manifestation_text`
(TextField, blank default) is broadcast as a system EMIT to the active scene when a
character accepts a plain Audere surge — `_broadcast_surge` in `world/magic/audere.py`,
fired from `offer_audere`'s accepted path after the bonus transaction commits. `{name}`
substitutes the character's primary-persona name. Blank text keeps the accept
room-silent, so the line is staff-authored content, never code-authored prose. The
scene-EMIT mechanics live in the shared `broadcast_scene_emit`
(`world/scenes/interaction_services.py`), which the Audere Majora
`_broadcast_manifestation` also delegates to — one dispatch shape for both beats.

**Audere alternate self (#4731, slice 2 of #4672).** An alternate self is a bond source in
the Audere ultimate reveal (#4098's deferred past-life source; see "Ultimates" below). Staff
attach ultimates to it with `AlternateSelf.ultimate_techniques` (M2M, ultimates only), and
every alternate self of hers that carries one shows up as a reveal group, worn or not;
a character may offer several. There is no flag: the player picks. When she chooses one of
that group's cards, `choose_ultimate` readies the ultimate as for any card and registers
`assume_alternate_self_for_audere(sheet, alt)` (`world/forms/services/__init__.py`) with
`transaction.on_commit(..., robust=True)`, so the self comes out only once the choice is
durable and nothing it does can undo the choice, the readied ultimate or Audere. The callback
assumes the self through `trigger_transformation(cause="audere")` in its own atomic block,
marks `ActiveAlternateSelf.assumed_at_audere=True`, and tells her "You assume <name>." (the
name is `AlternateSelf.shown_name`: display name, else persona name, else "an alternate
self"). The self she already wears is left as it is and unmarked, since she put it on
herself. A different worn self is reverted first in its own savepoint; when that revert is
refused because she is not in control, she is told "You cannot leave <worn> while not in
control of yourself, so <chosen> does not come out." and keeps the worn self, the ultimate
still readied. A self that cannot be assumed (a form or persona she does not own:
`AlternateSelfActiveError` / `FormOwnershipError` / `ActivePersonaError`) logs a warning and
rolls back the half-built assumption.

`AlternateSelf.revert_kind` says how it ends. `AUTOMATIC`: `revert_audere_alternate_self(sheet)`
reverts a worn self marked `assumed_at_audere` when Audere ends (`end_audere`), and
`revert_audere_alternate_selves(sheet_ids)` does the same for every participant at
`cleanup_completed_encounter` in one query, so the self also drops at the fight's end when
the Audere condition already ran out on a round duration, and after a self taken on at an
Audere Majora Crossing. A self she put on herself (`assumed_at_audere` False; every
assumption and revert resets it) is never reverted by Audere. The revert runs in its own
savepoint and never raises into encounter cleanup: a revert blocked by `in_control` is
logged at info and the self stays until she reverts it once in control; the forms refusals
are logged as warnings. `TALKED_DOWN`: the self also takes `emergence_condition` (a
behavior-altering `ConditionTemplate`, required by a DB check constraint and `clean()`),
stays after Audere ends, and `form revert` is refused until the condition is cleared by
`breakfree`, a rally or a calm-down. If the condition does not land (immunity, stacking), a
warning is logged, because nothing then stops her reverting at will. `clean()` and the DB
check reject an emergence condition on an `AUTOMATIC` self (it would block its own revert).

**Acting aura (#4731).** `acting_aura(sheet)` (`world/magic/services/acting_aura.py`)
returns an `ActingAura` (`percent_for(affinity)`, `dominant_affinity`, `is_alternate_self`):
100% of the active alternate self's resonance affinity when it has one, else the sheet's
`CharacterAura`. Readers that follow it (what she acts with):

- the technique cast aura-alignment term (`_aura_alignment`, `services/power_terms.py`);
- the place-of-power alignment boon on arrival (`refresh_resonance_alignment` via
  `evaluate_resonance_environment` with no technique);
- the place reaction during a cast (`use_technique` evaluates
  `evaluate_resonance_environment` with the technique; `resonance_environment_for_cast`
  and the power ledger consume that result);
- defilement, which reads the same `evaluate_resonance_environment` result;
- the covenant `ATTACKER_AFFINITY` situation (`_attacker_aura`,
  `world/covenants/perks/evaluators.py`).

Working affinities follow the alternate self too. `working_affinities(sheet, resonances)`
(same module) returns the worn self's resonance affinity in place of the gift's
resonances, as variant resolution does (`_effective_variant_resonance`), so her own
techniques work in the affinity she acts with: a Celestial-gift technique cast in an
Abyssal self gets the full alignment term. The alignment term and the cast-time resonance
of place (`_working_affinity_cast_time`, `_working_affinities_for_raw`) read it;
`gift_resonances_for` itself is unchanged, and the resonance-standing term still reads the
gift's resonances. Readers that keep the TRUE aura (who she is): the Fall threshold
(`perform_fall`), the Soul Tether affinity gate, the sheet's aura display and serializer,
and the `magical_profile` gate in `refresh_resonance_alignment`. An alternate self with no
resonance changes nothing.

**Drift and Resonance Conflict (#4732, slice 3 of #4672).** Resonance a character carries
outside the affinity she acts with is *drift*; drift past an authored threshold makes casting
call for a focus check, and a failed check puts the authored Resonance Conflict condition on
her for the template's duration (authored as the scene). All of it lives in `world/magic/services/drift.py` and the
`DriftConfig` singleton (`models/drift.py`, `get_drift_config()`); no number is in code.

- `DriftConfig` fields: `threshold_percent` (percent of the main balance), `threshold_floor`,
  `severity_step` (drift points past the threshold per severity step), `off_aura_pull_steps`
  (steps an off-aura pull adds), `focus_base_difficulty`, `focus_difficulty_per_step`, and two
  designations by FK, `focus_check_type` and `conflict_condition`. Either designation unset
  means the check does not run; the Required content dashboard probes list both, require
  the conflict condition's category to be `self_shakeable` and its `break_free_mode` not to be
  NONE (the field's default; breakfree, rally and the tick skip a NONE condition), and require
  the condition to carry at least one `ConditionCheckModifier` (else a failed roll costs
  nothing).
- `AffinityInteraction.conflict_weight` (default 1.00): how hard a balance in the first affinity
  pulls against the second. A pair with no authored row counts at 1.00.
- `drift_for(sheet) -> DriftReading` (`drift`, `threshold`, `steps_past`, `dominant_affinity`):
  the dominant affinity is `acting_aura(sheet).dominant_affinity`, so a worn alternate self turns
  her balance in her true affinity into drift. Main balance is the sum of her balances in the
  dominant affinity; drift is the sum of every other balance times its `conflict_weight`;
  threshold is `max(threshold_floor, main * threshold_percent / 100)`; `steps_past` is 0 at or
  under the threshold, else `1 + (drift - threshold - 1) // severity_step`. With no aura (no
  dominant affinity) the reading is all zero; with an aura and no off-aura balance the
  dominant affinity is set, the threshold is `threshold_floor`, and only `drift` and
  `steps_past` are 0.
- `check_resonance_focus(character, technique, *, pulled_resonance=None) -> FocusOutcome | None`
  runs once per cast, inside `_complete_technique_cast` in `use_technique`
  (`services/techniques.py`), after anima is deducted and before `resolve_fn` runs. That one
  seam means every cast path rolls it: scene, combat, clash, battles, standoffs and
  technique-enhanced social actions. A pull is part of its cast with no separate roll: the
  pulled resonance is `cast_pull`'s when the cast charges one, else the
  `use_technique(pulled_resonance=...)` its caller names. The combat round resolver and the
  clash contribution pass the round's committed `CombatPull` resonance
  (`world/combat/pull_helpers.py` `round_pull_resonance`); no other cast reads combat pulls.
  Whether the penalty lands on the same roll depends on where each path gathers modifiers:
  scene casts, combat casts, clash contributions and standoffs gather them inside
  `resolve_fn`, so the conflict counts on the roll that triggered it. Scene casts gather them
  after anima, the pull charge and the `TECHNIQUE_PRE_CAST` triggers, so a condition a
  PRE_CAST trigger applies also counts on that roll. Technique-enhanced social actions gather
  modifiers before `use_technique`, so there the penalty counts from her next roll. Battles
  roll focus, but the battle roll (`world/battles/resolution.py` `BattleTechniqueResolver`)
  reads no condition modifiers at all (pre-existing), so the conflict reaches only her later
  non-battle rolls. The joust is not a cast and rolls nothing. The condition's own authored `ConditionCheckModifier` reaches the
  roll under its own label through `condition_contributions`. Difficulty is
  `focus_base_difficulty + steps * focus_difficulty_per_step` (an off-aura pull adds
  `off_aura_pull_steps` to the steps); the roll is `focus_check_type` with
  `MagicActivity.KEEPING_FOCUS` skill terms. Before the roll she is told the check is
  happening and against which aura (the demo's Screen 4 warning line); a failure also tells her
  the condition took hold. A success level of 1 or more changes nothing.
  Below that, severity is `steps + (1 - success_level)` (a worse roll never costs less);
  already holding the condition, its severity advances by one instead.
- Shaking it off: `ConditionCategory.self_shakeable` (default False) is separate from
  `alters_behavior`, which drives `in_control`, consent and form revert and is never set for
  Resonance Conflict. `breakable_condition_filter()` (`world/conditions/services.py`) is
  `alters_behavior OR self_shakeable`; `breakfree`, `rally` and the break-free tick use it,
  `reveal` stays on `alters_behavior`. She types `breakfree`, an ally's `rally` helps.
- Stirring it up is authored content, not code: a social action whose consequence pool has an
  `APPLY_CONDITION` effect for the conflict condition on its target raises a holder's hold to
  the stir's authored severity through the ordinary `apply_condition` path; the higher
  severity wins (stacking templates also take the maximum, `_handle_stacking`), so a stir
  never lowers a hold and never adds to it.

**`RenownAwardConfig`** (`world/societies/renown_config.py` — relocated from
`world/magic/models/renown_config.py` in #1621 so any app can inherit it without a
magic import cycle) — abstract base (SharedMemoryModel) shared by
`DramaticMomentType`, `AudereMajoraThreshold`, and societies' propaganda models.
Carries `magnitude`, `risk`, `reach` (nullable override), and `archetypes` M2M to
`societies.PhilosophicalArchetype`. Provides `as_renown_award_kwargs() -> dict`.
When `risk == NONE`, `fire_renown_award` creates no `LegendEntry` — the invariant
that gates deed creation.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `AudereMajoraThreshold` | One row per boundary level (5/10/15/20). Inherits `RenownAwardConfig`. | `boundary_level`, `target_stage`, `minimum_intensity_tier` FK, `minimum_warp_stage` FK, `requires_active_audere`, `deed_title` (public — non-spoiler), `vision_text`/`manifestation_text` (spoiler-private — DB-only) |
| `PendingAudereMajoraOffer` | Poll-able Crossing offer, one per character | `character_sheet` FK, `threshold` FK |
| `AudereMajoraCrossing` | Irreversible receipt of a completed crossing (inherits `AbstractClassLevelAdvancement`) | `character_sheet` FK, `threshold` FK, `chosen_path` FK, `scene` FK, `declaration_interaction` FK, `level_before`, `level_after`, `legend_entry` OneToOneField → `societies.LegendEntry` (related_name `audere_majora_crossing`; null when no deed was minted) |

**The warp-stage picker only offers Soulfray stages (#4089).** The Crossing gate
compares the caster's current Soulfray stage order against `minimum_warp_stage`
(`audere_majora.py:359`), so a non-Soulfray `ConditionStage` there is always a
content error. `AudereMajoraThresholdAdmin.formfield_for_foreignkey` narrows the
field's queryset to `soulfray_stages()`, `AudereMajoraThresholdForm.clean_minimum_warp_stage`
refuses a non-Soulfray pick server-side, and `ConditionStageAdmin.get_search_results`
narrows the field's own autocomplete the same way via the generic
`web.admin.autocomplete.source_field_queryset` helper - a small seam any admin's
`get_search_results` can call to honour a remote admin's own
`formfield_for_foreignkey` narrowing without that remote app importing this one.

**Deed minting.** `cross_threshold` calls `_mint_crossing_deed(crossing)` after writing
the receipt. This resolves the character's primary persona, calls `fire_renown_award`
(full renown event), records every persona present in the scene as `WITNESSED` via
`grant_deed_knowledge` + `scene_witness_personas`, and stores the resulting
`LegendEntry` on `crossing.legend_entry`. Deed title uses `threshold.deed_title` when
authored, falling back to a generic public-fact composition; ceremony text is never used.
No deed is created when `threshold.risk == NONE` or when the sheet has no primary
persona (`legend_entry` stays null).

**Eligibility gate 8 (#1859):** `_evaluate_majora_gates` additionally checks the
`ClassLevelUnlock` authored for `(character's class, boundary_level + 1)`, via
`check_requirements_for_unlock` — the same hardcoded requirement-type list Ritual
of the Durance uses (`TraitRequirement`, `ItemRequirement`, etc.). No authored
unlock for that level means no gate (fail-open). Because the check is live and
non-cached, satisfying the last requirement mid-scene (e.g. acquiring a touchstone)
makes the very next eligibility poll pass — no separate re-sync step.

**Social safety bonus is staff-tunable (#4098 owner ruling).** `_get_social_safety_bonus()`
(`world/magic/services/techniques.py`) reads `SoulfrayConfig.social_safety_bonus`
(`PositiveIntegerField`, default 10) — the control bonus `get_runtime_technique_stats`
adds for a caster with no active `CharacterEngagement` row (i.e. not currently in
combat). Via `calculate_effective_anima_cost`'s control-delta formula (`effective_cost
= max(base_cost − (control − intensity), 0)`), raising this knob lowers the anima cost
of social/out-of-combat casting — high enough, it's nearly free. Falls back to the
field's own default (10) when no `SoulfrayConfig` row exists yet, matching
`apply_anima_ritual_outcome`'s handling of the same singleton in `anima.py`; the
"soulfray-config" TUNING row on the required-content dashboard already reports that
gap, so `_get_social_safety_bonus()` adds no separate guard of its own.

### Ultimates (#4098) [BUILT & WIRED]

Audere and Audere Majora are where a character's magic reaches powers no other path
reaches. See `docs/adr/adr-4098-ultimates-are-flagged-techniques-revealed-at-audere.md`
for the full design and rejected alternatives.

**An ultimate is a flagged `Technique`, never a separate catalog.**
`Technique.is_ultimate` (bool, indexed) marks it; `Technique.clean()` refuses to flip
the flag on a technique already sitting in a starter/tradition/item/alt-self pool or
known by a character. Keeping an *already*-ultimate technique out of those ordinary
pools in the first place is a separate, admin-side guard: every pool M2M
(`PathGiftGrant.starter_techniques`, `TraditionGiftGrant.starter_techniques`,
`TechniqueGrant.technique`, `AlternateSelfGrant.techniques`) carries
`limit_choices_to={"is_ultimate": False}`, which narrows the admin picker's options but
is not itself a `clean()`-time validation a programmatic `.add()` would hit. A
character's discovery of one is a `KnownUltimate` row
(`world/magic/models/ultimates.py`) - FKs `character` (CASCADE), `technique`
(PROTECT), nullable `crossing` (SET_NULL - which Crossing discovered it, null for a
plain Audere), `discovered_at`, `readied` (bool). Two constraints: one row per
`(character, technique)`, and at most one `readied=True` row per character - the
single pick of the character's current Audere. Deliberately not a
`CharacterTechnique`: that row means "castable now" and every ordinary cast surface
reads it, so keeping ultimates off it excludes them from everyday casting by
construction rather than by a filter someone could forget.

**Where an ultimate attaches:**

| Source | Field | Scope |
|--------|-------|-------|
| Owned (Path x major Gift) | `PathGiftGrant.ultimate_techniques` (M2M, mirrors `starter_techniques`) | major gifts only |
| Bond: patron | `WorshippedBeing.ultimate_techniques` (M2M) | devotees of that being |
| Bond: companion | `CompanionArchetype.ultimate_techniques` (M2M) | that archetype's bonded companions |
| Bond: alternate self (#4731) | `AlternateSelf.ultimate_techniques` (M2M, `limit_choices_to={"is_ultimate": True}`) | the character who has that alternate self |
| Gift (#4118) | `Gift.ultimate_techniques` (M2M, `limit_choices_to={"is_ultimate": True}`) | MINOR gifts only; any character holding the gift, Path-agnostic |

A minor gift's ultimates [BUILT & WIRED] are the fourth source (`UltimateSource.GIFT`,
`_gift_pools` in `world/magic/services/ultimates.py`): any `CharacterGift` row on a MINOR
gift contributes that gift's `ultimate_techniques` as one reveal group (card kind and
category rules unchanged; the telnet listing tags it `gift: <name>`). `_pools` drops a
technique already in an earlier pool, so one reachable through both a patron pool and a
gift pool shows only in the earlier (patron) group. The membership rules live in the admin
form (`GiftAdminForm` in `world/magic/admin.py`): only a MINOR gift may carry ultimates, and
every one must belong to that gift (`technique.gift`). An M2M cannot be validated in a
model `clean()` before the row has relations, so `Gift.clean()` covers the other direction
only: it rejects flipping a gift that already has ultimates to MAJOR. A major gift's
ultimates stay on its Path Gift Grants. No required-content probe flags a minor gift with
no ultimate: that is allowed.

Court pacts give enhancements only (decision 8), never ultimates of their own. Past-life
bond ultimates [BUILT & WIRED] (#4731) live on the past life's alternate self:
`UltimateSource.ALTERNATE_SELF`, `_alternate_self_pools`, one group per alternate self with
ultimates (between the companion and gift pools), labelled `bond: <name>` on telnet and by
`alternate_self_name` on the web. Choosing one of its cards also puts her in that self; see
"Audere alternate self" above. The pools are the same at an Audere Majora Crossing as at a
plain Audere, as for patron and companion bonds.

**Every ordinary acquisition surface excludes `is_ultimate=True`.** CG catalog pick
lists, covenant role auto-grants, the Sphinx's shopping list, the ORGANIZATION thread
weave (`Gift.inherited_techniques`), alternate-self ability suites, item
`TechniqueGrant`s, GM award, and ritual SERVICE dispatch all filter or refuse it; the
shared guard is `enforce_not_ultimate(technique)`
(`world/magic/services/gift_acquisition.py`), raising `UltimateNotLearnable`
(`exceptions.py`), called from both `learn_technique` and `charge_and_learn` ahead of
GM-fiat too.

**The reveal is computed state, not an offer table.** `ultimate_reveal_for(sheet)
-> UltimateReveal | None` (`world/magic/services/ultimates.py`) derives the
reveal fresh on every read: owned pools (current Path x major Gift, for a plain Audere;
the new Path x major Gift, for Audere Majora), owned-known pools (any technique the
character already knows via `KnownUltimate` whose grant is for a Gift still held as
MAJOR, regardless of which Path is current - so an owned known ultimate survives a
Crossing), bond pools (active patron devotion, active companion bond only - a
released bond's ultimates simply fall out of the pool, no extra check needed - and each of
her alternate selves with ultimates, #4731), and gift
pools (held MINOR gifts, #4118).
Candidates are filtered through #4097's `exclude_unmet_technique_requirements`
(promoted from the Sphinx's own prerequisite filter, now shared). Each pool is grouped
by category (`Technique.archetype_alignment` - Sword, Shield, Crown; display labels
come from `AudereThreshold.label_for_category`, never the raw enum word) into one of
three card kinds:

| Card kind | Shown | Never shown |
|-----------|-------|-------------|
| KNOWN | name, description | - |
| CATEGORY (undiscovered) | the category's authored label only | name, description, the technique's pk |
| UPGRADE | name, `upgrade_of_name` (the earlier ultimate it supersedes, #4097 prerequisite) | - |

An undiscovered candidate's identity never reaches the wire - the leak-analysis row in
the spec is enforced structurally by the card shape, not by a serializer omission that
could regress.

**Choosing readies; it does not cast.** `choose_ultimate(sheet, choice_key)`
(`@transaction.atomic`, `select_for_update`) re-resolves the reveal under the lock to
close a double-submit race (mapping a stale read to `UltimateRevealClosed`), then
`get_or_create`s the `KnownUltimate` row and sets `readied=True`. There is no explicit
clear-then-set: `ultimate_reveal_for`'s own `_has_readied` gate already returns `None`
(raising `UltimateRevealClosed`) whenever a readied row already exists, so this call
site is never reached with one in place, and the `one_readied_ultimate_per_character`
DB constraint is the backstop against a race that slips past that gate, not the
mechanism that clears a prior pick. This is the character's one pick
for the current Audere; it does not cast anything. `readied_ultimate` /
`clear_readied_ultimate` / `castable_technique_named` round out the read/clear/resolve
surface; `has_reveal_cards` answers "would accepting Audere show this character
anything" for the offer's framing line.

**Lifecycle wiring.** `offer_audere`'s accepted path, `end_audere`, `cross_threshold`,
and `end_audere_majora` (`world/magic/audere.py`, `audere_majora.py`) each clear any
readied pick - on accept (a stale pick from an abnormal end must not hide the next
reveal), on Audere/Majora ending, and on crossing (reopens the reveal for the new
Path's ultimates).

**Castable only in combat encounters.** `PlayerAction.is_ultimate` (actions/types.py)
and the corresponding serializer field mark a readied ultimate as a selectable combat
action; `_combat_actions` (`actions/player_interface.py`) appends it to the character's
`CharacterTechnique`-derived list only while building combat actions. Telnet's
`CmdDeclareTechnique._resolve_technique`/`_resolve_technique_id`
(`commands/combat.py`) resolve a readied ultimate by name only while the caller has an
active DECLARING round (`_combat_participant_or_none() is not None`) - never through
`CmdClashCommit`'s shared `_find_technique_id` mixin method, so an ultimate cannot be
played into a clash contribution or cast outside a combat round through the ordinary
cast command. An ultimate always resolves through the ordinary `use_technique` cast
pipeline once declared - no separate resolution path.

**Audere Majora round block narrowed to the undecided offer (#4098).**
`any_character_mid_audere_majora_crossing` (`world/magic/audere_majora.py`) used to
treat the whole Audere Majora condition lifetime (lasting until the encounter
completes) as blocking round resolution; it now checks only
`PendingAudereMajoraOffer` existence. The original guard protected the narratively
climactic, undecided moment of the offer from being overtaken by combat resolving
around the character before they chose to cross; left unscoped it also froze every
later round for the rest of the encounter, so a crosser could never act on the new
Path's ultimate. `is_mid_audere_majora_crossing` (single-character, disconnect-pause
use) is unchanged and still covers both windows.

**Required-content sentinels (`web/admin/tuning/required_content.py`):** a Path x
major Gift grant with zero rows in `ultimate_techniques` is flagged - an unfinished
Path (spec decision 15); the runtime fallback is minimal (Audere still gives its
surge, with no reveal). A second probe flags any `AudereThreshold` copy field
(`reveal_framing_text`, `deferred_death_text`, the three category labels) still
carrying its seeded PLACEHOLDER text.

**REST (`world/magic/views.py`, `serializers.py`):** `GET
/api/magic/audere/ultimates/?character_sheet_id=<id>` and `POST
/api/magic/audere/ultimates/choose/`, both owner-scoped (staff bypass; a foreign or
missing sheet both 404 identically - no existence leak).
`PendingAudereOfferSerializer.reveal_framing_text` surfaces the authored framing line,
blank unless `has_reveal_cards` is true. The character sheet's magic section gains a
plain `ultimates: KnownUltimateEntry[]` list (name, description, authored category
label - same visibility as the rest of the sheet's magic payload).

**Frontend:** `UltimateRevealDialog` / `UltimateRevealGate`
(`frontend/src/magic/components/`) - the gate mounts whenever a ceremony (Audere or
Audere Majora) is active, shows the reveal, and renders a persistent "Ultimate ready"
strip once a pick is readied; `AudereOfferDialog` gained the framing line;
`ActionDeclarationCard` marks a readied ultimate in the action list;
`SpellbookTab` lists known ultimates on the magic sheet.

**Telnet (`world/magic/offer_handlers.py`):** `UltimateRevealHandler` (keyword
`"ultimate"`) plus `format_ultimate_reveal`; the existing surge/crossing accept
handlers append the reveal listing after their success message. `accept ultimate <n>`
maps the ordinal onto the same stable card order the web reveal uses. Every reveal
listing snapshots its shown `choice_key`s onto `caller.ndb.ultimate_reveal_choice_keys`
- `accept ultimate <n>` is refused and the list reprinted, never resolved blind, if the
pool has changed since that snapshot (e.g. a stale listing after the character leveled
mid-read). Undiscovered cards show the authored label only, never the raw
Sword/Shield/Crown word.

**Deferred certain death.** Soulfray's `character_loss` consequence under Audere no
longer kills synchronously - see the "Soulfray" note below, `docs/systems/INDEX.md`'s
Vitals section, `docs/architecture/runtime-modifiers-audere.md`'s "Certain Death
Deferral" section, and ADR-4098.

### Manifesting a bound entity (#4118)

A technique can bring a bound entity into a fight: a worshipped being's avatar or the
character's own companion. See `docs/adr/adr-4118-a-manifested-entity-is-per-character-data-chosen-from-an-authored-list.md`.
Ordinary techniques and ultimates use the same mechanism: a low-tier option on an ordinary
technique is a limited form, a high-tier option on an ultimate is the full arrival.

| Piece | Status | What it is |
|-------|--------|------------|
| `TechniqueManifestOption` (`models/manifestation.py`) | [BUILT & WIRED] | Authored per-technique row: `technique`, then exactly one of `being` (`WorshippedBeing`) or `archetype` (`CompanionArchetype`) (check constraint `manifest_option_exactly_one_entity`; unique constraints `unique_manifest_option_being` and `unique_manifest_option_archetype`), plus `tier` (`OpponentTier`, default MOOK; a being's arrival size, ignored for an archetype) and `threat_pool` (nullable `ThreatPool`, #4076: what a being does each round on the caster's side; without one it arrives and never acts; ignored for an archetype). A technique with at least one option is a manifesting technique. Authored in the Technique admin through `TechniqueManifestOptionInline`. |
| `CharacterManifestation` (`models/manifestation.py`) | [BUILT & WIRED] | Per-character choice: `character` (`CharacterSheet`), `technique`, `option`, nullable `companion` (for an archetype option, the character's own `Companion`). Unique per (character, technique). Keyed by (character, technique) rather than hung on `CharacterTechnique` because an ultimate has no `CharacterTechnique` row. Set by GM or staff in the admin (`CharacterManifestationAdmin`). |
| `CharacterManifestation.bond_is_active()` | [BUILT & WIRED] | A being option holds while `active_patronage_for(character)` includes that being. An archetype option holds while the companion is the character's own, matches the archetype, and has no `released_at`. |
| `CharacterManifestation.clean()` | [BUILT & WIRED] | The option must belong to the technique; a being option takes no companion; an archetype option needs one; the bond must be active. |
| `manifest_bound_entity(participant, technique)` (`services/effect_handlers.py`) | [BUILT & WIRED] | Called from `CombatTechniqueResolver` (`world/combat/services/`) after conditions apply, on a successful, unbounced cast only (check `success_level >= 1`; a failed roll or a ward bounce manifests nothing). Returns the new ally `CombatOpponent` or None. |

`manifest_bound_entity` returns None (manifests nothing) when the caster is no longer
ACTIVE in the fight or has no location, has no `CharacterManifestation` for the technique
(the row's option must belong to that technique), the bond has lapsed, a being has no avatar
sheet, a companion has no body (`objectdb`) or is Savaged (`companion_is_savaged`, shared
with `CompanionFitToFightPrerequisite`), the body is still not in the caster's room after
the move below, a being's avatar still fights undefeated in a different encounter that is
not completed, or that entity already has a row in this encounter (one row per objectdb per
encounter, so a defeated avatar is not re-added). The body arrives: a being's avatar or a
companion's body is first moved into the caster's room with `move_to` (`add_opponent`
refuses a position in another room) and the location is read back, since a move can be
vetoed. A being then goes through `add_opponent` with the option's `tier` and
`threat_pool`, `existing_objectdb` and the caster's position, and the row is marked `allegiance=ALLY`,
`summoned_by=caster`. An archetype goes through `materialize_companion_as_combat_opponent`
(`world/companions/services.py`, unchanged). A being option whose tier has no
`OpponentTierTemplate` row makes `add_opponent` raise from `compute_opponent_stat_block`.
That is deliberate, not guarded: the raise rolls back the whole `resolve_round` for every
participant until staff add the row, and the avatar's move into the caster's room may then
show in memory while the database has it elsewhere. The `manifest-tier-templates`
dashboard probe flags it.

**An ultimate never fails (#4076).** `CombatTechniqueResolver._roll_check` passes the roll
through `_floor_ultimate_at_success`: when the technique `is_ultimate` and the roll graded
below success, the result's outcome becomes the lowest authored `CheckOutcome` with
`success_level >= 1`. Reaching Audere is the earned moment; the roll only grades how
spectacular the success is, so effects gated on success (manifestation) always fire.

**Required-content probes (`web/admin/tuning/required_content.py`, all REQUIRED tier):**
`manifest-being-avatars` (a being option whose being has no `avatar_sheet`: nobody arrives),
`manifest-archetype-abilities` (an archetype option whose archetype has no
`CompanionAbility` rows: it arrives and never acts), `manifest-being-threat-pools` (a being
option with no `threat_pool`: it arrives and never acts), `manifest-tier-templates` (a being
option's tier with no `OpponentTierTemplate`: the cast raises and the whole round rolls back).

**Coexists with the flow-payload `summon_ally`.** The threat-pool summon
(`summon_ally` / `summon_ally_on_condition`, see the effect-handler table below) is
untouched: it is reactive-flow driven and picks a `ThreatPool` entry, where manifestation is
a per-character choice among authored options.

**Not built:**
- [ABSENT] A character-creation picker for the manifested entity: choices are set in the
  admin by GM or staff.
- [ABSENT] Manifestation outside combat: the hook is in the combat resolver only.
- [ABSENT] A persistent bonded Companion created by a cast: a being arrives as a fight
  opponent row over its existing avatar character, and an archetype option materializes a
  Companion the character already owns.

### Dramatic Moment Tagging (#545 / #1139)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DramaticMomentType` | Staff-authored lookup inheriting `RenownAwardConfig`. Describes a taggable scene moment category. | `label`, `description`, `resonance` FK, `resonance_amount` (default 15), `per_scene_cap` (default 1), plus inherited `magnitude`/`risk`/`reach`/`archetypes` |
| `DramaticMomentTag` | Per-event record of a staff tag on a character in a scene | `moment_type` FK, `character_sheet` FK, `scene` FK (nullable/SET_NULL), `tagged_by` FK AccountDB (PROTECT), `interaction` FK (nullable/SET_NULL, `db_constraint=False` — partitioned table), `interaction_timestamp` (denormalized), `tagged_at` |

**Admin:** `DramaticMomentTypeAdmin` — full CRUD (staff author the catalog); `DramaticMomentTagAdmin` — read-only for provenance audit.

**Context fields on scenes serializers:** `SceneDetailSerializer.viewer_can_gm` (bool — True when the requesting user is the scene's GM, owner, or staff; controls GM control visibility); `InteractionSerializer.dramatic_moment_tags` (list — tags anchored to the pose; drives the interaction badge); `SceneParticipationSerializer.dramatic_moment_count` (int — per-participant tally in the scene).

### GM Prompt Queue: narration of mechanical events (#4101; `world/gm`)

Big mechanical moments (an Audere surge, an Audere Majora Crossing, a miracle, a death, a
resolved stake) used to fire with generic authored text and the GM running the scene got no
signal. `DramaticMomentSuggestion` (the #2183 confirm-only inbox below) is renamed
`GMPrompt`, moved to `world/gm/models.py`, and gains a `kind` (`GMPromptKind`, in
`world/gm/constants.py`): the original `dramatic_moment` confirm kind, plus six
**narration** kinds a GM narrates then closes: `audere_surge`, `audere_ultimate`,
`crossing`, `miracle`, `death`, `stake_outcome`. Full behavioral detail (release-on-close,
the frozen subject persona, the telnet/web surfaces): `docs/systems/scenes.md`'s "GM
narration of mechanical events" section; decision record: ADR-4101.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `GMPrompt` (`world/gm/models.py`) | One entry in a GM's queue; the `dramatic_moment` kind is the original #2183 suggestion (unchanged shape), the other six are narrated then closed | `kind` (`GMPromptKind`), `event_group` (UUID, shared by every GM's own copy of one event), `addressed_to` FK AccountDB (nullable, null only for `dramatic_moment`, which keeps the scene-GM/owner/staff gate instead), `moment_type`/`character_sheet`/`scene`/`interaction`/`interaction_timestamp`/`technique`/`success_level`/`status`/`resolved_by`/`confirmed_tag` (unchanged from `DramaticMomentSuggestion`; `status` is now `GMPromptStatus`: PENDING/CONFIRMED/DISMISSED/NARRATED), `subject_persona` FK Persona (nullable, SET_NULL; the subject's FACE frozen at routing time, #4101 fix round 3 ruling R9-3), `room_text`/`private_text` (the resolved authored or prepared defaults), `prepared_for_character` (bool), `stake_outcome` FK (nullable) |
| `GMPromptFilter` (`world/gm/models.py`) | A GM's per-account, per-`GMPromptGroup` opt-out switch; no row = prompted | `account` FK, `group` (`GMPromptGroup`: dramatic_moment/audere/miracle/death/stake_outcome), `enabled` |
| `GMPromptNarration` (`world/gm/models.py`) | Side row linking one narration `Interaction` back to the `GMPrompt` it narrates (ADR-0010 FK direction; ADR-0293's `InteractionReceiver` precedent for the composite-timestamp shape) | `prompt` FK (CASCADE), `interaction` FK (CASCADE, `db_constraint=False`, the partitioned `arxii_interaction` table), `interaction_timestamp` (denormalized from `interaction.timestamp`, required). Unique on `interaction` only, never `prompt`: a GM may narrate one prompt any number of times |

**Routing (`world.gm.prompt_services.route_narratable_event`):** six event sources resolve
their own text, build a `NarratableEvent` (kind, scene, character sheet, room/private text,
whether the text came from the subject's own prepared text, optional technique/stake
outcome), and call `route_narratable_event`. It asks `recipients_excluding_subject` which
GMs opted in (per-group `GMPromptFilter`, minus the event's own subject's currently-playing
account); with any recipient it creates one PENDING `GMPrompt` per GM, sharing one
`event_group`, and returns them; with none it returns `[]` and the **caller** delivers the
text unprompted, unchanged from before #4101.

| Kind | Event source | Text resolved by |
|------|--------------|-------------------|
| `audere_surge` | `world.magic.audere._announce_surge` | `resolve_surge_text` (character's `CharacterSurgeText`, then `AudereThreshold.surge_manifestation_text`) |
| `crossing` | `world.magic.audere_majora._route_crossing` | `resolve_crossing_text` (character's `CharacterCrossingText`, then the patron `AudereMajoraFaithVariant`, then `AudereMajoraThreshold`); the vision still logs (`narrate_privately`) even scene-less |
| `audere_ultimate` | `world.magic.services.ultimates._route_ultimate_chosen` | no authored default line exists for an ultimate pick; this kind is GM-signal-only, `_deliver()` is a no-op |
| `miracle` | `world.worship.services._route_miracle` | `Miracle.narrative_text` |
| `death` | `world.vitals.services._route_death` | deaths carry no authored room line today; `_deliver()` is a no-op, kept for shape consistency should one ever be authored |
| `stake_outcome` | `world.stories.services.stake_resolution._route_stake_outcome` | `StakeResolution.narrative_summary`, scene-less, routed to the story's Lead GM only (see `docs/systems/stakes.md`) |

**Prepared text (`models/prepared_text.py`, `services/prepared_text.py`):** `CharacterCrossingText`
/ `CharacterSurgeText`: one character's own authored line for their next Crossing or surge,
written by staff or that character's table GM (play-adjacent: lives and dies with the
character sheet, carries no natural key, never exported through the content pipeline, not
catalog content). `resolve_crossing_text`/`resolve_surge_text` layer field by field: the
character's own prepared text, then (Crossing only) the patron variant, then the tier
default. A Crossing's prepared text is consumed on use (`consume_prepared_crossing_text`,
the `crossing` OneToOne back-reference); a surge's is reusable. `prepared_for_character` on
the resulting `GMPrompt` flags when the vision specifically (not just the room line or deed
title) came from the character's own prepared text: the composer's "Prepared for this
character" badge.

**Web:** `GET /api/gm/prompts/?scene=<id>` (`GMPromptViewSet`, `world/gm/views.py`) lists
every open prompt (PENDING or NARRATED) the viewer may act on, dramatic moments plus
narration kinds addressed to them; `POST .../{id}/confirm/` / `.../dismiss/` / `.../narrate/`
dispatch by kind. `GET`/`POST /api/gm/prompt-filters/` (`GMPromptFilterViewSet`) is the
five-row per-group opt-out surface. **Telnet:** `gm prompts` / `gm prompt
send|dismiss|done <id>` (`commands/gm_ops.py`) plus `emit/prompt <id> <text>` /
`pemit/prompt <id> <name>[,<name>...]=<text>` (`commands/evennia_overrides/communication.py`),
see `src/commands/CLAUDE.md`. **Frontend:** `GMPromptQueue`/`GMPromptRow`/
`NarrationComposer` (`frontend/src/scenes/components/`) cover both the `dramatic_moment` kind
and the six narration kinds in one queue UI.

**Deferred (spec scope, not a gap in this build):** a new mechanical event wanting GM
narration needs a new `GMPromptKind` value plus a `PROMPT_GROUP_FOR_KIND` entry and an
event-source call site; the queue, filter, and composer surfaces are already generic over
`kind` and need no further change.

#### Dramatic Moment Suggestion — the technique-entrance recognition bridge (#2183)

A **Technique Entrance** (see below) that clears an authored success-level threshold does not
auto-tag; it creates a PENDING `GMPrompt` of kind `dramatic_moment` (see "GM Prompt Queue"
above; was `DramaticMomentSuggestion`) a GM later confirms (minting a real
`DramaticMomentTag`, with the usual resonance grant + renown award) or dismisses. See
ADR-0113 for why recognition stays a human-adjudicated nudge rather than a mechanical
auto-grant. This kind's shape is unchanged by the #4101 generalization: no `addressed_to`,
no narration, no `route_narratable_event` call; it keeps its own `maybe_suggest_dramatic_moments`
seam below.

**Knobs on `DramaticMomentType`:**
- `suggest_on_technique_entrance` (bool, default False) — opts this moment type into the
  technique-entrance bridge at all.
- `suggestion_min_success_level` (`PositiveSmallIntegerField`) — the cast success level that
  must be cleared (`>=`) for a suggestion to fire.

**Services (`services/gain.py`):**
- `maybe_suggest_dramatic_moments(*, character_sheet, scene, success_level, interaction=None) -> list[GMPrompt]`
  — scans `DramaticMomentType` rows flagged `suggest_on_technique_entrance` whose
  `suggestion_min_success_level <= success_level`; for each, skips if the character hasn't
  claimed the type's resonance, or if `per_scene_cap` real tags are already spent for this
  `(moment_type, scene)`; otherwise `get_or_create`s a PENDING suggestion (idempotent — a
  second qualifying cast in the same scene does not duplicate it). No-ops (`[]`) when
  `scene` is `None` — a suggestion is scene-scoped, same as the tag cap it mirrors.
- `resolve_dramatic_moment_suggestion(suggestion, *, resolver, confirm) -> GMPrompt`
  — confirm mints a real `DramaticMomentTag` via `create_dramatic_moment_tag` (full
  resonance-grant + renown-award side effects); dismiss just closes the suggestion out.
  Raises `DramaticMomentSuggestionAlreadyResolved` on a non-PENDING suggestion; `confirm`'s
  `EndorsementValidationError`/`DramaticMomentCapExceeded` propagate uncaught.

**Actions (`actions/definitions/dramatic_moments.py`):** `ConfirmDramaticMomentSuggestionAction`
(key `"confirm_dramatic_moment_suggestion"`) / `DismissDramaticMomentSuggestionAction`
(key `"dismiss_dramatic_moment_suggestion"`) — both **account-authorized** (mirrors
`actions/definitions/events.py`'s host-lifecycle actions: `actor=None`, `account=<resolver>`,
since a web GM confirming/dismissing may have no puppeted character). The GM gate
(`_account_can_gm_scene`) mirrors `IsSceneGMOrOwnerOrStaff` / `SceneDetailSerializer
.get_viewer_can_gm`: staff, or `scene.is_gm(account)`, or `scene.is_owner(account)`. The same
module's `DismissGMPromptAction` (key `"dismiss_gm_prompt"`) closes a narration-kind prompt
instead, addressed-GM-or-staff gated.

**Web:** the dedicated `DramaticMomentSuggestionViewSet` is retired: confirm/dismiss/narrate
now ride the one GM prompt queue, `GMPromptViewSet` (see "GM Prompt Queue" above).

**Telnet:** `CmdMoment` (`commands/dramatic_moments.py`, key `"moment"`) — `moment
suggestions` (PENDING suggestions for the active scene here), `moment confirm <id>`,
`moment dismiss <id>`. Account-authorized like the web surface (`account=self.caller.account`).

**Frontend:** the per-pose `DramaticMomentSuggestionChip` embed is retired with the
viewset; the `GMPromptQueue` UI covers this kind alongside the six narration kinds.

**Seed content:** `ensure_dramatic_entrance_content()` (`world/magic/factories.py`) seeds the
"Grand Entrance" `DramaticMomentType` with `suggest_on_technique_entrance=True` and
`suggestion_min_success_level=3` — framework-proving content so the bridge has something real
to surface, not only under test factories.

It carries **no resonance of its own** (#2967). It used to mint a "Fervor" Resonance by name
and pin the type to it, and because `create_dramatic_moment_tag` refused any character who
had not *claimed* that resonance, the game's only authored moment type was un-awardable to
every character alive. The resonance is resolved at tag time now — from the entrance
technique's gift thread, then the GM's explicit pick, then the character's anima-ritual
resonance (`_resolve_moment_resonance`, `services/gain.py`) — so the type's own `resonance`
is a last-resort override and stays null.

### Technique Entrance (#2183)

A **Technique Entrance** is a "make an entrance" whose check IS a technique cast — the
technique's own success level substitutes for the entrance's social check entirely (one
roll, not two; see ADR-0113). Reached via telnet `enter <technique>[=<target>]`
(`commands/social/entrance_flourish.py`'s `CmdEnter`, dispatching `EntranceAction().run()`
directly) or the web `EntranceTechniqueAttachment` popover
(`frontend/src/scenes/components/`) attached to the entry pose in `CommandInput`, which
POSTs to `/api/action-requests/` — `SceneActionRequestViewSet._create_technique_entrance`
(`world/scenes/action_views.py`) dispatches the same `EntranceAction().run()` seam rather
than the generic technique-as-`ActionEnhancement` consent path the rest of that endpoint
uses (#2183 Task 8 fold-in — that generic path has no `ActionEnhancement` row for
`"entrance"` and would always 400).

**Dispatch: `EntranceAction._execute_technique_entrance`** (`actions/definitions/social.py`)
mirrors `CastTechniqueAction.execute` (scene/persona/technique/target resolution, soulfray
`PendingCast` gating) but routes the outcome through a **deferral matrix** instead of a flat
success/failure, since the entrance's real success level isn't always known at declaration
time:

| Branch | What happens |
|--------|--------------|
| Resolved inline (self/room/no-target, or a benign no-consent cast at another PC) | Full hooks fire immediately once the success level clears 0: entry-flourish offer, disposition delta (non-hostile only), the `Dramatic Moment Suggestion` check. A **benign-intervention combat join** (`seat_caster_for_benign_intervention`, #2226/ADR-0119) fires for *any* benign cast (not just entrances) that affects an ACTIVE combatant — see the consent-routing note above. |
| Hostile cast at another PC | Seeds/feeds a combat encounter (`seed_or_feed_encounter_from_cast(..., from_entrance=True)`) — flourish only; the success level isn't known until the declared cast resolves at round resolution (see combat.md's `_maybe_suggest_entrance_dramatic_moment`). |
| PENDING (benign consent-gated, or hostile #777 risk-gated) | No hooks at declaration; `SceneActionRequest.originated_as_entrance` marks the request so `resolve_accepted_cast` fires the deferred hooks at accept-time resolution instead. |
| Soulfray gate not confirmed | Registers a `PendingCast` (mirrors `cast.py`) carrying an `"entrance": True` marker in its kwargs; `SoulfrayPendingHandler`'s `accept soulfray` re-dispatch reads the marker and re-enters through the `"entrance"` REGISTRY action (not `"cast_technique"`) so the flourish/suggestion/intervention hooks stay reachable — see `world/magic/offer_handlers.py`. |
| Already an ACTIVE participant in a feedable encounter | Clean failure — "You're already in the fight." |
| No active scene at the actor's location | The cast seam's own failure message. |

**Shared hook helper:** `run_entrance_success_hooks(actor, scene, *, success_level,
target_persona_id, technique, interaction=None) -> str | None` (`actions/definitions/social.py`)
— fires the entry-flourish offer (gated on the "Entrance" `ActionTemplate.grants_entry_flourish`,
independent of the technique's own template) and, when `success_level is not None`, the
Dramatic Moment Suggestion check (`maybe_suggest_dramatic_moments`). Shared by
`EntranceAction`'s inline/hostile branches, the accept-time deferred-hook path
(`world/scenes/cast_services.py`), and combat's round-resolution hook — one signature, three
call sites, no drift.

### Portal travel (#2222, ADR-0121)

A character who **knows** a portal-travel `Technique` and stands in a room carrying a
matching active anchor can travel instantly to any other room whose matching anchor is
reachable — no hop pacing, no `find_route()` walk. `TravelAction.execute()`
(`actions/definitions/movement.py`, key `travel_to`, #2163) tries the portal branch FIRST;
when ineligible it falls through to the pre-existing walking pathfinder byte-identical to
before this issue.

**Models** (`world/magic/models/portals.py`):

| Model | Purpose |
|-------|---------|
| `PortalAnchorKind` | Staff-authored catalog of anchor media (e.g. "Mirror"). `name` (unique), `description`, `arrival_verb`/`departure_verb` (default "steps out of"/"steps into") — narrate travel through anchors of this kind. |
| `PortalAnchor` | A concrete anchor installed in one room. FK `room_profile` (`evennia_extensions.RoomProfile`, CASCADE), FK `kind` (`PortalAnchorKind`, PROTECT), `name` (descriptive, e.g. "a tall silvered mirror"), `is_network_open` (bool, default True), FK `installed_by` (`scenes.Persona`, SET_NULL), `installed_at`, `dissolved_at` (null = active; soft-delete, mirrors `RoomFeatureInstance.dissolved_at`), nullable-unique `fixture_key` (#2451 — set when installed from the staff world-builder canvas; NULL for player-installed/test anchors; the grid-bundle export/import key, same pattern as `RoomProfile.fixture_key`). `.objects.active()` excludes dissolved rows. Partial `UniqueConstraint(room_profile, kind)` WHERE `dissolved_at IS NULL` — one active anchor per kind per room; dissolving frees the room for a fresh install of the same kind. |
| `Technique.travel_anchor_kind` | Nullable FK → `PortalAnchorKind` (PROTECT). Set = this technique is a portal-travel technique through this anchor medium; a character "knows" a travel kind by knowing any `CharacterTechnique` whose `Technique.travel_anchor_kind` matches. |

Migration `0101_portalanchorkind_technique_travel_anchor_kind_and_more.py` is the sole
migration for this feature.

**Eligibility chain** (never consults `RoomProfile.is_public` — network reachability is
governed entirely by the anchor's own openness/standing gate, #2222 Decision 5b):

1. The traveler knows a `Technique` with `travel_anchor_kind` set (any one technique per
   kind is enough — `_known_travel_technique_map`).
2. The traveler's **current** room carries an active `PortalAnchor` of that same kind.
3. The **destination** room carries an active `PortalAnchor` of the same kind.
4. That destination anchor is **open-or-standing**: `is_network_open=True`, OR the
   traveler holds owner/tenant standing at the destination room
   (`world.locations.services.is_owner`/`is_tenant`).

**Services** (`world/magic/services/portal_travel.py`):

```python
def travel_anchor_kinds_for(character: ObjectDB) -> list[PortalAnchorKind]: ...
    # kinds of the character's known travel-mode techniques

def portal_destinations(character: ObjectDB) -> list[PortalDestination]: ...
    # every active, reachable destination anchor (kinds narrowed to known techniques;
    # excludes the current room; locked anchors visible only with owner/tenant standing);
    # ordered by destination room name

def portal_route(character: ObjectDB, destination_room: ObjectDB) -> PortalRoute | None: ...
    # the eligible (technique, origin anchor, destination anchor) triple for one specific
    # destination, or None

def perform_portal_travel(character: ObjectDB, route: PortalRoute) -> None: ...
    # commits: anima debit (deduct_anima), departure broadcast, move_object(quiet=True),
    # arrival broadcast, room-state push

def install_portal_anchor(persona: Persona, room: ObjectDB, kind: PortalAnchorKind, name: str) -> PortalAnchor: ...
    # owner/tenant standing -> no existing active anchor of this kind here -> flat copper
    # debit (settings.PORTAL_ANCHOR_INSTALL_COST) from the persona's purse -> create

def install_portal_anchor_as_staff(room: ObjectDB, kind: PortalAnchorKind, name: str, *, fixture_key: str | None = None) -> PortalAnchor: ...
    # staff-authoring counterpart (#2451): no owner/tenant standing check, no currency
    # cost — still enforces PortalAnchorKindAlreadyInstalled. Called from the staff
    # world-builder canvas via staff_place_portal_anchor.

def dissolve_portal_anchor(persona: Persona, anchor: PortalAnchor) -> None: ...
    # owner-gated soft-delete (dissolved_at=now); no refund
```

`PortalRoute`/`PortalDestination` are frozen dataclasses in
`world/magic/types/portal_travel.py`. `perform_portal_travel`'s anima debit goes through
`world.magic.services.anima.deduct_anima` (the same standalone primitive `use_technique`
uses in the scene-cast pipeline — a no-op for `anima_cost <= 0`, which every seeded travel
technique is today); movement reuses `flows.service_functions.movement.move_object` plus the
`SceneDataManager` state-handle/`send_room_state` idiom `HomeAction` uses. Both departure and
arrival broadcasts are plain third-person text (not `$You()`/actor-stance), so every viewer —
including the traveler — sees the identical line.

`install_portal_anchor`'s **install cost** is a flat, staff-tunable setting:
`PORTAL_ANCHOR_INSTALL_COST = env.int("PORTAL_ANCHOR_INSTALL_COST", default=5000)`
(`src/server/conf/settings.py`) — copper, debited from the installer's purse via
`world.currency.services.transfer` (the same purse-debit primitive
`world.projects.services.donate_to_project` uses). The balance is checked before debiting
(never take the installer's money for an install that would be rejected anyway); a
`transfer()` `ValidationError` (the row-locked backstop against a concurrent debit racing the
pre-check) is caught and re-raised as `PortalAnchorFundsInsufficient`.

Exceptions (`world/magic/exceptions.py`): `PortalAnchorStandingRequired`,
`PortalAnchorKindAlreadyInstalled`, `PortalAnchorFundsInsufficient`,
`PortalAnchorDissolveNotAllowed` — each carries `user_message` for safe action-result/HTTP
surfacing.

**Actions & telnet** (`actions/definitions/portals.py`, both REGISTRY, `target_type=SELF`,
`category="magic"`):

- `InstallPortalAnchorAction` (key `portal_anchor_install`) — installs an anchor of a given
  `kind` (kwarg, resolved from an int pk, a `PortalAnchorKind` instance, or a name string) in
  the actor's current room.
- `DissolvePortalAnchorAction` (key `portal_anchor_dissolve`) — dissolves an `anchor` kwarg
  (pre-resolved instance, int pk, or omitted to auto-resolve the room's sole active anchor;
  an explicit id that fails to resolve fails loud rather than silently falling through to
  auto-resolution, which could dissolve the wrong anchor). A room with multiple active
  anchors and no explicit `anchor` fails with a disambiguation message.

`anchors_in_room(location)` (module helper) returns active anchors in a room, shared by
`DissolvePortalAnchorAction` and the telnet command (mirrors `sanctum_in_room`).

Telnet: `CmdPortalAnchor` (`commands/portals.py`, key `portal`) — `portal/install
<kind>=<name>` and `portal/dissolve [<kind>]`, switch-routed (mirrors `CmdRoom`'s manual
switch dispatch). Resolves kind/anchor from text before calling `.run()` directly — no
business logic in the command.

`TravelAction`'s portal branch (`_try_portal_travel`, a `@staticmethod` on `TravelAction`)
calls `portal_route` then `perform_portal_travel`; shared by telnet `CmdTravel` and the web
"Go there" buttons (both dispatch `travel_to` unchanged — only the eligibility check inside
`execute()` is new).

**Staff authoring from the world-builder canvas (#2451, epic #2436 slice 4):**
`StaffPlacePortalAnchorAction`/`StaffRemovePortalAnchorAction` (keys
`staff_place_portal_anchor`/`staff_remove_portal_anchor`,
`src/actions/definitions/world_builder.py`, `category="world_builder"`,
`StaffOnlyPrerequisite`-gated) call `install_portal_anchor_as_staff`/set
`dissolved_at` directly, so staff can place and dissolve anchors from the canvas
without owner/tenant standing or the currency cost. `PortalAnchor.fixture_key`
makes anchors exportable in the grid bundle's `portal_anchors` sidecar section
(keyed by `fixture_key`, referencing the room by its `fixture_key` and the kind by
`PortalAnchorKind.name`). **Ratified behavior:** reimporting an unchanged bundle
always converges an anchor back to active (`dissolved_at=None`) — bundles are
authoritative, matching the room/exit reimport precedent. If a GM dissolves an
anchor in play, staff must re-export before reloading grid content, or the reload
silently reactivates it; this is intentional, not a bug.

**API** (`world/locations/views.py` + `urls.py` + `serializers.py`, NOT under
`/api/magic/` — it lives alongside the sibling `ComfortViewSet` in `world.locations`, the app
that owns location-scoped, character-personal read APIs):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/locations/portal-destinations/?character_id=<id>` | GET | `PortalDestinationsViewSet` (list-only, paginated, `IsAuthenticated`) — every anchor `character_id` (must be an owned character) could portal-travel to right now. Rides `portal_destinations()` unmodified — no extra filtering at the API layer. Fields: `anchor_id`, `room_id`, `room_name`, `kind_name`, `anchor_name`. |

Discovery only — travel itself still dispatches the existing `travel_to` action.

**Frontend:** `PortalsBlock` (`frontend/src/game/components/room-panel/PortalsBlock.tsx`) —
mounted in `RoomPanel`; queries `usePortalDestinationsQuery` (`src/locations/queries.ts`,
disabled without an active character), renders nothing when the destination list is empty,
otherwise a compact kind/anchor/room list with a "Travel" button that dispatches the same
`travel_to` registry action the #2163 Go-there buttons use (`{ target: roomId }`).

**Seed content** (`world/seeds/game_content/magic.py`,
`ensure_portal_travel_content()`, called from `seed_magic_dev()`): starter Mirror
`PortalAnchor` rows on the content-authored "Mirror" `PortalAnchorKind`, placed in the
canonical fallback room plus, defensively, any room already present matching
`_MIRROR_ANCHOR_ROOM_SPECS` ("The Hallowed Threshold (Low)", "The Resonant Sanctum
(Aligned)") — a no-op skip when absent, not a lookup failure. Those two rooms are no
longer seeded by `seed_magic_dev()` itself (#2973 stripped
`_seed_resonance_environment_rooms()`, the cascade-room stand-in); they only exist when
the lore repo's #2451 grid bundle authors rooms under the same `db_key`s, in which case
the anchors attach to them. Idempotent throughout (`get_or_create`); skips entirely when
the anchor kind isn't authored.

It seeds **no gift, technique or resonance** (#2967). It used to invent a "Reflection"
Resonance, a MINOR `Gift` "Mirrorwalking" carrying it, a "Mirrorwalk" `Technique` and an XP
`GiftUnlock` — ruled a placeholder on 2026-08-04 and obliterated. Mirrorwalking was also the
only `Gift` in the catalog with a non-empty resonance set, so it was the only one the weave
gate could refuse outright.

**Portal travel consequently has no content today.** The machinery is complete; the gate is
knowing a technique whose `travel_anchor_kind` is set, and no such technique is authored in
the lore repo. That is the honest state — the seeded placeholder made a contentless feature
look shipped.

### Other

| Model | Purpose |
|-------|---------|
| `AnimaRitualPerformance` | Historical record of ritual performances |
| `Reincarnation` | Tracks character reincarnation events |

### Technique Treatment (#2668) [BUILT & WIRED]

A technique can perform a **bounded mend** — routing through `perform_treatment`'s
double-bounded machinery (per-healer-once-per-wound + never-to-full fraction,
ADR-0156) rather than creating a new healing path. This makes the Lifeward healer
fantasy castable magic, not just the mundane `treat_condition` scene action.

**Model:** `TechniqueTreatment` (`models/techniques.py`) — payload row FK linking a
`Technique` to a `conditions.TreatmentTemplate`. Fields: `target_kind` (default
ALLY), `minimum_success_level` (default 1), `mend_cap_fraction` (#4600, below).
UniqueConstraint on `(technique, treatment_template)`. Mirrors the
`TechniqueAppliedCondition` / `TechniqueRemovedCondition` pattern.

**Healing depends on the technique (#4600, ADR-0156 addendum) [BUILT & WIRED]:**
`TechniqueTreatment.mend_cap_fraction` (`DecimalField(3,2)`, default `0.75`) is how far this
technique may heal a wound, as a share of the damage the wound did. A `CheckConstraint`
(`technique_treatment_mend_cap_fraction_in_range`) keeps it above 0 and below 1, and the
field's validators (the shared `MEND_CAP_FRACTION_VALIDATORS`, `models/techniques.py`) hold it
between `0.01` and `NEVER_TO_FULL_FRACTION`, so the admin names the field and the limit. Staff
set it in the Technique admin's treatment inline; the
builder takes it on `TreatmentSpec` / the builder API's treatment rows (refused above the
ceiling there too); the draft workbench carries it on `TechniqueDraftTreatment` and
`add_draft_treatment(mend_cap_fraction=)`. `VowAddedEffectTreatment` carries the same field
and rule. `apply_technique_treatments` reads each row's fraction and threads it through
`_perform_treatment_for_target` and `perform_treatment(mend_cap_fraction=)` into
`mend_wound(cap_fraction=)`. Because each mend reads the wound's running total, healing on one
wound never passes the highest fraction any healer used on it. The fraction lives on the
technique row, not on `TreatmentTemplate`, because the template is a shared, named recipe
that mundane first aid uses too. The scene `treat` path passes `FIRST_AID_MEND_FRACTION` (0.50)
only for a mundane treatment (`conditions.services.is_magical_treatment` False); a magical
template offered through `treat` keeps the 0.75 ceiling.

**Service:** `apply_technique_treatments` (`services/condition_application.py`) —
sibling to `apply_technique_conditions` / `remove_technique_conditions`. For each
row passing the SL gate, finds the matching `ConditionInstance` (or
`PendingAlteration`) on each resolved target via `_condition_matches_treatment`,
resolves bond threads when `requires_bond`, and calls `perform_treatment` with
`skip_engagement_gate=True`. Treatment exceptions are caught — a treatment no-op
does not abort the cast.

**Cast pipeline ordering:** `apply_technique_treatments` fires AFTER
`apply_technique_conditions` + `apply_signature_bonus_conditions` and BEFORE
`remove_technique_conditions`. This ordering is critical: the treatment must fire
while the wound condition is still present. A technique author who wants "cleanse
a wound" (remove suffering + mend HP) adds both a `TechniqueRemovedCondition` and
a `TechniqueTreatment` to the same technique — the treatment mends HP first, then
the removal strips the condition.

**Engagement gate bypass:** `perform_treatment` gains `skip_engagement_gate=False`
(default). The technique-cast path passes `True` — magical treatment works in
combat. The mundane `treat_condition` scene action is unchanged (engagement-gated).
All other bounds (per-healer-once, never-to-full fraction, costs, check roll,
`TreatmentAttempt` record) are preserved. See ADR-0157.

**Budget builder:** `TreatmentSpec` (`types/technique_builder.py`) priced at flat
`payload_base_cost` (same as removed conditions). `build_technique` creates
`TechniqueTreatment` rows (with each spec's `mend_cap_fraction`). Draft workbench:
`TechniqueDraftTreatment` + `add_draft_treatment` / `remove_draft_treatment` /
`draft_to_design` conversion. The web builder form (`TechniqueBuilderForm.tsx`) has no
treatment editor yet; treatments are authored in the Technique admin.

**Power leg (#3391) [BUILT & WIRED]:** `TreatmentTemplate.mend_intensity_multiplier`
(`DecimalField`, default 0) scales the mend amount by the caster's effective intensity, so a
stronger cast heals more. `apply_technique_treatments` gained a required `eff_intensity: int`
kwarg, forwarded to `perform_treatment` as `power_intensity` (default 0 for the mundane
`treat_condition` caller, which has no power concept). Inside `perform_treatment`, once
`_map_outcome_to_mend` returns a nonzero base (a failed/unmended-tier outcome still mends 0
regardless of power), `mend_amount += int(treatment.mend_intensity_multiplier *
power_intensity)` — strictly before `mend_wound()`, whose never-to-full fraction cap and
`max_health` clamp (ADR-0156) remain the final, untouched word on what actually lands. At the
field's default 0 (every pre-#3391 row), the added term is exactly 0 — byte-identical to
before. Dispel's sibling power leg is `TechniqueRemovedCondition.cure_power_multiplier` — see
"Dispel / Cleanse" in `world/magic/CLAUDE.md`.

### Technique morale effect (#4619, ADR-4619-A) [BUILT & WIRED]

A technique can shake the morale of the enemies it lands on, by its own authored amount.

**Model:** `TechniqueMoraleEffect` (`models/techniques.py`) is a one-to-one payload row on
`Technique` (`related_name="morale_effect"`, read through `Technique.cached_morale_effect`).
Its columns live on `AbstractMoraleEffect`, shared with the draft copy
`TechniqueDraftMoraleEffect`: `minimum_success_level`, `base_morale`,
`morale_intensity_multiplier` and `morale_per_extra_sl`. `clean()` refuses a row whose three
amounts are all zero. There is no prose on the row.

**Formula:** `AbstractMoraleEffect.compute_morale(effective_power, success_level)` scales the
way a damage profile does (`_scale_by_power_and_sl`): the base, plus the power multiplier
times the cast's effective power (rounded down), plus the per-extra-level step for each
success level above the minimum. A cast below `minimum_success_level` shakes nobody.

**Who is shaken:** enemies only. `CombatTechniqueResolver._apply_morale` runs after damage
and conditions, reads the cast's existing check result (no new roll), and skips an opponent
that is not active, is not an `ENEMY` by `CombatOpponent.allegiance`, or is charmed
(effective allegiance `ALLY_OF_CASTER`). A mindless tier takes the `SpectacleConfig`
`mindless_percent` share (`combat.morale.mindless_share`; an amount of 0 stays 0, a positive
amount never rounds to 0). A ward bounce returns before this step, so a bounced cast shakes
nobody. The resolution carries the result as `CombatTechniqueResolution.morale_shifts`
(one `SpectacleShift` per opponent whose morale state changed).

**Enemy-only targeting:** a morale row makes a technique hostile (`is_technique_hostile`),
counts as specified (`technique_is_underspecified`), and derives an ENEMY relationship
(`derive_target_relationship`, `technique_relationship_is_ambiguous`), so a morale-only
technique is aimed at an opponent. The effect sentence adds "Shakes morale."

**Authoring:** the Technique admin has a `TechniqueMoraleEffectInline` (one row at most).
The builder takes `MoraleEffectSpec` on `TechniqueDesignInput.morale_effect`, priced per point like
damage: `payload_base_cost + (base_morale + morale_intensity_multiplier * intensity) *
damage_unit_cost` on the "Morale effect" line (no new budget column);
`build_technique` writes the row before the payload caches are cleared. The draft workbench
carries `TechniqueDraftMoraleEffect` through `set_draft_morale_effect` /
`clear_draft_morale_effect` and `draft_to_design`.

**Power valuation:** `_morale_valuation` (`services/technique_power_eval.py`) values the row
as an ESTIMATE: the expected morale over the matchup bands, capped at one break (the distance
from the default 70 to the break threshold 25, 45 points), as that share of one opponent's
round of reference incoming damage. It is a control-kind payload valuation. Both this
formula and the builder price (per point, like damage) are tuning values.

**Cache:** writers of the row call `invalidate_technique_payload_caches`; the prefetch is in
`technique_payload_prefetches` and `_PAYLOAD_CACHE_ATTRS`.

**Known gaps:** no narrated line for a technique's morale shift (players see only the
opponent's state chip); no vow added effect can carry morale.

Proven by `src/integration_tests/test_shaking_morale_journeys.py`.

### Vow added effects: the payload seams (#4581, ADR-4581-A) [BUILT & WIRED]

A covenant vow can add staff-authored payload to a technique cast (`VowAddedEffect` and its
children, see `docs/systems/covenants.md`'s "Vow added effects"). The magic side of that is
three additions to the shared payload seams plus one vocabulary change; there is no parallel
apply path.

- **`TechniqueFunction` gained `STRIKE` and `MEND`** (now 15 values). They are the function
  tags a vow row can key on for a plain attack or a plain mend. The members are choices on
  `VowAddedEffect.function`, `CovenantRoleTechniqueSpecialty.function`,
  `TechniqueFunctionTag.function` and `CompanionAbilityFunctionTag.function`, so migration
  `0281_vow_added_effects` carries choices-only `AlterField`s for the last three (with the
  `Situation.TARGET_IS_BOSS` ones on the perk situation and rung) and the OpenAPI enum
  (`frontend/src/generated/api.d.ts`, `src/schema.json`) changed.
- **`apply_technique_conditions`** gained `severity_bonus: int = 0` and
  `duration_bonus: int = 0`. The severity bonus is added to every non-team-lane row's computed
  severity; the duration bonus is added to a row's duration when it has one. A team-lane row
  ignores both (its severity is priced against the landing target and the lane is bounded).
  It already took `applied_condition_rows=` (#1582), which a vow row's children use.
  Since #4822 the caster's condition severity and duration modifiers (technique-scoped
  `ModifierTarget`s) apply to the technique's own rows in combat, scene casts and passive
  techniques. Since #4823 they arrive through a new `target_bonus: Callable[[ObjectDB],
  tuple[int, int]] | None = None` argument, which the call sites pass as
  `TechniqueConditionBonus.for_cast(sheet, technique).for_target` (`world/mechanics/effect_targets.py`),
  so an opponent scope reads who each condition lands on; it is added to the flat bonuses per
  target, and a team-lane row ignores it. `bonused_severity` / `bonused_duration` floor a negative
  bonus at 1 and leave a row with no duration without one. See `mechanics.md` "Technique effect
  scopes" and "Opponent scopes".
- **`remove_technique_conditions`** gained `removed_condition_rows: Iterable | None = None`;
  `None` reads `technique.removed_conditions` as before. Rows are anything exposing
  `condition`, `target_kind`, `minimum_success_level`, `remove_all_stacks` and
  `cure_power_multiplier`. The caster still rolls the cure check.
- **`apply_technique_treatments`** gained `treatment_rows: Iterable | None = None` (rows
  exposing `treatment_template`, `target_kind`, `minimum_success_level`; the caster stays the
  helper). It also now **skips a target with no `CharacterSheet`** (an NPC opponent) instead of
  raising `DoesNotExist` mid-round. It still raises for a sheetless caster.
- **`render_payload_clauses(*, applies, removes, damage, treatments) -> list[str]`**
  (`services/technique_effects.py`) renders the payload clauses in the order a technique
  sentence reads them, "Deals ...", "Applies ...", "Strips ...", "Treats ...". Both
  `render_technique_effect_sentence` and a vow row's plain-words summary call it, so the two
  cannot drift. `condition_payload`, `damage_payload` and `treatment_payload` lost their leading
  underscore (they are shared now); every technique sentence is byte-identical.
- **`validate_inert_removal_knobs(row)`** (`models/techniques.py`) is the removal-row knob check
  lifted out of `TechniqueRemovedCondition.clean` so `VowAddedEffectRemovedCondition` shares it.

Callers: `CombatTechniqueResolver._apply_conditions` and `_resolve_and_pose_cast` hand a vow
row's children through `world.covenants.added_effects.apply_vow_effect_payloads`, which calls
these three seams per fired row with that row's bonuses and children: every row's conditions
and treatments first, then every row's removals. Both callers call it after the technique's
own treatments and before the technique's own removals, so the cast order is: technique
conditions, signature conditions, technique treatments, vow conditions and treatments, vow
removals, technique removals. Every treatment still runs before any removal, so a removal
never strips the wound a treatment in the same cast was going to mend.

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
| Phase Step | Phase Step | `blink_dodge` (priority 30) | DAMAGE_PRE_APPLY; mutation-only; outside an NPC attack, avoids the hit and lands her on her dodge plan (else she stays); against an NPC attack it is a dodge source instead (#4676) |
| Phase Jump | Phase Jump | `move_position_on_condition` adapter | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |
| Barricade | Barricade | `create_obstacle_on_condition` adapter | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |
| Ghostform | Ghostform | intangibility category only (`grants_intangibility=True`) | `ConditionCategory`; holds no ground via `is_intangible`, protected by a severity-scaled Physical resistance row, stays targetable (#4742) |
| Earthmeld | Earthmeld | intangibility category only (1-round duration) | `ConditionCategory`; as Ghostform |
| Force Grip | Force Grip | `move_position_on_condition` adapter (ENEMY target) | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |

**Runtime destination selection (#2206 — supersedes the old placeholder-destination
follow-up note):** Phase Jump, Barricade, and Force Grip still embed
`destination_position_id=0` at seed time (`ensure_effect_palette_content()`), but that
value is now only ever a fallback — for **combat**, the player picks a real position at
declaration time. `CombatRoundAction` carries three nullable FKs to `areas.Position`:
`cast_destination` (Phase Jump / Force Grip — single point) and `cast_position_a`/
`cast_position_b` (Barricade — an endpoint pair). `resolve_cast_position_params`
(`world/combat/services/`) validates the declared position(s) against the encounter's
own battlefield room and the technique's `reach`/`reach_hops` at declaration; a foreign-room
position or a half-supplied pair is rejected outright. `position_target_shape(technique)`
(`services/targeting.py`) classifies which shape (`pair`/`single`/`none`) a technique's
effects consume, by walking its applied conditions' reactive-trigger flow steps for a
`create_obstacle_on_condition`-family (pair) or `move_position_on_condition`-family
(single) handler; this is exposed on available combat actions
(`actions/player_interface.py` → `RoundActionSerializer.position_target_shape`) so the
frontend picker knows whether to collect one point or two. See `docs/systems/INDEX.md`'s
Combat section ("Cast-position targeting") for the full declaration → resolver →
condition-handler wiring, including the shared-conditions root-cause fix
(`_stamp_cast_positions` stamps the FKs onto the `ConditionInstance` before
`CONDITION_APPLIED` fires, replacing the old post-hoc `_apply_position_params_to_instances`
helper and also fixing the non-combat live path). **Non-combat web casting still has no
position picker** — telnet's `position=`/`position_a=,position_b=` grammar (#2019,
`commands/combat.py`) is the only non-combat-web-adjacent entry point today, and that
grammar is what #2206 made actually reach validation/persistence in combat.

**Handlers and adapters** (`src/world/magic/services/effect_handlers.py`):

| Function | Kind | Purpose |
|----------|------|---------|
| `move_position(*, payload)` | direct handler | Move bearer's `ObjectDB` to a target `Position` |
| `create_obstacle(*, payload)` | direct handler | Create a blocking `Obstacle` at a target `Position` |
| `absorb_pool(*, payload)` | reactive handler (prio 10) | Drain `absorb_remaining` buffer; sets `payload.amount=0` when fully absorbed; overflow lands |
| `reflect_damage(*, payload)` | reactive handler (prio 20) | Pay `reactive_anima_cost`; resolve attacker from `payload.source.ref`; bounce via `bypass_pre_apply`; set `payload.amount=0` |
| `blink_dodge(*, payload)` | reactive handler (prio 30) | Steps aside while `DODGE_ROLL_ACTIVE`; else pay `reactive_anima_cost`, land on the dodge plan if any, set `payload.amount=0` |
| `strike_back(*, payload, instance)` | direct read at the damage seam (#4584) | Not a flow handler: `_answer_with_strike_backs` in `_emit_post_damage_events` calls it for each instance `retaliating_instances` finds on a PC bearer, right after `DAMAGE_APPLIED`. Pay `reactive_anima_cost`; deal `retaliation_damage` to the `CombatOpponent` that struck (typed, counted as the payer's threat); lay `retaliation_condition` with the ward's source as its source. Never strikes a PC |
| `summon_ally(*, payload)` | direct handler | Create a `CombatOpponent` with `allegiance=ALLY`, `summoned_by=caster` |
| `move_position_on_condition(*, payload, destination_position_id)` | CONDITION_APPLIED adapter | Thin wrapper → `move_position` |
| `create_obstacle_on_condition(*, payload, ...)` | CONDITION_APPLIED adapter | Thin wrapper → `create_obstacle` |
| `summon_ally_on_condition(*, payload, threat_pool_name, ...)` | CONDITION_APPLIED adapter | Bridges `ConditionAppliedPayload` (`.target` as bearer/caster) → `summon_ally` |
| `init_absorb_buffer(*, payload, buffer)` | CONDITION_APPLIED handler | Seeds `ConditionInstance.absorb_remaining` on Aegis Field application |

**Once-only wards and markers end after a successful fire (#4584).** An `UNTIL_USED`
condition is spent through `spend_condition_use` (`world/conditions/services.py`): `reflect_damage`,
`blink_dodge` and `strike_back` spend their ward after a successful fire (a fizzle is not a
use), `absorb_pool` ends an `UNTIL_USED` barrier after its first soak through the full
teardown (a lasting barrier keeps today's drain-to-zero behavior), and each `*_on_condition`
adapter (`move_position_on_condition`, `force_move_target_on_condition`,
`create_obstacle_on_condition`, `create_zone_hazard_on_condition`,
`raise_rampart_on_condition`, `summon_ally_on_condition`) spends its marker through
`_spend_marker` on normal exit of its effect, not on error. A condition staff give a lasting
duration is never spent by use.

**Strike-back has no seeded bundle (#4584).** There is no `ensure_strike_back_content`, no
strike-back flow, step or trigger row: the read is hard-coded at the damage seam and staff
author only the condition. The knobs are the `ConditionTemplate` fields `retaliation_damage`,
`retaliation_damage_type` and `retaliation_condition` (plus `reactive_anima_cost` and the
duration). Pairing `retaliation_condition` with a `forces_attack_on_source` condition makes
striking the ward mean facing its caster. Known gap: only a fizzle is narrated; a successful
strike-back moves the NPC's health with no line saying why.

**Reactive interceptor cost pattern** (ADR-0060):

- `ConditionTemplate.reactive_anima_cost` — anima spent per fire; can't pay → fizzle,
  attack lands.
- `ConditionTemplate.upkeep_anima_per_round` — drained each round by
  `drain_reactive_upkeep` on `COMBAT_ROUND_STARTING`.
- All three reactive handlers are **mutation-only** (no `CANCEL_EVENT` child step).
  A `CANCEL_EVENT` child fires unconditionally — even on the fizzle path — so an
  unaffordable defense would still cancel the attack. That bug was caught and fixed
  by the reactive E2E tests (#1584 Task 16).
- **Payer rule (#2208, ADR-0118):** both cost paths debit
  `ConditionInstance.source_character`, falling back to the bearer (`target`) when
  unset. `_try_spend_reactive` (fire cost) and `drain_reactive_upkeep` (round upkeep,
  per-participant) both resolve the payer this way — an ally ward strains its caster,
  never the ally wearing it; an upkeep payer who can't afford the round cost causes
  the ward to lapse (row deleted, `Trigger` rows cascade). Self-cast wards are
  unchanged: `source_character` already equals the bearer.

**Ally + party ward variants (#2208):** each of the three reactive-defense
`ensure_*_content()` builders above (Aegis Field / Mirror Ward / Phase Step) also
seeds an ALLY-single and an ALLY-`FILTERED_GROUP` (party) Technique variant, reusing
the exact same `ConditionTemplate`/triggers/flow as the self variant — no new
ConditionTemplates, triggers, or flows.

| Technique | Variant of | `target_kind` / `target_type` | Castable | `anima_cost` |
|-----------|------------|-------------------------------|----------|---------------|
| Aegis Ward | Aegis Field | ALLY / SINGLE | in or out of combat (existing ally-target seam) | 2 |
| Aegis Communion | Aegis Field | ALLY / FILTERED_GROUP | out-of-combat party preparation | 4 |
| Mirror Vigil | Mirror Ward | ALLY / SINGLE | in or out of combat | 2 |
| Mirror Communion | Mirror Ward | ALLY / FILTERED_GROUP | out-of-combat party preparation | 4 |
| Phase Guard | Phase Step | ALLY / SINGLE | in or out of combat | 2 |
| Phase Communion | Phase Step | ALLY / FILTERED_GROUP | out-of-combat party preparation | 4 |

Party (`Communion`) variants pay 2x the single variant's `anima_cost`. The
`FILTERED_GROUP` party route is deliberately **out-of-combat only** — casting a
party ward mid-encounter (in-combat party AoE) was not built; the reserved slot on
the technique-target join table remains unused for that case. `FILTERED_GROUP`
targeting is the benign, consent-free route per ADR-0045 (non-hostile group casts
don't need per-target consent the way hostile multi-target casts do).

### Resonance Gain Surfaces (Resonance Pivot Spec C)

`GainSource` (`world/magic/constants.py`) discriminates which typed source FK is
populated on a given `ResonanceGrant` row (the universal audit ledger — see "Spec C
Resonance Gain" in `docs/systems/INDEX.md`). Current values:

- `POSE_ENDORSEMENT` / `SCENE_ENTRY` — peer endorsement of a pose/scene-entry (#1138).
- `ROOM_RESIDENCE` — room residence trickle. Live end-to-end via a declare→tag→tick loop
  (#2036): `SetPrimaryHomeAction` declares `CharacterSheet.current_residence`,
  `tag_room_resonance`/`untag_room_resonance` tag the room's aura, `residence_trickle_tick()`
  grants daily for the tagged∩claimed intersection; `StartingArea.grants_residence_tenancy`
  auto-grants a CG starting tenancy so the gate is reachable with zero manual player step. A
  Sanctum's Ritual of Homecoming writes the same `LocationValueModifier` row shape onto its own
  room, so a resident Sanctum owner trickles from Homecoming growth as an intentional emergent
  synergy — see `world/magic/CLAUDE.md` "Residence declaration + room aura tagging" for detail.
- `OUTFIT_TRICKLE` — outfit presentation trickle (see `docs/architecture/items-fashion-mantles.md`). `outfit_item_facet` is PROTECT and a removed facet is soft-removed (`ItemFacet.removed_at`), so the grant history survives a sacrificed item or a stripped facet (#4461).
- `STAFF_GRANT` — manual staff grant.
- `SANCTUM_WEAVING` / `SANCTUM_OWNER_BONUS` / `SANCTUM_DISSOLUTION_RECOVERY` —
  Sanctum income and dissolution recovery (Plan 4).
- `PROJECT_CONTRIBUTION` — flat resonance per contribution to a project whose
  `ProjectKind` has opted in (#2038). `ProjectKindResonanceAward`
  (`world/projects/models.py`) is a staff-authored per-kind opt-in table
  (`kind` unique, `resonance_award_amount`; a missing row or amount 0 means the
  kind doesn't pay out — fail-closed, no `add_contribution` behavior change).
  Seeded today: only `ORGANIZATION_CAPABILITY` → 5 (`ensure_project_kind_resonance_awards`,
  `world/projects/seeds.py`, `project_resonance` cluster). The payout hook,
  `_maybe_grant_project_contribution_resonance` (`world/projects/services.py`), runs
  at the end of every `add_contribution` call regardless of `ContributionKind`;
  it reads resonance off `Project.resonance` (the typed source FK is
  `ResonanceGrant.source_project`, `PROTECT` since #4464: the shape constraint requires it,
  and a project is retired by `status`, never deleted) and is exception-guarded so a payout failure
  never rolls back the contribution itself. Uncapped by design — every
  contribution to an opted-in project's kind pays out again.
- `ENTRY_FLOURISH` — see "Entry-Flourish Declaration" above.
- `DRAMATIC_MOMENT` — see "Dramatic Moment Tagging" above.
- `STYLE_PRESENTATION` — style presentation endorsement (#1152).
- `MISSION_REWARD` — mission deed rewards; see "Aura Drift (#1737)" below.
- `MISSION_REPORT` — mission-report style payout (#1753); discriminator-only
  (no typed source FK, like `STAFF_GRANT`).
- `STAKE_REWARD` — stakes-contract WIN reward line (#1770 PR3); discriminator-only,
  provenance on the stories side (`StakeOutcome` + `StakeRewardLine`); see
  `docs/systems/stakes.md`.
- `DISTINCTION` — a distinction's authored `DistinctionResonanceGrant` flat seed
  (#1834); typed source FK `source_character_distinction`. See "Distinction → Resonance
  (#1834)" in `docs/systems/distinctions.md` for the model + reconcile/accelerator services.
- `DRIFT_CORRECTION` - the target side of a drift correction conversion (#4733); no typed source
  FK (`res_grant_drift_correction_shape`), never accelerated, not a deed. See "Drift correction".

**Telnet visibility (#2032).** Balances were earnable/spendable via telnet (pulls, imbuing,
sanctum weaving) but had no telnet surface showing `CharacterResonance.balance` at all. Two
read-only faces now expose it, both reading the same handler/service the web uses (no parallel
query pipeline):
- `sheet/magic` (`commands/account/sheet_sections.py`) — a `Resonance:` block listing every
  claimed resonance's balance + lifetime earned, built by
  `_build_magic_resonances` (`world/character_sheets/serializers.py`), which reads
  `character.resonances` (`CharacterResonanceHandler`, the cached identity-mapped accessor —
  not a fresh query). Folded into `MagicSection.resonances` so telnet and the web Magic tab
  share one data path.
- `resonance` (`commands/resonance.py`, key `resonance`) — bare `resonance` reuses
  `_build_magic_resonances` for the same balance listing; `resonance history [<name>]` shows
  the caller's last 10 `ResonanceGrant` rows (newest first, source label via
  `get_source_display()`), optionally narrowed to one claimed resonance, via
  `resonance_grant_history_for_sheet` (`world/magic/services/gain.py`) — mirrors
  `ResonanceGrantViewSet`'s `-granted_at` ordering.

`ACCELERATED_GAIN_SOURCES` / `NON_ACCELERATED_GAIN_SOURCES` (`world/magic/constants.py`,
ADR-0041) partition every `GainSource` member (a total-classification test enforces this):
perception/presence-driven sources a character actively performs to be seen (`POSE_ENDORSEMENT`,
`SCENE_ENTRY`, `ENTRY_FLOURISH`, `DRAMATIC_MOMENT`, `STYLE_PRESENTATION`, `OUTFIT_TRICKLE`,
`ROOM_RESIDENCE`) are scaled up by `distinction_earn_rate_for` (a character's summed
`DistinctionResonanceGrant.earn_rate_bonus_per_rank`) in `grant_resonance` before the amount is
written; authored/system sources (`STAFF_GRANT`, `MISSION_REWARD`, `MISSION_REPORT`,
`STAKE_REWARD`, `PROJECT_CONTRIBUTION`, the three `SANCTUM_*` sources, and `DISTINCTION`
itself — accelerating a distinction's own seed grant would be circular) are never accelerated.

The same `ACCELERATED_GAIN_SOURCES` gate also drives the reverse distinction link (#2037):
after an accelerated-source grant lands, `grant_resonance` calls
`check_distinction_rank_thresholds(character_sheet, resonance)`
(`world/magic/services/distinction_resonance.py`), which ranks up **held** distinctions whose
authored `DistinctionResonanceRankThreshold` (`world/magic/models/grants.py`) at exactly
`current_rank + 1` is crossed by the new `lifetime_earned` — looping to a fully caught-up
final state per grant, exclusion conflicts logged and skipped, and the whole check
failure-isolated (`logger.exception`) so the resonance grant itself always stands.
`DISTINCTION`-source seeds never trigger it (feedback-loop guard). Details:
`docs/systems/distinctions.md` "Reverse direction".

### Aura Drift (#1737)

`CharacterAura`'s stored `CharacterAuraShare` percentages are a write-through cache,
recomputed by `recompute_aura(character_sheet)` (`world/magic/services/aura.py`) on
**every** `grant_resonance()` call system-wide. The formula sums
`CharacterResonance.lifetime_earned` grouped by `Resonance.affinity` and normalizes to
percentages — deed history, not spendable balance, so spending resonance on pulls never
moves aura. No-op if the character has no `CharacterAura` row (not magically active) or
if total lifetime-earned resonance is 0 (leaves the existing stored values as-is).

`AuraAffinityThreshold` (`world/magic/models/aura.py`) is a small authored catalog
(affinity + threshold_percent + optional `discovery_achievement` FK). After each
recompute, `fire_aura_threshold_crossings` checks whether the drift crossed any
authored threshold and grants the linked achievement — mirroring the
`fire_variant_discoveries` discovery pattern (direct before/after check, not a Flows
event). Compound gates reuse the achievement's own `AchievementStatRequirement` rows.

Missions is the first deed source to grant morally-typed resonance:
`MissionOptionRouteReward.resonance` (author-set, required when `sink=RESONANCE`) flows
through `MissionDeedRewardLine.resonance` to the reward cron's `_grant_resonance`, which
calls `grant_resonance(..., source=GainSource.MISSION_REWARD)`. This closes the
RESONANCE half of `docs/plans/2026-05-18-missions-design.md` §13.3 (LEGEND_POINTS
remains a separate, still-open stub).

Note: `get_aura_percentages()`/`CharacterAffinityTotal` — unwired legacy code from
before `CharacterAura`'s stored-percentage mechanism existed — were removed in
#1739. `recompute_aura` never used them.

### Drift correction (#4733, slice 4 of #4672) [BUILT & WIRED]

**Vocabulary.** "Drift" here is resonance a character holds that sits off their aura: a
`CharacterResonance` with `balance > 0` whose resonance's affinity differs from the aura's
`dominant_affinity` (`drift_holdings`, `world/magic/services/drift.py`). It has no threshold in
this slice. `AuraDrift` / `recompute_aura` (the section above) is the older, different sense:
the shift in the aura's stored percentages. Drift correction converts held drift into the
character's own resonances through deeds; it is separate from Fall and Redemption, which change
affinity. Drift correction reuses their pair rates (`AffinityInteraction.conversion_multiplier`).

**Deed classification.** `DEED_GAIN_SOURCES` / `NON_DEED_GAIN_SOURCES` (`constants.py`)
partition every `GainSource`; `test_deed_classification.py` fails when a member is in neither or
both. Deeds are the poses and scene entries others endorsed, entry flourishes, dramatic
moments, style presentations, mission rewards and reports, stake rewards, project
contributions, combo discoveries and worship rites. Passive trickles (room residence, outfit),
staff grants, sanctum sources, distinction seeds, compromise, penance and both conversions
(`FALL_CONVERSION`, `DRIFT_CORRECTION`) are not deeds. Casting never counts. A new `GainSource`
member must be placed in one set.

**When an offer opens.** `grant_resonance` calls `open_or_extend_conversion_offer(grant)` after
the aura recompute. It does nothing unless all of these hold: the source is a deed; the
character has an aura with shares; the granted resonance's affinity is the aura's own; the
character holds convertible drift (drift with an authored conversion pair into the granted
resonance's affinity); and the character stands in a live scene. The scene is the one cached on
the grantee's current room at grant time (`get_active_scene`, which skips a Battle's backing
scene), not the scene the deed came from. A deed settled away
from a scene, such as the weekly pose-endorsement settlement, therefore opens no offer. This is
an accepted consequence, not an error. A finished scene cached on a room counts as no scene.

One `DriftConversionOffer` exists per character and scene (unique constraint); it holds one
`DriftConversionCap` per target resonance. Each qualifying grant adds `amount x cap_percent
// 100` to that cap and is linked in `cap.grants`, which stops a grant counting twice. Only the
grant that creates the cap row is floored at 1, so a first small deed opens a usable cap while
later small deeds can add 0; a cap never exceeds `cap_percent / 100` of its linked deed points
plus that one point. A `cap_percent` of 0 opens no offer at all. `cap` is a snapshot: a later
change to `cap_percent` does not rewrite it. The offer row is locked with `select_for_update`
while a cap changes, and the cap is re-read from the table under that lock; if a decline or a
lapse deleted the offer before the lock, the grant retries once and opens a fresh offer.

**Notices.** A new offer or a new cap row sends a telnet-only line on commit
(`send_text_to_non_web`, after `transaction.on_commit`); web players learn from the polled
pending endpoint. A cap bump says nothing. `lapse_conversion_offers(scene)` deletes the scene's
offers and sends the lapse line; `Scene.finish_scene` calls it, so every finish route lapses
them, and the rite refuses an offer whose scene has finished.

**The rite.** `DriftCorrectionConfig` (singleton, pk 1, created lazily) designates the rite
(`rite` FK to `Ritual`) and the roll (`check_type` FK to `CheckType`, `check_difficulty`), plus
`cap_percent`. The check type is deliberately not a `RitualCheckConfig` sidecar, which needs a
stat and a skill and looks up by ritual name. `DriftCorrectionOutcomeShare` (an
`OutcomeTierAward`) maps each `CheckOutcome` to `converted_share`, the fraction of the
requested amount that converts (not a fraction of the cap); `clean` keeps a better tier
from converting less than a worse one. `perform_drift_correction_rite` (`drift_correction.py`),
in one transaction: locks the offer; refuses unless `rite_is_ready(config)` (an unset rite or
check type, or any `CheckOutcome` with no share row: `DriftCorrectionNotConfiguredError`,
before anything is consumed); validates
the amount against the cap and the held balance and the source against `convertible_drift`;
picks the offering with `resolve_ritual_components` (no writes) with the target as
`resonance_context`; rolls the check with `focus_bonus` as extra modifiers; converts
`floor(amount x share)` of the source through `convert_resonance_amount`, granted as
`GainSource.DRIFT_CORRECTION` at `max(1, floor(converted x pair multiplier))` (an uphill pair
never rounds to zero); and only then spends the offering with `consume_materials`. Every step
that can raise runs before the first item write, so a refusal never leaves a cached item or
balance ahead of the rolled-back table. The cap shrinks by what converted; an empty cap row is
deleted, and the offer with it when no cap is left. A tier with no share row is refused up
front by `rite_is_ready`; a tier whose share is 0.00 converts nothing, spends the
offering and leaves the cap intact. Source and target lifetime move by the proportional share, so the
aura follows (`recompute_aura`). `_move_partial` (`conversion.py`, shared with the Rite of
Atonement) works that share out in integers as `amount x lifetime // balance`: exact when the
ratio is whole (4 of a 30 balance with 30 lifetime moves 4), rounded down on a true fraction.

**Component modes.** `RitualComponentRequirement` has a third mode, `matches_target_resonance`
(exclusive with `item_template` and `min_touchstone_tier`), with optional `min_item_meaning`
(minimum 1; blank turns the third route off). `qualifying_components` admits an item under the
first matching `ComponentMode`: `MATERIAL` (template tied to the target resonance), `FACET`
(a live item facet in the performer's motif for the target), `KEEPSAKE` (item meaning to the
performer at or over the bar). Results are ordered material, facet, keepsake, so spending in
order burns a plain material first. Items already allocated to a template or touchstone row are
not offered again.

**Focus.** `focus_bonus(sheet, target)` = `equipment_walk_total` on the target resonance's
modifier target + `touchstone_cast_bonus`. It adds to the check, not to the output.

**Exceptions** (`exceptions.py`): `DriftCorrectionError` (base) with
`DriftCorrectionNotConfiguredError`, `DriftOfferNotFoundError`, `DriftConversionInvalidError`;
`ConversionMappingError` for an unauthored pair; `RitualComponentError` for the offering.

**Surfaces.** Actions `perform_drift_correction` and `decline_drift_correction`
(`actions/definitions/drift_correction.py`); the rite's result line leads with the outcome tier
("Partial Success: 4 Ruin became 2 Dawnlight.", or "The rite fails; nothing is converted." when
nothing converts), and the web dialog composes the same words from the result; telnet `drift`, `drift convert <from>=<into>
[<amount>] [with <item>]` (by default offers every carried item except those that count only
as a facet or a keepsake, so a plain material is spent; `with <item>` names a faceted item or
keepsake to spend instead), `drift decline`; REST `GET /api/magic/drift-correction/pending/` (+ `{id}/`), `POST .../convert/`,
`POST .../decline/`, all scoped to the caller's own characters. React:
`DriftConversionOfferGate` polls the inbox and `DriftConversionOfferDialog` answers it; the gate
is mounted on `SceneDetailPage` and `GamePage`, keyed by scene id so each shows the offer of the
scene it displays. See `frontend/src/magic/CLAUDE.md`.

**Authoring and tuning.** Staff author `DriftCorrectionConfig`, one
`DriftCorrectionOutcomeShare` per outcome tier, the rite's `RitualComponentRequirement` rows and
the Fall and Redemption pair multipliers in admin; offers and caps are read-only there. Until
the rite and check type are set and every tier has a share, the rite refuses ("not set up yet")
though offers still open; the `drift-correction-config` Required content probe reports it.
While the rite, the check type or a tier's share is missing (`rite_is_ready()` false;
the tiers come from `outcome_tiers_without_a_share()`, which the probe reads too), telnet
`drift` and `drift convert` refuse with the same sentence (`RITE_NOT_READY_MESSAGE`, the
exception's `user_message`) instead of listing an offering, the rite refuses with it before
checking the cap or the request, and the pending serializer carries `rite_ready: false` and
`rite_not_ready_message`, which the dialog shows in place of the offering pills, with
"Perform the rite" disabled. The pending view works readiness out once per request and
hands it to the serializer as `context["rite_ready"]`.
`max_yield_per_earned_point(config)` is the anti-farm estimator: `cap_percent / 100 x largest
pair multiplier x largest share`, kept below 1 so correcting never out-earns the deed. It is
the per-point rate; the one floored point a new cap row opens with sits on top of it, once per
offer and target resonance.

**Tests.** `test_deed_classification.py`, `test_drift_models.py`, `test_drift_offer.py`,
`test_drift_correction_rite.py`, `test_conversion_amount.py`,
`test_ritual_components_target_mode.py`, `test_drift_correction_views.py`; journey
`integration_tests/test_drift_correction_journeys.py` (telnet, web, lapse, negatives).

### Thread retune: moving a thread to another resonance (slice 6 of #4672) [BUILT & WIRED]

A player moves one thread to another resonance by performing the retune rite: the SERVICE
`Ritual` whose `service_function_path` is `THREAD_RESONANCE_SERVICE_PATH`
(`world.magic.services.thread_resonance.change_thread_resonance`). Staff author the row and its
`RitualComponentRequirement` rows; code finds it with `thread_resonance_ritual()` (first by pk),
the way the Rite of Honors is found by `HONORS_SERVICE_PATH`. No roll.

- **Targets** (`thread_resonance_options(thread)` -> `ThreadResonanceOption`): every other
  resonance of the thread's affinity (rate 1, `conversion_type` None), plus, for each other
  affinity, the `ResonanceConversion` counterpart of the thread's resonance when
  `conversion_pair` succeeds (the pair's multiplier and Fall / Redemption type). No mapping or no
  pair: not offered. Sorted own affinity first, then affinity and resonance name, for display.
- **Points**: `developed_points` within the affinity unchanged; across affinities
  `scaled_thread_points` = `max(1, int(points x multiplier))` while points > 0 (a Redemption
  shrinks a thread but never empties it, like `convert_resonance_amount`). `level` is unchanged.
- **Merge**: `_reanchor_thread(thread, target_resonance_id, new_points)` (`services/conversion.py`,
  shared with the full Fall conversion's `_reanchor_threads`) adds the points to a live thread on
  the same anchor in the target resonance and retires the moved thread, else re-anchors it.
  The merge locks the surviving row and adds to the points the database holds, so two merges
  into one thread both count. `_find_existing_target_thread` compares every typed target FK id
  (organization included).
- **Refusals** (`ThreadResonanceChangeError`, `check_thread_resonance_change`): no thread named,
  a thread that is not the performer's or is retired, no target named (the message lists the
  options as "Name (id, same affinity|Fall|Redemption)"), and a target not among the options
  (its own resonance included). Under the lock it also refuses a thread whose resonance moved
  since it was read (`THREAD_MOVED_MESSAGE`). A retired thread holds no place: every per-anchor `Thread`
  unique constraint applies to live threads only (migration 0322 brought trait, technique,
  relationship track and relationship capstone in line with the others), so a merged thread
  can move back onto the resonance its retired partner left, by a retune or the full Fall.
- **Message**: the result's `message` ("Mercy of the Healer left Bene and now channels Praedari
  (40 points, now 48)." or "... merged into your Lumen thread on the same anchor: its 40 points
  brought 40, and that thread now holds 50."; a thread with no name is "Your <anchor> thread")
  is appended to "You perform <rite>." by `PerformRitualAction` (`_service_result_line`), and
  `RitualPerformView` returns that line as `message` for every SERVICE ritual with a result.
- **Nothing spent on refusal**: `PerformRitualAction._precheck` runs
  `check_thread_resonance_change` for this rite before components and anima are spent;
  `change_thread_resonance` locks the thread row and checks again. `_validate_components` passes
  `kwargs["target_resonance"]` as `resonance_context`, but only for a ritual that has a
  `matches_target_resonance` requirement (`has_target_resonance_requirement`), so the offering
  is paid toward the chosen resonance (material, facet or keepsake) and a stray `resonance=`
  changes no other ritual's components. The keepsake bar is `target_resonance_meaning_bar`
  (`services/ritual_components.py`, shared with drift correction's `offered_components`).
- **Aura**: balances are untouched, so no `recompute_aura`; `character.threads.invalidate()` runs.
- **Resolvers**: `resolve_target_resonance(id)` (`UnknownResonance`) and
  `resolve_owned_thread(sheet, id)` (`UnknownOwnedThread`), in `services/thread_resonance.py`,
  are shared by telnet's `ritual` command and `RitualPerformView`: a non-integer, unknown or
  foreign id is a plain refusal (telnet) or a 400 (web), never a 500. `target_resonance` is
  resolved for every ritual; `thread_id` through this resolver for the retune rite.
- **Anchor rules**: `thread_resonance_refusal(thread)` holds a SANCTUM thread (its sanctum's
  resonance; the Ritual of Purging changes it) and a TECHNIQUE thread whose `signature_bonus`
  has a `required_resonance` (clear the signature first); `thread_resonance_options` returns
  none for either, and narrows a GIFT thread to `gift.cached_resonances` when that set is
  non-empty (the `weave_thread` rule). `check_thread_resonance_change` applies both, so telnet
  and web refuse alike. Service refusals carry no telnet syntax; the `ritual` command adds
  `thread=<id>` / `resonance=<id>` hints before dispatch (`_refuse_incomplete_retune`).
- **Race**: a re-anchor that loses the partial unique index to another process raises
  `ThreadAnchorTakenError` (a `ThreadResonanceChangeError`) from a savepoint in
  `_reanchor_thread`, with the cached thread's `resonance_id` and `developed_points` put back.
- **A refusal after the spend gives the spend back, in memory too** (#4735): the perform's
  components and anima are spent before dispatch, so a service that refuses afterwards (this
  race, or any caught ritual exception) rolls the whole perform back. The rollback restores
  the tables; `PerformRitualAction`'s `_spend_restored_on_raise`, entered outside the
  `transaction.atomic()`, restores the identity map to match for every ritual: the items
  (`consumption_restored_on_raise` in `world/items/services/materials.py`: quantity,
  `destroyed_at`, holder and container in place, a consumed container's spilled contents
  too; a hard-deleted item re-cached; its deleted
  game object left out of the cache; the holder's `contents_cache` rebuilt and its carried
  and equipped handlers invalidated) and, when the rite channels, the `CharacterAnima` row.
  The full Fall re-anchors threads one by one, so a refusal part way would leave the threads
  already moved, and the balances already zeroed, moved in memory: `perform_fall` takes
  `conversion_restored_on_raise` (`services/conversion.py`) around its transaction, which
  keeps the character's `CharacterResonance` rows and live threads and writes them back in
  place on a raise, then invalidates the character's thread and resonance handlers. Both use `core.identity_map.CacheGuard` (ADR-4626's restore-in-place).
- **Surfaces**: telnet `ritual <rite> thread=<id> resonance=<id>` (alias `target_resonance=`;
  leave it out to list the options); the Spellbook's `ThreadResonanceDialog` on the thread
  detail page (vitest `ThreadResonanceDialog.test.tsx`); web `POST /api/magic/rituals/perform/` with
  `kwargs: {thread_id, target_resonance}` (`RitualPerformView` resolves both; the result is
  `ThreadResonanceChangeResult`: `thread_id` of the survivor, `from_resonance_id`,
  `to_resonance_id`, `points_before`, `points_moved`, `points_after`, `merged`,
  `conversion_type`); `GET /api/magic/threads/{id}/resonance-options/` (owner only) returns
  `{ritual_id | null, offering_required, offering_count, unavailable_reason, options:
  [{resonance_id, resonance_name, affinity_name, conversion_type (FALL / REDEMPTION / null),
  projected_points, merges_into_thread_id | null, qualifying: [{item_id, name, mode}]}]}`
  (`offering_count` sums the rite's `matches_target_resonance` quantities via
  `target_resonance_offering_count`; `qualifying` is filled only when it is non-zero;
  `unavailable_reason` from `thread_resonance_unavailable_reason`); the view works out every option's
  qualifying items in one batch (`qualifying_components_by_target` in `services/drift.py`), so
  its query count does not grow with the number of options. Required content rows
  `thread-resonance-ritual` ("No ritual changes a thread's resonance") and
  `thread-resonance-ritual-single` (TUNING: a second ritual on the path, which the Spellbook
  never offers) and `thread-resonance-ritual-web-payable` (TUNING: the rite has an
  item-template or touchstone component the Spellbook cannot pay). Journey:
  `integration_tests/test_thread_resonance_journeys.py`.

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

### Content pipeline — magic catalog export/import (#2486)

The full magic catalog is lore-repo-authorable content, not admin-only data: `Affinity`,
`Resonance`, `Facet`, `Gift`, `Tradition`, `IntensityTier`, `Technique` + its payload rows
(`TechniqueCapabilityGrant`/`TechniqueCapabilityRequirement`/`TechniqueDamageProfile`/
`TechniqueOutcomeModifier`/`TechniqueAppliedCondition`/`TechniqueRemovedCondition`/
`TechniqueFunctionTag`), `TechniqueStyle`, `StyleCapabilityRequirement`, `Restriction`,
`EffectType`, `PortalAnchorKind`,
`PathGiftGrant`, `TraditionGiftGrant`, plus `species.SpeciesGiftGrant` — all listed in
`CONTENT_MODELS`
(`core_management/content_export.py`) and exported/imported by the shared
`content_export.py`/`content_fixtures.py` pipeline (see `docs/systems/INDEX.md`'s
"Content-repo load" entry for the driver). Every model's natural key is its
`NaturalKeyConfig.fields`: `Technique` is keyed `(gift, name)` (the `unique_technique_gift_name`
`UniqueConstraint` backs it — authoring a second technique with the same name under the
same gift raises `DuplicateTechniqueName`, a clean 400, not an `IntegrityError`); the grant
tables (`PathGiftGrant`, `TraditionGiftGrant`, `SpeciesGiftGrant`) key on their FK pairs
(`(path, gift)`, `(tradition, gift)`, `(species, gift)`); the other payload rows key on their
owning technique plus their own unique-constraint fields, except `TechniqueOutcomeModifier`,
a global outcome-tier table with no technique FK — it's a `OneToOneField` to
`traits.CheckOutcome` and keys on `outcome` alone; `PortalAnchorKind` keys on `name`
(`achievements.Achievement` keys on `slug` and is now in `CONTENT_MODELS`
alongside `AchievementStatRequirement`/`AchievementReward`/`RewardDefinition`/
`ConditionStatRule` — #2832). `load_entries` (`core_management/content_fixtures.py`)
upserts by natural key. There is no in-repo seed catalog to fall back on: the lore repo is the
single source (`seed_starter_gift_catalog()` was retired by #2474 — see "CG Starter
Gift/Technique Catalog" and "Content-vs-config boundary in the dev seed" above for the
seed-vs-content sequencing, which seeds the "Technique Cast" `ActionTemplate` config
prerequisite before `load_world_content()` runs, and ADR-0142 for the rationale).
The deferred-retry loop resolves load-order gaps *within* the content/grid load; it
cannot conjure a config row the load itself never creates — which is why the config
prerequisites run first in that sequence.

**`magic.ritual` is content-exportable, but a player's personal anima ritual is not
(#2724, ADR-0171).** `Ritual` also carries `NaturalKeyMixin` and lives in
`CONTENT_MODELS` — staff/lore-authored rituals (Sanctification, Homecoming, Covenant
Formation, etc.) export and import through the same pipeline as the rest of the
catalog above. But `provision_player_anima_ritual` creates one `Ritual` row per
player (their personal SCENE_ACTION anima ritual, `author_account` set to the
provisioning account), and that row must never ship in the content corpus as if
authored. `core_management.content_export.EXPORT_FILTERS` filters `magic.ritual` on
`author_account__isnull=True` at export time — a row-level predicate applied on top
of the model-level `CONTENT_MODELS` allowlist, not a separate model registration.
See `docs/systems/checks.md`'s "Seeded Compositions" section for the parallel case
on `checks.checktype`/`checks.checktypetrait` (`owner_sheet`), and ADR-0171 for why
both use a real owner column rather than a name-pattern exclusion.

---

### Cast observation — who noticed that cast (#2710, ADR-0170)

**[BUILT & WIRED].** How obvious a cast is to bystanders is a property of the caster's
Path-derived `TechniqueStyle`, resolved per observer at the moment the cast poses — not
a room-wide visible/hidden flag on the Technique or the Interaction. See ADR-0170 for
the full decision record; this section is the reference for the mechanism.

**Entry point:** `resolve_cast_audience(*, caster, cast_openly=False) ->
CastAudience` (`world/magic/services/cast_observation.py`). `CastAudience` is a frozen
dataclass: `concealed` (bool), `full` (list of `Persona`), `vague` (list of `Persona`).
When `concealed` is False, `full`/`vague` are empty and the caller poses to the whole
room exactly as before #2710.

**Resolution:**
**Concealment hides attribution, not the event** (ADR-0187, #2734). Failing the
detection roll does not delete the cast from your feed — you still see what happened,
you just cannot say who did it. The tiers are a ladder of attribution:

0. Two free short-circuits run first, before any query: `cast_openly=True` (the caster's
   own one-way waiver) and a `SAME`-reach technique. Contact gives the actor away — you
   have to be standing on someone to stab or touch them — so a melee working is
   attributed no matter how subtly its caster works magic. This, not "is it magical", is
   what makes a sword swing unconcealable.
1. `_concealment_for(caster, technique)` checks `technique.gift.style` first — a Minor Gift
   may impose its own casting style, overriding whatever the caster's Path would otherwise
   supply (#2905, ADR-0199), since a species-granted gift is magic the character never
   chose. Only when the gift sets no style does it fall back to `cast_concealment` off the
   caster's current Path's `TechniqueStyle`
   (`world.progression.selectors.current_path_for_character`). Returns 0 (overt — no check,
   byte-identical to pre-#2710 behavior) when neither the gift nor the Path sets a style, or
   the caster has no Path.
2. When `cast_concealment > 0`, the caster is unconditionally added to `full` — a caster
   always knows what they just cast.
3. `world.checks.models.CheckType.objects.filter(name=DETECT_CAST_CHECK_NAME,
   is_active=True)` resolves the detection check. **Missing this row fails CLOSED on
   attribution** (ADR-0033): nobody can name the caster, logged as a warning — but a
   perceptible working is still narrated to the room, since erasing every combat event
   from every participant's feed is a different failure, not a safe default.
4. Difficulty = `cast_concealment + level_opposition(check_type, level=<caster's path
   level>, character=caster)` (ADR-0166 — level is a two-sided check term).
5. Every character co-located with the caster (excluding the caster) rolls
   `perform_check(observer, check_type, target_difficulty=difficulty)`:
   `success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL` (2) → `full` (sees who cast what);
   `== 1` → `vague` (sees the effect and knows it was *a working*, not by whom);
   `<= 0` → `effect_only` (sees the effect, with no sense that magic was involved).
6. **`Technique.has_perceptible_effect`** (BooleanField, default `True`) is the one thing
   that still vanishes outright. A working that leaves nothing to perceive — a silent
   binding, a curse laid at a distance — leaves `effect_only` empty, and the pre-#2734
   hide-entirely behaviour holds for it alone. The default is `True` because almost any
   applied condition produces something a bystander would see.

No observer receives more than one pose, and no tier is told strictly less than a tier
that rolled worse — the `vague` line folds the effect in rather than replacing it.
`render_unattributed_action_narration` / `render_unattributed_cast_narration` build the
unattributed line, and deliberately carry **none** of the attributed line's suffix
clauses: the signature clause is the caster's personal flourish (#1728) and the single
strongest attribution tell there is, the power clause names "the working"/"the ward"
(telling an `effect_only` observer that magic was involved), and the synergy clause
narrates condition interplay that reads as authored magic.

**The `PERCEIVED_ONLY` privacy tier** (`world.scenes.constants.InteractionVisibility`)
is how the resolved audience is persisted. It sits between `DEFAULT` and `VERY_PRIVATE`:
writer + `InteractionReceiver` rows can read it, **plus staff and the scene's GM** — a
scene must stay runnable for the person adjudicating it. The GM exception is a scene-log
read guarantee only (`InteractionQuerySet.visible_to`'s `gm_visible` branch); a non-staff
GM is denied on the REST object-access permission (`CanViewInteraction`) and the
reaction-witness gate (`can_view_interaction`), both staff-only. `VERY_PRIVATE` is
stricter and admits no exception, staff included; the two tiers are deliberately not
interchangeable (ADR-0170). `world.scenes.cast_services.create_cast_outcome_pose` writes up to three
Narrator OUTCOME poses when concealed — one per non-empty tier, each with that tier's
personas as receivers. Only the `full` pose carries `target_personas`: that FK drives
"this pose is about you" surfacing, and naming the target alongside an unattributed line
re-opens the attribution the lower tiers exist to withhold. It returns the attributed
pose, the one the caller wires to `SceneActionRequest.result_interaction`.
`_resolve_and_pose_cast` additionally sets the caster's own ACTION-mode Interaction to
`PERCEIVED_ONLY` with receivers = `audience.full` — concealing only the OUTCOME pose
would still show every bystander "Ilyra — Whisper of Binding" in the scene log via the
ACTION row's `technique_name`.

**`cast_openly`** (`SceneActionRequest.cast_openly`, `BooleanField`, default False) is
the caster's one-way waiver — it can only remove concealment for this cast, never add
it. Persisted rather than passed as a plain kwarg, because a consent-gated cast poses at
*accept* time: a flag held only in the declaring call's frame would silently go subtle
by the time a target accepts a PENDING request.

**Three enforcement points close three distinct leaks.** The scene log (above) is the
most visible one and the least of it — a concealed cast that only hid the pose while
still exposing the request row or the reaction gate would leak the caster's identity
through those other doors instead:

1. **`InteractionQuerySet.visible_to`** (`world/scenes/managers.py`) — read visibility
   for the scene log. **[BUILT & WIRED], needed NO change for #2710**: its room-heard
   predicate already requires `visibility=DEFAULT` and `receivers__isnull=True`, so a
   `PERCEIVED_ONLY` row is automatically excluded from "what the whole room heard"; its
   staff and GM branches already exclude only `VERY_PRIVATE`, so both already admit
   `PERCEIVED_ONLY`. The pre-existing writer/receiver `party` branch covers the caster
   and every observer in `audience.full`/`audience.vague` for free.
2. **`SceneActionRequestViewSet.get_queryset`** (`world/scenes/action_views.py`) — the
   REST object permission surface. The *target* of a cast rolls detection like any other
   observer and can fail to perceive it, but `SceneActionRequestSerializer` still
   serializes `technique_name` and `initiator_persona` on the request row itself — so a
   request whose result is `PERCEIVED_ONLY` is excluded for any non-initiator viewer who
   has no matching `InteractionReceiver` row on `result_interaction`, via a correlated
   `Exists()`/`OuterRef` subquery (not a joined `receivers__persona_id__in=` condition —
   see the code comment for why the join shape silently mis-hides multi-receiver rows).
3. **`can_view_interaction`** (`world/scenes/interaction_services.py`,
   `reaction_services.py:132`) — the witness gate for `react_to_window`. **[BUILT &
   WIRED]** — an earlier draft of this spec incorrectly claimed this predicate was
   unwired and proposed deleting it; it is not, and doing so would have let a bystander
   react to a concealed cast they never perceived, which is itself an IC act (a reaction
   implies "I saw that"). It was kept and taught the `PERCEIVED_ONLY` tier: writer or
   receiver, plus staff (unlike `VERY_PRIVATE`, which is writer/receiver-only).

These three surfaces stay legitimately distinct rather than collapsing into one
predicate: `visible_to` filters a **queryset** (the scene log feed), `CanViewInteraction`
(`interaction_permissions.py`) gates a **REST object** (single-interaction fetch/delete),
and `can_view_interaction` gates an **IC action** (can this persona react as a witness).
A viewer's account being permitted to read a row and a viewer's *character* having
witnessed the underlying event are different questions.

**Combat casts ARE covered as of #2734** (they were a stated scope boundary of #2710).
The seam is `world.combat.services._record_and_broadcast_pc_action` — the single site
that poses a resolved focused action — **not** `broadcast_action_outcome`, which has
~15 callers (flee outcomes, encounter-end lines, clash resolution, covenant
insight/weakness) and must stay unconditional for all of them. It instead takes an
optional `audience` kwarg plus an `unattributed_narration` string; `None`/`""` (every
non-cast caller) keeps the room-wide broadcast byte-identical. Concealed, it fans the
outcome out as one `PERCEIVED_ONLY` pose per non-empty tier, delivering live via
`_send_to_objects` rather than `_broadcast_to_location` so the WebSocket matches the
persisted receiver rows. The ACTION row (whose content is the technique name) is
concealed through the shared `conceal_action_interaction`, which moved from
`scenes/cast_services.py` to `world.magic.services.cast_observation` so both paths use
one implementation.

**Combat is why the model is an attribution ladder rather than an existence dial.** It is
the one place where hiding the pose erases something the player has no other way to
learn: vitals are viewer-scoped (`world/combat/serializers.py`'s `_can_view_vitals`) and
no damage path emits a separate "you take N damage" message, so the OUTCOME pose is the
only channel. Under the pre-#2734 model a concealed working could wound, knock out or
drop a PC whose feed showed an empty round and a health bar that silently moved.

There is **no `cast_openly` equivalent in combat**: `cast_openly` is a
`SceneActionRequest` field and `CombatRoundAction` has none, so a combat cast always
resolves at the caster's style concealment. A deliberate in-combat reveal is its own UX
surface, not built.

A fourth read surface was closed alongside the three above:
`ActionOutcomeDetailsView` (`world/combat/views_outcome_details.py`) gated on
`can_view_encounter_effects` — *encounter*-level, which answers "may you see effects in
this fight" but not "did you perceive THIS act" — so a concealed cast's effect rows were
readable by anyone in the encounter who passed its interaction id. It now filters
through `Interaction.objects.visible_to` first.

**Content dependency — this feature ships INERT until authored, and every piece of that
content lives in the lore repo, never as arxii seed data:**
- `DETECT_CAST_CHECK_NAME` (`world/magic/constants.py`, value `"Perception"`) — the
  detection `CheckType` row itself. Absent → fails closed (nobody ever detects).
- A `CheckTypeCapabilityModifier` row bridging a magic-detection capability into that
  `CheckType`, so a character with such a capability rolls better at detection. Without
  it, detection is a flat stat/skill roll with no capability leg (ADR-0170 — this bonus
  is deliberately never an auto-detect threshold).
- Non-zero `TechniqueStyle.cast_concealment` values per style. Every style defaults to 0
  (overt) until authored otherwise, so no existing style behavior changes until content
  chooses to make one subtle.

---

## Key Methods and Properties

### CharacterAura

```python
# Get a character's aura (OneToOne relationship)
aura = character.aura  # May raise DoesNotExist if not created

# Get dominant affinity
aura.dominant_affinity  # Returns the dominant Affinity row

# One affinity's share, by row
aura.percent_for(Affinity.objects.get_primal_affinity())  # Decimal

# Write all shares at once (must sum to 100)
from world.magic.services.aura import set_aura_shares
set_aura_shares(aura, [AffinityShare(affinity=celestial, percent=Decimal("50.00")), ...])
```

### Thread (new Spec A model)

```python
# The populated FK, picked by target_kind
thread.target   # Returns the Trait / Technique / ObjectDB / CharacterRelationship / RelationshipCapstone

# Resolved level cap (per Spec A §2.4)
from world.magic.services import (
    compute_anchor_cap,
    compute_level_cap,
    compute_effective_cap,
)
cap = compute_effective_cap(thread)   # min(level_cap, anchor_cap)
```

**Thread caps and the shown scale (#4585).** A thread level is stored ×10, like a stat:
stored 30 shows 3. `compute_level_cap(sheet)` = `get_character_path_level(character) ×
PATH_LEVEL_CAP_MULTIPLIER` (10, `world/magic/constants.py`; the sanctum Homecoming cap
reads the same constant), so a thread is never shown above its owner's level. A sheet
with no class level still gets 10. `compute_effective_cap` = min(level cap, anchor cap)
and is the only place the level cap applies; each anchor cap holds only what its anchor
imposes (ORGANIZATION: the org's granted cap; GIFT: the level cap; FACET:
`lifetime // ANCHOR_CAP_FACET_DIVISOR`). No cap reads Path stage; `_current_path_stage`
remains for the progression dashboard's display. An imbue that stops at the level cap
reports `blocked_by="LEVEL_CAP"`; the thread serializer's field is `level_cap`.

Every authored thread threshold is a **shown** level: crossings (3, 6, 11, 16, 21),
`ThreadCrossingThreshold.level`, `CrossingOption.crossing_level`,
`TechniqueVariant`/`CovenantRole.unlock_thread_level`,
`SignatureMotifBonus.min_crossing_level`, `ThreadPullEffect.min_thread_level`,
`CovenantRoleGiftGrant.unlock_thread_level`, `VowAddedEffect.unlock_thread_level`
(including its per-level scaling) and `CREATION_PERSONALIZATION_MAX_LEVEL`. Every
comparison goes through `shown_thread_level(level)` (= `level // 10`,
`services/threads.py`). The imbue loop checks a crossing only at a whole shown level
(`next_level % 10 == 0 and is_crossing_level(shown_thread_level(next_level))`); the
crossing handlers list shown crossings between the start and end levels with the same
`is_crossing_level` Paths use. Soul Tether's per-scene cap and Hollow max and the outfit
trickle's level factor also read the shown level. The predicate DSL's `min_thread_level`
stays on the stored scale, like its `min_trait`.

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

# Capability magnitude curve (#2708, ADR-0169) — see docs/systems/conditions.md's
# "Capability magnitude curve" section for the full formula/oracle detail.
context_free_power = character.threads.context_free_power  # int, memoized
contextual_power = character.threads.contextual_thread_power(action_ctx)  # int
```

### Capability Magnitude Curve — Technique & Thread Grants (#2708, ADR-0169) [BUILT & WIRED]

Both `TechniqueCapabilityGrant.calculate_value()` (`world/magic/models/techniques.py`)
and thread-passive tier-0 `CAPABILITY_GRANT` rows (`CharacterThreadHandler
._passive_capability_grants_cache`, `world/magic/handlers.py`) curve their authored
`base_value`/`capability_grant_value` geometrically by the caster's real power, via the
shared `world.magic.services.capability_curve.apply_capability_curve` helper:

```
value = round(base * 2 ** (sensitivity * power / power_per_doubling))
```

Gated on the `CapabilityPowerConfig` singleton (pk=1, `power_per_doubling` — power
required to double the value, default 10) existing at all (registered in the admin,
singleton-guarded, in #3712; before that the required-content dashboard reported the
row missing and there was no page on which to create it) — no row means every consumer
returns its pre-#2708 number unchanged, so the migration that ships the model is inert
on landing. `intensity_multiplier` (technique grants) / `thread_level_multiplier(level)`
(thread grants) is the curve's exponent sensitivity, not an additive term — a grant
authored at sensitivity `0` (every pre-#2708 row) is inert under the curve regardless of
config-row existence. Never returns less than `base` — the curve is a pure empowerment
axis; a negative `ConditionCapabilityEffect` is still how impairment works.

**Power inputs, by grant type:**

- **Technique grants** — `world.conditions.services._technique_capability_values`
  derives power as `technique.intensity + context_free_power + contextual_thread_power`,
  computed fresh per known technique and fed to `calculate_value(effective_power=...)`.
  `context_free_power` (`CharacterThreadHandler`, memoized `@cached_property`) is
  `_derive_power(channeled_intensity=0, technique=None, applicable_threads=[]).total` —
  the character-level term plus globally-scoped condition/character modifiers, nothing
  technique- or thread-contextual. `contextual_thread_power(ctx)` sums the batched,
  level-scaled tier-0 `INTENSITY_BUMP` of every owned thread that
  `_anchor_ambiently_active` (below) confirms is genuinely engaged by `ctx` right now.
  **Deliberately excludes combat's `eff_intensity`** — a character's capability standing
  must not flicker based on whether combat happens to be running.
- **Thread-passive `CAPABILITY_GRANT` rows** — sensitivity is
  `thread_level_multiplier(thread.level)` (the same #1718 level-bucketing helper pull
  resolution uses); power is the same `context_free_power` + `contextual_thread_power`
  figure. Multiple threads granting the same capability fold by **MAX**, mirroring
  ADR-0034 individuation on the technique-grant side — never sum.

**Ambient activation** — `world.magic.services.resonance._anchor_ambiently_active` —
is the demonstrable-activation gate for the contextual thread-power term: the passive
sibling of `_anchor_in_action` (the paid-pull predicate), and deliberately a **separate
function**, not a shared one with an `ambient=` flag. A pull is paid for, so
`_anchor_in_action` lets a player *assert* involvement for anchor kinds with no anchor in
the action graph (GIFT, RELATIONSHIP_*); a free passive contribution costs nothing, so
every arm of `_anchor_ambiently_active` tests real state instead — a GIFT arm checks the
involved technique's actual gift, a SANCTUM arm checks the character's actual current
room, a FACET arm checks actually-worn items. Nine arms total (COVENANT_ROLE, TECHNIQUE,
GIFT, TRAIT, SANCTUM, RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE, FACET, MANTLE);
`ORGANIZATION` deliberately returns `False` (needs-design follow-up — `PullActionContext`
carries no org/mission marker yet). The canonical case this predicate exists to catch: a
pyromancer's fire-gift thread must not raise their ability to climb a wall.

`get_effective_capability_value(sheet, capability, *, action_ctx=None)` (the agency
oracle, `world/conditions/services.py`) threads an optional real `PullActionContext`
through to the technique-grant power derivation above. Full detail (severity-scaling fix
on `ConditionCapabilityEffect`, the ambient-default fallback and its `TRAIT`-thread
limitation, the ORGANIZATION deferral, the two-grant-path disambiguation) lives in
`docs/systems/conditions.md`'s "Capability magnitude curve" section and
`docs/adr/0169-capability-magnitude-curves-geometrically-with-contextual-power.md`.

**Not the same mechanism as a paid pull's `CAPABILITY_GRANT`.** `resolve_pull_effects`
(tiers 0-3, feeding `CombatPull`/`CombatPullResolvedEffect` — see "Thread Pull —
Declaration Modifier" below) still treats `CAPABILITY_GRANT` as binary, gated only by
`min_thread_level`; it does not read `capability_grant_value` and is unaffected by this
curve. The two paths answer different questions from the same authored row: "is the
capability granted for this committed pull" (pull-commit) vs. "what is this capability's
standing value right now" (the oracle read above).

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

aura, created = CharacterAura.objects.get_or_create(character=character)
if created:
    set_aura_shares(aura, starting_aura_shares(None))  # 80 Primal / 20 Abyssal
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
    "target_relationship",
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
| `/styles/` | GET | List technique styles (the catalog a `Path` points at) |
| `/effect-types/` | GET | List effect types |
| `/restrictions/` | GET | List DESIGN-kind restrictions only (the builder catalog); PRICE-kind rows never appear here (#4099 final fix) |
| `/facets/` | GET | List facets (flat vocabulary, #3776) |
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
| `/character-anima/` | GET/POST/PATCH | Character anima pool (`band` — qualitative `anima_band_for` word, #1446) |
| `/character-anima-rituals/` | GET/POST/PATCH/DELETE | Character's rituals |
| `/character-facets/` | GET/POST/PATCH/DELETE | Character facet assignments |
| `/techniques/` | GET/POST/PATCH | Character techniques |
| `/techniques/author/` | POST | Author a technique via `AuthorTechniqueAction`; 201/400/403 |
| `/techniques/price/` | POST | Dry-run budget breakdown (read-only) |

### Technique Progress / Training Session (#2739)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/technique-progress/` | GET | The acting character's own `TechniqueProgress` meters (`X-Character-ID` header, mirrors `MotifStyleViewSet`'s scoping) — bare array, not paginated |
| `/technique-progress/{technique_id}/train/` | POST | Runs one training session via `TrainTechniqueAction`; body `{ap_to_invest?}`. `{technique_id}` is the `Technique` pk, not the meter's own pk — a technique with no meter fails 400 with the action's own message, never a 404 |

Telnet parity: `train <technique> [=<ap>]` / bare `train` for the meter list (`CmdTrain`).

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
| `/threads/` | POST | Weave a new thread. Body must include `character_sheet_id`; serializer delegates to `weave_thread`. For `target_kind=RELATIONSHIP_TRACK`, `target_id` is the `RelationshipType` **catalog** id (not a relationship row pk) and `target_persona_id` (required, that kind only) names the partner — see the RELATIONSHIP_TRACK contract note below (#2159, #3957) |
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
  `WeavingUnlockMissing`, `RelationshipBondNotOwned`, `XPInsufficient`,
  `RitualComponentError`). Views surface those messages as HTTP 400 detail
  (never raw `str(exc)`).
- **RELATIONSHIP_TRACK catalog-id contract (#2159, retargeted #3957).** `target_id` for a
  RELATIONSHIP_TRACK weave is the `RelationshipType` catalog id, never a relationship row
  pk. The request must also carry `target_persona_id` (write-only, RELATIONSHIP_TRACK only)
  naming the partner. `ThreadSerializer._resolve_relationship_track_target` resolves the
  caller's OWN side (`CharacterRelationship(source=character_sheet, target=partner_sheet,
  is_active=True)`) and refuses unless that side holds an OPEN label of that type — mirroring
  telnet's `CmdWeaveThread._resolve_track_anchor` — with a friendly, alt-safe message rather
  than a raw not-found error. The weave additionally requires the side's claimed `tier` to
  reach `RelationshipGrowthConfig.thread_min_tier` (`RelationshipTierTooLow`); soul-tether
  formation still weaves its RELATIONSHIP_CAPSTONE thread on a tier-0 tie. RELATIONSHIP_CAPSTONE
  keeps resolving by its own pk (`target_persona_id` not used).
- `weave_thread` asserts relationship-bond ownership for RELATIONSHIP_TRACK /
  RELATIONSHIP_CAPSTONE anchors (`_validate_relationship_ownership` resolves the
  side row through `relationship_side_from_row` — for RELATIONSHIP_TRACK the target IS
  that side since #3957 — and compares `side.source_id != character_sheet.pk`,
  raising `RelationshipBondNotOwned`, #2033) **after** the `ThreadWeavingUnlock`
  gate — the unlock gate alone is not sufficient because track-progress/capstone
  rows can belong to any character's relationship, but ordering the ownership
  check second means an unlocked-but-unauthorized direct-service caller sees
  `WeavingUnlockMissing` first, never confirming a foreign row's existence.
  This assertion is defense-in-depth for direct service callers only:
  `ThreadSerializer._resolve_target` (web) and the telnet `_resolve_track_anchor`
  /`_resolve_capstone_anchor` resolvers (`commands/weave.py`) both scope their
  target lookup to `relationship__source=<requesting character_sheet>`, so
  neither route can hand `weave_thread` a foreign row in the first place — a
  foreign id 400s with the same "does not exist" message a bogus id would
  produce, closing the existence/ownership oracle the unscoped lookup used to
  expose (#2033 adversarial review fix).
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

### Dramatic Moment Suggestion (#2183)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dramatic-moment-suggestions/?scene=<id>` | GET | PENDING suggestions for a scene; `IsSceneGMOrOwnerOrStaff`-gated (400 without `?scene=`, 403 if ungated) |
| `/dramatic-moment-suggestions/{id}/confirm/` | POST | Confirm — mints a `DramaticMomentTag` via `ConfirmDramaticMomentSuggestionAction` |
| `/dramatic-moment-suggestions/{id}/dismiss/` | POST | Dismiss — closes the suggestion with no reward via `DismissDramaticMomentSuggestionAction` |

Telnet parity: `moment suggestions` / `moment confirm <id>` / `moment dismiss <id>` (`CmdMoment`).

### Guided Glimpse Story (#2427)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/character-creation/glimpse-tags/` | GET | Active glimpse tag catalog (`CGGlimpseTagViewSet`, read-only, unpaginated, filterable by `?axis=`); each row embeds `suggested_distinctions`. Serves both the CG guided flow and the post-CG "finish later" surface |
| `/character-auras/{id}/set-glimpse-tags/` | POST | Body `{axis, tag_ids[]}`; replaces the aura's chosen tags for one axis |
| `/character-auras/{id}/set-glimpse-prose/` | POST | Body `{text}`; writes `glimpse_story` |
| `/character-auras/{id}/link-glimpse-distinction/` | POST | Body `{character_distinction_id}`; marks a distinction as born in the Glimpse |
| `/character-auras/{id}/unlink-glimpse-distinction/` | POST | Body `{character_distinction_id}`; clears the Glimpse provenance |

All four `CharacterAuraViewSet` actions return the updated `CharacterAuraSerializer`
payload; validation errors (unknown/inactive tag, cross-character link, wrong-axis
tag, arity violation) surface as HTTP 400 detail.

---

## Frontend Integration

### Types
`frontend/src/character-creation/types.ts`
- `Affinity`, `Resonance`, `Gift`, `GiftListItem`, `AnimaRitualType`

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

### Guided Glimpse Story (#2427)
- `GlimpseFlow` (`frontend/src/magic/components/glimpse/GlimpseFlow.tsx`) — shared,
  purely presentational guided flow; two mounts:
  - `GlimpseSection` (`frontend/src/character-creation/components/gift/GlimpseSection.tsx`)
    — CG mount inside `GiftStage`
  - `GlimpseEditorDialog` (`frontend/src/magic/components/glimpse/GlimpseEditorDialog.tsx`)
    — "finish later" dialog on the own-character sheet, mounted from `SpellbookTab`

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
- **Sanctification requires real components (#707 — ADR-0087)** — both Sanctification `Ritual` rows
  (Personal + Covenant) carry seeded `RitualComponentRequirement` rows (a touchstone tied to the
  founding Resonance + three generic reagents; see "Touchstones + reagents" above).
  `sanctum_install` validates/consumes them via `resolve_and_consume_ritual_components` before
  calling `perform_sanctification`. `CmdSanctum`'s `install` subverb auto-gathers everything the
  caller is carrying (`_gather_components`, mirrors `CmdRitual`); the web `install` endpoint takes
  an explicit `components` list of the caller's own `ItemInstance` pks
  (`SanctifyActionSerializer.components`).
- **Currency has no cap** - `CharacterResonance.balance` grows freely; the strategic tension is over allocation, not over a ceiling.
- **Pull-cost tuning surface** - `ThreadPullCost` rows hold per-tier numbers; the cost *formula shape* lives in `spend_resonance_for_pull`. Both the model docstring and service docstring cross-reference this split.
- **SoulTetherConfig tuning** - `SoulTetherConfig` singleton (pk=1) holds all Soul Tether tuning knobs (sineating costs, rescue budgets/thresholds). Read via `get_soul_tether_config()`. Staff-tunable via admin.
- **SOUL_TETHER_DISSOLVED** - Emitted by `dissolve_soul_tether` in `flows/constants.py` after bond dissolution.
- **CharacterSheet.get_tether_strain_stage()** - Returns the Sineater's current Tether Strain stage. Used by sineating offer payloads.
- **SharedMemoryModel** - All lookup tables + identity rows use Evennia's identity-map cache
- **Affinity/Resonance are domain models** - First-class models in this app with optional OneToOne links to `ModifierTarget` for modifier integration
- **Techniques are player-created** - Unlike lookup tables, techniques are unique per character
- **CG picks from a staff-authored catalog** - the magic stage links a catalog `Gift` +
  `Technique`s (#2426); it never mints new `Gift`/`Technique` rows at CG time
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


## Appetites: the anima feeding economy (#2853, ADR-0182)

- **Models** (`models/appetites.py`): `AppetiteUpkeep` (Distinction-keyed periodic drain:
  period DAILY/WEEKLY, amount, floor_percent), `AppetiteUpkeepReceipt` (per-holder-per-period
  idempotency), `FeedingRecord` (the audit row: feeder, victim, mode, lost_control,
  anima_taken, glut_gained, victim_fatigue, was_lethal). `CharacterAnima.glut` — decaying
  overfill (`effective_current` spends glut first; `clean()`'s current ≤ maximum stays).
- **Services**: `services/appetites.py` — `appetite_holder_sheet_ids` (the anima-regen
  skip-set: appetite holders never regen naturally), `appetite_upkeep_tick`, `decay_glut_tick`,
  `hunger_severity`, `reconcile_ravenous`; crons `magic.appetite_daily` / `magic.appetite_weekly`
  (DRAIN phase). `services/feeding.py` — `feed_anima(feeder, victim, amount_mode=SIP|DRINK|GORGE)`
  (sineating inverted; SIP non-fatal by construction; Ravenous restraint check may escalate to
  GORGE; NPC gorged past empty dies via `vitals.mark_fed_to_death` + a concealed murder-tagged
  deed with scene evidence), consent resolvers for the `feed`/`drain` action keys (registered in
  `world.magic.apps.ready()`; NPC targets auto-resolve, PC targets need consent — `drain` category
  under the antagonism root).
- **Actions/commands**: `FeedAction`/`DrainAction` (`actions/definitions/appetites.py`) — the
  NPC-direct path with explicit mode; telnet `feed`/`drain` (`commands/consent.py`) branch on
  target: PC → consent request, NPC → direct with `= sip|drink|gorge`.
- **Glut → sun**: appetite holders subtract `glut × factor` from felt sun exposure through the
  magic-mitigation lane (never clears a bane's shade-only floor). See ADR-0179/0180/0182.
- Regen note: daily regen now floors at 1 point when enabled — integer percent of the standard
  10-point pool used to floor to 0 (regen was silently inert).

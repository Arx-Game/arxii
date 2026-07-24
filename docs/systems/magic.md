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
| `Technique` | A specific magical ability within a Gift | `name`, `gift` (FK), `style` (FK to TechniqueStyle), `effect_type` (FK to EffectType), `restrictions` (M2M), `level`, `intensity`, `control`, `anima_cost`, `creator`, `target_type`, `reach`, `archetype_alignment` (#2529 — `RoleArchetype` choices, default CROWN, migration-seeded from `effect_type.category`: attack→sword, defense→shield, else→crown; which SWORD/SHIELD/CROWN blend axis of an engaged covenant role boosts this technique's cast). Natural key `(gift, name)`, backed by `unique_technique_gift_name` (#2474 — `name` alone is not globally unique; lore reuse or a player-crafted technique can share a name across gifts). Unique per `(gift, name)` |

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
distinction suggestions surfaced along the way. #2611 added the TRIGGER axis
(what *caused* the awakening) and path-gated tag filtering.

**Models** (`models/glimpse.py`):

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `GlimpseTag` | Authored catalog choice, one per axis. Content model — `CONTENT_MODELS` (`magic.glimpsetag`), lore-repo authored, no factory-seeded catalog | `axis` (`GlimpseTagAxis`), `name`, `slug` (natural key), `description`, `example`, `sort_order`, `is_active`, `paths` (M2M to `classes.Path`, empty = all paths; #2611) |
| `CharacterGlimpseTag` | A character's chosen tag. Instance data — never exported | `aura` FK (`CharacterAura`, `related_name="glimpse_tags"`), `tag` FK (PROTECT); unique per `(aura, tag)` |
| `GlimpseTagDistinctionSuggestion` | Curated tag→distinction suggestion. Content model (`magic.glimpsetagdistinctionsuggestion`) — grants nothing, purely a CG-flow suggestion surface. FK points *into* `distinctions.Distinction` (specific→general, ADR-0010) | `tag` FK (CASCADE), `distinction` FK (CASCADE), `sort_order`; unique per `(tag, distinction)` |

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
- `set_glimpse_prose(aura, text: str) -> None` — writes `glimpse_story` and
  calls `refresh_glimpse_state`.
- `link_distinction_to_glimpse(character_distinction: CharacterDistinction, aura: CharacterAura) -> None`
  — sets `from_glimpse`; raises `ValidationError` if the distinction and aura
  belong to different characters.
- `unlink_distinction_from_glimpse(character_distinction: CharacterDistinction) -> None`
  — clears `from_glimpse`.

**CG finalize wiring** (`world/character_creation/services.py`,
`finalize_magic_data`) — after creating `CharacterAura`, three `draft_data`
keys are consumed through
the glimpse services above (never written directly to the aura/tag rows):
`glimpse_tag_ids` (list of `GlimpseTag` ids, grouped by axis and passed to
`set_glimpse_tags` per axis), `glimpse_story` (passed to `set_glimpse_prose`,
defaults to `""`), `glimpse_linked_distinction_ids` (catalog `Distinction`
ids — resolved to the character's own `CharacterDistinction` rows by
`distinction_id__in=`, then passed to `link_distinction_to_glimpse`).

**API surfaces:**

- **CG catalog** — `GET /api/character-creation/glimpse-tags/`
  (`CGGlimpseTagViewSet`, read-only, unpaginated, filterable by `?axis=` and
  `?path_id=<N>`). The `path_id` filter (#2611) excludes tags whose `paths`
  M2M is non-empty and does not contain the given path — used by the CG flow
  to hide path-restricted trigger tags (e.g. "Patron Chose You" is Path of
  the Chosen only). Omitting `path_id` returns all tags (post-CG editor mode).
  Global authored catalog, not draft-dependent, so the same endpoint also
  backs the post-CG "finish your glimpse later" surface. Each row embeds its
  `suggested_distinctions` (prefetched `GlimpseTagDistinctionSuggestion` rows,
  ordered) via `CGGlimpseTagSerializer`.
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

**Frontend** — one shared, purely presentational guided flow with two mounts
(see `frontend/src/magic/CLAUDE.md` for the full contract):

- `GlimpseFlow` (`frontend/src/magic/components/glimpse/GlimpseFlow.tsx` +
  `glimpseTypes.ts`) — accordion of axis steps (TONE single-select,
  CONSEQUENCE/WITNESS multi-select; axes with zero catalog tags don't render a
  step), SENSORY as toggle chips inside the always-visible story textarea, a
  deduped suggestion panel, and a manual distinction-link fallback. No
  queries/mutations inside — purely props-in/callbacks-out.
- `GlimpseSection` (`frontend/src/character-creation/components/gift/GlimpseSection.tsx`)
  — the CG mount, binding `GlimpseFlow` to `draft_data.glimpse_tag_ids` /
  `glimpse_linked_distinction_ids` (prose stays on `GiftStage`'s
  `register('glimpse_story')`).
- `GlimpseEditorDialog` (`frontend/src/magic/components/glimpse/GlimpseEditorDialog.tsx`)
  — the "finish later" editor on the own-character sheet, opened from
  `SpellbookTab`'s aura card, gated on `isMyCharacter && aura.can_finish_glimpse`.
  Writes through the four aura actions above.

**Out of scope (verified against code, not deferred by accident):** no
mechanics hooks off tag picks, no LLM involvement anywhere in the flow, no new
privacy axis beyond the existing WITNESS tags, and no authored `GlimpseTag`/
`GlimpseTagDistinctionSuggestion` rows ship with this repo (lore-repo content,
authored later) — the flow renders gracefully with an empty catalog (axes with
no tags simply don't render a step).

### Content-vs-config boundary in the dev seed (#2474, ADR-0142)

`seed_dev_database()` (`world/seeds/database.py`) now sequences: (1) resolve
`CONTENT_REPO_PATH` via `core_management.content_repo.resolve_content_root()` —
raises `ContentError` immediately if unset/missing, before anything else runs; (2)
seed config prerequisites the content fixtures FK by natural key — currently just
`world.magic.seeds_cast.ensure_technique_cast_content()`, since lore-repo
`Technique` fixtures FK the shared "Technique Cast" `ActionTemplate` and the
content load's own deferred-retry loop can't conjure a config row the content/grid
load itself never creates; (3) `load_world_content()`; (4) the `CLUSTER_SEEDERS`
loop. NPC trainer seeds (`world/npc_services/seeds.py`) resolve their starter
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
| `get_character_anima_ritual(character)` | `services/anima.py` | Retrieves the character's personal SCENE_ACTION `Ritual` (their anima ritual) |
| `provision_player_anima_ritual(...)` | `services/anima.py` | Points `RitualCheckConfig.check_type` at the per-character check so ritual and technique casts share the same roll |
| `ensure_technique_catalog_content()` | `seeds_cast.py` | Idempotent seed: curated catalog of consequence-pool flavors (children of the base pool) + matching ActionTemplates |
| `resolve_cast_action_template()` | `services/technique_builder.py` | Resolves a chosen catalog pool id (or `None`) to the ActionTemplate a Technique's `action_template` should point at |

Cast resolution (`world/scenes/cast_services.py:_resolve_cast`) passes the caster's personal
check into `start_action_resolution` via the `check_type` override (optional kwarg added to
`src/actions/services.py`). No schema migration — all seeded via `ensure_technique_cast_content()`.

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
`TechniqueFunction` vocabulary (`constants.py`, 13-value `TextChoices` — also consumed
by Layer 4's situational perks, #2536) rather than the coarser SWORD/SHIELD/CROWN axis
Layer 1 reads.

For each of `character.covenant_roles.currently_engaged_roles()`, the term collects
`covenants.CovenantRoleTechniqueSpecialty` rows from the anchor role **plus** the
resolved sub-role's own rows when it differs (both role ids go into one lookup), filtered
to functions the cast technique carries (`technique.cached_function_tags`), and sums
`total_thread_level_across_all_kinds(sheet) × row.multiplier_tenths / 10` per matching
row. Returns 0 when the technique carries no `TechniqueFunctionTag`, no role is engaged,
or no specialty row matches. **Sub-role rows ADD to the anchor's — they are never
normalized away** — the opposite of the anchor-only rule
`covenant_role_action_scaling_bonus` uses; a promoted (specialized) member reads as
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
| `protective_condition_and_flavor(technique) -> tuple[ConditionTemplate, str] \| None` (#2207) | Classifies a technique's reactive-trigger handler into `barrier`/`blink`/`redirect` by walking `condition_applications → condition.reactive_triggers → flow_definition.steps` (one batched Prefetch query); returns the matched `ConditionTemplate` too, since combat's guardian resolution needs its `reactive_anima_cost`. No new authored field — derives from the existing effect-palette data. |
| `protective_flavor(technique) -> str \| None` (#2207) | Thin wrapper over `protective_condition_and_flavor` returning only the flavor string; used by `declare_interpose`'s declaration-time gate (combat, `world/combat/services.py`) |

**Consent routing** (in `world/scenes/cast_services.py:request_technique_cast`):
- Hostile → `seed_or_feed_encounter_from_cast` (combat).
- Benign + behavior-altering → PENDING `SceneActionRequest` (consent required).
- Benign + capability/stat → resolves immediately, including on other PCs.
- **Any benign cast that affects an ACTIVE combatant** seats the caster in
  that combatant's encounter (#2226, ADR-0119) — via
  `seat_caster_for_benign_intervention`, called post-resolution on both the
  immediate and consent-accept paths. Risk acknowledgement is automatic.

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

### Motif System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Motif` | Character-level magical aesthetic | `character`, `name`, `description` |
| `MotifResonance` | Resonances in a motif | `motif`, `resonance` (FK to ModifierTarget) |
| `MotifResonanceAssociation` | Links resonances to facets in a motif | `motif_resonance`, `facet` |
| `MotifResonanceStyle` | Player binding of a `Style` to one of the character's motif resonances (cap 3 per resonance, `MotifResonanceLink.clean()`-enforced) | `motif_resonance`, `style` (FK to `items.Style`) |
| `CharacterFacet` | Links characters to facets | `character`, `facet`, `resonance` |

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
| `SignatureMotifBonus` | Staff-authored bonus gated on the character's Motif | `name`, `narrative_snippet`, `required_facet` FK (Facet, nullable), `required_resonance` FK (Resonance, nullable), `flat_intensity_delta` (SmallInt, additive to effective intensity). At least one gate must be set (`clean()` enforces). AND semantics when both gates set. |
| `SignatureMotifBonusCapabilityGrant` | Capability granted by a bonus (inherits `AbstractCapabilityGrant`) | `signature_bonus` FK |
| `SignatureMotifBonusDamageProfile` | Damage profile for a bonus (inherits `AbstractDamageProfile`) | `signature_bonus` FK |
| `SignatureMotifBonusAppliedCondition` | Applied condition for a bonus (inherits `AbstractAppliedCondition`) | `signature_bonus` FK |

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
| `signature_damage_profiles(character, technique) -> list` | (#1728) Returns `bonus.cached_damage_profiles` or `[]`; `CombatTechniqueResolver._apply_damage` (`world/combat/services.py`) appends these to the technique's own profiles before resolving damage |
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
(`world/combat/services.py`).

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

**Deferred fast-follow (NOT shipped as of #1728):**
- `capability_grants` cast seam — no general technique-authored capability grant seam
  exists anywhere yet, so `SignatureMotifBonusCapabilityGrant` rows remain inert.

**Shipped in #1728** (see `docs/adr/0072-...` addendum): the `damage_profiles` combat
cast seam, combat cosmetic narration, and the web `SignatureViewSet`.

### Threads as Currency Consumers (Resonance Pivot Spec A §2.1)

The legacy 5-axis `Thread` / `ThreadType` / `ThreadJournal` / `ThreadResonance`
family was deleted in favor of a discriminator + typed-FK design. A Thread is
owned by a CharacterSheet, channels a single Resonance, and is anchored to
exactly one of: Trait / Technique / Facet / RelationshipTrackProgress /
RelationshipCapstone / CovenantRole / Mantle / SanctumDetails. The bare ROOM
`target_kind` was removed; SANCTUM is the leveled room anchor.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Thread` | Per-character attachment to one anchor that channels one Resonance | `owner` FK CharacterSheet, `resonance` FK, `target_kind`, `target_trait` / `target_technique` / `target_facet` / `target_relationship_track` / `target_capstone` / `target_covenant_role` / `target_gift` / `target_mantle` / `target_sanctum_details` (exactly one populated per kind), `name`, `description`, `developed_points`, `level`, `created_at`, `updated_at`, `retired_at` (soft-retire), `slot_kind` (SANCTUM only: PERSONAL_OWN / COVENANT / HELPER), `signature_bonus` (nullable FK to `SignatureMotifBonus`, PROTECT — only settable on TECHNIQUE-kind threads, enforced by `clean()` + `CheckConstraint`, #1582 ADR-0072) |
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
| `RitualComponentRequirement` | Items required to perform a Ritual | `ritual` FK, either `item_template` FK (template-mode) or `min_touchstone_tier` FK to `ResonanceTier` (touchstone-mode — exactly one of the two set, enforced by `CheckConstraint`), `quantity`, optional `min_quality_tier` FK, `authored_provenance` |
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
(`thread.target_relationship_track.relationship.target`), or holds an active,
mutually-consented (`is_active=True, is_pending=False`), net-negative
`CharacterRelationship.affection` toward them (hostile — "threatening"). The
shared `_relationship_pull_would_trigger(x_sheet, y_sheet)` helper decides this
for both the resolution path and the picker, mirroring
`_regard_polarity_matches`'s role for Court modulation.

Unlike Court modulation, there is **no polarity gate** — `ThreadPullEffect.regard_polarity`
is not consulted at all. This is a deliberate divergence (ADR-0092): Court modulates
an NPC master's preference (narrative consistency demands sign-matching), while
this rule rewards any PC-to-PC relationship investment unconditionally (rival or
lover alike).

Magnitude: `bonus = round(cap × S / (S + half_saturation))` where `S = coefficient
× CharacterRelationship(source=owner, target=threaded_person).developed_absolute_value`
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
  where `S = fraught_coefficient × min(pos_sum, neg_sum)`, and `(pos_sum, neg_sum) =
  bond.developed_signed_sums` (`world/relationships/models.py` — a `(positive_sum,
  negative_sum)` split of the same `developed_points` measure `developed_absolute_value`
  sums, computed off the cached `cached_track_progress` path, never a fresh query).
  Rewards a bond invested heavily in BOTH positive- and negative-sign tracks at once (a
  love/hate dynamic); a bond lopsided entirely in one direction earns nothing here, no
  matter how large.
- **Devotion** — `devotion_bonus = round(devotion_cap × S / (S + devotion_half_saturation))`
  where `S = devotion_coefficient × max(0, developed_absolute_value - devotion_threshold)`.
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
(#2035). See ADR-0110 for the rejected alternatives (`HybridRelationshipType`-driven
bonuses, sign-flip transition detection) and the cross-link to #1991 (the expression half —
a ceremony beat at RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE thread crossings; this feature
is the power half only).

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

**Cast-time variant wiring [BUILT & WIRED, #1581]:** `resolve_specialized_variant` is called
at two cast seams so unlocked variants shape every cast automatically: (1)
`get_runtime_technique_stats` (`world/magic/services/techniques.py`) — combat runtime stats;
variant `intensity`/`control` deltas reach the power ledger. (2) `_resolve_and_pose_cast`
(`world/scenes/cast_services.py`) — the non-combat standalone-cast path; variant form drives
cost, narration, and outcome. Both seams are gated on `unlock_thread_level`: below the
threshold the parent technique is returned unchanged. The dev seed (`integration_tests/game_content/magic.py`) authors
starter `TechniqueVariant` rows so a fresh dev environment has variants to exercise. The
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
- **Latent provisioning at CG** — `provision_latent_gift_thread(sheet, gift, *, resonance)`
  (`world/magic/specialization/services.py`) creates the level-0 GIFT thread at
  character-creation finalization, idempotent on `(owner, gift)` and write-once on resonance.
  Wires from `finalize_magic_data` after `CharacterGift` creation, reading the chosen
  `selected_gift_resonance_id` from `draft.draft_data` (frontend picker is built #1620;
  the `GiftStage` funnel writes the key, #2426 Task 10; `compute_magic_errors` requires it.
  Legacy/absent draft data falls back to `gift.resonances.first()`).
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
gift — added to `_ALWAYS_IN_ACTION_KINDS`). The frontend CG resonance picker is built (#1620).

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
Unbound `BeginningTradition` row now carries `required_distinction=<Unbound drawback>`
(`seed_beginning_traditions`, was `None` pre-#2442); `select_tradition`
(`world.character_creation.views`) auto-adds the drawback to the draft when selecting Unbound
without it already held — a one-off exception to #2426's normal "must already hold it" gate,
needed because Unbound is CG's tradition-agnostic default (Orphaned Tradition/Metallic Order
keep the un-auto-added behavior — that gate is a deliberate story pick, #2428 Task 5). Shed
automatically via `world.magic.services.tradition_membership.join_tradition` and re-applied by
`leave_tradition` (#2441 Task 8/9) — the underlying `CharacterModifier` row cascade-deletes with
the `CharacterDistinction` row (`ModifierSource.character_distinction` is `on_delete=CASCADE`),
so the surcharge disappears the moment the drawback is shed, no separate cleanup needed.

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

### Audere & Audere Majora (models/audere.py, audere_majora.py)

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

### Dramatic Moment Tagging (#545 / #1139)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DramaticMomentType` | Staff-authored lookup inheriting `RenownAwardConfig`. Describes a taggable scene moment category. | `label`, `description`, `resonance` FK, `resonance_amount` (default 15), `per_scene_cap` (default 1), plus inherited `magnitude`/`risk`/`reach`/`archetypes` |
| `DramaticMomentTag` | Per-event record of a staff tag on a character in a scene | `moment_type` FK, `character_sheet` FK, `scene` FK (nullable/SET_NULL), `tagged_by` FK AccountDB (PROTECT), `interaction` FK (nullable/SET_NULL, `db_constraint=False` — partitioned table), `interaction_timestamp` (denormalized), `tagged_at` |

**Admin:** `DramaticMomentTypeAdmin` — full CRUD (staff author the catalog); `DramaticMomentTagAdmin` — read-only for provenance audit.

**Context fields on scenes serializers:** `SceneDetailSerializer.viewer_can_gm` (bool — True when the requesting user is the scene's GM, owner, or staff; controls GM control visibility); `InteractionSerializer.dramatic_moment_tags` (list — tags anchored to the pose; drives the interaction badge); `SceneParticipationSerializer.dramatic_moment_count` (int — per-participant tally in the scene).

#### Dramatic Moment Suggestion — the technique-entrance recognition bridge (#2183)

A **Technique Entrance** (see below) that clears an authored success-level threshold does not
auto-tag — it creates a `DramaticMomentSuggestion` a GM later confirms (minting a real
`DramaticMomentTag`, with the usual resonance grant + renown award) or dismisses. See
ADR-0113 for why recognition stays a human-adjudicated nudge rather than a mechanical
auto-grant.

**Knobs on `DramaticMomentType`:**
- `suggest_on_technique_entrance` (bool, default False) — opts this moment type into the
  technique-entrance bridge at all.
- `suggestion_min_success_level` (`PositiveSmallIntegerField`) — the cast success level that
  must be cleared (`>=`) for a suggestion to fire.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DramaticMomentSuggestion` | GM-facing PENDING suggestion surfaced by a high-success technique entrance | `moment_type` FK (PROTECT), `character_sheet` FK (CASCADE), `scene` FK (nullable/SET_NULL), `interaction` FK (nullable/SET_NULL, `db_constraint=False` — the entrance pose that triggered it), `interaction_timestamp` (denormalized), `success_level`, `status` (`SuggestionStatus`: PENDING/CONFIRMED/DISMISSED), `resolved_by` FK AccountDB (PROTECT), `confirmed_tag` OneToOneField → `DramaticMomentTag` (the tag minted on confirmation, if any). Unique constraint: one PENDING suggestion per `(moment_type, character_sheet, scene)`. |

**Services (`services/gain.py`):**
- `maybe_suggest_dramatic_moments(*, character_sheet, scene, success_level, interaction=None) -> list[DramaticMomentSuggestion]`
  — scans `DramaticMomentType` rows flagged `suggest_on_technique_entrance` whose
  `suggestion_min_success_level <= success_level`; for each, skips if the character hasn't
  claimed the type's resonance, or if `per_scene_cap` real tags are already spent for this
  `(moment_type, scene)`; otherwise `get_or_create`s a PENDING suggestion (idempotent — a
  second qualifying cast in the same scene does not duplicate it). No-ops (`[]`) when
  `scene` is `None` — a suggestion is scene-scoped, same as the tag cap it mirrors.
- `resolve_dramatic_moment_suggestion(suggestion, *, resolver, confirm) -> DramaticMomentSuggestion`
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
.get_viewer_can_gm`: staff, or `scene.is_gm(account)`, or `scene.is_owner(account)`.

**Web:** `DramaticMomentSuggestionViewSet` (`world/magic/views.py`) —
`GET /api/magic/dramatic-moment-suggestions/?scene=<id>` (PENDING suggestions for a scene,
same GM/owner/staff gate as list); `POST .../{id}/confirm/` / `POST .../{id}/dismiss/`
dispatch the REGISTRY actions above.

**Telnet:** `CmdMoment` (`commands/dramatic_moments.py`, key `"moment"`) — `moment
suggestions` (PENDING suggestions for the active scene here), `moment confirm <id>`,
`moment dismiss <id>`. Account-authorized like the web surface (`account=self.caller.account`).

**Frontend:** `DramaticMomentSuggestionChip` (`frontend/src/scenes/components/`), mounted
in `PoseUnit` for the caller's own entrance poses.

**Seed content:** `ensure_dramatic_entrance_content()` (`world/magic/factories.py`) seeds the
"Grand Entrance" `DramaticMomentType` (self-contained — get-or-creates its own "Fervor"
Resonance + "Celestial" Affinity by name, mirroring `seeds_touchstone_content
.ensure_touchstone_content`) with `suggest_on_technique_entrance=True` and
`suggestion_min_success_level=3` — framework-proving content so the bridge has something real
to surface, not only under test factories.

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
`ensure_portal_travel_content()`, called from `seed_magic_dev()`): a "Mirror"
`PortalAnchorKind`; a self-contained "Reflection" Resonance (Celestial affinity) carried by a
new MINOR `Gift` "Mirrorwalking"; a "Mirrorwalk" `Technique`
(`travel_anchor_kind=Mirror`, `anima_cost=0`, reusing the "Translocation Stance" style and
"Teleport" `EffectType`); a `GiftUnlock` row gating it behind `xp_cost=50` (mirrors the two
other single-purpose magic unlocks this module seeds); and starter Mirror `PortalAnchor` rows
in the seeded magic-story cascade rooms ("The Hallowed Threshold (Low)", "The Resonant
Sanctum (Aligned)") so the network is reachable, not just cataloged. Idempotent throughout
(`get_or_create`).

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
ALLY), `minimum_success_level` (default 1). UniqueConstraint on
`(technique, treatment_template)`. Mirrors the `TechniqueAppliedCondition` /
`TechniqueRemovedCondition` pattern.

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
`TechniqueTreatment` rows. Draft workbench: `TechniqueDraftTreatment` +
`add_draft_treatment` / `remove_draft_treatment` / `draft_to_design` conversion.

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
| Phase Jump | Phase Jump | `move_position_on_condition` adapter | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |
| Barricade | Barricade | `create_obstacle_on_condition` adapter | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |
| Ghostform | Ghostform | intangibility category only (`grants_intangibility=True`) | `ConditionCategory`; intangibility gate via `is_untargetable` |
| Earthmeld | Earthmeld | intangibility category only (1-round duration) | `ConditionCategory`; as Ghostform |
| Force Grip | Force Grip | `move_position_on_condition` adapter (ENEMY target) | CONDITION_APPLIED; **runtime destination wired for combat, #2206** |

**Runtime destination selection (#2206 — supersedes the old placeholder-destination
follow-up note):** Phase Jump, Barricade, and Force Grip still embed
`destination_position_id=0` at seed time (`ensure_effect_palette_content()`), but that
value is now only ever a fallback — for **combat**, the player picks a real position at
declaration time. `CombatRoundAction` carries three nullable FKs to `areas.Position`:
`cast_destination` (Phase Jump / Force Grip — single point) and `cast_position_a`/
`cast_position_b` (Barricade — an endpoint pair). `resolve_cast_position_params`
(`world/combat/services.py`) validates the declared position(s) against the encounter's
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
- `OUTFIT_TRICKLE` — outfit presentation trickle (see `docs/architecture/items-fashion-mantles.md`).
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
  `ResonanceGrant.source_project`) and is exception-guarded so a payout failure
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

`CharacterAura`'s stored celestial/primal/abyssal percentages are a write-through cache,
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
event). Compound gates reuse the achievement's own `AchievementRequirement` rows.

Missions is the first deed source to grant morally-typed resonance:
`MissionOptionRouteReward.resonance` (author-set, required when `sink=RESONANCE`) flows
through `MissionDeedRewardLine.resonance` to the reward cron's `_grant_resonance`, which
calls `grant_resonance(..., source=GainSource.MISSION_REWARD)`. This closes the
RESONANCE half of `docs/plans/2026-05-18-missions-design.md` §13.3 (LEGEND_POINTS
remains a separate, still-open stub).

Note: `get_aura_percentages()`/`CharacterAffinityTotal` — unwired legacy code from
before `CharacterAura`'s stored-percentage mechanism existed — were removed in
#1739. `recompute_aura` never used them.

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
`TechniqueFunctionTag`), `TechniqueStyle`, `Restriction`, `EffectType`, `PortalAnchorKind`,
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
(`achievements.Achievement` also gained a name natural key this branch but is not itself
in `CONTENT_MODELS`). `load_entries` (`core_management/content_fixtures.py`) upserts by
natural key. There is no in-repo seed catalog to fall back on: the lore repo is the
single source (`seed_starter_gift_catalog()` was retired by #2474 — see "CG Starter
Gift/Technique Catalog" and "Content-vs-config boundary in the dev seed" above for the
seed-vs-content sequencing, which seeds the "Technique Cast" `ActionTemplate` config
prerequisite before `load_world_content()` runs, and ADR-0142 for the rationale).
The deferred-retry loop resolves load-order gaps *within* the content/grid load; it
cannot conjure a config row the load itself never creates — which is why the config
prerequisites run first in that sequence.

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
| `/character-anima/` | GET/POST/PATCH | Character anima pool (`band` — qualitative `anima_band_for` word, #1446) |
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
| `/threads/` | POST | Weave a new thread. Body must include `character_sheet_id`; serializer delegates to `weave_thread`. For `target_kind=RELATIONSHIP_TRACK`, `target_id` is the `RelationshipTrack` **catalog** id (not a `RelationshipTrackProgress` pk) and `target_persona_id` (required, that kind only) names the partner — see the RELATIONSHIP_TRACK contract note below (#2159) |
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
- **RELATIONSHIP_TRACK catalog-id contract (#2159).** `target_id` for a RELATIONSHIP_TRACK
  weave is the `RelationshipTrack` catalog id, never a `RelationshipTrackProgress` pk — no
  API exposes that pk (`RelationshipTrackProgressSerializer` has no id field). The request
  must also carry `target_persona_id` (write-only, RELATIONSHIP_TRACK only, same Persona-pk
  convention `RelationshipUpdateViewSet._resolve_target_sheet` uses) naming the partner.
  `ThreadSerializer._resolve_relationship_track_target` resolves the caller's own
  `RelationshipTrackProgress` by `(relationship__source=character_sheet,
  relationship__target=partner_sheet, track_id=target_id)` and never creates a progress row
  — mirroring telnet's `CmdWeaveThread._resolve_track_anchor` — surfacing a friendly message
  when the pair has no developed history on that track yet, instead of a raw not-found error.
  RELATIONSHIP_CAPSTONE keeps resolving by its own pk (`target_persona_id` not used).
- `weave_thread` asserts relationship-bond ownership for RELATIONSHIP_TRACK /
  RELATIONSHIP_CAPSTONE anchors (`target.relationship.source == character_sheet`,
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

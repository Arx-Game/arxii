# Species System

Species/race definitions with stat bonuses, subspecies hierarchy, and starting language assignments.

**Source:** `src/world/species/`

---

## Enums

The species app has no local enums. Stat bonuses reference `PrimaryStat` from the traits system:

```python
from world.traits.constants import PrimaryStat
# STRENGTH, AGILITY, STAMINA, CHARM, PRESENCE, PERCEPTION, INTELLECT, WITS, WILLPOWER
```

---

## Models

All models use `NaturalKeyMixin` (fixture support). `Species` and `Language` use `SharedMemoryModel` (cached).

### Lookup Tables (SharedMemoryModel)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Species` | Core species/subspecies with optional parent hierarchy | `name`, `description`, `parent` (FK self), `sort_order`, `starting_languages` (M2M to Language) |
| `Language` | Languages available in the game | `name`, `description` |

### Per-Species Data (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SpeciesStatBonus` | Permanent stat modifier for a species | `species` (FK), `stat` (PrimaryStat choices), `value` (SmallInt) |

### Species Gift Grants (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SpeciesGiftGrant` | A Minor Gift (and optional drawback/benefit) a species grants its members (ADR-0050) | `species` (FK), `gift` (FK to `magic.Gift`, must be `kind=MINOR`), `drawback_condition` (FK to `conditions.ConditionTemplate`, nullable — permanent negative condition applied at CG finalize, e.g. sunlight vulnerability), `benefit_condition` (FK to `conditions.ConditionTemplate`, nullable — permanent beneficial condition applied at CG finalize, e.g. a resist-check bonus, #1738), `drawback_distinction` (FK to `distinctions.Distinction`, nullable — forced drawback distinction applied at CG finalize, a social/reputation price rather than a mechanical one), `cg_point_cost` (PositiveInteger, default 0 — CG points charged for this grant) |

`provision_species_gifts` (`world.species.services`) mints the gift and applies
`drawback_condition`, `benefit_condition`, and `drawback_distinction` idempotently
at CG finalization — see
`docs/adr/0071-species-gift-drawbacks-mitigated-by-gift-thread.md`. The forced
distinction is granted via `world.distinctions.services.grant_distinction` with
`origin=DistinctionOrigin.SPECIES`.

`SpeciesGiftGrant` expresses species balance in four independent shapes, freely
combinable per grant (all four fields default to null/0, so an "empty" grant is
a free weak gift with no attached price):

- **Condition drawback** — `drawback_condition` set (mechanical downside, e.g.
  sunlight vulnerability).
- **Benefit condition** — `benefit_condition` set (mechanical upside, e.g. a
  resist-check bonus).
- **Drawback distinction** — `drawback_distinction` set (social/reputation
  downside, e.g. feared-and-distrusted, rather than a mechanical one).
- **CG point cost** — `cg_point_cost` > 0 (a straight points price; summed
  across the selected species + its ancestors into the `"species"` line of
  `CharacterDraft.calculate_cg_points_breakdown()` — see
  [character_creation.md](character_creation.md)).

Which species uses which shape (or combination) is **lore-repo content** — this
app never authors species/gift/distinction data itself. (Exception: the
`Bane: Sunlight` / `Allergy: Sunlight` Distinction anchor rows are seeded
unconditionally by `ensure_sunlight_distinctions()` because the sun-exposure
mechanics resolve against them; the species/gift rows that *use* them stay
content-owned.)

---

## Sunlight Bane & Allergy (#2846, ADR-0179; extends ADR-0073)

Sun vulnerability is a graded continuum, not a boolean:

- **`sun_exposure.felt_sun_exposure(character, room) -> SunExposure`** — one
  non-negative residual with a full breakdown: base (IC phase × sky exposure —
  `is_outdoor`, authored ROOFED/SEALED enclosure blocks; only the sun ever
  counts) − graded shade (radiant cascade `effective_value` + position
  shelter) − clothing coverage (non-revealing garments protect their equipped
  sun-relevant `BodyRegion`s, capped; `ItemTemplate.is_revealing` exposes
  skin) − authored `GarmentMitigation` SUN rows (hoods/veils/parasols;
  resonance-imbued rows tracked as their own field — the sun-flex read) −
  `sun_mitigation` ModifierTarget magic.
- **`sun_sensitivity.sun_sensitivity_for(sheet)`** — worst held tier by
  `DistinctionTag` (`sun-bane`/`sun-allergy`, #2752 pattern); innate
  (species-stamped) and voluntarily-taken (CG reimbursement) resolve
  identically. `sun_severity(tier, exposure)` maps residual → condition
  severity; the bane floor clears only under real shadow
  (`shade_only_residual`), never via clothing/magic.
- **`services.reconcile_sunlight_exposure(character, room)`** — syncs the
  staged Sunlight Exposure condition (Sun-Struck / Burning / Searing;
  impairment below Burning, stage-level fixed radiant DoT at Burning+) to the
  computed severity, with an IC-age escalation bonus for sustained exposure.
  Triggers: movement (typeclass hook), the `species.sun_reconcile` cron
  (5-min, DRAIN — stationary dawn pickup), and equip/position-change hooks via
  `reconcile_sun_exposure_safely`.
- **`sun_refuge.find_sun_refuge` / `flee_to_sun_refuge`** — bounded BFS over
  exits to the nearest shade-safe room (non-public wins ties); the AFK guard
  (`world.conditions.hazard_prompt`, `HazardResponseState`) prompts once on a
  damaging stage and auto-flees after the second unanswered damage instance.
  Player answers are the `hazard_endure` / `hazard_retreat` actions.
- **CG gate** — `species_innate_distinction_ids(species)` backs the draft
  validator: an innately-granted distinction is unselectable as a choice.
- Tuning constants (all PLACEHOLDER) live in `sun_constants.py`. Headline
  invariants are named tests in `world/species/tests/`.

### Hierarchy Design

Species uses a single-level parent/child hierarchy:
- **Top-level** (parent=null): Directly playable (e.g., Human) or category-only (e.g., Elven)
- **Subspecies** (parent set): Playable subspecies under a category (e.g., Rex'alfar -> Elven)

Access control for which species are available in CG is handled by `Beginnings.allowed_species` in the `character_creation` app, not in this model.

### Codex entries follow the hierarchy (#2880)

`Species.codex_entry` is a nullable FK to one `codex.CodexEntry`. The grant at CG
finalize (`character_creation.services._finalize_species_codex`) does **not** read
that field directly — it reads `Species.codex_entries`, which walks `Species.lineage`
(the species followed by every ancestor, nearest first) and collects each non-null
entry. So a Vulpi character is granted the Vulpi entry *and* the Khati umbrella entry.

This is what makes the authored split work: the umbrella entry (Khati, Elf, Infernal)
carries what the kinds share, and each kind entry carries the kind. Reading only the
leaf's own field — the pre-#2880 behavior — left the three umbrella entries reachable
by nobody who picked a subspecies. Ancestors whose `codex_entry` is still null drop
out rather than contributing a `None`.

## Appetites (#2853, ADR-0182)

Hunger is tag-anchored like sun sensitivity: `Appetite: Blood` (Vampire, Dhampir),
`Appetite: Essence` (Vulpi, Vesperi, Shades), `Undeath: Shade` (the drain anchor).
`world.species.appetites` carries the tags + `appetite_for(sheet)` probe + Ravenous
constants; the economy (regen skip, upkeep, glut, feeding) lives in
`world.magic.services.appetites` / `.feeding` — see `docs/systems/magic.md` and the
ADR. `ensure_appetite_distinctions` / `ensure_ravenous_condition` /
`ensure_shade_condition` / `apply_shade_undeath` (factories) are the runtime ensures;
seeded content routes through `authored_or_sample` in `_seed_appetite_content`
(Vesperi is the eighth khati subspecies).

## Moon Control & Lycans (#2845, ADR-0183)

The moon is a *control* pressure, not exposure damage. `world.species.moon_pull`
computes the felt pull (`illumination × sky exposure − radiant shade`; NIGHT
only; cloud cover rides ADR-0180 shelter rows for free — clothing/magic never
enter an instinct read) plus `moon_clarity_instance_value` (the battle-form
stat multiplier at shift time — voluntary and forced alike).
`world.species.moon_sensitivity` runs the control window: `Moon-Bound`
tag-anchored holders (Lycans innately, via "The Wolf's Fury" SpeciesGiftGrant
seeded in `_seed_moon_content`) above the pull threshold roll `moon_control`
(willpower + composure; ADR-0171 config prerequisite); difficulty scales with
pull, down with level and Wolf's-Fury thread level; level 6+ exempt unless
impaired (condition-driven willpower ≥1 tier down). Failure = forced shift
(`trigger_transformation(cause="moon")`, battle form lazily provisioned by
`world.species.moon_provisioning.ensure_lycan_battle_form`) + the shared
**Berserk** condition (production seed + Restore-to-Sense removal effect in
`world.conditions.berserk_content`; compulsion in
`world.combat.berserk_compulsion` — auto-attack fallback at round resolution,
disengage refusal, out-of-combat rampage; see the INDEX combat entry). Cani (the
umbrella subspecies) get the flavor-only Moonlit Unease under the open night
moon (`reconcile_cani_unease`). Cron: `species.moon_reconcile` (5-min DRAIN).

---

## Key Methods

### Species

```python
from world.species.models import Species

# Check if a species is a subspecies
species.is_subspecies  # Returns True if parent_id is not None

# Get stat bonuses as a dict
species.get_stat_bonuses_dict()
# Returns: {"strength": 1, "charm": -1}

# Access children (subspecies)
species.children.all()

# The species and every ancestor, nearest first (cycle-safe)
species.lineage  # [Vulpi, Khati]

# Every codex entry a character of this species is owed (#2880)
species.codex_entries  # [<CodexEntry: The Vulpi>, <CodexEntry: The Khati>]

# Access starting languages
species.starting_languages.all()

# String representation includes parent
str(subspecies)  # "Rex'alfar (Elven)"
str(top_level)   # "Human"
```

### SpeciesStatBonus

```python
from world.species.models import SpeciesStatBonus

# Access all bonuses for a species
species.stat_bonuses.all()

# String includes sign
str(bonus)  # "Infernal: -1 Charm"
```

---

## Integration Points

- **Forms System** (`world.forms`): `SpeciesFormTrait` links species to available physical appearance traits and options for CG — the per-species **palette**; `is_required=True` marks species identity markers (horns and a tail for Infernals) that CG must fill.
- **Character Creation** (`world.character_creation`): `Beginnings.allowed_species` controls which species are selectable during character creation.
- **Traits System** (`world.traits`): `SpeciesStatBonus.stat` uses `PrimaryStat` choices from `world.traits.constants`.
- **Heredity / Parent Dominance** (#2815): a child's species derives from its parents via `world.roster.services.heredity` — maternal by default, flipping to the father's line only when his power band strictly exceeds hers, with chimeric (unique authored `Species` rows) possible only when both parents are Grand+ (level 16+). Cross-species parents unlock *their actual colors* for the child in CG; palettes are broad with pointed per-species exclusions, and wearing an excluded color is the visible tell of cross-line blood. See `docs/systems/kinship.md` and ADR-0173. NB: "crossing" remains the magic-progression term — this system's vocabulary is "Parent Dominance" / "power band".

---

## Admin

All models registered in Django admin:

- **`SpeciesAdmin`** - List display with parent filter, stat bonus summary, and language count. Includes `SpeciesChildrenInline` (read-only subspecies list with change links), `SpeciesStatBonusInline` (editable stat bonuses), and `SpeciesGiftGrantInline` (#2846). Fieldsets cover `codex_entry` and the aging axes (`eternal_youth`, `decline_start_age`). Uses `filter_horizontal` for starting languages.
- **`SpeciesGiftGrantAdmin`** (#2846) - Standalone grant editing with species/inheritable filters.
- **`LanguageAdmin`** - Simple list with name search.

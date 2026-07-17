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
app never authors species/gift/distinction data itself.

### Hierarchy Design

Species uses a single-level parent/child hierarchy:
- **Top-level** (parent=null): Directly playable (e.g., Human) or category-only (e.g., Elven)
- **Subspecies** (parent set): Playable subspecies under a category (e.g., Rex'alfar -> Elven)

Access control for which species are available in CG is handled by `Beginnings.allowed_species` in the `character_creation` app, not in this model.

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

- **Forms System** (`world.forms`): `SpeciesFormTrait` links species to available physical appearance traits and options for CG.
- **Character Creation** (`world.character_creation`): `Beginnings.allowed_species` controls which species are selectable during character creation.
- **Traits System** (`world.traits`): `SpeciesStatBonus.stat` uses `PrimaryStat` choices from `world.traits.constants`.

---

## Admin

All models registered in Django admin:

- **`SpeciesAdmin`** - List display with parent filter, stat bonus summary, and language count. Includes `SpeciesChildrenInline` (read-only subspecies list with change links) and `SpeciesStatBonusInline` (editable stat bonuses). Uses `filter_horizontal` for starting languages.
- **`LanguageAdmin`** - Simple list with name search.

# Distinctions System

Character advantages and disadvantages that mechanically modify stats, rolls, and abilities.
Part of CG Stage 6 (Traits).

**Source:** `src/world/distinctions/`
**API Base:** `/api/distinctions/`
**Implementation Plan:** `docs/plans/2026-01-21-distinctions-system-implementation.md`

---

## Enums (types.py)

```python
from world.distinctions.types import (
    DistinctionOrigin,     # CHARACTER_CREATION, GAMEPLAY
    OtherStatus,           # PENDING_REVIEW, APPROVED, MAPPED
)

# Typed data structures
from world.distinctions.types import (
    ValidatedDistinction,    # Dataclass for validated add operations
    DraftDistinctionEntry,   # TypedDict for draft_data storage
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DistinctionCategory` | Categories like Physical, Mental, Social | `name`, `slug`, `description`, `display_order` |
| `DistinctionTag` | Searchable tags | `name`, `slug` |
| `Distinction` | The advantage/disadvantage definition | `name`, `category`, `cost_per_rank`, `max_rank`, `is_variant_parent`, `allow_other`, `secret_by_default`, `default_secret_level` |
| `DistinctionEffect` | Mechanical effects | `distinction`, `target` (FK `mechanics.ModifierTarget`), `value_per_rank`, `scaling_values`, `amplifies_sources_by`, `grants_immunity_to_negative`, `description` |
| `DistinctionPrerequisite` | Requirements (JSON rules) | `distinction`, `rule_json`, `description` |
| `DistinctionMutualExclusion` | Incompatible pairs | `distinction_a`, `distinction_b` |

**There is no `effect_type` enum/column.** `DistinctionEffect` targets a single
`mechanics.ModifierTarget` row, and the effect's *kind* is derived on read from
`target.category.name` — not stored as a separate discriminator. The consumer loop
(`create_distinction_modifiers` / `update_distinction_rank`, `world/mechanics/services.py`)
branches on `target.category.name`:
- `category.name == "resonance"` (`RESONANCE_CATEGORY_NAME`) — skipped by the ordinary
  `ModifierSource`/`CharacterModifier` loop entirely; see "Distinction → Resonance (#1834)"
  below for how this axis is actually granted.
- `category.name == "power"` (`POWER_CATEGORY_NAME`), optionally gated by
  `target.target_resonance` — still writes a normal `CharacterModifier` row (this is the
  **potency** axis; see below).
- Everything else (stat, affinity, goal, …) — writes a normal `CharacterModifier` row as
  always, via `ModifierSource(distinction_effect=effect, character_distinction=...)`.

### Character Data (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDistinction` | Character's acquired distinctions | `character`, `distinction`, `rank`, `origin`, `is_temporary`, `notes`, `secret` (→ `secrets.Secret`) |
| `CharacterDistinctionOther` | Freeform "Other" entries | `character`, `parent_distinction`, `freeform_text`, `status`, `staff_mapped_distinction` |

---

## Distinctions grant/shape Resonance (#1834)

A distinction can affect a character's `magic.Resonance` standing along **two independent
axes**. Both are authored per-distinction; neither is automatic.

### Standing / currency axis — `DistinctionResonanceGrant`

`DistinctionResonanceGrant` (`world/magic/models/grants.py` — lives in `world.magic`, not
`world.distinctions`, per ADR-0010: the general primitive `magic.Resonance` must not import
back into a dependent app) is a sidecar join authoring two rank-scaled currency knobs for a
`(distinction, resonance)` pair:

| Field | Purpose |
|-------|---------|
| `distinction` | FK → `distinctions.Distinction` |
| `resonance` | FK → `magic.Resonance` |
| `flat_amount_per_rank` | Flat resonance seeded per rank held in the distinction |
| `earn_rate_bonus_per_rank` | Percent bonus to the character's *earn rate* for this resonance, per rank |

Two consumer services in `world/magic/services/distinction_resonance.py`:

- **`reconcile_distinction_resonance_grants(character_distinction)`** — called at grant time
  by `create_distinction_modifiers` and at rank-change time by `update_distinction_rank`
  (`world/mechanics/services.py`). For every `DistinctionResonanceGrant` authored on the
  distinction: `get_or_create`s a `CharacterResonance` row for that resonance (establishing
  the character in it even before any seed is owed), then tops off a rank-scaled flat seed
  (`flat_amount_per_rank * rank`) via `grant_resonance(..., source=GainSource.DISTINCTION,
  source_character_distinction=character_distinction)`. Ledger-idempotent: sums this
  distinction's prior `DISTINCTION`-source grants for the resonance and only grants the
  shortfall. A second reconcile at the same rank grants 0; a rank-down never claws back
  (`CharacterResonance.lifetime_earned` is monotonic).
- **`distinction_earn_rate_for(character_sheet, resonance)`** — sums
  `earn_rate_bonus_per_rank * rank` across all of a character's distinctions that grant a
  bonus for `resonance`. Read by `grant_resonance` (`world/magic/services/resonance.py`) to
  scale up `amount` **before** writing, but only when `source` is one of
  `ACCELERATED_GAIN_SOURCES` (ADR-0041 — perception/presence-driven sources a character
  actively performs to be seen). Authored/system sources — including the `DISTINCTION` seed
  itself, to avoid a circular self-accelerating grant — are in `NON_ACCELERATED_GAIN_SOURCES`
  and are never scaled. Every `GainSource` member is asserted to land in exactly one of the
  two sets (a total-classification test in `world/magic/tests/`).

`GainSource.DISTINCTION` (`world/magic/constants.py`) is the ledger discriminator for the
seed grants above; `ResonanceGrant.source_character_distinction` is its typed source FK.

Wired at both distinction-acquisition sites: gameplay grant/rank-up
(`create_distinction_modifiers` / `update_distinction_rank`) and character creation
(`_create_distinction_modifiers_bulk` in `world/character_creation/services.py`, followed by
`recompute_aura` after `CharacterAura` is created during `finalize_magic_data`).

### Reverse direction — resonance thresholds rank up a held distinction (#2037)

`DistinctionResonanceRankThreshold` (`world/magic/models/grants.py`, beside
`DistinctionResonanceGrant`, same ADR-0010 placement) authors the opposite direction:
`(distinction, resonance, rank)`-unique rows saying "reaching `lifetime_earned_threshold`
lifetime-earned in this resonance unlocks this rank of this distinction."

Consumer: `check_distinction_rank_thresholds(character_sheet, resonance)`
(`world/magic/services/distinction_resonance.py`), called from `grant_resonance` **only when
`source` is in `ACCELERATED_GAIN_SOURCES`** — the "sustained endorsements" identity-
reinforcing-play cluster. Semantics:

- **Ranks up held distinctions only** — never mints a new `CharacterDistinction`; only rows
  whose threshold matches exactly `current_rank + 1` are candidates. That keying is also the
  re-fire guard: once a threshold fires, `current_rank + 1` moves past it, so repeated
  over-threshold grants are no-ops.
- **Multi-level catch-up loops to the final state** — one grant that crosses several
  thresholds ranks all the way up in that call (deterministic final state per grant), rather
  than one rank per grant.
- Rank-ups go through `grant_distinction(..., origin=DistinctionOrigin.ENDORSEMENT_THRESHOLD)`
  (`world/distinctions/services.py`), so the modifier/resonance-seed cascade fires normally;
  a `DistinctionExclusionError` is caught, logged, and skipped.
- **Never fires for `DISTINCTION`-source grants** (that source is not in
  `ACCELERATED_GAIN_SOURCES`), preventing a feedback loop where a distinction's own resonance
  seed re-triggers its own rank-up. The whole check is one query when no thresholds match;
  a crash in it is caught in `grant_resonance` (`logger.exception`) so the resonance grant
  itself always stands — mirrors the `PROJECT_CONTRIBUTION` bonus-isolation precedent in
  `world/projects/services.py`.

### Potency axis — POWER-category `DistinctionEffect`

A distinction expresses **potency** for a resonance (as opposed to standing/currency above)
using the ordinary authoring surface — a `DistinctionEffect` whose `target` is a
POWER-category `ModifierTarget`, optionally gated by `target.target_resonance`. This writes a
normal `CharacterModifier` row (unaffected by the resonance-category skip described in
"Enums" above). Two consumers read it: a technique cast's FLAT power stage
(`_derive_power` in `world/magic/services/techniques.py`), and a standalone thread pull via
`power_flat_bonus_for_resonance` (`world/mechanics/services.py`) folded in by
`_fold_distinction_pull_bonus` (`world/magic/services/resonance.py`). See
`docs/systems/mechanics.md` and `src/world/magic/CLAUDE.md` "Distinction Potency (POWER
axis)" for the full wiring — **note the pull path only folds this one modifier; it does not
include condition-sourced POWER contributions that a cast's FLAT stage also sums.**

The dead resonance-category `CharacterModifier` write that predated this axis split (the
distinction wrote a modifier nothing read) was removed from both grant paths as part of
#1834; the `resonance` `ModifierCategory` itself stays live for non-distinction sources
(facet/mantle/motif-coherence passive bonuses via `equipment_walk_total`).

---

## Profile Visibility — relocated into Secrets (#1109 → #1334)

A sensitive distinction is no longer flagged public/private; it is **relocated into a Secret**
(the privacy primitive of the mystery loop — see [secrets.md](secrets.md)):

- **Kind default** — `Distinction.secret_by_default` + `default_secret_level`. Taking a
  criminal / scandalous kind auto-mints a `Secret` at finalize, so it never lands on the public
  list. (Which kinds are secret is a content/author pass.)
- **Per-grant state** — `CharacterDistinction.secret` (`OneToOneField(secrets.Secret, SET_NULL)`).
  **The FK's presence *is* the secret-state** — `CharacterDistinction.is_secret` reads it; there
  is no separate boolean. A player self-gating an otherwise-public distinction mints a
  player-flavor secret on that grant.

Minting/clearing go through `world.distinctions.services.mint_distinction_secret` /
`clear_distinction_secret` (the single authority). The profile serializer filters on
`is_secret`: a non-owner (not staff, not the playing account) receives only **non-secret**
distinctions; the owner and staff see all, and the `DistinctionEntry` payload carries `is_secret`
so the owner's gate UI can show which are relocated. A relocated distinction surfaces for a
*learner* on the **secret tab** (via the ordinary `SecretKnowledge` loop), not back on this list.
The old `DistinctionVisibility` enum / `default_visibility` / `visibility_override` /
`effective_visibility` / `is_publicly_visible` are removed.

---

## Key Methods

### Distinction

```python
# Calculate total cost at a specific rank
distinction.calculate_total_cost(rank=2)  # Returns cost_per_rank * rank

# Get all effect descriptions
distinction.effects.all()

# Check if has variants
if distinction.is_variant_parent:
    variants = distinction.variants.filter(is_active=True)
```

### DistinctionMutualExclusion

```python
# Get all distinctions that conflict with a given distinction
excluded = DistinctionMutualExclusion.get_excluded_for(distinction)
# Returns QuerySet of Distinction objects that are mutually exclusive
```

### CharacterDistinction

```python
# Calculate total cost for character's rank
char_distinction.calculate_total_cost()  # Uses self.rank

# Get all distinctions for a character
CharacterDistinction.objects.filter(character=character)

# Get by origin
CharacterDistinction.objects.filter(
    character=character,
    origin=DistinctionOrigin.CHARACTER_CREATION
)
```

---

## API Endpoints

### Categories
- `GET /api/distinctions/categories/` - List all categories

### Distinctions
- `GET /api/distinctions/distinctions/` - List active distinctions
- `GET /api/distinctions/distinctions/{id}/` - Get distinction details

**Query Parameters:**
- `category` - Filter by category slug
- `search` - Search name, description, tags, effects
- `exclude_variants` - Hide variant children (show only parents)
- `draft_id` - Add lock status based on draft's distinctions

### Draft Distinctions
- `GET /api/distinctions/drafts/{draft_id}/distinctions/` - List draft's distinctions
- `POST /api/distinctions/drafts/{draft_id}/distinctions/` - Add distinction
- `DELETE /api/distinctions/drafts/{draft_id}/distinctions/{pk}/` - Remove distinction
- `POST /api/distinctions/drafts/{draft_id}/distinctions/swap/` - Swap mutually exclusive

---

## CG Integration

During character creation, distinctions are stored in `CharacterDraft.draft_data["distinctions"]` as a list:

```python
draft.draft_data["distinctions"] = [
    {
        "distinction_id": 1,
        "distinction_name": "Strong",
        "distinction_slug": "strong",
        "category_slug": "physical",
        "rank": 2,
        "cost": 20,
        "notes": "",
    },
    # ...
]
```

### Stage Completion

The Traits stage is complete when:
1. `draft.draft_data["traits_complete"]` is `True` (set by frontend when user makes any selection)
2. CG points remaining >= 0 (not over budget)

```python
# In CharacterDraft._is_traits_complete()
return (
    self.draft_data.get("traits_complete", False)
    and self.calculate_cg_points_remaining() >= 0
)
```

---

## Frontend Hooks

```typescript
import {
    useDistinctionCategories,
    useDistinctions,
    useDraftDistinctions,
    useAddDistinction,
    useRemoveDistinction,
} from '@/hooks/useDistinctions';

// Categories for tabs
const { data: categories } = useDistinctionCategories();

// Distinctions with filtering and lock status
const { data: distinctions } = useDistinctions({
    category: selectedCategory,
    search: searchQuery,
    draftId: draft.id,
});

// Draft's current distinctions
const { data: draftDistinctions } = useDraftDistinctions(draft.id);

// Mutations
const addDistinction = useAddDistinction(draft.id);
const removeDistinction = useRemoveDistinction(draft.id);

addDistinction.mutate({ distinction_id: 1, rank: 2 });
removeDistinction.mutate(distinctionId);
```

---

## Admin

All models are registered in Django admin with appropriate filters, search, and inline editing:

- `DistinctionAdmin` - Full editing with effects and prerequisites inline
- `CharacterDistinctionAdmin` - With `list_select_related` for performance
- `CharacterDistinctionOtherAdmin` - Bulk approve action for freeform entries

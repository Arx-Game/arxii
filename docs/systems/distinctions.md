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
    EffectType,            # STAT_MODIFIER, AFFINITY_MODIFIER, RESONANCE_MODIFIER, ROLL_MODIFIER, CODE_HANDLED
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
| `DistinctionEffect` | Mechanical effects | `distinction`, `effect_type`, `target`, `value_per_rank`, `scaling_values` |
| `DistinctionPrerequisite` | Requirements (JSON rules) | `distinction`, `rule_json`, `description` |
| `DistinctionMutualExclusion` | Incompatible pairs | `distinction_a`, `distinction_b` |

### Character Data (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDistinction` | Character's acquired distinctions | `character`, `distinction`, `rank`, `origin`, `is_temporary`, `notes`, `secret` (→ `secrets.Secret`) |
| `CharacterDistinctionOther` | Freeform "Other" entries | `character`, `parent_distinction`, `freeform_text`, `status`, `staff_mapped_distinction` |

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

# Societies System

Social structures, organizations, reputation, and legend tracking for character identities (guises).

**Source:** `src/world/societies/`

---

## Enums (types.py)

```python
from world.societies.types import ReputationTier
# Values: REVILED, DESPISED, DISLIKED, DISFAVORED, UNKNOWN, FAVORED, LIKED, HONORED, REVERED

# Convert numeric reputation to tier
tier = ReputationTier.from_value(350)       # ReputationTier.LIKED
tier.display_name                            # "Liked"
tier.range_description                       # "+250 to +499"
```

**Reputation Tier Thresholds:**

| Tier | Range |
|------|-------|
| Reviled | -1000 to -750 |
| Despised | -749 to -500 |
| Disliked | -499 to -250 |
| Disfavored | -249 to -100 |
| Unknown | -99 to +99 |
| Favored | +100 to +249 |
| Liked | +250 to +499 |
| Honored | +500 to +749 |
| Revered | +750 to +1000 |

---

## Models

### Core Structures (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Society` | Socio-political stratum within a Realm | `name`, `realm` (FK to `realms.Realm`), `description`, 6 principle fields (`mercy`, `method`, `status`, `change`, `allegiance`, `power`) |
| `OrganizationType` | Template with default rank titles for org categories | `name`, `rank_1_title` through `rank_5_title` |
| `Organization` | Specific group within a Society | `name`, `society`, `org_type`, 6 `*_override` principle fields, 5 `rank_*_title_override` fields |

### Membership and Reputation (models.Model - per-guise instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrganizationMembership` | Links a Guise to an Organization with rank | `organization`, `guise` (FK to `character_sheets.Guise`), `rank` (1-5), `joined_date` |
| `SocietyReputation` | Guise's reputation with a Society | `guise`, `society`, `value` (-1000 to +1000) |
| `OrganizationReputation` | Guise's reputation with an Organization | `guise`, `organization`, `value` (-1000 to +1000) |

### Legend System (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `LegendEntry` | A deed that earns legend for a guise | `guise`, `title`, `description`, `base_value`, `source_note`, `location_note`, `societies_aware` (M2M) |
| `LegendSpread` | An instance of spreading/embellishing a deed | `legend_entry`, `spreader_guise`, `value_added`, `description`, `method`, `societies_reached` (M2M) |

---

## Principles System

Six value axes on a -5 to +5 scale. Organizations can override society values.

| Principle | Negative (-5) | Positive (+5) |
|-----------|---------------|---------------|
| `mercy` | Ruthlessness | Compassion |
| `method` | Cunning | Honor |
| `status` | Ambition | Humility |
| `change` | Tradition | Progress |
| `allegiance` | Loyalty | Independence |
| `power` | Hierarchy | Equality |

---

## Key Methods

### Organization

```python
from world.societies.models import Organization

# Get effective principle (override or inherit from society)
org.get_effective_principle("mercy")  # Returns int (-5 to +5)

# Get effective rank title (override or inherit from org_type)
org.get_rank_title(1)  # Returns str, e.g., "Patriarch"
```

### OrganizationMembership

```python
from world.societies.models import OrganizationMembership

# Get the title for this member's rank
membership.get_title()  # Delegates to org.get_rank_title(self.rank)

# Validation: only default or persistent guises can join
membership.clean()  # Raises ValidationError for temporary disguises
```

### SocietyReputation / OrganizationReputation

```python
from world.societies.models import SocietyReputation

# Get named tier from hidden numeric value
reputation.get_tier()  # Returns ReputationTier enum member
reputation.get_tier().display_name  # "Favored"
```

### LegendEntry

```python
from world.societies.models import LegendEntry

# Total legend = base + all spreads
entry.get_total_value()  # base_value + sum(spreads.value_added)
```

---

## Key Constraints

- Only default (`is_default=True`) or persistent (`is_persistent=True`) guises can:
  - Hold organization memberships
  - Have reputation with societies or organizations
- Temporary disguises are rejected via `clean()` validation on save
- `OrganizationMembership` has a unique constraint on `(organization, guise)`
- `SocietyReputation` has a unique constraint on `(guise, society)`
- `OrganizationReputation` has a unique constraint on `(guise, organization)`

---

## Admin

All models registered with Django admin:

- `SocietyAdmin` - Principle fields grouped in fieldsets, `OrganizationInline` for child orgs
- `OrganizationTypeAdmin` - Rank title management
- `OrganizationAdmin` - Collapsible principle/rank overrides, `OrganizationMembershipInline`
- `OrganizationMembershipAdmin` - With effective title display
- `SocietyReputationAdmin` / `OrganizationReputationAdmin` - With tier display
- `LegendEntryAdmin` - With total value, spread count, `LegendSpreadInline`
- `LegendSpreadAdmin` - With society reach tracking

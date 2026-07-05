# Societies System

Social structures, organizations, reputation, and legend tracking for character identities (personas).

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

### Membership and Reputation (SharedMemoryModel - per-persona instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrganizationRank` | One rung on an org's five-tier authority ladder | `organization`, `name`, `tier` (1 highest, 5 lowest), `can_invite`, `can_kick`, `can_manage_ranks` |
| `OrganizationMembership` | Links a Persona to an Organization at a rank | `organization`, `persona` (FK to `scenes.Persona`), `rank` (FK to `OrganizationRank`), `joined_date`, `left_at`, `exiled_at` |
| `OrganizationMembershipOffer` | Pending or resolved invitation/application | `organization`, `from_persona`, `to_persona`, `kind` (`INVITE`/`APPLICATION`), `status` (`PENDING`/`ACCEPTED`/`DECLINED`/`CANCELLED`), `created_at`, `resolved_at` |
| `SocietyReputation` | Persona's reputation with a Society | `persona`, `society`, `value` (-1000 to +1000) |
| `OrganizationReputation` | Persona's reputation with an Organization | `persona`, `organization`, `value` (-1000 to +1000) |

### Legend System (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `LegendEntry` | A deed that earns legend for a persona | `persona`, `title`, `description`, `base_value`, `source_note`, `location_note`, `societies_aware` (M2M) |
| `LegendSpread` | An instance of spreading/embellishing a deed | `legend_entry`, `spreader_persona`, `value_added`, `description`, `method`, `societies_reached` (M2M) |

**Audere Majora crossing → deed.** When a character completes an Audere Majora
threshold crossing (`world/magic/audere_majora.py`), `_mint_crossing_deed` calls
`fire_renown_award` using the threshold's authored `RenownAwardConfig` fields
(magnitude/risk/reach/archetypes). This creates a `LegendEntry` attributed to the
crosser's primary persona (and fires fame/prestige/society-reputation awards). The
resulting entry is linked back via `AudereMajoraCrossing.legend_entry` (OneToOneField,
related_name `audere_majora_crossing`). Personas present in the scene are recorded as
`WITNESSED` via `grant_deed_knowledge`. No `LegendEntry` is created when
`threshold.risk == NONE`.

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

# Validation: only primary or established personas can join
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

## Membership Lifecycle

Generic (non-covenant) organizations use a rank-based lifecycle defined in
`world.societies.membership_services`. Covenants have their own lifecycle and are
rejected by these services/actions.

### Service functions

```python
from world.societies.membership_services import (
    ensure_default_rank_ladder,
    base_rank_for_organization,
    active_membership_for_persona,
    join_organization,
    leave_organization,
    invite_to_organization,
    apply_to_organization,
    accept_invitation,
    decline_invitation,
    accept_application,
    decline_application,
    promote_member,
    demote_member,
    expel_member,
)
```

- `ensure_default_rank_ladder(organization)` creates tiers 1–5 if absent; top tier gets all capability flags.
- `join_organization(organization, persona)` admits at the lowest tier (5) after checking blocks and persona validity.
- `invite_to_organization(...)` / `apply_to_organization(...)` create pending offers.
- `accept_invitation(offer, persona)` / `accept_application(offer, actor_persona)` promote the offer to a membership.
- `leave_organization(membership)` records a voluntary departure (`left_at`).
- `expel_member(target, actor)` records an expulsion (`left_at` and `exiled_at`).
- `promote_member(target, actor)` / `demote_member(target, actor)` move a member one tier, gated by `can_manage_ranks`.

### Player actions and telnet command

All major transitions are actions on the shared `action.run()` / `dispatch_player_action()` seam:

| Action key | Telnet usage | Purpose |
|------------|--------------|---------|
| `org_invite` | `org invite <name> in <organization>` | Invite a persona to join |
| `org_apply` | `org apply <organization>` | Apply to join an organization |
| `org_join` | `org join <organization>` | Accept a pending invitation |
| `org_leave` | `org leave <organization>` | Voluntarily leave the organization |
| `org_promote` | `org promote <name> in <organization>` | Move a member up one tier |
| `org_demote` | `org demote <name> in <organization>` | Move a member down one tier |
| `org_expel` | `org expel <name> from <organization>` | Remove a member from the organization |

`CmdOrg` routes `org <subverb>` through the same dispatcher the web UI uses.
Invitation accept/decline also flows through the existing `accept org` / `decline org`
offer registry (`commands/offer_registry`) with `OrgInviteHandler` registered under
keyword `org`.

### DRF endpoints

Read-only endpoints under `/api/societies/`:

| Endpoint | Viewset | Purpose |
|----------|---------|---------|
| `/organizations/` | `OrganizationViewSet` | Organizations the requester belongs to (staff see all); `?name=` filters iexact (family-org resolve) |
| `/memberships/` | `OrganizationMembershipViewSet` | Current memberships, excluding covenants |
| `/ranks/` | `OrganizationRankViewSet` | Rank ladders for visible organizations |
| `/offers/` | `OrganizationMembershipOfferViewSet` | Offers owned/received/org-visible to the requester |
| `/reputations/` | `OrganizationReputationViewSet` | The requester's active persona's org reputations (standing) — `{id, persona, organization, organization_name, tier}`, tier only, self-scoped (#1446) |

All covenant-backed organizations are excluded from the membership/rank/offer endpoints.

---

## Key Constraints

- Only personas with `persona.is_established_or_primary` (PRIMARY or ESTABLISHED) can:
  - Hold organization memberships
  - Have reputation with societies or organizations
- Temporary disguises are rejected via `clean()` validation on save
- `OrganizationMembership` has a unique constraint on `(organization, persona)`
- `SocietyReputation` has a unique constraint on `(persona, society)`
- `OrganizationReputation` has a unique constraint on `(persona, organization)`

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

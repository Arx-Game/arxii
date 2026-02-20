# Consent System

OOC visibility groups for player-controlled content sharing, separate from IC mechanical relationships.

**Source:** `src/world/consent/`

---

## Enums (VisibilityMixin.VisibilityMode)

```python
from world.consent.models import VisibilityMixin

# VisibilityMixin.VisibilityMode (TextChoices):
# PUBLIC     - Everyone can see
# PRIVATE    - No one can see (except owner, handled by caller)
# CHARACTERS - Only specified tenures
# GROUPS     - Only members of specified consent groups
```

---

## Models

### Consent Groups

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConsentGroup` | Custom group created by a player for visibility purposes | `owner` (RosterTenure), `name`, `created_at` |
| `ConsentGroupMember` | Membership in a consent group | `group`, `tenure` (RosterTenure), `added_at` |

### Visibility Mixin (abstract)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `VisibilityMixin` | Abstract mixin for models needing OOC visibility control | `visibility_mode`, `visible_to_tenures` (M2M RosterTenure), `visible_to_groups` (M2M ConsentGroup), `excluded_tenures` (M2M RosterTenure) |

**Design note:** Uses `RosterTenure` instead of `ObjectDB` because consent belongs to a player's tenure with a character, not the character itself. If a character changes hands, the new player does not inherit the previous player's consent preferences.

---

## Key Methods

### VisibilityMixin

```python
from world.consent.models import VisibilityMixin

# Check if a viewer can see content controlled by this mixin
visible = my_instance.is_visible_to(viewer_tenure)

# Visibility rules (in priority order):
# 1. Excluded tenures are ALWAYS blocked (regardless of mode)
# 2. PUBLIC: Everyone can see
# 3. PRIVATE: No one can see (caller must handle owner check separately)
# 4. CHARACTERS: Only tenures in visible_to_tenures
# 5. GROUPS: Only tenures who are members of any group in visible_to_groups
```

### Using VisibilityMixin in Your Models

```python
from world.consent.models import VisibilityMixin

class MyModel(VisibilityMixin, models.Model):
    """A model with player-controlled visibility."""
    # Your fields here...
    pass

# The mixin adds these fields automatically:
# - visibility_mode (CharField with VisibilityMode choices)
# - visible_to_tenures (M2M to RosterTenure, related_name="%(class)s_visible")
# - visible_to_groups (M2M to ConsentGroup, related_name="%(class)s_visible")
# - excluded_tenures (M2M to RosterTenure, related_name="%(class)s_excluded")
```

---

## Integration Points

The `VisibilityMixin` is used by other systems that need OOC visibility control:

```python
# Codex system uses it for teaching offers
from world.codex.models import CodexTeachingOffer
# CodexTeachingOffer(VisibilityMixin, models.Model) - controls who can see teaching offers
```

---

## Admin

- `ConsentGroupAdmin` - Group management with inline member editing, shows member count
  - Inline `ConsentGroupMemberInline` for adding/removing members with `raw_id_fields` for tenure lookup
  - Search by group name or owner's character name

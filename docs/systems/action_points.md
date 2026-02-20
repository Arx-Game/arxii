# Action Points System

Time/effort resource economy with current/banked/maximum pools, modifier-adjusted regeneration via cron, and race-condition-safe operations.

**Source:** `src/world/action_points/`

---

## Models

### Configuration (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ActionPointConfig` | Global AP economy settings (only one active at a time) | `name` (unique), `default_maximum` (default 200), `daily_regen` (default 5), `weekly_regen` (default 100), `is_active` |

### Per-Character Pool (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ActionPointPool` | A character's AP pool with current/banked/maximum | `character` (OneToOne ObjectDB), `current` (default 200), `maximum` (default 200), `banked` (default 0), `last_daily_regen` |

---

## Key Methods

### ActionPointConfig (Class Methods)

```python
from world.action_points.models import ActionPointConfig

# Get the active configuration (returns None if no active config)
config = ActionPointConfig.get_active()

# Convenience accessors (fall back to hardcoded defaults if no active config)
ActionPointConfig.get_default_maximum()  # 200 fallback
ActionPointConfig.get_daily_regen()      # 5 fallback
ActionPointConfig.get_weekly_regen()     # 100 fallback
```

### ActionPointPool

All mutating methods use `select_for_update()` to prevent race conditions.

```python
from world.action_points.models import ActionPointPool

# Get or create pool for a character (uses active config defaults)
pool = ActionPointPool.get_or_create_for_character(character)

# Check affordability
pool.can_afford(50)  # True if current >= 50
pool.can_bank(30)    # True if current >= 30

# Spend AP from current pool
success = pool.spend(50)  # Returns bool

# Bank AP (move from current to banked, for teaching offers)
success = pool.bank(30)  # Returns bool

# Unbank AP (return banked to current, capped at effective maximum; excess is lost)
actually_restored = pool.unbank(30)  # Returns int (actual amount restored)

# Consume banked AP (when an offer is accepted -- removes from banked, not returned to current)
success = pool.consume_banked(30)  # Returns bool

# Regenerate AP (add to current, capped at effective maximum)
actually_added = pool.regenerate(50)  # Returns int (actual amount added)

# Cron-triggered regeneration (applies modifier adjustments)
actually_added = pool.apply_daily_regen()   # Uses config + ap_daily_regen modifier, updates timestamp
actually_added = pool.apply_weekly_regen()  # Uses config + ap_weekly_regen modifier

# Effective maximum (base maximum + ap_maximum modifier from distinctions)
effective_max = pool.get_effective_maximum()  # Returns max(1, maximum + modifier)
```

### Pool Behavior Summary

| Operation | Source | Destination | Cap | Lost on overflow |
|-----------|--------|-------------|-----|-----------------|
| `spend(n)` | current | consumed | n/a (fails if insufficient) | No |
| `bank(n)` | current | banked | n/a (fails if insufficient) | No |
| `unbank(n)` | banked | current | effective maximum | Yes (excess lost) |
| `consume_banked(n)` | banked | consumed | n/a (fails if insufficient) | No |
| `regenerate(n)` | external | current | effective maximum | Yes (capped) |

---

## Modifier Integration

The action points system reads modifiers from the mechanics system to adjust regeneration rates and maximum capacity.

```python
# Internal method called by apply_daily_regen, apply_weekly_regen, get_effective_maximum
pool._get_ap_modifier("ap_daily_regen")   # Total modifier value (can be negative)
pool._get_ap_modifier("ap_weekly_regen")  # e.g., Indolent distinction reduces regen
pool._get_ap_modifier("ap_maximum")       # e.g., Efficient distinction increases cap

# Under the hood, delegates to:
from world.mechanics.services import get_modifier_for_character
get_modifier_for_character(character, "action_points", "ap_daily_regen")
```

**Modifier Type names** (registered as `ModifierType` in the mechanics system under category `action_points`):

| Modifier Type Name | Effect |
|-------------------|--------|
| `ap_daily_regen` | Added to base daily regen amount (can be negative; floored at 0) |
| `ap_weekly_regen` | Added to base weekly regen amount (can be negative; floored at 0) |
| `ap_maximum` | Added to base maximum (effective max is `max(1, maximum + modifier)`) |

---

## Cron Integration

Daily and weekly regeneration are triggered by cron jobs that iterate over all `ActionPointPool` records:

```python
# Daily cron (per game day):
for pool in ActionPointPool.objects.all():
    pool.apply_daily_regen()

# Weekly cron:
for pool in ActionPointPool.objects.all():
    pool.apply_weekly_regen()
```

`apply_daily_regen()` also updates `last_daily_regen` timestamp for tracking.

---

## Integration Points

- **Mechanics**: Reads `ap_daily_regen`, `ap_weekly_regen`, and `ap_maximum` modifiers via `get_modifier_for_character()`. Distinctions like Indolent or Efficient create these modifiers.
- **Codex** (future): Teaching activities cost action points via `pool.spend()` or `pool.bank()`.
- **Cron**: Daily and weekly jobs call `apply_daily_regen()` and `apply_weekly_regen()` on all pools.

---

## Admin

Both models registered with organized fieldsets:

- `ActionPointConfigAdmin` - Fieldsets for identity (name, is_active), default values (default_maximum), and regeneration rates (daily_regen, weekly_regen). Filterable by `is_active`.
- `ActionPointPoolAdmin` - Fieldsets for character, action points (current, maximum, banked with descriptions), and timestamps (collapsible). `raw_id_fields` for character, `readonly_fields` for `last_daily_regen`.

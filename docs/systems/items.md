# Items & Equipment System

Items, equipment, inventory, and currency. Provides the data model foundation for
everything characters can own, wear, wield, and interact with.

**Source:** `src/world/items/`
**API Base:** `/api/items/`

---

## Constants (constants.py)

```python
from world.items.constants import (
    BodyRegion,          # HEAD, FACE, NECK, SHOULDERS, TORSO, BACK, WAIST,
                         # LEFT_ARM, RIGHT_ARM, LEFT_HAND, RIGHT_HAND,
                         # LEFT_LEG, RIGHT_LEG, FEET, LEFT_FINGER, RIGHT_FINGER,
                         # LEFT_EAR, RIGHT_EAR
    EquipmentLayer,      # SKIN, UNDER, BASE, OVER, OUTER, ACCESSORY
    OwnershipEventType,  # CREATED, GIVEN, STOLEN, TRANSFERRED
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `QualityTier` | Color-coded quality levels with stat scaling | `name`, `color_hex`, `numeric_min`, `numeric_max`, `stat_multiplier`, `sort_order` |
| `InteractionType` | Extensible item actions (eat, wield, study, etc.) | `name` (internal), `label` (player-facing), `description` |

### Item Archetypes

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ItemTemplate` | Archetype definition for an item type | `name`, `description`, `weight`, `size`, `value`, `is_active`, container fields, stacking fields, consumable fields, crafting fields, `interactions` (M2M to InteractionType), `minimum_quality_tier` (FK) |
| `TemplateSlot` | Body region + layer an item occupies | `template` (FK), `body_region`, `equipment_layer`, `covers_lower_layers` |
| `TemplateInteraction` | Flavor text for a specific interaction on a template | `template` (FK), `interaction_type` (FK), `flavor_text` |

### Per-Item State

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ItemInstance` | A specific item in the game world | `template` (FK, PROTECT), `game_object` (OneToOne to ObjectDB), `custom_name`, `custom_description`, `quality_tier` (FK), `quantity`, `charges`, `is_open`, `owner` (FK to AccountDB), `crafter` (FK to AccountDB) |
| `EquippedItem` | Tracks equipped item at a body slot | `character` (FK to ObjectDB), `item_instance` (FK), `body_region`, `equipment_layer`. Unique on (character, body_region, equipment_layer) |

### Economy & History

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OwnershipEvent` | Append-only ownership transition ledger | `item_instance` (FK), `event_type`, `from_account` (FK), `to_account` (FK), `notes`, `created_at` |
| `CurrencyBalance` | Per-account gold balance | `account` (OneToOne to AccountDB), `gold` |

---

## API Endpoints (Read-Only)

| Endpoint | ViewSet | Notes |
|----------|---------|-------|
| `/api/items/quality-tiers/` | `QualityTierViewSet` | List quality tiers |
| `/api/items/interaction-types/` | `InteractionTypeViewSet` | List interaction types |
| `/api/items/templates/` | `ItemTemplateViewSet` | List/detail with nested slots and interaction bindings |

---

## Key Design Decisions

### Single Typeclass
All items use the same Evennia `Object` typeclass. Item behavior is driven entirely by
`ItemTemplate` properties and `InteractionType` bindings, not by typeclass inheritance.
This avoids typeclass proliferation and keeps game logic in Django models.

### Templates + Instances
`ItemTemplate` defines the archetype (iron longsword, silk shirt). `ItemInstance` holds
per-item state (custom name, quality, charges, owner). Instances reference their template
with `on_delete=PROTECT` to prevent accidental archetype deletion.

### Region + Layer Equipment Grid
Equipment slots use a two-dimensional grid: `BodyRegion` (where on the body) x
`EquipmentLayer` (depth from skin to outermost). This allows layered clothing (underwear,
shirt, jacket, cloak all on the torso) and multi-region items (full plate creates
EquippedItem rows for torso, both arms, etc.). The unique constraint
`(character, body_region, equipment_layer)` enforces one item per slot.

### Ownership Ledger
`OwnershipEvent` is append-only — ownership transitions are recorded, never deleted.
This supports investigation mechanics, theft tracking, and provenance queries.

---

## What's Not Yet Built

- **Service functions** for equip/unequip, give, pick up, drop, consume
- **Combat stat blocks** for weapons and armor
- **Fashion facet integration** with the magic/resonance system
- **Visible equipment rendering** for character appearance
- **Frontend inventory UI**
- **Modifier source integration** with the mechanics system (equipment as modifier sources)

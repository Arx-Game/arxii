# Items & Equipment

**Status:** in-progress
**Depends on:** Magic (facets/resonance), Crafting

## Overview
The item and equipment system handles everything characters can own, wear, wield, and interact with. Items serve double duty: practical combat stats AND magical resonance through fashion facets. What you wear defines both your combat capability and your magical identity.

## Key Design Points
- **Body slot system:** Different items worn on different body parts — standard MUD/Arx 1 style equipment slots
- **Visible equipment:** What's showing on a character is visible to others, feeding into social perception and aura farming
- **Combat stats:** Weapons and armor have mechanical combat properties
- **Fashion facets:** Items carry facets that map to character resonances. The combat value of gear is only partly in stats — the magical resonance complement matters as much or more
- **Item quality:** Crafted items vary in quality based on crafter skill and materials
- **Item descriptions:** Rich text descriptions that contribute to the game's aesthetic feel

## What Exists
- **Evennia ObjectDB:** Base typeclass for objects exists in typeclasses/objects.py
- **Forms app:** HeightBand, Build — physical form descriptors (tangentially related)
- **Items app (`src/world/items/`):** Data model foundation with:
  - `QualityTier` — color-coded quality levels with stat multipliers (lookup table)
  - `InteractionType` — extensible item actions like eat, wield, study (lookup table)
  - `ItemTemplate` — archetype definitions with weight, size, value, container/stacking/crafting properties
  - `TemplateSlot` — body region + equipment layer declarations per template
  - `ItemInstance` — per-item state with custom name/description, quality, charges, owner
  - `TemplateInteraction` — interaction flavor text per template (e.g., what a muffin tastes like)
  - `EquippedItem` — character equipment tracking at body region + layer
  - `OwnershipEvent` — append-only ownership transition ledger
  - `CurrencyBalance` — per-account gold balance
- **Read-only API endpoints** at `/api/items/` for quality tiers, interaction types, and templates
- **Full test suite** covering models, serializers, and API views**

## What's Needed for MVP
- ~~Equipment slot / body part model~~ — **done** (TemplateSlot with BodyRegion + EquipmentLayer)
- ~~Worn items tracking~~ — **done** (EquippedItem model, data layer only)
- ~~Item type system~~ — **partially done** (ItemTemplate with container/stacking/consumable flags; no weapon/armor stat blocks yet)
- ~~Item quality~~ — **done** (QualityTier lookup table with stat multipliers)
- Item stats model — combat properties, condition/durability (not started)
- Item facet system — fashion facets on items that map to resonances (not started)
- Visible equipment display — what others see when looking at a character (not started)
- Inventory service functions — equip/unequip, give, pick up, drop (not started)
- Item interaction service functions — using items, consuming charges (not started)
- Equipment UI — inventory management, equipping/unequipping, viewing item details (not started)

## Magic Integration (Spec A)
- **Items as thread anchors** — The new `Thread` model supports an `ITEM` anchor kind
  (`thread.item` FK to `ItemInstance`). Heirloom weapons, legendary relics, and other
  thread-capable items can accrue resonance and level as persistent threads
- **Ritual components** — `RitualComponentRequirement` FKs to `ItemTemplate` (with an
  optional `QualityTier`) to declare what items a ritual consumes when cast
- Cross-reference: `docs/systems/magic.md` for the full model lineup

## Notes

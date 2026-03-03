# Items & Equipment

**Status:** not-started
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
- **Character sheets:** References to item data handler in tests suggest some Arx 1 item_data descriptor patterns may be partially present
- **No dedicated equipment slot system, worn items tracking, or body parts model visible**

## What's Needed for MVP
- Equipment slot / body part model — defining where items can be worn
- Worn items tracking — what a character currently has equipped
- Item type system — weapons, armor, clothing, accessories, consumables, etc.
- Item stats model — combat properties, quality, condition/durability
- Item facet system — fashion facets on items that map to resonances
- Visible equipment display — what others see when looking at a character
- Inventory system — carrying, storing, organizing items
- Item interaction — picking up, dropping, giving, using items
- Item descriptions and appearance
- Equipment UI — inventory management, equipping/unequipping, viewing item details

## Notes

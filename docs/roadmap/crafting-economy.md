# Crafting, Fashion & Economy

**Status:** not-started
**Depends on:** Items & Equipment, Magic (resonance/facets), Societies, Areas

## Overview
A rich economic layer that encompasses crafting, fashion, player housing, businesses, and domain management. Crafting was extremely popular in Arx 1 and will be central to Arx II. The fashion-to-resonance feedback loop is unique: assembling a wardrobe that complements your magical motif literally makes you more powerful.

## Key Design Points
- **Crafting as hobby, not class:** Crafting is separate from Path identity. Paths represent a character's adventurer calling; crafts are hobbies or side professions. Avoids overlap with combat roles
- **Material acquisition:** Through world interaction (harvesting gameplay loops), economy (buying), mission rewards, and other sources
- **Recipes:** Discovered, learned, or purchased. Gated by crafting skill levels
- **Fashion-resonance loop:** Items have facets that map to character resonances. A character with a spider facet mapped to their predatory nature gets Praedari resonance bonuses. Assembling a wardrobe that's admired by others creates a feedback loop — social perception feeds magical power
- **Player housing:** Players buy/build rooms, decorate them (decorations give room statistics), run stores and businesses from them
- **Holdings:** Large-scale constructions with defensive stats, research labs, room-specific bonuses
- **Businesses and stores:** Player-run economic entities
- **Ships:** Ownable, upgradeable vessels (e.g., a pirate ship that gets equipped, crewed, and taken on missions)
- **Noble domains:** Territories with material generation, exports/imports, economic management
- **Game economy:** Materials, trade, imports/exports — largely player-driven through crafting and domain interaction
- **Economic progression:** Owning and developing assets is another progression axis alongside XP and Path steps

## What Exists
- **Nothing substantial.** Gold cost references exist (CodexTeachingOffer.gold_cost) but no economy, crafting, housing, or trade models

## What's Needed for MVP
- Material/resource models — types, sources, quantities, storage
- Crafting system — recipes, skill requirements, material costs, quality outcomes
- Item creation pipeline — crafted items with stats, facets, and fashion properties
- Fashion system — how worn item facets map to resonances, admiration mechanics
- Player housing — room purchase/construction, decoration system, room stats from decor
- Store/business system — player-run shops, inventory management, pricing
- Holdings — large constructions with defensive stats, research labs, special bonuses
- Ship system — vessel models, upgrades, crew, integration with missions
- Domain management — noble territory models, material generation, imports/exports
- Trade system — player-to-player and NPC trade mechanics
- Economy balancing — currency flow, material scarcity, price stabilization
- Economy UI — crafting interface, shop management, domain overview, housing decoration

## Notes

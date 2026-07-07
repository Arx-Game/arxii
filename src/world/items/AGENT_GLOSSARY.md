# Items glossary

**Facet**:
A node of hierarchical imagery or symbolism (Creatures > Mammals > Wolf; Materials > Textiles > Silk) that players assign to resonances to define personal magical meaning. An item carries facets (via ItemFacet rows) so that a wearer's matching Threads on those facets boost their magic — the symbolic axis.
_Avoid_: tag, theme, symbol

**Style**:
A staff-curated aesthetic vocabulary word (Seductive, Menacing, Regal) that an item can carry. Distinct from a Facet: a Style is an aesthetic adjective each character binds to a resonance of their choosing for a coherence bonus, where a Facet is fixed symbolic imagery — the same Style can mean different magic for different characters.
_Avoid_: aesthetic, look, vibe

**Audacity**:
A Style's ordinal daring tier (Understated/Expressive/Bold/Outrageous, `StyleAudacity`) that scales how much that Style is mechanically rewarded — both the passive motif-coherence bonus and peer style-presentation endorsements read the worn/matched Style's audacity through the staff-tunable `AudacityTuning` singleton (default multipliers 0.75/1.00/1.35/1.75). Daring styles are rewarded mechanically, not just narratively.
_Avoid_: boldness, daring level, flashiness

**QualityTier**:
A discrete, color-coded quality level (Common=white, Fine=green, Masterwork=purple) spanning an internal numeric range and carrying a stat multiplier, reused across systems to give consistent visual language for quality and difficulty.
_Avoid_: grade, rarity, quality level

**GearArchetype**:
A coarse equipment categorization (Light/Medium/Heavy Armor, Robe, one- or two-handed Melee, Ranged, Thrown, Shield, Jewelry, Clothing) used to gate covenant-role compatibility and combat-stat eligibility.
_Avoid_: gear type, equipment class, item category

**CraftingRecipe**:
The top-level record that drives one crafting workflow, unique per recipe kind, bundling the check configuration, resource costs, success thresholds, and default consumption policy for crafting attempts.
_Avoid_: blueprint, formula, pattern

**CraftingSkillCap**:
A row mapping a minimum skill value to the highest QualityTier a crafter at that skill band can produce for a recipe; the crafter's craftable ceiling is the cap of the highest band whose threshold they meet.
_Avoid_: skill gate, quality limit

**lore-critical**:
The property of an ItemInstance that must never be auto-purged by soft-delete cleanup because it carries material lore value, attached facets, or transfer provenance (it changed hands). A strict subset of "differs from template" — cosmetic-only data like a custom name or quality tier is not lore-critical.
_Avoid_: significant, important, protected

**Container Access Policy**:
A container-only setting (`ItemInstance.access_policy`: Open / Friends / Owner Only) controlling who may take items *out* of that container with a plain take. Non-containers ignore it. It governs only the immediate container an item sits in — no chaining up nested containers — and it never blocks Steal, which is the deliberate bypass.
_Avoid_: container lock, container permissions

**Steal**:
The deliberate ownership-gate bypass (`flows.service_functions.inventory.steal`) that takes an item a plain Take refuses — the item is owned by someone else, or barred by a container's Access Policy. Unlike Take, Steal always leaves consequences: an `OwnershipEvent(STOLEN)` (ownership genuinely transfers, the item is never destroyed) and a crime-tagged, concealed Legend deed. Whether Steal is even offered is target-side only: an NPC's holdings are always antagonism-allowed, a player's holdings gate on that player's theft consent (default-deny — opt-in required).
_Avoid_: take (as a synonym), pickpocket, loot (as a verb for a live owner's item)

- **Market square** — a capital's transactional trade hub (#2066): NPC stock
  stalls (materials/reagents/necessities — pure sinks) + PC stalls of
  unfinished wares. One per realm capital. _Avoid:_ shop (that's a crafter's
  own station-bearing room), bazaar.
- **Unfinished ware** — a real crafted `ItemInstance` listed generic
  (`WareListing`): stats and quality are the crafter's, the name and prose
  are the buyer's via a one-shot **finishing pass**. _Avoid:_ design/template
  listing (stock is finite, actual instances).
- **Craft-as-service** — a standing `CraftingServiceOffer`: the buyer runs
  the attempt at the crafter's shop using the CRAFTER's skill, paying their
  fee (works with the crafter offline). Arx 1's real loop, made honest.
  _Avoid:_ commission (reserved for the personal full-prose channel).
- **Dual provenance** — `crafter_*` + `designer_*` pairs on `ItemInstance`;
  renders "Crafted by X, Designed by Y", collapsing when equal. The prose
  author is never erased again. _Avoid:_ maker (ambiguous).

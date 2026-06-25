# Items glossary

**Facet**:
A node of hierarchical imagery or symbolism (Creatures > Mammals > Wolf; Materials > Textiles > Silk) that players assign to resonances to define personal magical meaning. An item carries facets (via ItemFacet rows) so that a wearer's matching Threads on those facets boost their magic — the symbolic axis.
_Avoid_: tag, theme, symbol

**Style**:
A staff-curated aesthetic vocabulary word (Seductive, Menacing, Regal) that an item can carry. Distinct from a Facet: a Style is an aesthetic adjective each character binds to a resonance of their choosing for a coherence bonus, where a Facet is fixed symbolic imagery — the same Style can mean different magic for different characters.
_Avoid_: aesthetic, look, vibe

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

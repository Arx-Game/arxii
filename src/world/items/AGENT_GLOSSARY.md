# Items glossary

**Facet**:
A node of hierarchical imagery or symbolism (Creatures > Mammals > Wolf; Materials > Textiles > Silk) that players assign to resonances to define personal magical meaning. An item carries facets (via ItemFacet rows) so that a wearer's matching Threads on those facets boost their magic — the symbolic axis.
_Avoid_: tag, theme, symbol

**Style**:
A cultural/historical fashion register an item can carry (Arxian Court, Old-Regime — re-ruled #2907; intent adjectives like "Seductive" are Accent-redundant and rejected at authoring). A Style says where a piece's fashion LANGUAGE comes from — a regional culture, an era, an aesthetic school — never what the piece is trying to do (that's an Accent). Carries `origin`, `era` (current/ancient — ancient registers are investigation-rediscoverable), and a `founder` persona FK for icon-founded styles. Distinct from a Facet (fixed symbolic imagery); characters still bind Styles to resonances for coherence bonuses.
_Avoid_: intent adjectives as style names, vibe words that shadow an accent axis

**Silhouette**:
The wearable FORM — the fashion noun (#2907): boot, thigh-high boot, stiletto heel. Umbrella hierarchy via `parent`; grouped by `WearFamily`; authored default on `ItemTemplate.silhouette` with a family-validated crafter pick at making stored on `ItemInstance.silhouette` (`effective_silhouette` resolves the fallback). Litmus test vs Style: if it changes the SHAPE it's a (sub-)silhouette; if it changes how the piece reads while the shape stays, it's a Style. Revealing-ness is shape, so it lives here: `exposes_beneath` (#2985, Apostate's 2026-08-05 ruling) marks cuts that expose whatever lies beneath them — the slit gown shows the stockings, or the skin and its markings when nothing is underneath; skin is just what you find when you run out of layers, and plain cuts conceal beneath by default. Read by the shared `covered_regions` predicate (marking visibility + felt sun exposure), OR-composed with `ItemTemplate.is_revealing` (material sheerness). Prose never says "silhouette" for garments/jewelry — `silhouette_prose_noun` gives "cut"/"setting" ("Cut" as a model name is reserved for future gem cuts).
_Avoid_: Cut (reserved for gemstones), Form (collides with the forms app), shape
_Avoid_: aesthetic, look, vibe

**Worn Open**:
The performed exposure state (#2985, ADR-0199): the show verb sets `EquippedItem.opened_at`
on the covering garments so whatever lies beneath shows — the next layer, or skin at the
bottom of the stack. Cleared by conceal or by dressing at the region; dies with the row on
unequip. The state always lives on the coverer, never on the hidden thing.
_Avoid_: revealed (the old hidden-thing state), unbuttoned

**Show / Conceal**:
The declarative exposure verbs (keys `reveal`/`cover`; telnet aliases show/reveal and
conceal/cover): the player names the GOAL — a body part, worn piece, or marking — and the
layer walk computes which covering garments to part or close. Honest when fabric cannot
help ("nothing you wear covers that").
_Avoid_: toggle visibility, flash

**Audacity**:
A Style's ordinal daring tier (Understated/Expressive/Bold/Outrageous, `StyleAudacity`) that scales how much that Style is mechanically rewarded — both the passive motif-coherence bonus and peer style-presentation endorsements read the worn/matched Style's audacity through the staff-tunable `AudacityTuning` singleton (default multipliers 0.75/1.00/1.35/1.75). Daring styles are rewarded mechanically, not just narratively.
_Avoid_: boldness, daring level, flashiness

**QualityTier**:
A discrete, color-coded quality level (Common=white, Fine=green, Masterwork=purple) spanning an internal numeric range and carrying a stat multiplier, reused across systems to give consistent visual language for quality and difficulty.
_Avoid_: grade, rarity, quality level

**GearArchetype**:
A coarse equipment categorization (Light/Medium/Heavy Armor, Robe, one- or two-handed Melee, Ranged, Thrown, Shield, Jewelry, Clothing) used to gate covenant-role compatibility and physics gates (wind penalty, lance maneuvers, hands). The combat stat-override fallback for a weapon `ItemTemplate` with no `WeaponClass` set (#2879) — when `WeaponClass` is set, it takes precedence for the strength/agility blend instead.
_Avoid_: gear type, equipment class, item category

**WeaponClass** (#2879):
A named strength/agility blend classification for a weapon `ItemTemplate` (e.g. "Longsword", "Recurve Bow"), replacing the earlier small/medium/heavy override. Carries `strength_tenths` (0-10; agility's share is 10 minus it) — strength 10 is a pure-strength weapon like a maul, 0 is pure agility like a crossbow. `ItemTemplate.weapon_class` FKs to it (nullable, `PROTECT`); null falls back to the coarser `GearArchetype` stat map. The check-resolution seam substitutes the blended value for the check's STAT trait. Evocative names double as player-facing vocabulary. See `world/items/models.py` (`WeaponClass`) and `world/combat/stat_mapping.py` (the fallback lookup).
_Avoid_: weapon type, weapon tier, weapon category

**CraftingRecipe**:
The top-level record that drives one crafting workflow, unique per recipe kind, bundling the check configuration, resource costs, success thresholds, and default consumption policy for crafting attempts.
_Avoid_: blueprint, formula, pattern

**CraftingSkillCap**:
A row mapping a minimum skill value to the highest QualityTier a crafter at that skill band can produce for a recipe; the crafter's craftable ceiling is the cap of the highest band whose threshold they meet.
_Avoid_: skill gate, quality limit

**lore-critical**:
The property of an ItemInstance that must never be auto-purged by soft-delete cleanup because it carries material lore value, attached facets, or transfer provenance (it changed hands). A strict subset of "differs from template" — cosmetic-only data like a custom name or quality tier is not lore-critical.
_Avoid_: significant, important, protected

**Template default Properties** (#2503):
The `mechanics.Property` rows an `ItemTemplate` declares via `ItemTemplateProperty`
(e.g. a Torch template → `flammable`) — applied to every materialized instance's
physical `ObjectDB` at the single materialization chokepoint
(`apply_template_properties`, `world/items/services/materialize.py`), whether it
lands in a character's inventory or a GM-staged room prop. Feeds the mechanics app's
bare-object affordance scan (`_bare_object_actions`) — see
`world/mechanics/AGENT_GLOSSARY.md`'s "Bare-object affordance".
_Avoid_: default tags, template flags, inherent properties

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
- **Standing-based service gating** (#2995) — a persona-bearing NPC seller
  (`MarketStall.shopkeeper_persona`, `CraftingServiceOffer.crafter_persona`)
  reads `NpcRegard` (#1717) of the buyer at purchase time: this is a
  functionary **service** the NPC extends, not a fixed shop window — their
  opinion shifts the price (`REGARD_PRICE_BANDS`), gates reserved stock
  (`min_regard`), and past `REGARD_REFUSAL_FLOOR` refuses service outright.
  Scoped to persona-bearing NPCs only — a class-1 `Functionary` (see
  `npc_services/AGENT_GLOSSARY.md`) has no `Persona` to hold the opinion, and
  a PC seller's stall/offer is never gated (`NpcRegard` never holds a PC's
  opinion, ADR-0085). _Avoid:_ shop discount/markup (frames it as a fixed
  price rule rather than the NPC's own standing-driven judgment).
- **Revealing (garment)** — `ItemTemplate.is_revealing`: the garment occupies
  its slots but leaves the covered skin exposed — no sun coverage
  (`world.species.sun_exposure`), and the future tattoo/skin-visibility
  consumer reads the same flag. A non-revealing garment fully covers the body
  regions it is equipped over. _Avoid:_ skimpy (flavor, not the field), a
  separate coverage-percentage model.

- **Accent** — a style axis the crafter worked into a specific piece at the
  forge (#2878): an `ItemAccent` row (instance × styleable `ModifierTarget` ×
  `AccentLevel`). Chosen per-instance, never recipe/template data; each Accent
  rolls its own check at craft time and its realized rung is thread-capped.
  Feeds `crafted_modifier_value` and flatters fashion presentations.
  _Avoid_: Styling (collides with `Style`), Finish, Touch, Aura, enchantment
  (that's facets).
- **Accent ladder** — the benefit-only 7-rung `AccentLevel` ladder (slightly →
  legendarily); the adverbs ARE the display grammar ("a quite menacing
  accent"). Separate from `QualityTier` by design — Accents have no "poor"
  end. _Avoid_: reusing QualityTier rows for accent levels.
- **Material grade** — `ItemTemplate.material_grade`: the quality-score head
  start a material contributes when consumed in crafting (#2878, ADR-0192).
  Materials are potential, never performance — no material→stat table, ever.
  _Avoid_: material tier multiplier, material stat scaling.
- **Quality rung** — a `QualityTier.sort_order` position on the 12-rung ladder
  (1–9 mundane-reachable; 10 divine / 11 transcendent / 12 legendary are
  thread-gated: base cap + one rung per Thread woven into the crafting
  skill). _Avoid_: level (ambiguous with character level).
- **Refinement project** — the guaranteed long road (#2878): an
  `ITEM_REFINEMENT` project (instant-completion, `ItemRefinementDetails`)
  whose funded threshold deterministically applies +1 to an Accent or the
  base quality rung. NO per-cycle rolls; threshold scales with item value ×
  target rung; the threshold-crossing contribution needs a contributor whose
  thread-capped ceiling reaches the goal (the master gate). _Avoid_:
  refine-attempt rolls (Arx 1's shape, explicitly rejected).

- **Accent exclusion** — a symmetric `AccentExclusion` pair that cannot coexist
  on one item (#2886): Dramatic ⊥ Unassuming. Data rows, never an enum.
  _Avoid_: hardcoded pair checks.
- **Recycle (item)** — owner-only destruction for `SALVAGE_FRACTION` of the
  recipe's materials (#2886). **Story-protected** items (active legend deeds)
  need an APPROVED `RecycleRequest` (GM sign-off) first. _Avoid_: junk,
  disenchant, salvage-as-a-skill (it's a lifecycle act, not a craft).

# ADR-4099: Personalization starts at creation, on the character's hold of a technique

**Status:** Accepted (2026-10-01, #4099). Supersedes in part ADR-0136 (its clause that
mechanical personalization starts at thread level 3).

A character personalizes a technique on their hold of it (`CharacterTechnique`), never on
the shared catalog `Technique`. The hold carries: the player's own `custom_name` and
`custom_description` (free and unreviewed, display only, never a lookup key); a `price` (a
`Restriction` with `kind=PRICE`, whose `power_bonus` is added to every cast as a
power-ledger term and whose `cast_narration` joins the cast narration); and an `early_form`
(a `TechniqueVariant` bought before the gift thread reaches its level, honored by the
variant resolver only when the cast's resolved resonance matches the form's own authored
resonance, checked after ordinary variant matching, for its buyer only, never for a
role-granted hold).
Price lives as a `kind` on the existing `Restriction` model rather than a sibling table, so
design-side limitation and cast-time price share one catalog with a discriminator instead
of two parallel mechanisms.

A price costs something real (owner rulings, 2026-10-02): it buys power because it makes
the technique less convenient to use. It may consume carried items on every cast that pays
it (`PriceComponentRequirement` rows: item template, quantity, optional minimum quality)
and may inflict an authored `ConditionTemplate` on the caster (`Restriction
.inflicted_condition`, applied through `apply_condition` on every paid cast; the
condition's own rules decide stacking and refreshing). Both are PRICE-only (`clean()` on
both models, plus a DB constraint on the condition column). A caster without the
components still casts, never refused, just without the price: no power bonus, no
narration clause, no condition, nothing consumed, so a player never loses a core
technique by running out of a component. Exactly one service decides whether a cast pays,
`price_paid_for_cast`, called once inside `use_technique` (the seam every cast path
shares: scene, social, combat, clash, battle, so a combat cast decides at round
resolution, never at declaration). Its `PricePayment` threads into the power term, the
post-resolution settlement (`settle_price_payment`, consumption and condition in the
cast's transaction, after `resolve_fn`, so a refused or cancelled cast spends nothing) and
`TechniqueUseResult.price_paid`, which every narration seam reads instead of the hold.
The component table is a sibling of `RitualComponentRequirement` keyed to `Restriction`,
matched and consumed by the same shared `gather_consumable_pks` / `consume_materials`
helpers rituals and crafting already use, against the caster's carried inventory
(`character.carried_items`).

The early flourish is the existing `Thread.signature_bonus`: creation weaves the TECHNIQUE
thread at the flourish's own `min_crossing_level`, up to `CREATION_PERSONALIZATION_MAX_LEVEL`
(2), so it never skips a crossing. The hard level-3 floor on signing is gone; each bonus's
authored `min_crossing_level` is now the only gate, so flourishes grow as the thread is
imbued rather than unlocking in one step at level 3. Each catalog row (price, flourish, or
early form) is offered in creation only when staff set its `creation_point_cost`; a blank
cost means the option is not offered, and every creation cost is non-negative. A Motif is
seeded for every new character at finalize so a flourish (resonance-gated via its
`required_resonance`; a price carries no resonance of its own) can qualify once the
character's gift resonance resolves. Rename/re-price of a hold is creation-only for this
PR (owner ruling, 2026-10-01); nothing in play lets a character rename or re-price a
technique they already hold. The custom name and description are display only and are
never used as a lookup key anywhere a technique is resolved. A hold's custom description
and its price follow the same `magic_visibility` tier as the technique itself, per the
spec's leak table, so neither is stricter nor looser than what the technique's own name
and effects already reveal to the same viewer.

Panel copy (the creation stage's static prose) is seeded at read time through
`CGExplanation` keys: a missing key renders a visible `PLACEHOLDER: {key}` marker and a
Required-content row lists every missing key, rather than a data migration writing the
copy. We rejected:
- a sibling price catalog (a second "limitation buys power" mechanism beside
  `Restriction`; the `kind` discriminator keeps design restrictions and prices apart in one
  table instead);
- reading a price through the builder's refund multiplier (that converts to design budget,
  not cast power, and the two are different ledgers);
- leaving early forms derive-on-read only with no hold record (a low-level variant would
  apply free to every character at that resonance, not just the one who paid for it);
- per-technique personalization catalogs (one authored gate per flourish/form/price serves
  every technique, so a per-technique catalog would duplicate authoring for no gain);
- generalizing `RitualComponentRequirement` to also key on `Restriction` (it would need a
  nullable `ritual` FK plus an exactly-one-owner constraint, and drag its touchstone mode,
  which an attuned-and-kept item never fits, onto prices; the matching/consumption code is
  already duck-typed and shared, so a sibling table reuses it with no parallel consumer, the
  same way `CraftingMaterialRequirement` does);
- refusing a cast whose caster lacks the component (a price must never take a core
  technique away), and re-deciding "is it paid" separately in the power term and each
  narration seam (they could disagree; one decision is threaded instead);
- a seed migration for the creation panel's static copy (the repo's
  "no seed data in migrations" hook forbids one, and authored content lives in the database,
  never a migration, per ADR-0238). Instead, a missing `CGExplanation` copy key renders one
  visible `PLACEHOLDER: {key}` marker at read time, and a Required-content row lists every
  key still missing, so staff see the gap until they author it.

> Status: accepted · Source: issue #4099 · Supersedes in part: ADR-0136

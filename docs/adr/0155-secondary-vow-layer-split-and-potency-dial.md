# Secondary vows scale Layers 2/4 by a potency dial; Layers 1/3 stay strictly primary-only

#2641 lets a character hold a second, weaker covenant vow (`CharacterCovenantRole.is_secondary`)
alongside their primary — a group-gap filler and hybrid fantasy, never a replacement for a real
specialist (design/covenant-vows-consolidated.md §4, rounds 13-14). The chosen shape splits
ADR-0149's four-layer vow-power model down the middle: Layer 1 (combat-identity blend) and Layer 3
(defense/gear/stat scaling) — the chassis — read ONLY engaged PRIMARY memberships
(`currently_engaged_primary_roles()`); Layer 2 (technique specialty) and Layer 4 (situational
perks) read BOTH, but a firing sourced from a secondary membership is scaled down by a single
tunable `SecondaryVowConfig.potency_tenths` (seeded 6 = ×0.6, the ratified batch-2 F-2 value).
Depth stays primary-only too: a secondary membership resolves at its ANCHOR role only — no
sub-role graduation, no deep rungs, no signature, no unique name — and its outcome guarantees
(`TIER_FLOOR`) bind one tier weaker (`floor_success_level - 1`); `BOTCH_IMMUNITY` is left
unweakened as a judgment call (it has no numeric field to soften — "half-immune to a botch" has
no coherent meaning). This is why the flag is named `is_secondary` rather than reusing "primary,"
which already means "anchor role" (vs. sub-role) elsewhere in this app — see the glossary.

**Rejected: a shared power cap/convexity penalty** (rounds 13-14) — scale the SUM of a
character's vow contributions down as more vows are held (e.g. a soft cap or diminishing curve
applied globally), rather than tagging each contribution by source. Rejected because it can't
express the specialist-supremacy invariant precisely: a global convexity penalty either weakens
the PRIMARY vow too (violating "a 3/0 build must never envy a 2/1" from the other direction — the
specialist should stay exactly as strong as before) or requires per-source bookkeeping anyway to
exempt the primary, at which point it's the same layer-split design with extra curve-fitting.

**Rejected: aggregate diffusion** — spread a FIXED total power budget across all engaged vows
(so two vows split what one vow would have gotten), rather than a secondary being purely
additive at a discount. Rejected because it makes taking a secondary vow a strict trade against
the primary (holding a secondary would visibly weaken the primary's own numbers), contradicting
the "fill a group gap" framing — a secondary should feel like a bonus capability layered on top,
never a tax on the primary's existing identity. The chosen design keeps Layer 1/3 completely
untouched by a secondary's presence (proven by the zero-chassis-leak tests), so a 3/0 specialist
is byte-identical whether or not a hypothetical secondary-holding rival exists.

**Conservative flip, flagged:** `covenant_level_bonus` (`world.mechanics.services`, keyed on
covenant LEVEL, not covenant ROLE) is not one of the four layers proper, but was flipped to
primary-only anyway — it is chassis-shaped (a flat passive stacking with gear/stat scaling), so
extending the "secondary never touches the chassis" rule to it avoids a fifth exception the next
reader would have to rediscover.

> Status: accepted · Source: issue #2641 · Related: ADR-0149 (four-layer vow-power model),
> ADR-0151/ADR-0152/ADR-0153 (Layer 4 situational-perk machinery)

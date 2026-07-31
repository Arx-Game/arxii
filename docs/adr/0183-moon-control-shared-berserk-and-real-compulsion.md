# ADR-0183: Moon control rides one shared Berserk, and Berserk finally compels

**Status:** Accepted (built #2845; extends ADR-0179)

**Decision.** The moon is a *control* pressure, not an exposure damage ladder: a
moon-bound character (tag-anchored `Moon-Bound` distinction, ADR-0179 — Lycans
innately via the "The Wolf's Fury" `SpeciesGiftGrant`) under a felt pull
(`illumination × sky exposure − shade`; clouds ride the ADR-0180 radiant-shelter
rows with zero moon-side code; clothing/magic never enter an instinct read) rolls
`moon_control` (willpower 1.0 + composure 0.5 — both existing stats, no new
skill) each reconcile window. Difficulty scales with pull and down with character
level, and gift-thread level; at level 6+ the check fires only while impaired
(condition-driven willpower a full tier down — drink, drugs, despair). Failure
forces the battle-form shift through the existing `trigger_transformation` seam
with `instance_value` = a moon-clarity multiplier (voluntary shifts get the same
multiplier — the moon empowers the form regardless of who chose the shift), and
applies the **same Berserk condition the fury engine applies** — one shared row
(now production-seeded with a healing ensure; it previously existed only as a
test factory plus a miscategorized dormant fixture), so revert-blocking, the
compulsion below, and the Restore to Sense break-out serve every producer (fury,
moon, future demonic rage). Berserk also gains real **compulsion**: an
auto-declared simplest-damaging-technique attack at the NPC-selection fallback
each combat round (steerable, not refusable), flee/parley/leave refusal, and an
out-of-combat rampage window that seeds a real encounter against the nearest NPC
through the ordinary hostile-cast seam. Restore to Sense — wired since #567 but
content-free — gets its production seed (Persuasion roll removes Berserk),
closing the talk-the-beast-down loop. Cani (the umbrella subspecies — khati
stay umbrella families, no per-animal rows) feel a flavor-only Moonlit Unease
under the open night moon.

**Rejected alternatives.** (a) A moon-specific rage condition — a second
loss-of-control state would fork the revert-block/break-out machinery and
orphan fury's Berserk. (b) A clock-driven battle-form stat engine — the built
`instance_value` snapshot at shift time gets the clear-full-moon peak without
any recompute machinery. (c) Consent-side gating for the in-combat compulsion —
everyone in an encounter already passed the entry gates; out-of-combat rampage
simply never grabs PCs in v1. (d) A `Lupi` wolf subspecies for the unease —
per-animal khati rows balloon uncontrollably (ruled); the Cani umbrella carries
it.

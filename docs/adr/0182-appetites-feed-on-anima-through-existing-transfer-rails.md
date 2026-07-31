# ADR-0182: Appetites feed on anima through existing transfer rails; NPC gorging kills through the real death pipeline

**Status:** Accepted (built #2853; extends ADR-0179)

**Decision.** Hunger is tag-anchored Distinctions (`Appetite: Blood` / `Appetite: Essence`,
plus `Undeath: Shade` as its own drain anchor so the half-living never pay upkeep): holders
are a bulk skip-set in the daily anima regen (no natural recovery IS the half-living
penalty), and periodic upkeep (vampires −1/week floor 10%; shades −1/day floor 0) mirrors
the purse-drain pattern exactly — config keyed on the Distinction, per-period receipts,
DRAIN-phase crons. Feeding is one commit seam (`feed_anima`, sineating inverted): SIP is
non-fatal by construction (never below a reserve), DRINK is bounded, GORGE drains to zero;
a Ravenous feeder attempting restraint rolls willpower and failure escalates to GORGE.
Overfill lands in a decaying `glut` field (never `current` — its `≤ maximum` validation
stays), spends first, never satisfies floors or quiets Ravenous, and grants sun mitigation
to appetite holders (stolen life answers the sun, but never clears a bane's shade-only
floor). Victim cost rides the existing anima→fatigue cast ratios, so a drained-empty victim
collapses through fatigue zones — no new knockout mechanic. PC targets ride the consent
request flow (a `drain` category under the antagonism root; `feed`/`drain` action-key
resolvers perform the transfer on an accepted successful roll); NPC targets bypass consent
(auto-resolve) and may be gorged to death — `mark_fed_to_death` is a narrow public seam
into the same `_mark_dead` finalization aging uses (estate, kinship, lifecycle), gated on
victim-is-NPC + story protection, and every kill mints a concealed murder-tagged deed that
generates scene evidence and witness knowledge through the standing justice seams. The desc
footer collapses the tired/hungry family to ONE worst-wins clause (deep Ravenous outranks
tiredness) beside the wound clause — never a line per condition.

**Rejected alternatives.** (a) A bespoke feeding-death path skipping `_mark_dead` — loses
estate/kinship/lifecycle finalization and the aging precedent already blesses direct
finalization for non-PC-source deaths. (b) Overfill as a raised `maximum` or unclamped
`current` — breaks the standing validation and turns gluttony into a durable tank.
(c) A per-species appetite probe — the distinction-tag anchor (ADR-0179) already unifies
innate and acquired (Shade) holders. (d) Upkeep on `Appetite: Essence` directly — would
drain Vulpi/Vesperi, contradicting the no-drain ruling; the shade drain gets its own anchor.

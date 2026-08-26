# ADR-0233: Situation declaration has no GM override — GMs make it true, not assert it

**Status:** Accepted (2026-08-26, Tehom in-session).

All 19 `Situation` evaluators (`world/covenants/perks/evaluators.py`) are pure
functions of live DB/positional state; no GM override path exists to force one
true by narration alone. This is deliberate, not a gap: **GMs are responsible
for creating the situation and making it true**, not for asserting it past the
evaluators. A narrated ambush should exist in checkable state — positioning,
encounter settings, an authored flag — not as a GM's unaudited "this is
happening now." Overriding a Situation evaluator would let a covenant perk
fire on narration alone, breaking the vow-power-is-stark invariant that perks
fire only on real state (extends ADR-0151/ADR-0153's situational-perk-machinery
decisions). GM tooling investment in this area goes toward making state
genuinely true — richer positioning (#3385), encounter settings (#3383) —
never toward an evaluator-bypass lever.

**Rejected:** *A narrow GM-declaration override for narrative-only
situations* — rejected because "narrative-only" is not a stable category
(a Situation used only for flavor today can gate a perk tomorrow), and a
declared-not-derived Situation is indistinguishable from a real one to any
future consumer, silently reintroducing evaluator fiat by another name.

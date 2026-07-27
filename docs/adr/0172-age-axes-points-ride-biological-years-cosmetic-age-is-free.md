# 0172. Age axes: Maturation Points ride biological matured years; cosmetic age change is free

**Status:** Accepted (#2756, 2026-07-27)

Character age is three derivable axes — chronological (`ic_birth_year` against the
game clock; null = unknowable, e.g. Sleepers), biological (`matured_years +
withered_years`), and apparent (= biological; cosmetic overrides live in the
appearance layer) — and the deterministic Maturation Point milestones (21, 24, 27,
…) ride **biological matured years only**. A spend is active iff its milestone
year ≤ current matured years, so freeze/reversal/catch-up reduce to one
comparison. Withered (curse) years count toward decline and death but earn
nothing: hostile aging is pure detriment. Glamours, disguises, and shapechange
never touch the stored axes — looking young is deliberately *free*, because the
advantage of illusion over true age-change (a beautiful mask over a mortally
aging true form) is the narrative point of illusions; pricing it would collapse
the two into one mechanic. **Rejected:** points riding *apparent* age (makes
every appearance system a stat toggle and forces disguise/persona integration);
random birthday rewards (a lottery birthday disappoints half the room — see the
decline curve's deterministic Frailty costs for the same principle); a stored
chronological age (derivation from the clock makes time skips correct for free).

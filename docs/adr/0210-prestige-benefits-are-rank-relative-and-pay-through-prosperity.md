# ADR-0210: Prestige benefits are rank-relative and pay through prosperity

**Status:** Accepted (#3091, 2026-08-10)

Mechanical benefits of prestige key on **relative rank, never raw value**:
being the highest-standing org matters identically whether the top score is
twenty thousand or a billion, so the authored `PrestigeRankBand` catalog maps
1-based ranks (declining scale across the top 100, minimal 101–1000, and
penalties for *negative* standing) to effects, and ranks are contextual —
all orgs on one ladder, personas on another. The monetary reward routes
**through bounded domain prosperity** (a weekly drift, granted only with zero
open threats, capped so the top rank approaches ~3× base income at full
prosperity) rather than any direct income multiplier. This keeps the reward
strong but structurally incapable of runaway: prosperity is clamped 0–100,
and the no-open-threats gate means predators and rivals can literally break a
rich house's bonus — prestige income is a thing you defend, not an annuity.
Raw treasury still never mints prestige (wealth impresses only when displayed
or spent — the existing dwellings/items/fashion channels). Rejected:
raw-threshold benefits (inflation-hostile: every economy drift re-tunes the
thresholds); a direct rank factor in the income-accrual chain (unbounded,
invisible, and double-counts with prosperity); treasury→prestige derivation
(double-counts economic might, which is its own Stature component).

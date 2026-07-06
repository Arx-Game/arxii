# ADR-0093: Housing neglect regresses a condition tier, never structure; above-normal shine is a temporary spend; inactivity mothballs, never ruins

#1930 replaces #676 Phase E's decay-on-miss (missed weekly upkeep drained
`BuildingProjectInstancePolish` rows, eventually flipping the building
"dormant") with a **condition-tier ladder** on `Building` — because automatic
loss may only regress, never destroy, and absence must never be punished
beyond opportunity (tuning-ledger principles ratified 2026-07-06; the
Second-Life ghost-town failure mode). Three deliberate shape choices: (1)
condition is a **step ladder of qualitative labels** (Decayed…Excellent…
Immaculate) with a per-tier prestige multiplier, NOT a continuously creeping
0–100 number — a visibly creeping value reinforces always-logged-in pressure,
while discrete tiers with long dwell times (arrears accrue for a grace window
before the first slide; ~a month of sustained neglect per tier after) *are*
the grace, and Excellent (100%) is presented as *normal* so most owners are
content there; (2) tiers **above** normal (150%/200%) are a deliberate,
temporary luxury spend (Grand Preparation before a gala) that dwell-decays
back within about a week — only the top tier can be *held*, via an
outrageous ultra-upkeep premium, so showing off is a positional-race cost,
never a treadmill; (3) long owner inactivity **mothballs** the building
(rooms hidden via their existing `is_public` lever, all accrual frozen, no
back-billing on return) — ghost towns are authored, not accidental. The
mothball sweep is its own weekly cron in `buildings` rather than a step
inside roster's `sweep_activity_states`, keeping the dependency pointing
specific→general (ADR-0010). Rejected alternatives: keeping polish-drain
with gentler numbers (still destroys player investment, still needs the
never-wired restoration half); a single decaying percentage multiplier
(rejected by Apostate for the always-online pressure above); back-billing
mothballed weeks (punishes absence beyond opportunity). Supersedes the
#676 Phase E decay/dormancy design; "dormant" is retired from the buildings
vocabulary (collision with `DecayTier.DORMANT`).

> Status: accepted · Source: #1930, tuning ledger §6 · Supersedes: #676 Phase E decay

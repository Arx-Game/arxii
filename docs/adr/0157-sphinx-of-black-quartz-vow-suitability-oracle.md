# The Sphinx of Black Quartz: a three-tier, code-defined, soft-gate vow-suitability oracle

The Sphinx (#2640) answers "would this character's kit satisfy this vow's authored
demands" as a **read-only report**, not a resolution-time gate: `world.covenants.sphinx
.judge_vow` re-runs the same kit∩role-demand join `covenant_role_specialty_power_term`
(`world.magic.services.power_terms`, #2443) already uses for the always-on specialty power
term, but reports a verdict instead of computing a bonus. The verdict is **three-tier, never
pass/fail** (`SphinxTier.TAKES`/`DORMANT`/`NOT_YET`, `world.covenants.constants`) — TAKES
when every demand is covered (or the vow is unauthored and so makes no demands at all),
DORMANT when some but not all are, NOT_YET when none are (paired with a bounded shopping
list of learnable techniques that would flip the answer). The demand set folds in
situation-sourced demands from a role's SELF-beneficiary `VowSituationalPerk` rows via a
new, deliberately small, code-defined `SITUATION_CREATOR_FUNCTIONS` mapping
(`world.covenants.perks.constants`) — the `TARGET_DISTRACTED`/`TARGET_SWAYED_BY_ALLY`
provenance mapping (which technique casts can DB-state-create a DB-state situation) run in
**reverse** as a static report, rather than re-deriving provenance live; situations absent
from the mapping are positional/encounter state and demand nothing from a kit. Critically,
the Sphinx **never gates anything** — the soft-gate ruling holds: a player may swear a vow
the Sphinx warned about (`assign_covenant_role`/`change_role` remain ungated, correctly),
and dormant-vow messaging (#2536 slice 3) already carries the "you took the vow anyway"
diegetic follow-through. Rejected alternative: a hard qualification gate at role assignment
(refuse to let a character swear a vow their kit can't yet answer) — rejected because it
would contradict the ratified stark-power/informed-mismatch design (a vow's weakness is
something a character can grow into, not a wall that keeps them out of the story), and
because it would require the Sphinx to become a second, blocking source of truth
duplicating whatever `assign_covenant_role`'s own prerequisites decide, rather than staying
a single, pure, side-effect-free advisory report reused identically by the staff coverage
audit, the player REST endpoint, and the `sphinx` telnet command.

> Status: accepted · Source: issue #2640 · Amends: none · Related: ADR-0149 (four-layer
> vow-power model — the specialty/situational-perk demand tables this reads), ADR-0151
> (situational-perk machinery, slice 1 — `Situation`/`VowSituationalPerk` shape),
> ADR-0153 (dormant-vow messaging — the diegetic follow-through for an informed mismatch)

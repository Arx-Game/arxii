# Removal-from-play is reached through the fuse walk, never granted by fiat

Legend requires that removal-from-play (character death/permanent loss) be
*reachable*, not that every staked beat threaten it directly. `RiskCalibration.max_fuse_hops`
(`world/stories/models.py`) sets, per `RenownRisk` tier, how many failure-cascade
episode-hops may separate a beat from a stake at `StakeSeverity.REMOVAL` — EXTREME
is 0 (the beat itself must offer removal), LOW is 3 (removal may be three failed
transitions away). `services.stakes._jeopardy_reachable` BFS-walks the authored
failure cascade (`Transition.cached_required_outcomes` — FAILURE-gated or
unconditioned transitions, stopping at PITCH-maturity episodes) to enforce
this at readiness-check time. Removal itself stays mechanically mediated
end-to-end: a branch firing routes through the existing vitals/consequence
pipeline, never a bespoke "kill this character" write. PR2's structured
world-state writers enforce this with validation
(`stake_resolution_payload_problems`, shared by serializer and model `clean`):
`StakeResolution.sets_subject_lifecycle` is only legal for NPC_FATE subjects
whose sheet is not player-held, and the writer re-checks the gate at fire
time. PC deaths only ever happen via a succession of lost stakes walking the
fuse to its end (peril pools → `process_damage_consequences` → `_mark_dead`,
which propagates `LifecycleState.DEAD` to the roster), never a single beat's
fiat.

We rejected requiring every beat to wager jeopardy directly (mandatory
per-beat stakes at the terminal severity) as too blunt — a staked negotiation
or heist beat legitimately doesn't threaten a life on its own turn, only through
what it sets up. We also rejected letting a `StakeResolution` branch carry a
direct death/removal payload, since that would let authored content bypass
stats, defenses, and the vitals pipeline that ADR-0040 and ADR-0049 already
established as the sole path to incapacitation and loss.

> Status: accepted · Source: #1770; see also ADR-0067 (Beat.risk is the stakes
> wager declaration), ADR-0023 (PvP is structurally non-lethal), ADR-0054
> (Legend is monotonic), ADR-0037 (difficulty scales on party size/level only)

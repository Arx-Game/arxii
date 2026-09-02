# Stake branches are chosen by authored key, never by a GM pick

A `Stake`'s named branch inside a WIN/LOSS/WITHDRAWAL column (`StakeResolution.outcome_key`,
#1760) used to be reached only through `resolve_stake_by_gm_pick`: a GM, after the beat
resolved, chose which named branch fired from the stake's authored set. #3561 retires that
runtime choice (ruling 2026-09-01: GM choice happens while designing, never after players
act). `_branch_for_column` now selects the branch itself, in this order: a lifecycle-state
match (unchanged, #1760), then the branch whose `outcome_key` equals the completing beat's
own `outcome_key` (the option the party's route ended on, #3565), then the column's plain
default, then the column's first authored branch. A column with no branch authored for the
resolved outcome - WIN, LOSS, WITHDRAWAL, or the per-stake revoked-consent override - records
`StakeOutcome(resolution=None)` and fires nothing, on every path (Decision 2, #3561): an
unready contract that ran anyway is auditable, never a stake left pending a decision. The
readiness report catches the authoring gaps this creates ahead of time: a column with a named
branch but no default, and a named key that no option of the beat's scenario declares.

**Rejected: keep the constrained pick, build an adjudication UI for it.** The constrained pick
already existed and worked; the alternative to retiring it was building the stakes editor
around it - a "resolve stake" control on the GM story rail letting the GM name the branch once
the beat resolved. That keeps exactly the failure mode #3559 (`docs/adr/0257`) already removed
from beat outcomes: a runtime judgment call made after play has moved on, on a second surface
(the individual stake) instead of the beat as a whole. Authored-key selection needs no new UI
at all - the GM already named the branch's key when they wrote it, and the party's own choices
during play supply the other half.

**Supersedes:** the PR2 "GM constrained pick" decision recorded in `docs/systems/stakes.md`'s
old "GM constrained pick" section (no prior ADR existed for it). Migration
`0211_retire_stake_outcome_gm_pick` is a restructure, not a discard (ADR-0237): it rewrites
every historical `StakeOutcome.method="gm_pick"` row to `"machine"` before narrowing
`StakeOutcomeMethod`'s choices to `MACHINE` alone; `resolved_by`/`gm_notes` are kept
unmodified as historical audit fields on those rows.

> Status: accepted · Source: session 2026-09-02 (#3561; ruling 2026-09-01 GM choice before play, `feedback-gm-choice-before-play-scenario-graph`)

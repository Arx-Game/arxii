# Battle-earned Legend is win-gated at authored tier values, with a standout exception for both sides

`world.battles.legend_wiring.apply_battle_legend_awards` (#2184), registered as a
battle-conclusion hook, mints a shared `create_legend_event` **only for the winning
side** — every `BattleParticipant` plus every `BattleUnit.commander` on
`battle.outcome`'s winning `BattleSideRole`, at an authored flat tier value
(`BATTLE_LEGEND_DECISIVE_VALUE = 25` / `BATTLE_LEGEND_MARGINAL_VALUE = 12`, mirroring
`DECISIVE_MARGIN`'s existing decisive/marginal split). The losing side earns nothing
from the event. Separately, a smaller **standout pass** (`BATTLE_LEGEND_STANDOUT_VALUE
= 15`) scans every resolved `BattleActionDeclaration` on *either* side with
`success_level >= STANDOUT_SUCCESS_LEVEL` (2, clearly above bare success) on a
`DRAMATIC_KINDS` action (RESCUE/ROUT/BREACH) and awards its actor a solo deed via
`create_solo_deed` — stacking with the victory event by design, since a losing-side
rescue is still a story worth telling.

Rejected: minting a deed for every participant regardless of outcome (or scaling
value by battle size/duration). That reads as automatic legend inflation — every
battle a PC merely shows up for would pad their legend total, diluting Legend as a
"remarkable accomplishments" signal (see `docs/systems/societies.md`) and undercutting
the curated, authored-consequence-pool design tenet the checks/consequence system
already holds elsewhere in this codebase. Win-gating plus a narrow standout exception
keeps the story-worthiness bar high while still rewarding a dramatic losing-side
action on its own merits.

**Amended by #3467 (ADR-0249).** The flat tier values this ADR authored
(`BATTLE_LEGEND_DECISIVE_VALUE` 25 / `_MARGINAL_` 12 / `_STANDOUT_` 15) are
retired: what a battle pays now comes from its beat's risk tier through
`RiskCalibration.legend_award`, priced per person by station and personal risk
in `world.battles.legend_settlement`. Two things this ADR decided are kept
verbatim, and were kept deliberately rather than by accident:

1. **The curation.** A battle standout is still specifically RESCUE / ROUT /
   BREACH at or above `STANDOUT_SUCCESS_LEVEL`, on either side — not any high
   roll. The generic ledger has no such notion, so battles keep reading
   `BattleActionDeclaration`, and the per-kind titles ("Daring rescue at X")
   travel with the deed.
2. **The stacking.** Standouts stack with the victory event, as this ADR says
   "by design". The generic seam introduced in #3463 does the opposite — it
   skips anyone already paid a share, reasoning that stacking double-pays the
   same act. That reasoning holds where the crucial contribution IS what the
   shared deed is paying for; it does not hold for a war, where a rescue under
   fire is not what the victory deed was about. Battles therefore run the
   standout pass separately. **Whether the generic seam should also stack is an
   open question, flagged rather than silently settled.**

This ADR's own generalisation — "a losing-side rescue is still a story worth
telling" — became the general rule in ADR-0249, which applies it to every
source rather than to `Battle` alone.

> Status: accepted · Source: #2184 · Related: `docs/systems/battles.md` §Legend
> Wiring, `docs/systems/societies.md` §Legend System, ADR-0010 (FK direction —
> `battles` importing `societies` here, both being general/reusable systems)

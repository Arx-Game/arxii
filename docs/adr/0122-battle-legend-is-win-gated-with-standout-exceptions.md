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

> Status: accepted · Source: #2184 · Related: `docs/systems/battles.md` §Legend
> Wiring, `docs/systems/societies.md` §Legend System, ADR-0010 (FK direction —
> `battles` importing `societies` here, both being general/reusable systems)

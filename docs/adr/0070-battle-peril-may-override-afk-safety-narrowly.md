# Battle Surrounded peril may override AFK-safety, narrowly and explicitly

A `Battle` may opt in (`Battle.afk_peril_override`, default off) to letting a
Surrounded participant's peril escalate every round the GM resolves, regardless of
whether that participant declared this round — bypassing the battle-scoped equivalent
of the room-based `#1480` own-peril skip. This is a narrow, explicit exception to
ADR-0004 (tempo is action-driven, never wall-clock): the trigger is still the GM's own
`resolve_battle_round` call (action-driven, never `game_clock`), not a timer; only the
Surrounded escalation is affected — round advancement itself stays entirely
GM-triggered, and nothing else ADR-0004 protects changes. Large multi-hundred-PC
engagements would otherwise force a GM to either stall on absent players' safety or
manually track which of them get a "free pass" each round; the knob makes the
trade-off explicit and per-battle rather than silently inconsistent. Rejected: a
global AFK-safety toggle (too broad, would weaken ADR-0004 everywhere) and an
automatic per-participant timeout (adds a wall-clock dependency ADR-0004 exists to
avoid).

> Status: accepted · Source: #1592 Decision 8, #1733 · Extends: ADR-0004

# Out-of-combat sudden harm defers via the scene-round declare/resolve shape, not a pre-armed check

Combat's Interpose arms via a `CombatRoundAction` declared during a round's DECLARING phase before
the blow resolves, but out-of-combat sudden harm (a trap, a failed-check consequence) had no
round/declaration structure — it fired synchronously in one call
(`world.mechanics.effect_handlers._deal_damage`). Rather than synchronously checking for an
already-armed declaration (which only helps a party already on guard *before* harm occurs, and gives
no reactive window to anyone not already prepared), `arm_or_apply_sudden_harm` holds the damage
(`PendingSuddenHarm`) and bootstraps a real STRICT scene round
(`ensure_round_for_acute_condition`, already used by falling/bleed-out) when a bystander is present,
giving them a genuine declare-then-resolve window — the same shape combat already has — before
resolving through the unchanged `dispatch_interpose`. We rejected mirroring Succor's non-combat
sibling (#1744), a synchronous "declare Interpose ahead of time, in case something happens" model:
that pattern only works for a recurring per-round hazard tick (there's always a next tick to arm
against), but a one-shot ambush/trap has no recurring moment to pre-arm for — the round has to be
created reactively, at the moment of harm, or the bystander never gets a window at all.

> Status: accepted · Source: issue #1316

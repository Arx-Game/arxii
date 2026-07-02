# Effective risk is priced relative to declared target level, not the raw declared tier

`Beat.risk` (ADR-0067) is the GM's declared magnitude, but what a party actually
risks depends on how they compare to the beat's `target_level` at the moment the
contract locks. `services.stakes.compute_effective_risk` shifts the declared
`RenownRisk` down the `RISK_LADDER` one tier per `LEVELS_PER_TIER` (2) levels the
party's average is over target, and up by a bounded `UNDER_LEVEL_MAX_UPGRADE` (1)
tier when under target; `RenownRisk.NONE` is a fixed point (never upgraded).
`activate_stakes_contract` computes this once at lock time and stores it on
`StakeContractActivation.effective_risk`, which is what Legend actually pays on
(`effective_risk_for_beat`) — not the raw `declared_risk`. Payout can downgrade
(an over-leveled party, or an unready contract per the menu-first ADR, both price
toward NONE) but consequences authored on `StakeResolution` never downgrade: the
fuse and its failure branches fire at full authored severity regardless of party
level, because losing is losing. This is deliberately the *only* axis effective
risk scales on, per ADR-0037 (encounter difficulty scales on party size + average
level only) — no thread, relationship, covenant, or fashion inputs.

The rationale is anti-farming: a beat that's highly risky to a level-4 party is
not risky at all to a level-10 party grinding it for easy Legend, so the payout
must decay toward NONE rather than staying fixed at the declared tier. We
rejected scaling the *encounter's difficulty* instead (buffing enemies/stakes to
match an over-leveled party) because ADR-0037 already forecloses that axis for
combat, and doing it here for stakes would silently reopen it through a side
door. We also rejected scaling effective risk by any input besides
party-size/average-level (threads, covenant standing, gear) for the same reason.

> Status: accepted · Source: #1770; respects ADR-0037 (encounter difficulty
> scales on party size + average level only), extends ADR-0067 (Beat.risk is
> the stakes wager declaration)

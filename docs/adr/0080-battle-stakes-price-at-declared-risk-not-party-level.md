# Battle stakes price at declared risk, not party-level-adjusted risk

ADR-0077 established that `activate_stakes_contract` prices a stakes contract's
effective risk relative to the gap between `Beat.target_level` and the
activating party's average character level — a beat highly risky to a level-4
party is trivial to a level-10 party, so payout decays toward NONE rather than
staying fixed. That reasoning holds for scene-level stakes (a duel, a
negotiation, a single encounter), but not for a war-scale `Battle`: a battle is
fought over an objective — a bridge, a city, a campaign-track position — whose
stakes don't get less real because a handful of strong PCs happened to be
enlisted that day. The war's importance is authored by the story designer via
`Beat.risk`, not a function of the specific attendee roster on any given day of
an extended, real-time conflict.

`activate_stakes_contract` (`world.stories.services.stakes`) gains an additive
`scale_by_party_level: bool = True` parameter. When `False`, a ready contract's
`effective_risk` equals its `declared_risk` unconditionally — the
party-level-gap computation (`compute_effective_risk`) is skipped entirely.
The readiness gate is unaffected: an unready contract (no stakes authored, no
`RiskCalibration` row, etc.) still activates at effective `NONE` regardless of
this flag — a contract that was never properly authored doesn't pay out just
because its risk isn't scaled. `world.battles.beat_wiring.activate_stakes_for_battle`
is the only caller that passes `False`; every existing caller (combat's
`activate_stakes_for_scene`, missions' `activate_stakes_for_instance`, the
`declare_stakes` GM action) keeps the default `True`, unaffected.

We rejected computing an alternative party-level-style gap from army/unit
strength (`BattleSide`/`BattleUnit`) instead of bypassing the mechanism
entirely — there's no existing "declared target strength" lever to diff
against, and inventing one is unjustified scope for what a single boolean
already expresses correctly. We also rejected leaving the existing
party-level scaling in place for Battle (simplicity via no new parameter) — it
directly contradicts the premise that a war's stakes are about the objective,
not the attendees; a battle over a strategic bridge fought by a
lower-level militia and one fought by legendary heroes should carry the same
stakes for that bridge.

> Status: accepted · Source: #1785; carves out ADR-0077 (effective risk is
> priced relative to declared target level) for war-scale Battle stakes only —
> ADR-0077's mechanism and rationale remain unchanged and in force for every
> other caller.

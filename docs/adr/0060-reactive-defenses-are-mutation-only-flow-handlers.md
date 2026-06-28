# Reactive defenses are mutation-only DAMAGE_PRE_APPLY flow handlers with a shared anima-cost pattern

Force-field (absorb), reflect, and blink ride the existing
condition → reactive-trigger → flow spine on `DAMAGE_PRE_APPLY`. Each handler is
**mutation-only**: it sets `payload.amount = 0` on success; lower-priority
interceptors guard `if payload.amount <= 0: return` so the cascade is preserved
without cancelling the event. Priority order is blink 30 > reflect 20 > absorb 10.
We rejected adding a `CANCEL_EVENT` child step to the reflect/blink flows: child
steps run unconditionally after their parent step, so a `CANCEL_EVENT` fires even
when the anima-cost fizzle path returns early — the attack would be cancelled even
when the bearer cannot afford the defense, making the fizzle path dead and the
anima cost meaningless. This bug was caught by the first real emit→flow→handler E2E
test (#1584 Task 16). The shared cost pattern uses two `ConditionTemplate` fields:
`upkeep_anima_per_round` (drained each round by `drain_reactive_upkeep` on the
`COMBAT_ROUND_STARTING` event) and `reactive_anima_cost` (paid per fire; an
unaffordable cost means the handler returns early without zeroing the payload and
the attack lands). `reflect_damage` avoids a redirect loop via a `bypass_pre_apply`
kwarg on both `apply_damage_to_participant` and `apply_damage_to_opponent` that
skips the emit + interpose path for the bounced hit (loop-safety is structural,
not a runtime flag check).

> Status: accepted · Source: issue #1584 · Confidence: built & E2E-tested (
> `magic/tests/test_effect_handlers.py` 3 reactive E2Es); `ConditionTemplate.
> upkeep_anima_per_round` / `reactive_anima_cost`; `bypass_pre_apply` kwarg on
> both `apply_damage_to_*`; Task 16 production-bug fix.

# ADR-4747-A: A vow steps a buff in points, not outcomes, fixed at cast

A caster whose engaged vow has a technique specialty for the function of the technique she
casts makes its sized buff or debuff one size step stronger: each modifier adds
value(L, size + 1) minus value(L, size) from the lane's `ModifierValue` table, signed like the
authored modifier, as the contribution's untapered `vow_part`. L is her vow thread's shown
level, and only that: a weak cast from a deep vow still steps at the vow's depth (the owner's
2026-10-27 ruling). We chose points only. #4551 section 5.4 also proposed outcome floors and
ceilings for a vowed buff; the owner dropped them on 2026-10-27, so the step never touches
`_apply_outcome_guarantees` and a vowed buff can still fail to matter on a bad roll. We also
chose to snapshot L at cast, in `ConditionInstance.modifier_vow_level`, rather than derive it
on read: deriving it would cost a thread query on every stat and check read of a buffed
character (the #552 combat hot path), and the buff would change strength mid-scene as the
thread grew. The price is that a buff cast before a thread levels keeps its old step until
it is re-cast (a re-cast keeps the higher step level, like `modifier_level`). A secondary vow
can be the stamped vow (it is first when the primary is disengaged); it steps at its thread
level scaled by `SecondaryVowConfig.potency_tenths`, the convention of the specialty layer
the step is keyed on.

> Status: accepted · Source: owner rulings 2026-10-27 on #4551 · issue #4747 (slice 9 of #4551)

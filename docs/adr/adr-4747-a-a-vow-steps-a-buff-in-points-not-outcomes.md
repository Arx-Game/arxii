# ADR-4747-A: A vow steps a buff in points, not outcomes, tuned per vow and fixed at cast

A caster whose engaged vow has a technique specialty for the function of the technique she
casts makes its sized buff or debuff one size step stronger: each modifier adds
(value(L, size + 1) minus value(L, size)) x tenths / 10 from the lane's `ModifierValue` table,
rounded half up and signed like the authored modifier, as the contribution's untapered
`vow_part`. Only that one-size-up shape is fixed in code; every amount is staff-tuned data.
L is her vow thread's shown level, and only that: a weak cast from a deep vow still steps at
the vow's depth. The tenths are the matching `CovenantRoleTechniqueSpecialty` row's
`multiplier_tenths`, the same row that names the function and already scales the
specialty's cast power, so one dial tunes a vow's buffs; when her role and its sub-role (or
anchor) both carry a matching row, the larger multiplier counts, not the sum. A secondary
vow (the stamped vow when her primary is disengaged) keeps the full L and multiplies the
tenths by `SecondaryVowConfig.potency_tenths / 10`, rounded half up, as the specialty layer
scales a secondary everywhere else (the first build scaled the secondary's level instead,
and the owner replaced that on 2026-10-27). We chose points only: #4551 section 5.4 also proposed outcome floors and ceilings for a vowed buff,
and the owner dropped them on 2026-10-27, so the step never touches
`_apply_outcome_guarantees` and a vowed buff can still fail to matter on a bad roll. We
chose to snapshot L and the tenths at cast (`ConditionInstance.modifier_vow_level`,
`modifier_vow_tenths`) rather than derive them on read: deriving would cost thread and
specialty queries on every stat and check read of a buffed character (the #552 combat hot
path), and the buff would change strength mid-scene as the thread grew or staff retuned
the row. The price is that a buff cast before a thread levels or a retune keeps its old
step until re-cast; a re-cast keeps the stronger step, compared by level and then tenths.

> Status: accepted · Source: owner rulings 2026-10-27 on #4551 and #4747 · issue #4747 (slice 9 of #4551)

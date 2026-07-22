# Boss fights get their three-act shape from diversity-weighted break accrual, a proportional lieutenant gate, and a Soulfray-derived pacing floor — not authored acts

Ratified design (lore repo `design/covenant-vows-consolidated.md` §6, batch-3 transcripts
`design/2026-07-22-vow-transcripts-batch-3.md` F-6a/b, F-7a; arxii#2642): a boss fight should
read as suppress-the-court → break-the-wall → the-earned-one-shot without anyone authoring
"act 1"/"act 2" beats. Three mechanical levers produce that shape as an emergent property of
existing systems, replacing three earlier judgment calls:

1. **Diversity-weighted break-bar accrual replaces the flat chip (dead by ruling).** The pre-#2642
   `assess_break_bar` had two feeds: combo `bonus_damage`, and a flat 1-unit chip gated on ">=2
   distinct PCs dealt damage with >=2 distinct effect_types this round" — an all-or-nothing gate
   that blocked a solo PC entirely and never credited non-damage pressure. `BreakBarContribution`
   (mirrors `ClashContribution`'s per-round audit shape) now persists one row per qualifying feed
   — DAMAGE, COMBO, plus three new non-damage feeds: HOLD (a PC-side LOCK-clash win against the
   boss this round), DEBUFF (a new behavior-altering condition landed on the boss), SUPPRESSION (a
   reinforcing lieutenant newly suppressed). Depletion sums 1 unit per distinct (actor, kind) pair
   this round — no per-actor cap, so a solo PC's diverse actions now count instead of being
   entirely gated out — doubled for a (kind, effect_type) pair's first-ever appearance in the
   encounter (`BREAK_NOVELTY_MULTIPLIER`), which is what makes "suppress the court" (HOLD/
   SUPPRESSION feeds) mechanically matter even before any damage lands on the wall.
2. **The lieutenant gate is proportional, not a hard block.** `CombatOpponent.reinforces` (a
   self-FK, null for non-lieutenants) marks a lieutenant's boss. Each round's raw depletion is
   divided by `1 + active_unsuppressed_reinforcers` — active meaning ACTIVE status, morale not
   BREAK, no behavior-altering condition, not pinned in an ACTIVE `EngagementLock`, and it acted
   this round (a parked/idle lieutenant never gates). Floored at 1 unit whenever depletion
   occurred, so the gate slows the wall, never stalls it outright — the fight cannot softlock on
   an uncleared court.
3. **The pacing floor derives from Soulfray staging, not an arbitrary constant.**
   `minimum_break_bar_threshold()` clamps a stamped `break_bar_threshold` to at least
   `(soulfray_stage_count + 2) * BAR_UNITS_PER_ROUND`, applied at both stamping sites
   (`_stamp_phase_break_bar_config` at spawn, `_stamp_break_bar` at phase transition). This ties
   the wall's authored capacity to how long the anima -> Soulfray -> audere climb actually takes to
   play out (batch-3's median 6-8 rounds, tail ~10) instead of an author guessing a number in
   isolation. Returns 0 (no clamp) when Soulfray has zero authored `ConditionStage` rows — a
   bare/test DB is never forced onto a floor derived from unauthored content.

Two smaller, tightly-scoped additions round out the three-act read: BOSS-tier opponents resist a
decisive Parley calm by one success-level step (`BOSS_PARLEY_RESISTANCE_STEP`) at the single clean
seam in `_resolve_parley` — the court can be calmed at the normal threshold, the boss cannot; and
the break moment broadcasts a celebration naming every distinct contributor recorded across the
encounter's `BreakBarContribution` rows, mirroring the combo-finisher narration precedent
(`join_labels`, promoted from `interaction_services._join_labels` to a shared public helper since
it now has two callers).

`assess_break_bar` moved from before to after `resolve_round`'s clash post-pass (still before
phase transitions) so the HOLD feed can see a LOCK-clash win that resolved in the same round —
without the reorder, `run_clash_round`'s resolution for the current round would not exist yet when
break-bar assessment ran.

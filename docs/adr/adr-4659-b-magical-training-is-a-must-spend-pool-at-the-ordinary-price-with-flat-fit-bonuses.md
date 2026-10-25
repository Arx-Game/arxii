# ADR-4659-B: Magical training is a must-spend pool at the ordinary price, with flat fit bonuses

**Date:** 2026-10-25
**Status:** Accepted (owner ruling 2026-10-25 on the parent spec #4659; built in its slice 2, #4665)
**Issue:** #4659, #4665. Supersedes ADR-4457-A (the schooling floor).

## Decision

A schooled character no longer starts with every Magic skill at one fixed level. Character creation
gives a pool of magical training points and the player spends all of it on Magic skills.

- **The pool.** The base is the sum of the draft's distinction effects on the `magic_training_points`
  modifier target (the schooling stance's granted distinction, plus any other distinction that
  carries the effect). `CharacterDraft.magic_training_pool` computes it live.
- **Flat fit bonuses, only with some training.** When the base is above 0, a Tradition that favors
  the student's Major Gift adds `gift_fit_training_bonus` and one that favors the student's aura
  adds `affinity_fit_training_bonus` (`TraditionTeachingConfig`). A draft with no training gets
  nothing, even when it fits both. The total is rounded down to one skill step.
- **The ordinary price.** A Magic skill value costs its own value in points, 10 per step, as every
  skill does. Fit raises how much a student has to spend and never changes a price.
- **Must spend.** The Gift stage fails until the allocation equals `required_spend`, which is the
  pool capped at what the active Magic skills can hold.
- **Academy.** The same fit eases a course taught under the Tradition by lowering the session
  check's difficulty. The roll's outcome still decides how much development is gained.

The fit is resolved in one place, `teaching_fit` in `world/magic/services/teaching_fit.py`, which
character creation and the Academy both call. Migration 0299 carried each old stance floor into its
distinction as `floor x active Magic skill count`, and 0300 dropped the column.

## Rejected

- **A per-step price discount for a fitting student.** Prices that move with the student read as
  confusing at the point of spending (owner ruling 2026-10-25). A flat bonus to the pool says the
  same thing in one number.
- **Fit as more development per Academy session.** Checks decide gain in this game; fit makes the
  check easier and the outcome decides the rest.
- **A bonus proportional to the base.** It rounds to odd numbers that do not land on a skill step.
- **Keeping the uniform floor** (ADR-4457-A). One level for every Magic skill gave the player no
  choice of what their schooling was in, and had no place for a Tradition to teach some students
  better than others.

> Status: accepted · Source: #4659 owner ruling 2026-10-25 · Confidence: built and wired in #4665

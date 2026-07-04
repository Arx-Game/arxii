# ADR-0086: Thread pulls are target-aware via a per-target_kind modulation seam; regard attaches to the pull, not the Prerequisite system

## Status

Accepted

## Context

Thread pulls (`resolve_pull_effects`) previously resolved a pull effect's scaled
value purely from the pulling character's own thread level and the effect's
authored payload — no notion of *who* the pull's action was aimed at. #1831 needed
Court (`COVENANT_ROLE`) pulls to react to the Court leader's `NpcRegard` (#1717,
ADR-0085) opinion of the live target: a servant striking someone their master
despises, or shielding someone their master favors, should hit harder.

Two designs were considered for wiring the target in:

1. **Extend the `Prerequisite`/targeting-precondition system** (the machinery
   `Technique.target_prerequisites` uses, #1793) to also carry a scaling factor,
   so "regard-scaled" became a property of the *technique's target validation*.
2. **Attach modulation to the pull itself** — thread the live target through
   `resolve_pull_effects` and dispatch a scaling rule keyed on `thread.target_kind`,
   independent of the technique's own targeting/prerequisite machinery.

The Prerequisite system answers "is this a legal target" (a boolean gate,
evaluated pre-flight or per-target in an AoE filter) — it was never a value
pipeline, and bolting a numeric multiplier onto a pass/fail gate would have
made every consumer of `Prerequisite` reason about two unrelated return shapes.
Regard-scaling is also thread-specific (only COVENANT_ROLE threads care), not
technique-specific — the same technique cast by two different servants pulling
different threads should scale differently, which the technique's own
prerequisites can't express.

## Decision

- `resolve_pull_effects(threads, tier, *, in_combat, target=None)` gains a
  `target: ObjectDB | None` parameter — the live target the pull's action is
  directed at (combat's focused target via `PullActionContext.target`, or the
  non-combat cast's resolved target via `use_technique(pull_target=...)`).
  `None` for ephemeral/untargeted pulls — existing behavior is unchanged.
- A new, single-purpose seam — `apply_target_modulation(thread, target,
  effect_row, base_scaled)` (`world/magic/services/pull_modulation.py`) —
  dispatches on `thread.target_kind` and is a no-op unless a rule is registered
  for that kind. This is the one extension point for all future per-`target_kind`
  pull modulation (a deferred RELATIONSHIP_TRACK rule is noted in the module
  docstring, not built).
- The only rule wired today, `court_regard_modulation`
  (`world/magic/services/pull_modulation_court.py`), fires for `COVENANT_ROLE`
  threads: it resolves the Court leader's persona, reads their signed `NpcRegard`
  for the target, and empowers the pull when the effect row's new
  `ThreadPullEffect.regard_polarity` (`RegardPolarity`: OFFENSIVE / PROTECTIVE /
  NEUTRAL) matches the sign of that regard.
- Regard-based scaling is **not** modeled as a `Prerequisite` and does not touch
  `Technique.target_prerequisites` or the AoE/SINGLE targeting-precondition
  machinery (#1793) at all — it lives entirely inside the pull-resolution path,
  orthogonal to whether the technique's own target is legal.

## Consequences

- `resolve_pull_effects` and `PullActionContext` (`world/magic/types/pull.py`)
  now carry a target concept that non-COVENANT_ROLE pulls simply ignore — every
  existing pull stays byte-identical because `apply_target_modulation` no-ops
  without a registered rule.
- A future consumer that wants "scale this pull by some relationship to the
  target" (e.g. RELATIONSHIP_TRACK) extends `apply_target_modulation` with one
  more dispatch branch — it does not need to touch `Prerequisite` or the
  technique targeting system.
- The combat-UI picker (`compute_thread_applicability`) needed its own signal
  for "this pull would have no stake here" — `InapplicabilityReason.
  COURT_LEADER_NO_STAKE` — computed independently from the same regard/polarity
  facts, since applicability is a pre-cast UI concern while modulation is a
  resolution-time concern; keeping them separate avoided coupling the picker to
  the resolution path's internals.

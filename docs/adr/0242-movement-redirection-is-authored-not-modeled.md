# ADR-0242: Special movement is authored in the flows DSL, never modeled per space

<!--
Numbering note (#3416): docs/adr/ topped out at 0241 both in this worktree and
on origin/main at the time of writing. Re-verify at enqueue in case another PR
claimed 0242 in the meantime - collisions merge silently.
-->

**Status:** Accepted (2026-08-28, #3416)

## Context

We wanted a hedge maze where every direction takes you deeper and you always
arrive within a bounded number of moves. The first design proposed a
`Labyrinth` / `LabyrinthLayer` / `LabyrinthRoom` / `LabyrinthTransit` model set
plus a destination-substitution seam in `TraverseExitAction`.

That was rejected on review. The objection was not that the models were wrong
in detail; it was that adding a model and a hardcoded implementation for each
interesting mechanic is the road that ends at a `LordFluffwinkleOrbOfAnnihilation`
class. Flows, behaviors and conditions were built (#42) precisely so arbitrary
mechanics could be authored as rows. That they had no production consumers was
a gap to close, not evidence to route around them.

The same failure mode is already visible in field form: `ConditionInstance`
carries nine FKs, several of them one-off anchors bolted on per feature
(`source_vow` for #2643, `cast_destination` for #2019).

## Decision

**Special movement is authored, not modeled.** A magical space is
`ConditionTemplate` / `ConditionStage` / `ConditionInstance` /
`FlowDefinition` / `FlowStepDefinition` / `TriggerDefinition` / `Trigger` rows,
plus generic service-function verbs. No model, field, or class names any
particular space.

The mapping, none of which required a new model or field:

| Concept | Existing surface |
|---|---|
| a character's depth in a space | `ConditionInstance.current_stage` -> `ConditionStage.stage_order` |
| dwell budget at each depth | `ConditionStage.rounds_to_next` |
| the arrival guarantee | the authored sum of `rounds_to_next` - **data, not a Python rule** |
| per-depth effect on entry | `ConditionStage.on_entry_conditions` |
| per-depth prose | stage `name` / `description` |
| the space's logic | a `TriggerDefinition` + `FlowDefinition` |
| which rooms belong at which depth | a condition on the **room** (`ConditionInstance.target` accepts rooms) |

`Character.move_to` dispatches `MOVE_PRE_DEPART` and honors the payload's
destination, so an authored flow redirects a move with `MODIFY_PAYLOAD` or a
service-function verb.

## Alternatives rejected

- **A `Labyrinth` model set** (the original spec). Rejected as above: it solves
  one space and teaches the codebase the wrong lesson.
- **Redirecting inside `TraverseExitAction`.** Only covers exit traversal, and
  leaves teleports, portals and every other movement path untouched.
- **Dynamically rewriting exit `destination` rows.** Corrupts the authored grid
  and races between concurrent walkers.
- **A bespoke room typeclass.** Forks the movement pipeline.
- **Redirecting from `at_pre_move`.** Not possible: Evennia binds `destination`
  as a local in `move_to` before calling the hook, so it can veto a move but
  never change where it goes. Hence the dispatch moved up into `move_to`.
- **A generic "typed edge between two objects" store** for per-character
  progress. Unnecessary once `ConditionStage` was found to already model
  ordered progression; rejected rather than invent a graph layer on one example.
- **Evennia Attributes** for the progress counter. Prohibited: unqueryable,
  unvalidatable pickled blobs, an Arx I failure mode we are not repeating. A
  JSONField was likewise rejected (ADR-0007).

## Consequences

- New special-movement content needs no engineer and no migration.
- The DSL's authoring surface is now the bottleneck, not its runtime. Filed
  as #3417: `FlowDefinition` / `TriggerDefinition` / `Trigger` have bare
  `ModelAdmin` registrations with no step inlines, so authoring a flow today
  means hand-wiring `FlowStepDefinition` parent FKs and hand-writing
  `parameters` JSON.
- `flows/tests/test_authored_movement_redirection.py` asserts that no
  `Labyrinth*` model exists. If one is ever added, that test must be deleted
  deliberately, not quietly updated.

# ADR-0244: Flow step parameter schemas are hand-declared catalog data, not introspected or DB rows

<!--
Numbering note (#3417): docs/adr/ topped out at 0242 in this worktree at the
time of writing. ADR-0243 is believed already taken by #3418 on origin/main
(not yet merged into this branch). Re-verify at enqueue in case another PR
also claimed 0244 in the meantime - collisions merge silently.
-->

**Status:** Accepted (2026-08-28, #3417)

## Context

#3417 needed a way for a staff authoring UI and the server-side step
validator to agree on what parameters each `FlowActionChoices` step action
takes, what type each parameter is, and what its `variable_name` field
means. That schema does not exist anywhere today: `FlowStepDefinition.parameters`
is a bare JSONField, and each action's real shape lives only implicitly in
its `_execute_*` handler body (e.g. `params.get("attribute")`, `params.get("modifier")`).

## Decision

`src/flows/catalog.py` hand-declares one `StepActionSpec` (label, description,
`variable_name` role, and a tuple of `ParamSpec`s with name/type/required/
`accepts_reference`/choices) per `FlowActionChoices` member, built by a small
per-action function whose docstring names the handler it mirrors.
`STEP_ACTION_SPECS` is the single dict consumed by both
`flows.step_validation.validate_step_tree` (server-side save-time validation)
and `DslCatalogViewSet` (the frontend authoring palette), so the two cannot
drift, and `test_catalog.py` asserts every `FlowActionChoices` member has an
entry so a new action can't ship undescribed.

## Alternatives rejected

- **Introspecting handler bodies.** A handler reads its `parameters` dict with
  `params.get("name")` calls scattered through arbitrary Python control flow
  (conditionals, helper calls, `.get(..., default)`); there is no reliable way
  to statically recover the set of keys a function reads, let alone their
  types, from its bytecode or AST. This is a strictly harder version of the
  same problem the missions predicate catalog already solves by declaring
  leaves explicitly rather than introspecting resolver bodies.
- **Per-action schema rows in the database.** A `FlowStepParamSchema` model
  would be data describing code (which literal action strings exist, which
  params each one reads) rather than data describing game content, and would
  drift from the actual handler dispatch in `FlowStepDefinition.execute` the
  same way ADR-0007 already rejects JSON-shaped config in favor of typed code
  paths: the handler is the ground truth, and duplicating its shape into a
  row that can silently fall out of sync is worse than declaring the shape
  once, in code, next to a docstring naming the handler it mirrors.

## Consequences

- Adding a new `FlowActionChoices` action requires adding a matching
  `StepActionSpec` in the same PR, or `test_catalog.py` fails; the catalog
  cannot silently fall behind the runtime dispatch table.
- The catalog is authored by hand, so accuracy depends on whoever adds an
  action keeping the spec in sync with the handler body; there is no
  compiler-enforced link between the two beyond the completeness test.

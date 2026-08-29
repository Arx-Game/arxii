# Flows glossary

See the root `AGENT_GLOSSARY_MAP.md` for the cross-cutting Flow/Trigger/Event
terms (Architecture seam section). This file covers vocabulary local to the
flows authoring API (#3417).

**Step catalog**:
The hand-declared `flows.catalog.STEP_ACTION_SPECS` mapping every
`FlowActionChoices` action to a `StepActionSpec` (label, description,
variable-name role, parameter schema). It exists because a step's
`parameters` shape is only implicit in its execution handler's body and
cannot be introspected; the catalog is the single source of truth shared by
server-side validation (`step_validation.py`) and the frontend authoring
palette, so the two cannot drift. _Avoid_: schema registry, parameter map.

**Variable-name role**:
What a `FlowStepDefinition.variable_name` field means for a given action -
one of `flow_variable`, `object_pk_variable`, `service_function_name`,
`event_store_key`, or `unused` (`flows.catalog.VariableNameRole`). The same
column means a different thing depending on the step's action; the role is
what lets an authoring UI render the right label and control for it instead
of one generic text field. _Avoid_: variable type, field purpose.

**Full-tree replace**:
The write semantics of `FlowDefinitionWriteSerializer.steps`: saving deletes
every existing `FlowStepDefinition` on the flow and re-creates the entire
authored tree depth-first from client-chosen `client_id`/`parent_client_id`
references, rather than diffing and patching individual step rows. Chosen
because the tree may mix new steps with renames of existing ones in one
save, and the client authors the whole shape at once. _Avoid_: step diff,
incremental save, patch semantics.

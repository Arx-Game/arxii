# ADR-0243: Action interception events are generic, not per-verb

**Status:** Accepted (2026-08-28, #3418)

## Context

Every `Action` declared `intent_event`/`result_event` names (`before_get`,
`before_say`, ...) and nothing ever emitted them; the placeholders waited on a
per-verb `EventName` vocabulary that would grow by two members (plus a
choices migration on `TriggerDefinition.event_name`) for every action added.
Every action since the system landed (#319, 2026-03) shipped without anyone
paying that toll — which is how the action layer stayed invisible to the
reactive layer since #395, roughly six months.

## Decision

`Action.run()` emits exactly two events for all actions, forever:
`ACTION_INTENT` (mutable payload, before the prerequisite gate — intent means
"wants to", firing even when the actor can't act, and a cancelled intent
charges nothing) and `ACTION_RESULT` (frozen, success and failed attempts
alike, not emitted after an intent cancel). The verb is
`payload.action_key`; authored trigger filters discriminate with one clause
(`{"path": "action_key", "op": "==", "value": "get"}`), and a filter-less
trigger spans every verb — inexpressible under per-verb names without one
row per verb. The 24 placeholder declarations and 8 never-emitted
outfit/fashion `EventName` members were deleted.

## Alternatives rejected

- **Per-verb members** (`before_get`/`get`, the original design): reads
  slightly better per trigger row, but couples the enum to the action
  registry in lockstep — the exact bookkeeping that was never done.
- **Reviving the pre-#395 `Event` lookup table**: an event name with no
  emitter and no payload schema is inert; the vocabulary belongs where the
  code coupling is.

## Consequences

Domain events (`MOVE_PRE_DEPART`, `EXAMINE_PRE`, `TECHNIQUE_PRE_CAST`, ...)
keep their deeper seams and richer typed payloads; `look`/`traverse` fire
both layers. Deep kwarg mutation is not supported — the filter DSL and
MODIFY_PAYLOAD walk attributes only, so the mutable knobs are the typed
payload fields (`target`, `cancel_message`). `MODIFY_PAYLOAD`'s `value` is a
JSON step parameter, so it can only write pk-shaped or scalar kwargs — the
same constraint ADR-0242 already hit for movement `destination`. Redirecting
`target` to a real `ObjectDB` instance goes through a resolving service
function instead (`redirect_action_target`,
`flows/service_functions/actions.py`, mirroring `redirect_move`); a bare
`MODIFY_PAYLOAD` on `target` is only correct when the action itself resolves
the pk (as `objectdb_target_kwargs` actions already do for REST dispatch).

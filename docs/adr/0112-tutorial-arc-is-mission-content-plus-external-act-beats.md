# ADR-0112: Tutorial arc is mission content plus external-act beats

Issue #1035 needed a seeded, level-1 walkthrough of the core loops (fieldwork, a
crafted power, a covenant vow, a legend-tier job) without inventing a tutorial
engine: chain progress **is** ordinary `MissionInstance` rows advancing through a
seven-`MissionTemplate` chain gated by the existing `has_completed_mission`
predicate leaf, and the one new primitive is `OptionKind.EXTERNAL_ACT` — a
`MissionOption` with `required_act` (an `ExternalAct`: `TECHNIQUE_CAST`,
`THREAD_WOVEN`, `COVENANT_SWORN`) that is presented like any option but is never
pickable; it resolves when `satisfy_external_act(character_sheet, act)` is called
directly (log-and-continue, ADR-0009 style, inside a savepoint so a resolution
failure can't roll back the caller's own commit) from `weave_thread`,
`create_covenant`/`induct_member_via_session`, and `use_technique` after each
succeeds, plus a durable-act fast-forward at `enter_node` for acts already true
(`THREAD_WOVEN`/`COVENANT_SWORN`; `TECHNIQUE_CAST` is transient and never
fast-forwards). No `TutorialProgress` model, no tutorial-specific status enum, no
new engine — the tutorial is authored content over the mission graph exactly like
any other quest chain. We rejected minting new `EventName` values and per-character
`Trigger` rows for the external acts: that shape is a `TutorialProgress` table in
disguise (a parallel state store shadowing `MissionInstance.current_node`), and
`LAUNCH_FLOW`, the trigger handler that would fire the mission advance, is
currently a stub — building on it would mean finishing an unrelated flows feature
to ship a mission content pack. Revisit if a second real consumer of
weave/covenant events appears (i.e., a caller who isn't satisfied by a direct
service call) — then a proper event is worth the machinery it wasn't worth building
for one.

> Status: accepted · Source: issue #1035

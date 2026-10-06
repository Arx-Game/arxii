# ADR-4030: Target menus are composed server-side from each action's own prerequisites

**Status:** Accepted (2026-09-27, #4030).

`build_persona_menu` (`src/actions/persona_menu.py`) builds the persona right-click menu, and
sets the pattern for any target menu after it, entirely from each action's own
`check_availability()`: an item is available exactly when `Action.run()` would accept it, and
its reason text is the prerequisite's own refusal message, never a second copy kept beside it.
Any check that used to live inline in an action's `execute()` (Challenge's same-room/consent/
block checks, Succor and Interpose's round checks) moves into a `Prerequisite` the day that
action joins a menu, so both callers, the menu and `run()`, share the one gate and can never
disagree about what is offered. Rejected: a client-side `canX` predicate reading the scene cache,
which is how the persona menu worked until now, and which went blank the moment there was no
scene to read and drifted from the server whenever an action's rule changed without a matching
frontend edit (#4030); and the 2025 `BaseState.dispatcher_tags` per-object command list, which
never shipped a production caller and stayed empty (`[]`) in every real payload it was meant to
carry.

## #4032 typed-target extension

Target menus distinguish semantic applicability from temporary availability. An entry requiring declared input may be available to begin selection after every check decidable from bound inputs passes and at least one viewer-visible, semantically applicable complete choice can pass the same shared checks. Only those declared pending inputs may defer dependent checks; unrelated bound checks and central lifecycle gates still run. A complete input must pass the same `Action.check_availability` used by `Action.run`, which repeats after intent/enhancements and before costs and execution. Menu reads never run actions or authorize later execution. A zero-eligible-choice action is disabled with a safe explanation, not an empty enabled chooser.

Typed targets keep their domain-specific IDs: ItemInstance rows, room ObjectDBs, exits, and places are resolved within the viewer's current scope. Visible worn rows use the owner persona assertion supplied by the visible-worn response (or the server-provided room persona ID); no private inventory enumeration or identity inference from a displayed name is allowed.

The typed-target client cache is partitioned by account, actor, target kind, target ID, and optional owner/container assertions, with 30-second freshness. Identical reads coalesce. Accepted room snapshots and settled dispatch outcomes mark only the affected actor partition stale without refetching; the open menu keeps its captured view, and a stale menu refreshes on deliberate close and reopen. This cache policy applies to #4032 typed-target menus and does not change the persona-menu cache contract established by #4030.

The typed-target endpoint uses account-scoped throttling through the configured Django cache backend. With the inherited LocMemCache this is process-local best effort, not a worker-global guarantee; deployment-wide enforcement requires a shared cache backend. A throttled read does not auto-retry or refresh an open menu; recovery is deliberate after the server-provided wait interval.

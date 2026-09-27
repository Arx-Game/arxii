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

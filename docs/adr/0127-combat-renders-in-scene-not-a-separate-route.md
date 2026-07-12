# Combat renders in-scene, not on a separate route

`CombatRail` (#2197) — the tab strip, `CombatTurnPanel`, `CombatTacticalMap`, and encounter
banners previously composed by `CombatScenePage` on its own `/scenes/:id/combat` route — is now
folded directly into `SceneDetailPage`: a two-column grid renders `CombatRail` as the right
column whenever `useEncounterForScene` resolves an active encounter for the scene, and a single
column otherwise. `/scenes/:id/combat` now just redirects to `/scenes/:id`. The rejected
alternative was keeping combat as its own page (the pre-#2197 shape): that means a fight leaving
the room it's happening in — the player navigates away from the pose log, the place bar, and
everything else the scene surface carries — which directly contradicts the one-conversation
north star (chat bubbles, never terminal; combat is part of the same scene, not a side trip).
This is scoped to the combat UI only: `ScenePull`-gated, non-combat `<ActionDeclarationCard>`
adoption on the scene page (unified-combat-ui-design.md §9) remains a separate, deferred
brainstorm — no `ScenePull` envelope exists in the backend yet.

> Status: accepted · Source: issue #2197 · Related: docs/architecture/unified-combat-ui-design.md §9

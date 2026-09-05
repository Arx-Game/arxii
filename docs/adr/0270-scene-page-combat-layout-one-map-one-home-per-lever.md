# During an encounter the scene page has one map and one home per GM lever

While a `CombatEncounter` is active, `SceneDetailPage` (#3557) unmounts the header
`SceneTacticalMap` and makes the rail's `CombatTacticalMap` the only map, drawing
non-combatant scene personas dimmed as bystanders from the scene's cached
`persona_positions`; `CombatRail` grows a GM tab (`CombatGMTab`) holding the encounter
controls plus the Condition, Dramatic Beat and Traps tools, and the header
`GMAdjudicationPanel` drops those three tabs (via its `tabs` prop) so each lever has
exactly one home; the remaining idle header panels fold behind one closed "Scene tools"
accordion, with prompts that need an answer (consent, check-call, sineating, soul-tether,
entry flourish) staying inline. Outside an encounter the page is unchanged. Both maps
already read the same `position_graph(room)` and the same `ObjectPosition` store; only
their occupant sets differed, which is why merging occupants into one map was the fix
rather than swapping maps. Three alternatives were rejected: keeping both maps (the
same graph twice, and no way to tell which is live); moving the whole eleven-tab GM
toolkit into the 360px rail permanently (unreadable, and it changes the idle page);
and copying the three combat tabs into the rail while the header kept them (the
duplication the issue objected to for the map). Set the Stage rides on the header map
and is deliberately unavailable mid-fight: instantiating a blueprint would reshape the
fight's own graph; it returns when the encounter completes.

One consequence is accepted knowingly: `SelfCheckPanel` and `TavernGameWidget` hold local
form drafts, and the idle-to-combat swap remounts the folded subtree, so a draft in progress
at the poll tick an encounter starts is lost. The window is one form, one moment, a few times
a night at most; keeping both widgets mounted across both shapes would change the idle page,
which decision 4 forbids. Prompts that need an answer are never folded, so nothing a player
must respond to is affected.

> Status: accepted · Source: issue #3557 · Related: ADR-0127,
> ADR-0111 (one-play-surface, `0111-one-play-surface-game-absorbs-scene-toolset.md`),
> `docs/architecture/unified-combat-ui-design.md` §1/§2

# ADR-0309: The feudal ladder's rungs are real Atlas levels, not a sentinel organization

**Status:** Accepted (2026-09-23, #3983).

Before the Almanach, a title's realm-of-control had no shape on the Atlas above `REGION`/
`KINGDOM` — a duchy or a county existed only as an abstract fact on `Title`/`FealtyEdge`,
disconnected from where the land actually sits on the world-builder's map. `AreaLevel` gains
`BARONY`(46)/`COUNTY`(53)/`DUCHY`(56)/`EMPIRE`(65) between `CITY` and `CONTINENT` (alongside the
existing `KINGDOM`), so a rung IS a real `Area` in the same `parent`/`child` tree every other
Atlas query already walks: `plant_rung` mints one `Area` per tier down to its barony seat, and
`liege_for_title` finds a title's containment liege by walking plain `Area.parent` — no separate
query path, no drift between "who a house answers to" and "whose territory this land physically
sits inside." The rejected alternative was a **sentinel organization per rung** — representing
duchy-contains-county-contains-barony purely through `FealtyEdge`/`Organization` nesting, with no
`Area` of its own. That would let a title's declared containment diverge from where its land is
actually drawn on the map (a rung could claim to sit inside a duchy the Atlas places somewhere
else entirely), and it would mean building a second ancestry walk parallel to the one
`Area.parent` already provides, for the sole purpose of keeping two hierarchies in sync by hand.

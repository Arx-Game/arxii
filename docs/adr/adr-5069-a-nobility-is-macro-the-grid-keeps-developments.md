# ADR-5069-A — Nobility is macro and the grid keeps developments; dormancy freezes accumulators, never equilibria

**Status:** accepted (2026-11-11, #5069; slice 1 is #5071). Amends ADR-0319 (a Domain's
units are its people, a Turf's its rooms). Narrows ADR-0320, 0321 and 0322 to the grid layer
they describe; none is superseded.

The Almanach's first pass put every family into one shape. `plant_rung` made a `Domain`
with civ stats, a territory stream and a developments table on every rung of a chain,
kingdom to barony, so a duchy page carried a "Farmland" row above its counties and a
population nobody could reconcile with the land beneath it. The owner's ruling
(2026-11-10): "NOBILITY is inherently different from every other kind of domain system
because it is the ONLY one that deals with macro level control, it is about managing
entire regions. Every other family is focused on something that is on the grid, and micro
based, and frankly us trying to smash them together just makes no sense."

**Decision.** Two layers, one seam.

- *The noble layer is regions.* A barony is one pip on the world map, a holding and its
  immediate surroundings. A county is its baronies plus a hinterland whose people are an
  undistributed rural pool. A duchy is exactly its counties, a kingdom its duchies, an
  empire its kingdoms: organization with no ground of its own. So a `Domain` exists only
  at barony and county; everything above has none, and its people and income are sums on
  read. Above barony, "Holdings" means the baronies and counties a house holds directly
  against those its vassals hold, never a table of developments.
- *Importance is population, never pip count.* Pips can be developed but overwhelmingly
  stay empty; a city barony of three hundred thousand and a glacier pip of nobody sit on
  the same map. Terrain sets capacity (`TerrainCalibration`, one authored row per
  `Terrain`; `DomainTerrainCount`, counted where a footprint changes) and a holding's
  people move toward it. A noble's land income is people times coppers per head, which
  amends ADR-0319: a Domain's units are its people; a Turf's stay its outdoor rooms.
- *Population is a formula, not a tick.* `Domain.population` is a base as of
  `population_rebased_at`; `demography.population_now` moves it toward capacity by the
  in-character months elapsed. Nothing ticks and a read never writes; a write is a rebase
  (an event, a staff edit, layout). Pips and terrain never tick either.
- *The grid layer stays as built.* A sited `DomainHolding` on a room, building or field
  with `owner_org` is what a commoner family, a guild or a gang runs (ADR-0320), it may
  stand on someone else's land (ADR-0322) and it pays the levies above it (ADR-0321). The
  layers meet at the barony, where a business stands on a noble's ground and pays the
  levy; a barony page shows its own people and the businesses other families run on it as
  two different things.
- *Dormancy freezes accumulators, never equilibria.* A house with no played character
  goes dormant and its coin stops accruing, so nobody apping into an empty house inherits
  a jackpot; a house in a lull keeps accruing uncapped. Population, prosperity and unrest
  converge to terrain-set values and run everywhere by formula, so dormant land can be
  struck by a regional event and can recover. (Dormancy and regional events are slices 3
  and 4 of #5069.)

**Rejected.** (a) One model, macro superseding micro: the grid layer is correct for
non-noble families. (b) Extents as counts in columns on a barony: a typed number is not a
fact about the land and nothing can strike it. (c) A development on every pip: tens of
thousands of trivial rows, and a glacier pip weighing what a city does. (d) Capping pools
at a season of income to stop NPC hoards: the problem is the empty house, not a lull, and
the owner wants a lull's income kept. (e) Freezing everything on dormancy: frozen land can
neither be hit by a disaster nor heal.

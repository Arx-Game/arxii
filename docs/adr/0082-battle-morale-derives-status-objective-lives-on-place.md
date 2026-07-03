# Battle morale derives status; the front itself is the objective; VP stays award-only

`BattleUnit` gains a second numeric resource, `morale` (#1712), alongside `strength`.
`BattleUnitStatus` is always derived jointly from both via
`world.battles.resolution._compute_unit_status` — DESTROYED still requires
`strength == 0` (morale collapse alone never kills a unit), and ROUTED now triggers from
either resource crossing its own threshold. Rejected: a `WAVERING` status enum value
representing morale collapse as a distinct state from strength-based ROUTED. That
approach couldn't scale with `success_level` the way a numeric resource does (ROUT/RALLY
need graduated damage/healing, not a binary flag flip) and would have required
hand-written branching at every existing `status` call site to decide which of two
"broken" states applies, duplicating logic the shared derivation function now centralizes
in one place.

`BattlePlace.controlled_by` (nullable FK → `BattleSide`) makes the front itself the
capturable objective — a successful HOLD declaration sets it, and `None` means
uncontrolled/contested. Rejected: a separate `Objective` model decoupled from
`BattlePlace`. Nothing in the current design calls for more than one capturable point per
front, and introducing a second model purely to represent "the thing HOLD captures" would
duplicate `BattlePlace`'s identity (name, terrain, unit occupancy) without a concrete want
driving the split. If a future issue needs multiple independently-capturable objectives
within one front, that's the point to reconsider — not before.

Victory points stay award-only: ROUT, RALLY, REPEL, and HOLD all add to
`BattleSide.victory_points` like STRIKE/SUPPORT before them, and no action kind
subtracts or transfers VP between sides. Rejected: a genuine VP tug-of-war (declarations
that reduce an enemy side's VP, not just award your own). That would touch
`check_victory`'s monotonic-VP assumption (it only checks for crossing a threshold
upward) and raises open design questions — can VP go negative, does a denial action need
its own threshold-crossing semantics — that have no concrete want behind them yet.
Deferred as `needs-design`, not built.

> Status: accepted · Source: #1712 Decisions 1-3 · Related: ADR-0081 (BattlePlace as the
> existing home for battle-scale front data)

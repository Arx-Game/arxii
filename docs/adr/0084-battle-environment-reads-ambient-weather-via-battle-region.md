# Battle environment reads ambient weather via Battle.region, not the room graph

#1715 needed battlefield weather to matter mechanically. The issue's own draft suggested
reusing `Position`/`PositionEdge` (the room-scale tactical graph) for "where the state
applies" — but ADR-0081 had already rejected exactly that coupling for terrain, because
battles are deliberately location-less (`Battle.save()` explicitly nulls the backing
`Scene.location`; mass battles have no real positional room to anchor hundreds of PCs
to). Separately, the design went through a mid-review pivot: the first draft scoped
weather entirely per-`BattlePlace` (no real battle-wide concept). A reviewer pointed out
this was backwards for anything genuinely ambient — "a storm doesn't skip one part of
the field" — while local variation (cover, wards, a hostile local squall) is real and
should stay representable.

`Battle` gains an optional `region: FK[areas.Area, null=True]`, resolved via the
existing `world.weather.services.get_effective_weather(area)` (unchanged, BUILT & WIRED)
to seed an ambient weather baseline — one Area reference per `Battle`, not a revival of
the room/`Position` graph, and not a second reference per `BattlePlace` (the first
draft's proposal, which would have been a bigger deviation from ADR-0081). Weather is
two-tier: `Battle.weather_override` is the battle-wide default (set by a `BATTLE`-scoped
`SET_ENVIRONMENT` cast); `BattlePlace.weather_override` is a local exception that beats
the battle-wide value at one front only (`PLACE`-scoped cast). Resolution order: place
override -> battle override -> ambient (via `region`) -> none. `Position`/`PositionEdge`
remain untouched — ADR-0081's holding is fully preserved.

We rejected extending `Position`/`PositionEdge` for battle terrain/weather — ADR-0081
already rejected this for terrain, and the reasoning (battles are location-less by
design) applies identically to weather. We rejected per-`BattlePlace`-only weather with
no battle-wide tier — the original #1715 draft — after reviewer feedback made clear it
left "a storm doesn't skip one part of the field" unrepresentable without repeating a
cast at every front. We also rejected a `Battle.region`-less, override-only design (no
ambient tie at all): ambient regional weather already existing and mattering to a war
fought during it (user story 5) was worth the one narrow Area reference. `world.battles`
now has exactly one new cross-app read dependency
(`world.weather.services.get_effective_weather`), no write dependency —
`world.weather`'s internals are unchanged; and because `effective_weather()`'s ambient
branch re-queries `get_effective_weather` on every call, ambient weather is already live
mid-battle with no extra work if a future issue wants that.

> Status: accepted · Source: #1715; carves a narrow read-only exception into
> ADR-0081's "battles are location-less" holding for ambient weather only —
> `Position`/`PositionEdge` remain otherwise untouched.

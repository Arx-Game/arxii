# Ambient-reaction TriggerDefinition/Flow rows are derived from content, not authored or fixed config

`AmbientEmoteLine`/`AmbientEmoteCondition` (#2471) needed real Trigger-system filter conditions
(species/resonance/distinction/fame-tier, optionally AND/OR-composed) so condition matching is
evaluated by the DSL (`flows/filters/evaluator.py`), not duplicated in application code. Since
lines with an identical compiled condition can be authored per room/area (and multiple flavor
variants of the same condition should draw from one weighted pool, not fire independently), one
`TriggerDefinition`/`FlowDefinition`/`Trigger` set is created per DISTINCT compiled condition
per room, not one per authored line and not one fixed shared row. These rows are neither
lore-repo-authored content (no `NaturalKeyMixin`, not in `content_export.py`'s `CONTENT_MODELS`)
nor a fixed config singleton (`ensure_*_content()`-style) — they're **derived**, computed by
`core_management.grid_import._install_ambient_triggers` from the actually-imported
`AmbientEmoteLine`/`AmbientEmoteCondition` rows on every import, named deterministically
(`moved_ambient_<scope>_<scope_key>_<filter-digest>`) so re-imports of unchanged content resolve
to the same rows via `get_or_create`. This mirrors how `RegionWeatherState` is computed rather
than authored, applied to the Trigger system for the first time. Room-vs-area "most specific
wins" resolves per condition-group at this derivation step (a room's own override for condition
X doesn't suppress an area's unrelated condition Y), not as a wholesale pool replacement.

Rejected: authoring `TriggerDefinition`/`Flow*` directly as lore-repo content (would require
content authors to hand-construct filter-DSL JSON and Flow step wiring per condition, duplicating
what `AmbientEmoteCondition`'s proper-column fields already express more safely). Rejected: one
fixed shared `TriggerDefinition` doing all matching in a Python service function (the design this
ADR supersedes, from a closed PR — matched conditions in bespoke Python instead of the DSL,
reinventing condition-evaluation logic the Trigger system already provides).

> Status: accepted · Source: issue #2471 · Related: ADR-0140 (grid content exports), ADR-0007
> (no JSON fields — `base_filter_condition`/`parameters` are pre-existing flows-app JSON fields
> for compiled expression trees, not new authored-settings JSON being introduced here)

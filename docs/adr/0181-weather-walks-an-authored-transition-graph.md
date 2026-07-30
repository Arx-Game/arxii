# ADR-0181: Weather walks an authored transition graph, not a memoryless roll

**Status:** Accepted (built on #2845; complements ADR-0180)

**Decision.** The weather roll is no longer memoryless: `WeatherTransition` rows
(`(from_type, to_type) → weight`) form an authored graph, and a region holding a type with
outgoing edges draws its next weather from those edges (intersected with climate
eligibility) instead of the global `selection_weight` pool. Weather therefore *trends* —
a thunderstorm arrives through overcast rather than snapping from a cloudless sky, a high
self-edge makes systems linger, and sun-sensitive players can read the sky for patterns
(the gameplay point: foreshadowing). Sparse authoring degrades gracefully: a type with no
outgoing edges, an eligibility-pruned edge set, a forced feast-day special, or a fresh
region all fall back to the global weighted roll — the pre-graph behavior. Content-repo-
owned (`weather.weathertransition` in CONTENT_MODELS; `weather_transitions.json` in the
seed upsert loader); edge weights are a PLACEHOLDER author pass.

**Rejected alternatives.** (a) A severity/turbulence ordinal on `WeatherType` with ±1-step
transitions — one axis can't express real adjacency (Foggy and Snowy are both "mild" but
not neighbors), and it re-opens the ratified "no intensity scalar — the type IS the
intensity" stance. (b) Keeping the memoryless roll with smaller weights on extreme types —
reduces but never removes jump-cuts, and can't express persistence or foreshadowing.
(c) A full hourly interpolation/simulation layer — massive machinery for what an authored
graph expresses in rows.

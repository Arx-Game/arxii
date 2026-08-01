# Weather

Region-scoped, authored weather that moves on the IC clock, shelters the things
standing in it, and is readable from both telnet and the web.

**Source:** `src/world/weather/`
**ADRs:** ADR-0180 (cloud cover is area-wide hazard shelter), ADR-0181 (weather
walks an authored transition graph)

---

## Models

- **`Climate`** — the regional band a `RegionWeatherState` rolls within.
- **`WeatherType`** — one authored condition (clear, overcast, storm…) with its
  season/phase eligibility.
- **`WeatherTypeExposure`** — `(weather_type, stat_key) → value`: how a condition
  pushes a location's comfort-relevant stats (COLD/HEAT/WET/WIND). Materialized as
  decaying `LocationValueModifier` rows on the STAT axis.
- **`WeatherTypeShelter`** (ADR-0180) — `(weather_type, damage_type) → value`:
  how a condition *shelters* against a hazard axis. **Cloud cover IS area-wide
  shelter**: overcast writes a radiant-shelter row, which the sunlight system's
  existing shade term reads with zero sun-side code. The same rows dampen the
  moon's pull (#2845).
- **`WeatherTransition`** (ADR-0181) — the authored Markov edge
  `(from_type → to_type, weight)`. Weather walks this graph instead of rolling
  independently, so a clear day trends to overcast before it storms; a sparse
  graph falls back to an unweighted roll rather than freezing.
- **`WeatherEmit`** — the season/phase-appropriate flavor line pushed on change.
- **`RegionWeatherState`** — the live per-region row (current type, last roll).
- **`FeastDay`** — authored calendar days with their own weather flavor.

## Movement

`weather.roll` (game-clock cron) advances each region's state at IC
phase boundaries — `_phase_transitioned_since_last_run` compares the IC phase at
`last_ic_run_at` against now, so weather changes line up with dawn/day/dusk/night
rather than drifting on wall-clock time. Clockless worlds fall back to a legacy
2-hour cadence.

## Reading it

- **Telnet:** `time` (alias `weather`) — IC time, server time, the local weather
  state, and (at night) the moon phase. `weather squelch` / `unsquelch` toggles the
  periodic echo.
- **Web:** `GET /api/weather/conditions/` → `WeatherWidget` in the top bar. This is
  the only REST surface in the celestial/weather family; `moon_phase` is exposed
  here rather than on the clock endpoint.

## Moon

The moon is a **pure IC-time derivation** — no state, no cron writer:
`game_clock.services.get_moon_phase` / `get_moon_illumination` compute from a fixed
epoch (`MOON_SYNODIC_IC_DAYS`, PLACEHOLDER 30 IC days), so a staff time-skip moves
the moon with it. Consumers: the weather readout above, and the lycan control
window (`species.moon_pull.felt_moon_pull` — illumination × sky exposure − shade,
the shade term being the same radiant-shelter read the sun uses).

## Content

Authored corpus (types, exposures, shelters, transitions, feast days) lives in the
content repo and loads via the **`weather` seed cluster**
(`world/seeds/weather_content.py`), which resolves the fixtures directory from
`WEATHER_SEED_PATH` or `<content repo>/weather`. A missing corpus logs a warning
and no-ops — the cron then runs against an empty transition graph, which is a
content-authoring gap rather than a seeder bug. `tools/load_weather_seed.py`
remains for out-of-band reloads.

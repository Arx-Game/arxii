# Weather - Climate Baseline & (later) Transient Weather

Mechanical climate for the world (#1522). Built on top of the #1514 climate→comfort
substrate in `world.locations`: climate makes a region's temperature/moisture **mechanical**
(it feeds the exposure axes that drive comfort and AP regen), so the world enforces theme
through play rather than flavour text.

## What exists

### Climate baseline (slice 1)

- **`Climate`** — an authorable regional baseline. Two signed "weights":
  - `temperature` — positive feeds the **HEAT** exposure axis (tropical/desert), negative
    feeds **COLD** (arctic); 0 is temperate.
  - `moisture` — positive feeds **WET** (tropical/coastal), negative feeds **DRY** (desert).

  Each signed weight decomposes onto exactly one of its floored axis pair (see
  `services.climate_exposure_base`). Lore lives in a linked `codex.CodexSubject`, surfaced
  inline at point-of-use (not siloed). Uses `SharedMemoryModel`.

- **`Area.climate`** (FK on `world.areas.Area`) — designates a region's climate. Resolved
  **most-specific-wins** up the hierarchy by `services.get_effective_climate`, a direct
  mirror of `world.areas.services.get_effective_realm`. So a parent region (Luxen) can stay
  temperate while a sub-region (Cinderus) designates desert, and a room resolves the nearest.

- **Global per-month temperature shift** (`constants.MONTH_TEMPERATURE_SHIFT`) — a 12-value
  curve (coldest Jan, hottest Jul, neutral in the shoulder months) read off the **existing IC
  clock** (`world.game_clock.services.get_ic_now().month`) by `services.current_temperature_shift`.
  It rides on top of each region's flat baseline, so a temperate region crosses into real COLD
  in winter while a tropical region's high baseline keeps it warm year-round ("no real winter")
  for free. **Moisture has no monthly curve** — its seasonality rides on the (later) weather
  layer. Magnitudes are `PLACEHOLDER` (author-tuning pass).

## Integration with comfort

Climate is **not** a second exposure pipeline. `world.locations.services.felt_exposure`
folds the resolved climate base (`climate_exposure_base`, including the seasonal shift) into
the **same pre-floor sum** as the local cascade modifiers, so a desert's HEAT base and a
cooling fixture's negative HEAT modifier combine *before* the 0-floor (build-to-win). A
warded-sanctum `LocationValueOverride` still trumps both. **WIND is never climate-driven**
(it comes from weather/magic), so `climate_exposure_base` returns 0 for it.

## Resolving climate

```python
from world.weather.services import get_effective_climate, current_temperature_shift

climate = get_effective_climate(room.room_profile.area)  # Climate | None, most-specific-wins
shift = current_temperature_shift()                       # int, 0 if no game clock yet
```

For comfort reads, don't call these directly — `world.locations.services` resolves climate
once per room (`_exposure_context`) and folds it in. Use `get_effective_climate` for
non-comfort consumers (e.g. a "what's the climate here" display).

### Transient weather — mechanical layer (slice 2a)

- **`WeatherType`** — a kind of weather (Clear, Stormy, Snowy, …). `is_automated` (eligible for
  the ambient roll vs special/event weather triggered only by the feast-day loop),
  `selection_weight` (weighted-random), and a `min`/`max_temperature` climate band (keeps
  blizzards out of the tropics). **No** Arx-1 intensity scalar — the type *is* the intensity.
- **`WeatherTypeExposure`** — `(weather_type, stat_key) -> value` (mirrors `StyleAffinity`); the
  exposure a type imparts while it holds (Stormy → +WET, +WIND).
- **`WeatherEmit`** — atmospheric flavour lines, gated by IC season (`in_*`) + time-of-day phase
  (`at_*`) flags, weighted. Seeded (slice 2b) from the Arx-1 corpus; `text` is PLACEHOLDER.
- **`RegionWeatherState`** — one row per region Area; the current weather, resolved
  most-specific-wins (`get_effective_weather`, like climate).

Services (`world.weather.services`):
- `roll_region_weather(area, *, weather_type=None)` — force a type, or pick a weighted-random
  automated type eligible for the region's climate; writes `RegionWeatherState` + rewrites the
  region's **decaying source-tagged** (`weather:<area_pk>`) WET/WIND exposure modifiers (fade
  over `WEATHER_FADE_DAYS`, so weather softens between rolls and self-clears if the cron stalls).
- `eligible_weather_types(area)` — automated/active types whose temp band fits the climate.
- `apply_weather_exposure(state)` / `clear_region_weather(area)` — (re)write / remove the
  weather modifiers (same cascade as climate/style; countered by the same fixtures).
- `select_weather_emit(area, *, season=None, phase=None)` — weighted-random emit for the
  region's weather, gated by the current IC season + phase.

### The live loop + player surface (slice 2b)

- **Cron** (`world.weather.tasks.roll_and_echo_weather`, registered in `game_clock` at
  `timedelta(hours=2)` REAL ≈ 6 IC hours): rerolls each climate-bearing region's weather, then
  echoes one emit to the **online** occupants of its rooms as a `NarrativeCategory.WEATHER`
  message (its own category, so the frontend routes it to a weather tab and players squelch it
  precisely; offline players skip it — no stale catch-up flood).
- **Squelch** — `narrative.UserCategoryMute` (mirrors `UserStoryMute`: suppress the live push,
  keep it readable in the tab). `narrative.services.set_category_mute` / `is_category_muted`;
  `time` command exposes `weather squelch` / `weather unsquelch` on the WEATHER category.
- **`current_conditions(room) -> ConditionsSummary`** (`types.py`): IC time + phase + season +
  the room's effective weather + one emit line. Any field is None when its source is absent.
- **`time` command** (`commands/weather.py`, `CmdTime`, alias `weather`): the telnet face of
  `current_conditions` for the caller's room.
- **API + React widget**: `GET /api/weather/conditions/?room_id=<id>` (`world.weather.views`
  `WeatherViewSet`, `ConditionsSerializer`) → the `Conditions` schema. The frontend
  `WeatherWidget` (`frontend/src/weather/`) reads the active character's room id from Redux,
  queries it via React Query, and renders a compact "phase · weather" glance in the `GameTopBar`
  (tooltip carries the full emit line). Weather echoes use `NarrativeCategory.WEATHER`, so
  `CategoryBadge` must include a `weather` entry (frontend exhaustive map).
- **Feast-day special weather** (`FeastDay` + `special_weather_for_today`): an annually-recurring
  IC date (`ic_month`, `ic_day`) tied to a special `WeatherType` (Eclipse / Moon Madness,
  `is_automated=False`). On a feast day the tick *forces* that type world-wide, overriding the
  normal climate-gated roll — the automation that replaces a GM manually pulling the lever. Off
  a feast day the next tick reverts to the random roll (special types are never randomly rolled).
  Feast dates are seed data (PLACEHOLDER). Any *mechanical* madness effect on characters is
  out of scope here (combat/conditions — Tehom's domain).

## Not yet built (later slices of #1522)

- **Corpus seeding (done — data lives in the seed-data store, not this repo):** Django fixtures
  for 7 `WeatherType` rows (Clear/Stormy/Snowy/Windy/Foggy automated; Eclipse of Mirrors / Moon
  Madness special) + their exposures + 263 `WeatherEmit` rows were generated from the Arx-1
  corpus. `WeatherType` carries a **name natural key** so the exposure/emit fixtures reference it
  by name. Load order: `weather_types` → `weather_type_exposures` → `weather_emits` (via
  `loaddata`). Exposure magnitudes, temperature bands, and selection weights are PLACEHOLDER.
  Weather is inert in any DB until these are loaded (`roll_region_weather` returns None with no
  types). **Re-seeding** an edited corpus goes through `world.weather.seed` (the upsert path), NOT
  a second `loaddata`: `loaddata` can't UPDATE idmapper rows and DUPLICATES the keyless `WeatherEmit`
  rows (#944/#946). `seed.load_weather_seed(fixtures_dir)` upserts each model by natural identity
  (`WeatherType`→name, `WeatherTypeExposure`→(type, axis), `WeatherEmit`→(type, text),
  `FeastDay`→(month, day)), so editing a magnitude/weight/flag and re-running mutates in place.
  The same generated fixture JSON stays valid for fresh-DB `loaddata`. Invoke via the tools wrapper
  `tools/load_weather_seed.py` (`--fixtures-dir` or `WEATHER_SEED_PATH`); not a management command.
- **Wind as a mechanic** (flyers/arrows/gale spells, driven by the active weather's WIND) —
  combat/technique consumer, **Tehom's domain**; filed as **#1555** (`needs-design`). The WIND
  *provider* side is done (`felt_exposure(room, WIND)` / `current_conditions`).

## Conventions

- `SharedMemoryModel` for all concrete models; absolute imports; no JSON fields; 100-char lines.
- Avoid multiple migrations during early development (new-app discipline).
- This app depends on `world.locations.constants` (StatKey), `world.game_clock` (IC time),
  and `codex`. The `Area.climate` FK lives on `areas` pointing at `weather.Climate`
  (mirrors `Area.realm`); `weather` does **not** import `areas` at runtime.

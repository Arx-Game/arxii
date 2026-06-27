# Weather - Climate Baseline & (later) Transient Weather

Mechanical climate for the world (#1522). Built on top of the #1514 climate→comfort
substrate in `world.locations`: climate makes a region's temperature/moisture **mechanical**
(it feeds the exposure axes that drive comfort and AP regen), so the world enforces theme
through play rather than flavour text.

## What exists (slice 1)

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

## Not yet built (later slices of #1522)

- **`WeatherType` / `WeatherEmit` / `RegionWeatherState`** — transient weather writing
  decaying source-tagged exposure modifiers (WET/WIND) over the climate baseline, with a cron
  loop. Emits seed from the extracted Arx-1 corpus; emit selection gates on
  `game_clock` season + time-of-day phase (`get_ic_season` / `get_ic_phase`).
- **Special feast-day weather** (Moon Madness / Eclipse) — its own automated loop.
- **Wind as a mechanic** (flyers/arrows/gale spells) — transient, intensity-driven.

## Conventions

- `SharedMemoryModel` for all concrete models; absolute imports; no JSON fields; 100-char lines.
- Avoid multiple migrations during early development (new-app discipline).
- This app depends on `world.locations.constants` (StatKey), `world.game_clock` (IC time),
  and `codex`. The `Area.climate` FK lives on `areas` pointing at `weather.Climate`
  (mirrors `Area.realm`); `weather` does **not** import `areas` at runtime.

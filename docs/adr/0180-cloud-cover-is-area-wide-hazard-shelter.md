# ADR-0180: Cloud cover is area-wide hazard shelter; the moon is a pure clock derivation

**Status:** Accepted (built on #2845's celestial layer; extends ADR-0073/ADR-0179)

**Decision.** Weather couples into sun (and any future sky hazard) severity as **shelter, not a
new scalar**: `WeatherTypeShelter` rows (`(weather_type, damage_type) → value`) are
materialized by the existing weather roll as decaying, source-tagged `LocationValueModifier`
rows on the region's Area — the `KeyType.DAMAGE_TYPE` axis of the same cascade authored room
shade already uses. An overcast region therefore raises the graded shade term of
`felt_sun_exposure` (#2846) with **zero sun-side code**, stacks with authored shade and position
shelter, softens between rolls, and self-clears if the cron stalls — all behavior inherited
from the weather-modifier machinery, not rebuilt. A heavy storm genuinely clearing a
bane-tier character's condition (shade-only residual under the clear threshold) is correct
fiction, not a bug. The moon is a **stateless derivation**: `get_moon_phase` /
`get_moon_illumination` compute the synodic position (PLACEHOLDER 30 IC days) from a fixed IC
epoch — no cron writer, no state row; staff time-skips move the moon automatically, and the
weather `Conditions` read/widget surface it at night. `WeatherTypeShelter` is content-repo-owned
(magnitudes are an author pass); the seed upsert loader handles `weather_type_shelters.json`.

**Rejected alternatives.** (a) A `sky_visibility` float on `WeatherType` multiplying base sun —
a parallel channel that bypasses the cascade (no stacking with authored shade, no decay, no
per-area cascade semantics) and helps no other hazard. (b) A `MoonState` model advanced by cron
— state that can drift from the clock it mirrors; a pure function cannot. (c) Per-room weather
shelter — weather is regional by design (`RegionWeatherState` is per-Area); rooms compose their
own shade on top via the same cascade.

# Environmental vulnerabilities are ConditionDamageOverTime rows riding the peril pipeline

A species environmental vulnerability (e.g. vampire ↔ sunlight) is a
`ConditionDamageOverTime` row (radiant) on a "Sunlight Exposure"
`ConditionTemplate`, applied when the character is outdoors during a daylight
phase (gated by `RoomProfile.is_outdoor` + `get_ic_phase()`). It rides the
existing `_process_round_tick` → `tick_round_for_targets` →
`process_damage_consequences` → peril-pipeline machinery that poison, Burning,
and Bleeding-Out already use — no new cron, no new tick, no new model. Exposure
ensures a danger scene round via `ensure_round_for_acute_condition` (the plummet
pattern) so the tick runs; the AFK-safety contract (ADR-0004/ADR-0049) holds
unchanged: an unconscious victim flows into `abandonment_environmental`, never a
raw death. Immunity to a damage type is not a boolean; it is a very high
`ConditionResistanceModifier` that overwhelming damage exceeds — so god-tier
power pierces "immunity" by arithmetic, not a special code path. This extends
ADR-0071 (broad framework + environmental triggers, per the roadmap's #1588
row). We rejected a bespoke environmental-damage cron and a reactive
`DAMAGE_PRE_APPLY` modifier: the former reintroduces AFK-kill risk, the latter
makes sunlight combat-only and misses passive exposure. We also rejected a new
`is_immune` boolean: a hard flag cannot be overcome by overwhelming power, which
contradicts the design tenet that sufficiently powerful effects punch through
"immunity."

> Status: accepted · Source: issue #1588 · Confidence: built (E2E `test_sunlight_exposure_e2e.py`)

# Vitals System — Survivability Pipeline

Character mortality, health tracking, and the acute-peril dying state. System-agnostic — called by
combat, poison, spells, exhaustion, and any other damage source.

**Source:** `src/world/vitals/`
**Models:** `CharacterVitals`, `VitalsConsequenceConfig`

---

## Key Files

### `models.py`
- **`CharacterVitals`** (SharedMemoryModel, OneToOne on `CharacterSheet`): mortality marker
  (`life_state`: `ALIVE` / `DEAD`) + health (`health`, `max_health`, `base_max_health` — null means
  derive from level/stamina/role). `died_at` timestamp set on death. Consciousness and dying are
  conditions, not fields. #2287 adds `died_in_scene` (FK `scenes.Scene`, the active scene at the
  body's location when `_mark_dead` fired — bounds the ghost emit window and death-kudos
  eligibility; null for offscreen deaths) and `retired_at` (set by `retire_character`; the final
  puppet lock — see "Death off-ramp" below).
- **`VitalsConsequenceConfig`** (singleton pk=1): tunable difficulty scaling (`knockout_base_difficulty`,
  `death_base_difficulty`, `wound_base_difficulty` + per-percent scalars) and the global
  `knockout_pool`, `default_wound_pool`, `default_death_pool`. #2287 adds the wake-arc knobs
  (`wake_base_difficulty`, `wake_scaling_per_percent`, `wake_ease_per_round`,
  `wake_guaranteed_rounds`), `auto_retire_days`, and the admin-editable `death_condolence_body`
  (PLACEHOLDER text seeded; final wording is ApostateCD's).

### `constants.py`
- **`CharacterLifeState`** (`TextChoices`): `ALIVE` / `DEAD` — the binary mortality axis.
- **Derived wire statuses**: `DERIVED_STATUS_DEAD/DYING/INCAPACITATED/ALIVE` — computed at read time
  by `derive_character_status`; never persisted.
- **Health thresholds**: `KNOCKOUT_HEALTH_THRESHOLD = 0.20`, `DEATH_HEALTH_THRESHOLD = 0.0`,
  `PERMANENT_WOUND_THRESHOLD = 0.50`.
- **Peril pool names** (natural keys; seed via `world.vitals.factories`):
  `POOL_BLEED_OUT_TERMINAL`, `POOL_ABANDONMENT_ENEMY`, `POOL_ABANDONMENT_PVP`,
  `POOL_ABANDONMENT_ENVIRONMENTAL`.

### `services.py`
Core survivability pipeline:
- `is_dead(sheet) -> bool`, `is_alive(sheet) -> bool` — mortality gate (degrades gracefully on
  missing sheet).
- `can_act(sheet) -> bool` — coarse round-participation gate: `not dead AND awareness > 0`. A
  dying-but-conscious character keeps awareness → True. An Unconscious character has awareness 0 →
  False.
- `derive_character_status(sheet) -> str` — compute dead/dying/incapacitated/alive label at read
  time; never a persisted field.
- `process_damage_consequences(character_sheet, damage, ...)` — full survivability pipeline for a
  single damage event: knockout check → death check → permanent wound check. Each tier rolls the
  corresponding pool (knockout/death/wound) via `resolve_vitals_consequence`.
- `apply_damage_to_participant(...)`, `apply_exhaustion_damage(...)` — caller entry points.
- `advance_bleed_out(sheet) -> bool` — called once per round for each participant carrying
  Bleeding Out. Non-terminal stages: resist-check; failure advances stage. Terminal stage: delegates
  to `_resolve_terminal_bleed_out` (guarded pool, not unconditional death). Returns True iff the
  character died.

**Acute-peril dying state (#1479) — guarded consequence pool (ADR-0049):**
- `_resolve_peril_via_pool(sheet, instance, pool, *, death_permitted) -> bool` — shared
  death-gated core: resolves a `ConditionInstance` through an authored `ConsequencePool`;
  excludes `character_loss` (`die`) candidates when the caller-supplied `death_permitted` is
  False (ADR-0023). `death_permitted` is computed by the caller (bleed-out/abandonment via
  `death_is_permitted`; battle Surrounded via `select_surrounded_terminal_pool` routing,
  #1733) rather than derived internally, since not every peril source is an `ObjectDB`
  character. Clears the acute-peril condition on BOTH death and survival so
  `_danger_persists` returns False. Returns True iff character died.
- `_resolve_terminal_bleed_out(sheet, instance) -> bool` — routes to `_resolve_peril_via_pool`
  with the `bleed_out_terminal` pool; seeding gap holds the victim (never kills ungated).
- `resolve_abandonment(sheet) -> bool` — resolves an abandoned victim's fate through the
  source-appropriate pool (`select_abandonment_pool`); no-op when no resolvable acute-peril
  instance (rescue beats the check); seeding gap holds rather than kills.

### `peril_resolution.py`
Involved-party classification and death-permission helpers used by both `services.py` and
`world.scenes.round_services`:
- `acute_peril_condition_names() -> list[str]` — returns `[BLEED_OUT_CONDITION_NAME]`. PLUMMETING
  is EXCLUDED: falls are environmental and self-completing; the hold/abandonment logic does not apply.
- `acute_peril_instances(sheet) -> QuerySet` — active Bleeding-Out `ConditionInstance`s on a victim.
- `is_pc_source(source_character) -> bool` — True iff the source has a `db_account` (player-
  controlled); False for None / NPCs.
- `death_is_permitted(*, victim_sheet, source_character) -> bool` — True only for a non-PC source
  with no active `death_deferred` condition on the victim; False for PC sources (ADR-0023), None
  sources, and `death_deferred` victims.
- `select_abandonment_pool(source_character) -> ConsequencePool` — returns
  `abandonment_pvp` / `abandonment_enemy` / `abandonment_environmental` by source kind; raises
  `ConsequencePool.DoesNotExist` on seeding gap.
- `hostile_drove_round(victim_sheet, scene_round, declared_ids) -> bool` — True when the peril's
  `source_character` declared this round (their participant pk is in `declared_ids`); drives the
  hold/advance decision in `resolve_scene_round`.
- `potential_rescuer_present(victim_sheet, room, *, exclude_character_id=None) -> bool` — True when
  any conscious non-hostile non-victim is in the room; `exclude_character_id` omits the departing
  character for the solo-departure case.
- `mark_abandoned(victim_sheet, scene_round)` — stamps `ConditionInstance.abandoned_since_round`
  once (first hold beat); no-op when no potential rescuer is present.
- `clear_abandoned(victim_sheet)` — clears the stamp when a hostile party drives again.

### `factories.py`
- `create_bleed_out_terminal_pool()` — seeds the `bleed_out_terminal` `ConsequencePool` (recover /
  stay_incapacitated / die). (A prior version of this doc listed a `create_bleed_out_condition()`
  here — it never existed; the Bleeding-Out template + stages are authored by
  `seeds.ensure_bleeding_out_condition()`, #2287.)
- `create_abandonment_pools()` — seeds all three abandonment pools (enemy / pvp / environmental);
  the `abandonment_enemy` pool includes a `captured_alive` outcome (CAPTURE effect, `EffectType.CAPTURE`)
  that creates a `HELD` `Captivity` — the merciful non-lethal alternative to death with no consent gate.

### `seeds.py` — production content (#2287)

`seed_survivability_content()` (cluster `"survivability"` in `world/seeds/clusters.py`) is what
makes the pipeline fire on a real database — before #2287 every pool lived only in test factories
and `process_damage_consequences` no-op'd each tier. Idempotent (get_or_create / fill-only-when-
null so staff edits survive re-seeding). Seeds: the foundational `CapabilityType` rows
(awareness/movement/limb_use — without the awareness row `can_act` degrades to always-True), the
`Unconscious` condition + capability-zeroing effects, the `Bleeding Out` staged condition
(3 stages, Mortal Resolve resists), the `knockout`/`default_death`/`default_wound` pools wired
onto `VitalsConsequenceConfig`, the peril pools via the factories above, the `death`
KudosSourceCategory, the liminal dream room (tag `dream_liminal`, category `system`), and the
PLACEHOLDER condolence text.

### Wake arc — unconscious recovery (#2287)

`attempt_wake(sheet, *, in_combat_tick=False)` is Bleeding Out inverted: one Endurance roll per
round, difficulty `calculate_wake_difficulty` (scales with missing health, eases per round
unconscious and with healing), guaranteed wake at the `expires_at` deadline stamped by the
knockout tier (`wake_guaranteed_rounds × SECONDS_PER_ROUND`; the hourly
`conditions.expiration_cleanup` task is the force-wake backstop). Out of combat the attempt is
rate-limited via `ConditionInstance.last_resist_attempt_at`; `tick_round_for_targets` grants one
free roll per combat round. Dying (active Bleeding Out) blocks waking. Surface: `WakeAction`
(key `wake`) / telnet `wake`.

**Dreamside perception:** while Unconscious, `perceives_dreamside` is True and the player's view
relocates to the liminal dream room (`get_dream_room`) — web room-state push, room-target look,
and `message_location` broadcasts all honor it. The dead are never dreamside (ghosts watch the
waking room). The dream realm proper replaces the placeholder room (#2290).

### Death off-ramp (#2287, ADR-0131)

`_mark_dead` additionally stamps `died_in_scene` and delivers the condolence
(`death_condolence_body`: character text + `character_died` WS frame, best-effort). The ghost
interlude: dead characters stay puppetable as spectators — `DEAD_ALLOWED_ACTION_KEYS`
(`actions/constants.py`) whitelists their verbs; `GhostWindowPrerequisite` bounds emit/pose to
the death scene while active or the IC day of death. Release: `retire_character` (player
`RetireCharacterAction`/`retire`, staff-forceable, `vitals.auto_retire` scheduler backstop after
`auto_retire_days`) sets `retired_at`, enforced at `Account.can_puppet_character` and
`PlayerData.get_available_characters`. **No resurrection path exists.**

### `death_kudos.py` (#2287)

`award_death_kudos(giver_account, dead_character)` — the capped graceful-death channel on the
existing account kudos (ADR-0115): death-scene GM/staff `max(20, 50% of lifetime XP spend)`,
participants `max(1, 5%)`, scaled grants aggregate-capped at 100% of lifetime spend
(`CharacterXP.total_spent` sum), post-cap trickle floors (1 player / 20 staff). Window:
death → retire. Offscreen deaths staff-only. Surfaces: `GiveDeathKudosAction` (key
`death_kudos`) / telnet `kudos death <name>`.

---

## Consequence Pools (authored; seeded via factories)

| Pool name | Outcomes | PC-source death gate |
|-----------|----------|---------------------|
| `bleed_out_terminal` | recover / stay_incapacitated / die | `die` excluded for PC source |
| `abandonment_enemy` | recover / stay_incapacitated / die / captured_alive | `die` excluded for PC source |
| `abandonment_pvp` | recover / stay_incapacitated / die | `die` always excluded (PC source) |
| `abandonment_environmental` | recover / stay_incapacitated / die | `die` excluded for PC source |

---

## Design Invariants

- **No unconditional `_mark_dead`** (ADR-0049): the terminal stage of every acute-peril condition
  resolves through a guarded pool, never a raw death call.
- **PC sources structurally cannot kill** (ADR-0023): `death_is_permitted` returns False for any PC
  attacker, not just in the encounter layer but at the death-selection layer.
- **Abandonment is action-driven** (ADR-0004): the grace window counts `round_number` beats, not
  wall-clock time.
- **Plummet is exempt** from the hold/abandonment model: `acute_peril_condition_names()` returns
  BLEED_OUT only; plummet descent always advances regardless of who drove the round.

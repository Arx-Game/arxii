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
  conditions, not fields.
- **`VitalsConsequenceConfig`** (singleton pk=1): tunable difficulty scaling (`knockout_base_difficulty`,
  `death_base_difficulty`, `wound_base_difficulty` + per-percent scalars) and the global
  `knockout_pool`, `default_wound_pool`, `default_death_pool`.

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
- `_resolve_peril_via_pool(sheet, instance, pool) -> bool` — shared death-gated core: resolves
  a `ConditionInstance` through an authored `ConsequencePool`; excludes `character_loss`
  (`die`) candidates when `death_is_permitted` returns False (ADR-0023). Clears the acute-peril
  condition on BOTH death and survival so `_danger_persists` returns False. Returns True iff
  character died.
- `_resolve_terminal_bleed_out(sheet, instance) -> bool` — routes to `_resolve_peril_via_pool`
  with the `bleed_out_terminal` pool; seeding gap holds the victim (never kills ungated).
- `resolve_abandonment(sheet) -> bool` — resolves an abandoned victim's fate through the
  source-appropriate pool (`select_abandonment_pool`); no-op when no resolvable acute-peril
  instance (rescue beats the check); seeding gap holds rather than kills.

### `peril_resolution.py`
Involved-party classification and death-permission helpers used by both `services.py` and
`world.scenes.round_services`:
- `_acute_peril_condition_names() -> list[str]` — returns `[BLEED_OUT_CONDITION_NAME]`. PLUMMETING
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
- `create_bleed_out_condition()` — idempotent seed for the Bleeding-Out `ConditionTemplate` +
  stages + resist-check types.
- `create_bleed_out_terminal_pool()` — seeds the `bleed_out_terminal` `ConsequencePool` (recover /
  stay_incapacitated / die).
- `create_abandonment_pools()` — seeds all three abandonment pools (enemy / pvp / environmental);
  the `abandonment_enemy` pool includes a `captured_alive` outcome (CAPTURE effect, `EffectType.CAPTURE`)
  that creates a `HELD` `Captivity` — the merciful non-lethal alternative to death with no consent gate.

---

## Consequence Pools (authored; seeded via factories)

| Pool name | Outcomes | PC-source death gate |
|-----------|----------|---------------------|
| `bleed_out_terminal` | recover / stay_incapacitated / die | `die` excluded for PC source |
| `abandonment_enemy` | recover / captured_alive / die | `die` excluded for PC source |
| `abandonment_pvp` | recover / captured_alive | `die` always excluded (PC source) |
| `abandonment_environmental` | recover / die | `die` excluded for PC source |

---

## Design Invariants

- **No unconditional `_mark_dead`** (ADR-0049): the terminal stage of every acute-peril condition
  resolves through a guarded pool, never a raw death call.
- **PC sources structurally cannot kill** (ADR-0023): `death_is_permitted` returns False for any PC
  attacker, not just in the encounter layer but at the death-selection layer.
- **Abandonment is action-driven** (ADR-0004): the grace window counts `round_number` beats, not
  wall-clock time.
- **Plummet is exempt** from the hold/abandonment model: `_acute_peril_condition_names()` returns
  BLEED_OUT only; plummet descent always advances regardless of who drove the round.

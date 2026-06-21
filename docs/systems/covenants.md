# Covenants

Magically-empowered group oaths with roles, gear compatibility, a per-covenant rank
ladder, and (as of #1165) a Mentor's Vow bond system for level-mismatched parties.

**Standing invariant:** `CovenantRole` = combat power (archetype, speed_rank, Thread
pulls). `CovenantRank` = administrative authority (invite/kick/manage). These two
axes are orthogonal — never re-merge them.

## Models

### Core covenant models

- **`CharacterCovenantRole`** — per-character membership row; `left_at IS NULL` =
  currently active. Fields include `covenant` FK, `covenant_role` FK, `engaged`
  boolean, `rank` FK → `CovenantRank`.
- **`GearArchetypeCompatibility`** — existence-only join: which `CovenantRole`s are
  compatible with which `GearArchetype` values (read-only authored content).
- **`CovenantRole`** sub-role fields — a sub-role is a `CovenantRole` with a non-null
  `parent_role` (self-FK) and `resonance` (FK → `magic.Resonance`). Additional fields:
  - `unlock_thread_level` (PositiveIntegerField, default 0 for primary roles; >0 for
    sub-roles) — the COVENANT_ROLE thread level a character must reach to manifest this
    sub-role variant.
  - `discovery_achievement` (FK → `achievements.Achievement`, nullable) — sub-roles only;
    the achievement granted (with a global-first `Discovery` row) on first threshold crossing.
  - `codex_entry` (FK → `codex.CodexEntry`, nullable) — sub-roles only; the lore entry
    unlocked (`CharacterCodexKnowledge(KNOWN)`) on threshold crossing.
- **`CovenantRoleBonus`** — authored config: one row per `(CovenantRole, ModifierTarget)`
  with `bonus_per_level` SmallInt. `role_base_bonus_for_target(role, target,
  char_level)` returns `char_level × bonus_per_level`; no row → 0. Admin-registered.
- **`CovenantRank`** — per-covenant administrative authority tier. Fields: `covenant`
  FK (CASCADE, `related_name="ranks"`), `name` (max 60, player-chosen), `tier`
  (PositiveInt; 1 = top authority), `description`, `can_invite` bool, `can_kick` bool,
  `can_manage_ranks` bool. Unique `(covenant, tier)` and `(covenant, name)`. Ordered by
  `["covenant", "tier"]`.

### Mentor's Vow models (#1165)

- **`MentorBondConfig`** (pk=1 singleton) — global parameters for Mentor's Vow
  scaling. Fields:
  - `band_width` (PositiveSmallInt, default 2) — level-range half-width for eligible
    mentor/sidekick pairs. The covenant band is `[covenant.level − band_width,
    covenant.level + band_width]`.
  - `adjacency_offset` (PositiveSmallInt, default 1) — additional level offset applied
    when computing the adjusted party's effective level.
  - `max_sidekicks_per_mentor` (PositiveSmallInt, nullable; null = unlimited) — cap on
    active bonds per mentor per covenant.
  - `updated_at` / `updated_by` — audit timestamps. Seeded via
    `seed_mentor_bond_defaults()` in factories.py; staff-tunable in Django admin.

- **`MentorBond`** — one active bond record per (covenant, sidekick_sheet) pair (via
  partial unique constraint `unique_active_sidekick_bond`). Dissolved bonds are retained
  as an audit trail. Fields:
  - `covenant` FK (CASCADE, `related_name="mentor_bonds"`)
  - `mentor_sheet` FK → `CharacterSheet` (`related_name="mentor_bonds_as_mentor"`)
  - `sidekick_sheet` FK → `CharacterSheet` (`related_name="mentor_bonds_as_sidekick"`)
  - `adjusted_party` CharField (`MentorBondAdjusted.MENTOR` / `SIDEKICK`) — records
    which party the level adjustment is applied to.
  - `formed_at` DateTimeField (auto)
  - `dissolved_at` DateTimeField (null = still active; set on dissolution)
  - Custom manager method: `.active()` → filters `dissolved_at__isnull=True`.

## Handlers

- `character.covenant_roles` (`CharacterCovenantRoleHandler`):
  - `has_ever_held(role)` — True if the character has ever held this role (active or ended).
  - `currently_held_role_in(covenant)` — active role in the specified covenant, or None.
  - `currently_engaged_roles()` — list of **resolved (effective) roles** for every
    active+engaged membership. Calls `resolve_effective_role` per row: if the character's
    COVENANT_ROLE thread qualifies for a resonance sub-role, the sub-role is returned instead
    of the parent. Consumers that must key on the stored anchor identity should use
    `anchor_role_in()` instead.
  - `anchor_role_in(covenant)` — returns the **stored parent (anchor) role** for the active
    membership in `covenant`, ignoring sub-role resolution. Use this when the consumer must
    key on the thread's `target_covenant_role_id` or the raw membership row.
  - `invalidate()` — clear the cached assignment list; called by mutator services.

## Key Services

### Resonance sub-role resolution

- **`resolve_effective_role(*, character, role) -> CovenantRole`** (`world.covenants.services`) —
  derive-on-read. Given a primary role, walks the character's COVENANT_ROLE threads and finds the
  highest-qualifying resonance sub-role (highest `unlock_thread_level` the thread has crossed).
  Returns `role` unchanged when no qualifying sub-role exists, or when `role` is already a
  sub-role (single-depth; no re-promotion). Called per-row by `currently_engaged_roles()`.

- **`fire_subrole_discoveries(*, thread, starting_level, new_level) -> None`**
  (`world.covenants.discovery`) — fired by `spend_resonance_for_imbuing` after every COVENANT_ROLE
  thread imbue. For each sub-role whose `unlock_thread_level` was newly crossed (i.e.,
  `starting_level < unlock_thread_level <= new_level`):
  - Grants `discovery_achievement` via `grant_achievement` (creates a global-first `Discovery` row
    when this is the first ever earner).
  - Unlocks `codex_entry` via `CharacterCodexKnowledge.objects.get_or_create(status=KNOWN)`,
    keyed on `roster_entry`.
  - Sends a `NarrativeMessage(category=COVENANT)`: gamewide to all `active_player_character_sheets()`
    on first-ever discovery; personal to the discovering sheet otherwise.
  - Idempotent: an already-existing `CharacterAchievement` row gates the whole beat (no duplicates
    on replay).

### Core covenant services

- `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
- `end_covenant_role(role_assignment) -> None`
- `kick_member(*, target, actor) -> None` — actor's rank must have `can_kick=True`
  and `actor.rank.tier < target.rank.tier` (lower tier = higher authority); raises
  `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError`
- `is_gear_compatible(role, archetype) -> bool` — existence-only join lookup
- `role_base_bonus_for_target(role, target, char_level) -> int` (in
  `world.mechanics.services`) — reads `CovenantRoleBonus`; returns
  `char_level × bonus_per_level`; 0 if no row
- **Rank management** — all require `actor.rank.can_manage_ranks=True`:
  `create_rank`, `rename_rank`, `set_rank_capabilities`, `reorder_ranks`,
  `delete_rank`, `assign_rank`, `transfer_top`. Lock-out invariant:
  `LastManagerRankError` if an op would leave zero active managers.

### Mentor's Vow services (`world.covenants.mentorship`)

- **`covenant_band(covenant) -> tuple[int, int]`** — returns `(low, high)` inclusive
  level band `[covenant.level − band_width, covenant.level + band_width]`.
- **`is_in_band(covenant, raw_level) -> bool`** — True if raw_level is within the band.
- **`active_bond_adjusting(sheet) -> MentorBond | None`** — returns the active,
  non-graduated bond where `sheet` is the adjusted party; None if absent, dissolved,
  or graduated.
- **`bond_adjusted_level(sheet) -> int | None`** — returns the adjusted effective level
  when an active non-graduated bond reshapes `sheet`; None otherwise.
- **`effective_combat_level(sheet) -> int`** — the bond-adjusted combat level. When an
  active non-graduated bond exists, returns the adjusted level; otherwise returns the
  raw primary class level via `get_character_path_level`. This is what
  `compute_party_profile` calls per participant — outlier distortion is absorbed here.

  Adjustment rule:
  - **SIDEKICK adjusted**: `effective = clamp(mentor_raw − adjacency_offset, band)`
  - **MENTOR adjusted**: `top` = max raw primary level over all active MENTOR-adjusted
    sidekick bonds (one bulk query); `effective = clamp(top + adjacency_offset, band)`
  - **Graduated** (adjusted party's raw primary level is already in band) → treated as
    inactive → returns raw primary level.

- **`is_bond_graduated(bond) -> bool`** — True when the adjusted party's raw primary
  level has re-entered the covenant band (bond is mechanically inactive).
- **`establish_mentor_bond(*, covenant, mentor_sheet, sidekick_sheet) -> MentorBond`** —
  atomically determines `adjusted_party` (exactly one must be out of band), enforces the
  `max_sidekicks_per_mentor` cap (counts all active bonds where this character is the
  mentor in this covenant), and creates the `MentorBond`. Raises `MentorBondError` on
  constraint violations.
- **`dissolve_mentor_bond(bond) -> None`** — sets `dissolved_at = now()`.
- **`assert_membership_level_allowed(*, covenant, character_sheet) -> None`** — the
  **Vow gate**. Raises `VowGateError` if the character's raw primary level is outside
  the covenant band AND they have no active bond (as mentor or sidekick) in this
  covenant. Called by `add_member`; `create_covenant` (formation) is ungated. Gate is
  inactive when `MentorBondConfig` has not been seeded.

### Mentor's Vow ritual service

- **`establish_mentor_bond_via_session(*, session: RitualSession) -> MentorBond`** —
  the service function wired to `MentorsVowRitualFactory` (in `world.magic.factories`).
  The ritual is a consensual BILATERAL_SERVICE ritual; the session's leader and
  co-performer are the two bond parties. Unpacks the session, identifies which
  participant is mentor vs. sidekick based on band position, and calls
  `establish_mentor_bond`.

## Enums / Constants

- **`MentorBondAdjusted`** (`TextChoices` in `world.covenants.constants`) —
  `MENTOR` / `SIDEKICK`: which party the encounter-scaling adjustment is applied to.

## Combat Seams

### Role bonuses (#985)

`apply_equipped_armor_soak` adds `_covenant_armor_soak_bonus` (armor-soak
`ModifierTarget` total) on top of raw soak; `_weapon_augmented_budget` adds
`_combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)` to technique budget. Both
route through `get_modifier_total` → `covenant_role_bonus` equipment walk.

In combat, the covenant role bonus reads the **bond-adjusted level** rather than the
raw primary level: `_combat_target_bonus(sheet)` calls `bond_adjusted_level(sheet)` and
passes the result as `level_override` through `get_modifier_total` →
`equipment_walk_total` → `covenant_role_bonus`. A suppressed mentor's role bonus
shrinks; an elevated sidekick's bonus grows.

### Encounter scaling (#1165)

`compute_party_profile` (in `world/combat/scaling.py`) calls `effective_combat_level`
per ACTIVE participant before averaging. Level-outlier distortion is absorbed into the
bond math; the #566 invariant (difficulty keys off level and party size only, never
threads/relationships/covenants/facets/fashion) is preserved.

Graduation: when the adjusted party's real primary level re-enters the band,
`effective_combat_level` returns the raw level and the bond is dissolved at
`begin_declaration_phase`.

## Exceptions (`world.covenants.exceptions`)

- `CovenantRoleNeverHeldError` (Thread weave gate)
- `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError` (kick service)
- `NotAuthorizedToManageRanksError`, `LastManagerRankError`, `CrossCovenantRankError`,
  `IncompleteRankReorderError`, `CannotTransferToDepartedMemberError` (rank management)
- `MentorBondError` (bond creation / cap enforcement)
- `VowGateError` (membership level gate: `add_member` refused)

## API Endpoints

- `GET /api/covenants/gear-compatibilities/` — read-only authored content
- `GET /api/covenants/character-roles/` — read-only; non-staff scoped to own
  currently-played sheets; exposes nested `rank` + `viewer_capabilities`.
  `CharacterCovenantRoleSerializer` fields:
  - `covenant_role` — the **resolved (effective) sub-role** when the character's thread has
    crossed a sub-role threshold; otherwise the stored parent role. Derive-on-read via
    `resolve_effective_role`.
  - `anchor_role` — the **stored parent (anchor) role** on the membership row, ignoring
    sub-role resolution. Consumers that need to key on thread identity use this field.
- `GET|POST /api/covenants/ranks/` — list / create ranks
- `GET|PATCH|DELETE /api/covenants/ranks/{pk}/` — retrieve / update / delete
- `POST /api/covenants/ranks/reorder/` — bulk tier reorder
- `POST /api/covenants/ranks/{pk}/assign-member/` — assign member to rank
- `POST /api/covenants/ranks/{pk}/transfer-top/` — move top rank to member

## Follow-ups

- **Health scaling (#1256)** — `max_health` is not currently level-derived (it is
  `base_max_health + thread_addend`); Path-level-driven health is deferred to #1256.
- **Abyssal master/apprentice display labels** — the Mentor's Vow mechanic is flavor-neutral
  in the model layer. Thematic display labels (e.g. "Abyssal master/apprentice") are a
  future display-label layer with no model surface in v1.
- **Graduation auto-dissolve** — `begin_declaration_phase` dissolves graduated bonds;
  a separate async/background path for non-combat graduation is a follow-up.

## Integrates With

- Magic (`COVENANT_ROLE` Thread anchor cap = `current_level × 10`; `MentorsVowRitualFactory`;
  `spend_resonance_for_imbuing` hooks `fire_subrole_discoveries` after each imbue)
- Mechanics (`covenant_role_bonus` in modifier walk; `level_override` via `bond_adjusted_level`)
- Items (`gear_archetype` on `ItemTemplate`)
- Combat (`apply_equipped_armor_soak` + `_weapon_augmented_budget`; `compute_party_profile`
  via `effective_combat_level`)
- Achievements (`CovenantRole.discovery_achievement` FK; `grant_achievement` on sub-role
  threshold crossing; `Discovery` row created on first-ever earner)
- Codex (`CovenantRole.codex_entry` FK; `CharacterCodexKnowledge(status=KNOWN)` created per
  roster_entry on threshold crossing)
- Narrative (`send_narrative_message(category=COVENANT)` for gamewide / personal discovery
  announcements; `active_player_character_sheets()` from `world.roster.selectors` selects
  gamewide recipients on first-ever discovery)

## Source

`src/world/covenants/`

- `models.py` — all covenant + mentor bond models
- `handlers.py` — `CharacterCovenantRoleHandler` (including `resolve_effective_role` routing)
- `services.py` — covenant lifecycle + `resolve_effective_role` + `establish_mentor_bond_via_session`
- `discovery.py` — `fire_subrole_discoveries` (sub-role discovery beat)
- `mentorship.py` — `effective_combat_level` and Mentor's Vow math
- `factories.py` — `seed_resonance_subrole_slice`, `SubroleCovenantRoleFactory`
- `exceptions.py` — all exceptions

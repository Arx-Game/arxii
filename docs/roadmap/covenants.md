# Covenants

**Status:** in-progress (role mechanics + Spec D integration shipped; covenant entity / lifecycle / formation ritual still post-MVP)
**Depends on:** Magic (Threads, Rituals), Combat (uses speed_rank), Items (gear archetype compatibility), Character Sheets

## Overview

Covenants are magically-empowered oaths — blood rituals that enshrine each
participant's role and bind them to a shared goal. Every covenant has a sworn
objective that all members commit to achieving together. The magic is real: the
oath grants power, and the roles shape how that power manifests.

This domain owns role definitions, character-to-role assignment, gear
compatibility, and combat speed integration. The data layer for those exists
today and is consumed by combat, the modifier pipeline, and the magic Thread
system. **The Covenant entity itself — the social structure that contains
members, holds a sworn objective, and progresses as a unit — does not yet
exist.** Members today hold roles in isolation; there is no covenant they
belong to. That work is the post-MVP scope.

## Key Design Points

### Covenant Types

- **Covenant of the Durance** — The foundational type. An adventuring party
  swears to support each other as they pursue the Durance (their overarching
  story of magical discovery). Long-lived, deeply personal, built around
  relationship bonds.
- **Covenant of Battle** — Formed for a specific war or battle scene. Assigns
  war roles that empower participants for large-scale conflict. Shorter-lived,
  can stack with a character's existing Durance covenant. Dissolved when the
  battle ends or objective is achieved.
- **Other types TBD** — The covenant framework should support different oath
  types with different durations, goals, and role sets (investigation,
  vengeance, trade pact — anywhere a sworn magical oath with defined roles
  makes narrative sense).

The `CovenantType` `TextChoices` enum (`world.covenants.constants`) currently
ships `DURANCE` and `BATTLE`.

### Foundational Role Archetypes (for Durance covenants)

Three archetypes capture combat identity:

- **Sword** (offense)
- **Shield** (defense)
- **Crown** (support)

At early levels players pick from these three. As the covenant or members
level up, specialized sub-roles unlock within each archetype (e.g., Vanguard,
Sentinel, Arbiter). Battle covenants and other types may have their own role
sets. Specific role names are authored content (`CovenantRole` rows).

### Combat Integration

- `CovenantRole.speed_rank` drives combat resolution order. Lower is faster.
  Combat reads the role directly from the per-character `CharacterCovenantRole`
  assignment — speed is **never denormalized** onto combat participants.
- Characters with no role default to `NO_ROLE_SPEED_RANK = 20` (slowest). NPCs
  default to `~rank 15`.
- See `docs/roadmap/combat.md` for the full combat resolution pipeline.

### Gear × Role Compatibility (Spec D §4.4)

Covenant role bonuses are always granted in full — they are *never* reduced.
Per equipped slot:

- **Compatible gear** (a `GearArchetypeCompatibility` row exists for the
  role × archetype pair): role bonus + gear stat (additive).
- **Incompatible gear** (no row): `max(role_bonus, gear_stat)`.

At low levels gear stats dominate either way; at higher levels role bonuses
dominate, and compatible gear adds a small mundane-stat increment on top.
Compatibility is staff-authored existence-only data — no boolean column,
just row-presence.

### Magic Integration: COVENANT_ROLE Thread Anchors (Spec D §6.3)

`world.magic.constants.TargetKind` includes `COVENANT_ROLE`. Characters can
weave Threads anchored on a `CovenantRole` and invest resonance in them.

- **Weave gate:** the character must have **ever held the role** (active or
  ended). `CharacterCovenantRoleHandler.has_ever_held(role)` enforces this.
  Violations raise `CovenantRoleNeverHeldError`.
- **Anchor cap formula:** `current_level × 10`, scaling with the character's
  current covenant level. (`current_level` is a placeholder until the
  Covenant entity ships with its own progression; today it reads from the
  authored character level.)

### Constraints (cross-cutting)

- Roles are unique within a covenant — no two members hold the same role
  (enforced today only at the role-assignment level; covenant-level
  uniqueness will land when the Covenant entity does).
- Covenant bonds will function like enhanced Threads with shared resonance.
- Covenant role influences which techniques are empowered during group content.
- Covenant-level progression unlocks group abilities.
- Battle covenants stack with Durance covenants — a character can be in both
  simultaneously.

## What Exists

### Data Layer (`src/world/covenants/`)

- **Models:**
  - `CovenantRole` — staff-authored lookup (SharedMemoryModel) with
    `name`, `slug`, `covenant_type`, `archetype`, `speed_rank`, `description`.
    Unique `(covenant_type, name)`.
  - `CharacterCovenantRole` — per-character role assignment with
    `joined_at`/`left_at` timestamps. Partial unique constraint enforces
    "at most one active assignment per (character, role)" via
    `left_at IS NULL`. PROTECT FK to `CovenantRole`.
  - `GearArchetypeCompatibility` — existence-only join (CovenantRole ×
    `world.items.constants.GearArchetype`). Row present = additive
    compatibility; absent = `max(role_bonus, gear_stat)`.

- **Constants** (`world.covenants.constants`): `CovenantType` (DURANCE,
  BATTLE), `RoleArchetype` (SWORD, SHIELD, CROWN).

- **Service functions** (`world.covenants.services`):
  - `assign_covenant_role(*, character_sheet, covenant_role)` —
    creates a new active assignment row, invalidates handler cache.
  - `end_covenant_role(*, assignment)` — sets `left_at`, idempotent,
    invalidates cache.
  - `is_gear_compatible(role, archetype)` — existence-only lookup.

- **Cached handler** (`world.covenants.handlers.CharacterCovenantRoleHandler`,
  attached as `character.covenant_roles`):
  - `has_ever_held(role)` — enforces the COVENANT_ROLE thread weave gate.
  - `currently_held()` — returns the active role or `None`.
  - `invalidate()` — called by mutator services.

- **Typed exceptions** (`world.covenants.exceptions`):
  - `CovenantError` (base, with `user_message` and `SAFE_MESSAGES` allowlist).
  - `CovenantRoleNeverHeldError` — raised by Thread weaving.

- **REST API** (`/api/covenants/`):
  - `GET /character-roles/` — `CharacterCovenantRoleViewSet` (read-only).
    Non-staff scoped to character sheets the user currently plays via the
    active RosterTenure chain. Staff see all.
  - `GET /gear-compatibilities/` — `GearArchetypeCompatibilityViewSet`
    (read-only, no pagination — small lookup table). Filterable by
    `covenant_role` and `gear_archetype`.

- **Tests** (`world/covenants/tests/`): exceptions, handler caching,
  models, services, views (5 test files).

### Cross-App Integration

- **Magic** (`world.magic`):
  - `Thread.target_covenant_role` typed FK + `COVENANT_ROLE` `TargetKind`.
  - Anchor cap formula `current_level × 10` in `compute_anchor_cap`
    (Spec D §6.3).
  - Thread weaving validates `has_ever_held(role)` before allowing weave.
  - Integration test: `world/magic/tests/integration/test_covenant_role_thread_pipeline.py`.

- **Mechanics** (`world.mechanics.services`):
  - `covenant_role_bonus(sheet, target)` contributes to `get_modifier_total`
    via the `EQUIPMENT_RELEVANT_CATEGORIES` gate (Spec D §5.2, §5.6).

- **Items** (`world.items`):
  - `GearArchetype` enum lives in `world.items.constants` and is the join
    target for `GearArchetypeCompatibility`.
  - `is_gear_compatible()` is the gate consulted by the gear×role math.

- **Combat** (`world.combat`):
  - `CombatParticipant.covenant_role` FK → `CovenantRole`.
  - Combat resolution order sorts by `speed_rank`; characters without a
    role fall back to `NO_ROLE_SPEED_RANK = 20`.

## What's Needed for MVP

The role mechanics (above) are complete. The covenant **entity** and its
lifecycle remain unbuilt:

- **`Covenant` model** — the social structure that contains members and a
  sworn objective. Fields likely include `name`, `covenant_type`, `level`,
  `sworn_objective`, `formed_at`, `dissolved_at`, plus FK columns specific
  to type (`durance_focus_FK`, `battle_encounter_FK`, etc., or a
  discriminator + typed FKs in the existing project pattern).
- **`CovenantMembership`** — `Covenant ↔ CharacterSheet` with role
  attached. Subsumes the current `CharacterCovenantRole` (which assumes
  roles in isolation), or coexists with it as a thin lookup. Decision
  point for the future spec.
- **Formation ritual** — a `Ritual` (already exists in `world.magic`)
  that creates the covenant, binds members, and assigns initial roles.
  Likely uses the existing `PerformRitualAction` dispatch surface.
- **Member lifecycle** — invite, accept, leave, kick. Sub-role unlock
  events (Vanguard → Sentinel-vs-other-Sword sub-role) tied to covenant
  level + member level.
- **Covenant-level progression** — XP/milestone system that levels the
  covenant as a unit, gating access to specialized sub-roles, group
  techniques, and the COVENANT_ROLE anchor cap (currently keyed off
  character level).
- **Sworn objective tracking** — what the covenant is sworn *to* —
  hooks into Stories/Missions to mark objectives as advanced or fulfilled.
  Likely overlaps with Stories' Beat/Episode model.
- **Dissolution paths** — voluntary, automatic-on-objective, fractured
  (members betray oath). Each may have different magical consequences.
- **Stacking rules** — a character in both a Durance covenant and a Battle
  covenant: which role applies in combat? Spec implies Battle takes
  precedence in war contexts but this is not yet authored.
- **Group abilities** — covenant-level techniques or rituals available
  only when ≥N members are present and active. Authored content.
- **API surface** — full CRUD for covenants, membership management,
  ritual invocation, sub-role unlock requests.
- **Frontend UI** — covenant browser, member roster, sworn-objective
  tracker, role-assignment UI, formation/dissolution flows.

## Cross-References

- **`docs/roadmap/combat.md`** — uses `CovenantRole.speed_rank` for
  resolution order; the "What Exists" section already documents the
  covenants integration accurately.
- **`docs/roadmap/items-equipment.md`** — Spec D PR1 section documents
  the covenant gear compatibility integration.
- **`docs/roadmap/magic.md`** — Resonance Pivot Spec D PR1 documents the
  COVENANT_ROLE Thread anchor and weave gate. (The "Covenants (Post-MVP)"
  section there has been superseded by this file.)
- **Spec:** `docs/superpowers/specs/2026-04-26-items-fashion-mantles-spec-d-design.md`
  — the design that landed the role/gear/Thread integration.

## Notes

- The `current_level` used by the COVENANT_ROLE anchor cap is a placeholder
  until covenant-level progression ships. When the Covenant entity lands
  with its own level field, the cap formula reads from it directly without
  changing call sites.
- Forward-looking nods elsewhere in the roadmap: `gm-system.md` references
  "Covenants stub" as a prerequisite (now understated — should read
  "Covenants role mechanics"); `seed-and-integration-tests.md` task 2Q
  authors the canonical CovenantRole seed set so combat resolution order
  becomes meaningful.

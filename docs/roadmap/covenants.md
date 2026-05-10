# Covenants

**Status:** in-progress (Slice A entity + membership FK + engagement context shipped; lifecycle / formation ritual / progression / group abilities still post-MVP)
**Depends on:** Magic (Threads, Rituals), Combat (uses speed_rank), Items (gear archetype compatibility), Character Sheets

## Overview

Covenants are magically-empowered oaths — blood rituals that enshrine each
participant's role and bind them to a shared goal. Every covenant has a sworn
objective that all members commit to achieving together. The magic is real: the
oath grants power, and the roles shape how that power manifests.

This domain owns the Covenant entity, character memberships (with engagement
context), role definitions, gear compatibility, and combat speed integration.
Slice A landed the foundational entity + membership FK + engagement gating in
the modifier pipeline and Thread pull eligibility. The remaining work
(formation ritual, progression, group abilities, sworn-objective tracking,
dissolution paths) is the rest of the multi-slice buildout.

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

### Covenants Are Group-Only

A covenant cannot be founded with a single character. Formation requires at
least two distinct character sheets, each with a role, supplied as the
initial set of founder memberships. The entire point of the system is to
require collaborative play to be significant — there will never, ever be a
"solo" covenant.

`create_covenant(*, founders: Sequence[CovenantFounder])` enforces this at
the service layer with typed exceptions (`InsufficientFoundersError`,
`DuplicateFounderError`). Future UI flows (Slice B) gate participant
selection so the API layer never receives fewer than two founders. Slice B
will also decide dissolution behavior when membership later drops below 2
(likely: auto-flag for replacement, then auto-dissolve after a grace period).

### Membership is Non-Exclusive

While each individual covenant has ≥2 members, an individual character can
be an active member of multiple covenants simultaneously — including
multiple Durance covenants, plus a Battle covenant. This is a deliberate
design call (Slice A §3.1) so the social structure stays resilient to
varying player activity: an active player naturally supports several groups
as "primary" in some, "supporting" in others, without having to leave any.

The active-uniqueness DB constraint enforces "at most one active role per
character per covenant" — *not* "per character per covenant_type" and *not*
"per character per role". Same role across two covenants (Vanguard of A +
Vanguard of B) is permitted; that's two distinct memberships, not a conflict.

"Primary covenant" as a player-declared designation is **future** work
(probably a boolean on membership with a partial unique, or an FK on
`CharacterSheet`). It is not the same concept as membership uniqueness.

### Engagement (Runtime Context)

`CharacterCovenantRole.engaged` is a per-row boolean indicating the character
is currently *fulfilling* this role for this covenant. **At most one engaged
active row per (character, covenant_type)** — i.e., a character can be engaged
with at most one Durance covenant AND at most one Battle covenant
simultaneously. Cross-type stacking is additive; same-type engagement is
mutually exclusive.

The invariant lives at the service layer (`set_engaged_membership` un-engages
any same-type row before engaging the target) plus a `clean()` validator on
the model. There is no DB-level CHECK or partial unique on the engagement
flag — Postgres can't put a partial-index WHERE on a joined column
(`covenant.covenant_type` lives on the related Covenant row), and
denormalizing the type onto the membership row would violate the project's
"avoid denormalization" rule.

**Surfaces gated by engagement** (Slice A):
- Modifier pipeline (`covenant_role_bonus`) iterates `currently_engaged_roles`
  and SUMs contributions across engaged roles (additive across types).
- COVENANT_ROLE Thread pull eligibility (`_anchor_in_action`) checks
  ANY-match against engaged memberships; mismatch raises
  `CovenantRoleNotEngagedError`.
- Combat speed_rank stays encounter-scoped via `CombatParticipant.covenant_role`
  (set at combat setup); Slice E will decide combat-side precedence between
  Durance and Battle for war contexts.

**Surfaces NOT gated by engagement** (persistent character properties):
- Thread anchor cap — `max(covenant.level across all CCR rows for this role) × 10`.
- Thread weave gate — `has_ever_held(role)`.

Auto-set / scene-context detection / mission-driven engagement / UI is Slice B.
Today, engagement is set via explicit `set_engaged_membership` calls (e.g., in
test setUpTestData or future API endpoints).

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

### Magic Integration: COVENANT_ROLE Thread Anchors

`world.magic.constants.TargetKind` includes `COVENANT_ROLE`. Characters can
weave Threads anchored on a `CovenantRole` and invest resonance in them.

- **Weave gate:** the character must have **ever held the role** (active or
  ended) in any covenant. `CharacterCovenantRoleHandler.has_ever_held(role)`
  enforces this. Violations raise `CovenantRoleNeverHeldError`.
- **Anchor cap formula** (Slice A §3.5): `max(covenant.level across the
  character's all-time CharacterCovenantRole rows for this role) × 10`. Cap
  is a persistent character property — independent of current engagement.
  Scales naturally when Slice D adds covenant XP. Use-based capping (legend
  earned in role / time held in role / etc.) is Slice G.
- **Pull eligibility** (Slice A §3.6): COVENANT_ROLE Thread pull effects fire
  only when the character is currently engaged with a covenant where they
  hold the anchored role. Mismatch raises `CovenantRoleNotEngagedError`
  (subclass of `InvalidImbueAmount`). Out-of-context, the Thread is dormant.

### Constraints (cross-cutting)

- One active role per character per covenant (enforced via partial unique
  constraint `covenants_one_active_role_per_covenant`). The same role can be
  active across multiple covenants — that's two memberships.
- "Roles unique within a covenant" (no two members hold the same role) is
  *not* a Slice A constraint and is unlikely to be added: Slice A intentionally
  permits non-exclusive memberships, including multiple members holding the
  same role within one covenant.
- Covenant bonds will function like enhanced Threads with shared resonance.
- Covenant role influences which techniques are empowered during group content.
- Covenant-level progression unlocks group abilities.
- Battle covenants stack with Durance covenants — a character can be engaged
  with both simultaneously, and their role bonuses sum additively.

## What Exists

### Data Layer (`src/world/covenants/`)

- **Models:**
  - `Covenant` — the social/magical structure (Slice A). Fields: `name`,
    `covenant_type`, `level` (default 1; Slice D drives growth),
    `sworn_objective` (TextField; Slice C structures), `formed_at`,
    `dissolved_at`. SharedMemoryModel.
  - `CovenantRole` — staff-authored lookup (SharedMemoryModel) with
    `name`, `slug`, `covenant_type`, `archetype`, `speed_rank`, `description`.
    Unique `(covenant_type, name)`.
  - `CharacterCovenantRole` — per-character membership row.
    `character_sheet`, `covenant` FK (PROTECT, related_name=`memberships`),
    `covenant_role`, `engaged` boolean, `joined_at`/`left_at`. Partial
    unique constraint `covenants_one_active_role_per_covenant` on
    `(character_sheet, covenant)` where `left_at IS NULL`. `clean()`
    enforces engagement invariants.
  - `GearArchetypeCompatibility` — existence-only join (CovenantRole ×
    `world.items.constants.GearArchetype`). Row present = additive
    compatibility; absent = `max(role_bonus, gear_stat)`.

- **Constants** (`world.covenants.constants`): `CovenantType` (DURANCE,
  BATTLE), `RoleArchetype` (SWORD, SHIELD, CROWN).

- **Service functions** (`world.covenants.services`):
  - **Lifecycle (Slice A):**
    - `create_covenant(...)` — atomically creates a covenant + founder
      membership.
    - `add_member(...)` — creates a new active membership.
    - `change_role(...)` — closes old membership, creates new one in same
      covenant.
    - `dissolve_covenant(...)` — idempotent; ends all active memberships
      and stamps `dissolved_at`.
    - `assign_covenant_role(*, character_sheet, covenant, covenant_role)` —
      creates a new active membership row, invalidates handler cache.
    - `end_covenant_role(*, assignment)` — un-engages and sets `left_at`,
      idempotent, invalidates cache.
  - **Engagement (Slice A):**
    - `set_engaged_membership(*, membership)` — atomically un-engages
      same-type rows, then engages target. Cross-type independent.
    - `clear_engaged_membership(*, membership)` — idempotent un-engage.
    - `clear_engaged_for_type(*, character_sheet, covenant_type)` —
      bulk un-engage by type.
  - `is_gear_compatible(role, archetype)` — existence-only lookup.

- **Cached handler** (`world.covenants.handlers.CharacterCovenantRoleHandler`,
  attached as `character.covenant_roles`):
  - `has_ever_held(role)` — enforces the COVENANT_ROLE thread weave gate
    (covers all-time rows, any covenant).
  - `currently_held_role_in(covenant)` — active role in the specified
    covenant, or None.
  - `currently_engaged_roles()` — list of roles where `engaged AND
    left_at IS None`.
  - `max_covenant_level_for_role(role)` — drives the COVENANT_ROLE
    anchor cap formula. Includes historical rows.
  - `invalidate()` — called by mutator services.

- **Typed exceptions** (`world.covenants.exceptions`):
  - `CovenantError` (base, with `user_message` and `SAFE_MESSAGES` allowlist).
  - `CovenantRoleNeverHeldError` — raised by Thread weaving.

- **REST API** (`/api/covenants/`):
  - `GET /covenants/` — `CovenantViewSet` (read-only). Non-staff scoped to
    covenants where the user has an active membership; staff see all.
    FilterSet: `covenant_type`, `is_active`. Detail endpoint exposes
    `member_count` + `is_active`.
  - `GET /character-roles/` — `CharacterCovenantRoleViewSet` (read-only).
    Non-staff scoped to character sheets the user currently plays via the
    active RosterTenure chain. Staff see all. Serializer exposes
    `covenant` (PK) + `engaged`.
  - `GET /gear-compatibilities/` — `GearArchetypeCompatibilityViewSet`
    (read-only, no pagination — small lookup table). Filterable by
    `covenant_role` and `gear_archetype`.
  - Full read+write CRUD lands in Slice B.

- **Tests** (`world/covenants/tests/`): exceptions, handler caching,
  models (incl. `Covenant` model + constraint + clean tests),
  services (incl. lifecycle + engagement), views (incl. `Covenant`
  endpoints + serializer exposure).

### Cross-App Integration

- **Magic** (`world.magic`):
  - `Thread.target_covenant_role` typed FK + `COVENANT_ROLE` `TargetKind`.
  - Anchor cap formula (Slice A): `max_covenant_level_for_role(role) × 10`
    in `compute_anchor_cap`. Reads from membership covenant.level; cap
    persists across engagement changes.
  - Thread weaving validates `has_ever_held(role)` before allowing weave.
  - Pull eligibility (Slice A): `_anchor_in_action` ANY-matches engaged
    roles for COVENANT_ROLE Threads. Mismatch raises
    `CovenantRoleNotEngagedError(InvalidImbueAmount)`.
  - Integration tests: `test_covenant_role_thread_pipeline.py`,
    `test_pull_engagement_gate.py`,
    `test_modifier_total_no_query.py::CovenantRoleAnchorCapQueryBudgetTests`.

- **Mechanics** (`world.mechanics.services`):
  - `covenant_role_bonus(sheet, target)` (Slice A): iterates
    `currently_engaged_roles()` and SUMs contributions across engaged roles.
    Returns 0 when no roles engaged. Stacks additively across covenant
    types (Durance + Battle).

- **Items** (`world.items`):
  - `GearArchetype` enum lives in `world.items.constants` and is the join
    target for `GearArchetypeCompatibility`.
  - `is_gear_compatible()` is the gate consulted by the gear×role math.

- **Combat** (`world.combat`):
  - `CombatParticipant.covenant_role` FK → `CovenantRole`.
  - Combat resolution order sorts by `speed_rank`; characters without a
    role fall back to `NO_ROLE_SPEED_RANK = 20`.
  - Combat-side precedence between Durance and Battle for war contexts is
    Slice E (not yet authored).

## What's Needed for MVP

Slice A landed the foundational entity + membership FK + engagement context +
anchor cap formula + pull gating. The remaining work is decomposed into
independent slices, each with its own design+plan+implementation cycle:

### Slice B — Lifecycle + UI

- **Formation ritual** — a `Ritual` (already exists in `world.magic`)
  that creates the covenant, binds members, and assigns initial roles.
  Likely uses the existing `PerformRitualAction` dispatch surface.
- **Member lifecycle** — invite, accept, leave, kick. Web-first flows.
- **Dissolution paths** — voluntary, automatic-on-objective, fractured
  (members betray oath). Each may have different magical consequences.
  Slice A's `dissolve_covenant` covers the basic case; Slice B layers
  reasons, kinds, and follow-on consequences.
- **Scene/mission engagement triggers** — auto-set / clear engaged based
  on scene context. Today engagement is set explicitly via
  `set_engaged_membership`; Slice B wires it to runtime triggers.
- **UI for engage/disengage** — surfaces the engagement state to players.
- **Full CRUD API** — covenant create/dissolve, membership add/remove/
  change-role, engage/disengage. Read-only Slice A endpoints get extended.

### Slice C — Sworn Objective + Stories integration

- **`SwornObjective` model** — replaces the free-text `sworn_objective`
  field with structured data. Likely overlaps with Stories' Beat/Episode
  model.
- **Sworn objective tracking** — what the covenant is sworn *to* —
  hooks into Stories/Missions to mark objectives as advanced or fulfilled.

### Slice D — Covenant progression

- **Covenant-level XP/milestones** — system that levels the covenant as a
  unit. Drives the existing `Covenant.level` field that the anchor cap
  formula already reads.
- **Group-ability unlocks at covenant level** — gates specialized
  sub-roles, group techniques, etc.
- **Sub-role unlock events** — Vanguard → Sentinel-vs-other-Sword sub-role
  tied to covenant level + member level.

### Slice E — Battle Covenants + Durance × Battle stacking

- **Type-specific data** — `durance_focus_FK`, `battle_encounter_FK`,
  etc., on Covenant. Discriminator + typed FK pattern.
- **Combat-side precedence** between Durance and Battle for war contexts.
  Spec implies Battle takes precedence in war contexts but this is not yet
  authored.

### Slice F — Group Abilities

- **Covenant-level techniques or rituals** available only when ≥N members
  are engaged and present. Authored content layered on the Slice A
  engagement substrate.

### Slice G — Use-based Thread mechanics

- **Use-based weave gate** — Tehom's "force people to actually use the
  role before they could weave threads into it" — replaces (or augments)
  today's `has_ever_held` gate.
- **Use-based anchor cap** — legend earned in role / time held in role /
  etc. — richer signal than max_covenant_level. Layered on top of the
  Slice A formula.

### Cross-cutting (post-Covenants)

- **Thread situational gating for non-COVENANT_ROLE kinds** — bringing
  RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE / FACET into the same
  "in-action" model that Slice A added for COVENANT_ROLE. Project-wide
  Thread-discipline work, not Covenant-specific.
- **Frontend UI** — covenant browser, member roster, sworn-objective
  tracker, engage/disengage controls, formation/dissolution flows.

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

- The Slice A spec is `docs/superpowers/specs/2026-05-09-covenants-slice-a-design.md`
  and the implementation plan is
  `docs/superpowers/plans/2026-05-10-covenants-slice-a-implementation.md`.
- The COVENANT_ROLE anchor cap formula now reads from `covenant.level`
  via the membership table. The placeholder `current_level × 10` formula
  was replaced in Slice A. When Slice D ships covenant-level XP, the cap
  scales naturally without changing call sites.
- Forward-looking nods elsewhere in the roadmap: `gm-system.md` references
  "Covenants stub" as a prerequisite (now understated — should read
  "Covenants Slice A"); `seed-and-integration-tests.md` task 2Q
  authors the canonical CovenantRole seed set so combat resolution order
  becomes meaningful.

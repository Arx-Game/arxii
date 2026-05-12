# Covenants

**Status:** in-progress (Slice A entity + membership FK + engagement context shipped; Slice B RitualSession primitive + formation ritual + engagement UI shipped; progression / group abilities / dissolution still post-MVP)
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
`DuplicateFounderError`). The Slice B `CovenantFormationRitualFactory` gates
participant selection so the API layer never receives fewer than two founders.
Dissolution behavior when membership later drops below 2 is **not in MVP** —
see the "Covenants Languish" design decision in "What Slice B Added".

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

Auto-set via scene context is wired in Slice B: `evaluate_scene_engagement`
fires at `move_object`, `ensure_scene_for_location`, and
`_ensure_scene_participation` subscription points. Manual engage/disengage
endpoints also landed in Slice B. Mission-driven engagement is post-MVP.

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
    `sworn_objective` (TextField; intentionally free-text — see "Durable
    Design Decision: Sworn Objective" below), `formed_at`, `dissolved_at`.
    SharedMemoryModel.
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
  - Engage/disengage actions + `RitualSessionViewSet` landed in Slice B.
    Full lifecycle CRUD (invite/leave/kick) is post-MVP.

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

### What Slice B Added

- **`RitualSession` primitive in `world/magic`** — multi-participant ritual
  coordination (draft/accept/decline/fire/cancel lifecycle), discriminator-M2M
  `RitualSessionReference` for typed FK references, factory-driven Ritual rows
  (no data migrations). Participation rules: `SINGLE_ACTOR`, `BILATERAL`,
  `OPEN_ENROLLMENT`. Session-level role choices propagate through `reference_kind`
  to the fired service.
- **Covenant ritual wrappers** — `create_covenant_via_session` and
  `induct_member_via_session` thin shims around Slice A services;
  `CovenantFormationRitualFactory` and `CovenantInductionRitualFactory` that seed
  the Ritual rows on startup.
- **Soul Tether BILATERAL retrofit** — Soul Tether ritual factory now `BILATERAL`
  with sineater + sinner role choices; `accept_soul_tether_via_session` wrapper.
  `soul_tether_rescue` stays `SINGLE_ACTOR` (rescue inherently can't require
  consent). All `SoulTetherRole.ABYSSAL` references renamed `SINNER` everywhere
  (models, tests, services, frontend).
- **Engagement** — manual UI (POST engage/disengage endpoints with
  `can_engage_durance_membership` prerequisite check) + scene auto-engage via
  three subscription points: `move_object`, `ensure_scene_for_location`,
  `_ensure_scene_participation`. `evaluate_scene_engagement` selects the best
  membership for the room context (most co-present covenant members).
- **API** — `RitualSessionViewSet` at `/api/magic/rituals/sessions/` with
  list/detail/draft/accept/decline/fire/cancel actions; engage/disengage actions
  on `CharacterCovenantRoleViewSet`.
- **Frontend** — `RitualSessionInboxPage`, `RitualSessionDetailPage`,
  `RitualSessionDraftDialog`, `RitualSessionResponseDialog`; new field types
  (`covenant_picker`, `covenant_role_picker`, `soul_tether_role_picker`);
  `CovenantsListPage`, `CovenantDetailPage`; inbox notification badge in header.

### Durable Design Decision: Covenants Languish, No Exit Lifecycle in MVP

Covenants do not have an exit lifecycle in MVP. There is no "leave covenant",
"kick member", or "dissolve when membership drops below 2" flow. Members simply
stop engaging; the covenant record persists indefinitely. This is an intentional
design constraint:

- Dissolution paths (voluntary, automatic-on-objective, fractured betrayal) are
  post-MVP and belong in a later Slice. All future slice designs must treat this
  as a given — do not add exit mechanics unless explicitly specced.
- If membership falls below 2, the covenant remains valid but effectively
  dormant. There is no auto-flag, grace period, or auto-dissolve in MVP.
- This keeps Slice B scope bounded and avoids speccing dissolution consequences
  (magical fallout, Thread breakage, etc.) before the magic system is mature
  enough to design them properly.

**Future slices must respect this constraint.** Do not add exit mechanics or
dissolution triggers in Slice C–G without a dedicated design session.

### Durable Design Decision: Sworn Objective Is an Enduring Mission Statement

`Covenant.sworn_objective` is intentionally a free-text TextField, and is
intended to stay that way. It is **not** an achievable goal that triggers
events when "completed":

- Examples that fit the intent: "Defense of the Umbral Empire", "The
  Reformation of my lost Noble House", "To protect the innocent from Evil".
- Sworn objectives are enduring mission statements / oaths — closer to a
  Player's House motto or a knightly Order's vow than to a quest objective.
- Achieving the objective should NOT dissolve the covenant. The covenant
  persists as long as members care to engage with it.
- There is no `SwornObjective` model planned. Earlier roadmap drafts and
  Slice A's spec speculated about structuring this into a separate model
  ("Slice C structures it"); that speculation was AI-authored and never
  validated. Discard it.

**Future slices must respect this constraint.** If a future system wants
covenants to participate in goal/objective mechanics, route that through a
different concept (Stories, Missions) and link the covenant to those — do
not retrofit `sworn_objective` into structured data.

## What's Needed for MVP

Slices A and B are shipped. The remaining work is decomposed into independent
slices, each with its own design+plan+implementation cycle:

### Slice B — Lifecycle + UI (SHIPPED)

- Formation ritual via `RitualSession` — DONE
- Member induction via `RitualSession` — DONE
- Scene/mission engagement auto-triggers — DONE
- Manual engage/disengage API — DONE
- Covenant + RitualSession frontend pages — DONE
- Soul Tether BILATERAL retrofit — DONE
- No exit lifecycle in MVP (languish design decision) — DOCUMENTED

### Slice C — Dropped (was: Sworn Objective + Stories)

The original Slice C scope ("structure `sworn_objective` into a model;
hook objectives into Stories/Missions to mark fulfillment") was AI-authored
speculation, not user-validated design. See "Durable Design Decision: Sworn
Objective Is an Enduring Mission Statement" above. Sworn objective stays
free-text.

The "Stories integration" half of the original Slice C is preserved in
**Slice D** below (covenants can be tied to Stories; story-beat completion
is the primary covenant XP source). The "structured objective" half is
discarded entirely.

### Slice D — Covenant progression + Story integration

Combines the original Slice D (covenant XP / leveling) with the surviving
half of Slice C (covenants can be tied to Stories; story participation is
where XP comes from). Sworn objective stays free-text per the design
decision above.

**Mechanics:**
- **Covenant-level XP/milestones** — system that levels the covenant as a
  unit. Drives the existing `Covenant.level` field that the anchor cap
  formula already reads.
- **Story integration** — covenants can be linked to Stories, either
  implicitly (when all participants in a Story share a covenant, that
  Story is treated as a "covenant story") or explicitly (a Story can be
  declared as the covenant's storyline by the table running it).
  Achieving a related Story's beats grants the covenant XP.
- **Sub-role unlocks at covenant level** — Vanguard → Sentinel-vs-other-Sword
  sub-role tied to covenant level + member level. (Sub-role authoring is
  the bulk-content piece that ties to integration tests / future
  "start-your-own-arx" quickstart.)

**Group-ability unlocks** at covenant level were originally bundled here but
are split into Slice F so this slice stays focused on the XP loop and the
authoring foundation.

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
- **Frontend UI (remaining)** — Battle covenant UI, group ability triggers,
  covenant-Story linkage UI (Slice D). Covenant browser, engage/disengage
  controls, and formation/induction flows landed in Slice B. (No
  sworn-objective tracker — sworn_objective is intentionally free text;
  see the durable design decision above.)

## Cross-References

- **`docs/roadmap/combat.md`** — uses `CovenantRole.speed_rank` for
  resolution order; the "What Exists" section already documents the
  covenants integration accurately.
- **`docs/roadmap/items-equipment.md`** — Spec D PR1 section documents
  the covenant gear compatibility integration.
- **`docs/roadmap/magic.md`** — Resonance Pivot Spec D PR1 documents the
  COVENANT_ROLE Thread anchor and weave gate. (The "Covenants (Post-MVP)"
  section there has been superseded by this file.)
- **Spec (Slice A):** `docs/superpowers/specs/2026-04-26-items-fashion-mantles-spec-d-design.md`
  — the design that landed the role/gear/Thread integration.
- **Spec (Slice B):** `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md`
  — the design for the RitualSession primitive, Soul Tether BILATERAL retrofit,
  formation/induction wrappers, engagement auto-triggers, and frontend pages.

## Notes

- The Slice A spec is `docs/superpowers/specs/2026-05-09-covenants-slice-a-design.md`
  and the implementation plan is
  `docs/superpowers/plans/2026-05-10-covenants-slice-a-implementation.md`.
- The Slice B spec is `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md`
  and the implementation plan is
  `docs/superpowers/plans/2026-05-10-covenants-slice-b-implementation.md`.
- The COVENANT_ROLE anchor cap formula now reads from `covenant.level`
  via the membership table. The placeholder `current_level × 10` formula
  was replaced in Slice A. When Slice D ships covenant-level XP, the cap
  scales naturally without changing call sites.
- Forward-looking nods elsewhere in the roadmap: `gm-system.md` references
  "Covenants stub" as a prerequisite (now understated — should read
  "Covenants Slices A+B"); `seed-and-integration-tests.md` task 2Q
  authors the canonical CovenantRole seed set so combat resolution order
  becomes meaningful.
- The "Frontend UI" bullet in Cross-cutting is partially delivered by Slice B
  (covenant browser, engage/disengage, formation/induction ritual flow). What
  remains: sworn-objective tracker, advanced dissolution flows, Battle covenant
  UI, group ability triggers.

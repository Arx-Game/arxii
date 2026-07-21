# Covenants

**Status:** in-progress (Slice A entity + membership FK + engagement context shipped; Slice B RitualSession primitive + formation ritual + engagement UI shipped; Slice D covenant progression + Story integration shipped; Slice E Battle covenants + Durance×Battle combat-precedence shipped; Slice F covenant rites shipped including role-aware level-banded severity-scaling stat packages (#753); per-role powers (#751: tier-0 passive capability application surface + per-(role,resonance) `ThreadPullEffect` catalog) shipped; rite stat-buffs now flow into checks (#783); battle/group-ability/role-power/promotion frontend (#518) shipped; covenant rank passive bonus (#762: authored `CovenantLevelBonus` config, engagement-gated, level-scaled, derive-on-read via `covenant_level_bonus` in the modifier pipeline) shipped; exit lifecycle — voluntary leave + leader-gated kick + below-2 auto-dissolve, soft-only (#519) — shipped; Slice G use-based COVENANT_ROLE anchor cap (#517: additive legend-earned-in-role + time-held-in-role on top of the covenant-level floor, derive-on-read, no migration) shipped; the Slice G use-based weave gate still post-MVP; rank ladder — `CovenantRank` per-covenant authority tier, two-axis `CovenantRole`/`CovenantRank` model, rank management services, `CovenantRankViewSet` API, rank-ladder UI (#1027) — shipped; covenant-role armor-soak gate — compatible→additive, incompatible→`max(physical, resonant pool)`, level-scaled; #1174 — shipped; resonance sub-role runtime resolution (derive-on-read via `resolve_effective_role` + `fire_subrole_discoveries` discovery beat; `discovery_achievement`/`codex_entry` FKs on sub-role `CovenantRole`; `anchor_role` API field; #1277) — shipped; telnet membership lifecycle — `CmdCovenant` (`covenant engage/disengage/leave/kick/rank/transfer/standdown`), seven `action.run()` REGISTRY Actions in `actions/definitions/covenants.py`, `world.covenants.selectors` shared by Actions + viewsets, covenant induction + banner-call rise via `CmdRitual` adapter registry (`commands/ritual_adapters.py` — `CovenantInductionAdapter` + `BannerCallAdapter`) (#1346) — shipped; combat-identity blend — `CovenantRole.archetype` single-enum replaced by `sword_weight`/`shield_weight`/`crown_weight` (sum to 1 on primaries, sub-roles delegate via `blend_weight_for`), `CovenantRoleActionScaling` replacing `ArchetypeActionScaling`, always-on `covenant_role_blend_power_term` baseline cast power term — Layer 1 of ADR-0149's four-layer vow-power model (#2529) — shipped; per-vow finer technique specialty — `CovenantRoleTechniqueSpecialty` (NK `(covenant_role, function)`, valid on primaries AND sub-roles, sub-role rows ADD) + always-on `covenant_role_specialty_power_term`, keyed on the shared code-defined `magic.TechniqueFunction` vocabulary also consumed by Layer 4's situational perks — Layer 2 of ADR-0149 (#2443) — shipped; defense styles + gear substitution — `DefenseStyle` (GEAR_SOAK/EVASION/BARRIER) + per-role `CovenantRoleDefenseProfile.gear_additive_tenths`, `gear_additive_fraction` scaling the compatible-armor bucket once at the #1174 soak seam, `VowGearScaling` removed (subsumed by the profile fraction) — Layer 3 of ADR-0149 (#2533) — shipped; Layer 4 slice 1 of 3 — the deterministic situational-perk machinery: code-defined `Situation` library + evaluator registry, `VowSituationalPerk`/`VowSituationalPerkSituation`/`VowSituationalPerkRung` authoring models, `POWER_BONUS`/`CHECK_BONUS` delivery, and the dual-dispatch (WS + telnet) announce presentation contract — ADR-0151 (#2536) — shipped; Layer 4 slice 2 of 3 — outcome guarantees: `VowSituationalPerk.floor_success_level` (authored, canonical −10..+10 scale, `TIER_FLOOR`-only), the centralized `world.checks.constants.BOTCH_SUCCESS_LEVEL_MAX` botch boundary, multi-kind `applicable_perks(effect_kind=tuple[...])`, and `TIER_FLOOR`/`BOTCH_IMMUNITY` wired into `perform_check`'s outcome resolution (`_apply_outcome_guarantees`, both the rolled and test-rig forced paths) — absolute (never thread-scaled), ungated, announce-on-bind-only — plus the covenant-mate reversal (ally `COVENANT_ALLIES`/`WHOLE_GROUP` group-perks now scope on membership + co-presence, the mate's own `engaged` flag is irrelevant — no death-spiral) — ADR-0152 (#2536) — shipped; Layer 4 slice 3 of 3 (Court/Battle situation scoping + dormant-vow messaging) remains)
**Depends on:** Magic (Threads, Rituals), Combat (uses speed_rank), Items (gear archetype compatibility), Character Sheets

## Overview

Covenants are magically-empowered oaths — blood rituals that enshrine each
participant's role and bind them to a shared goal. Every covenant has a sworn
objective that all members commit to achieving together. The magic is real: the
oath grants power, and the roles shape how that power manifests.

This domain owns the Covenant entity, character memberships (with engagement
context), role definitions, gear compatibility, combat speed integration, and
(#1027) the rank ladder that provides per-covenant administrative authority.
Slice A landed the foundational entity + membership FK + engagement gating in
the modifier pipeline and Thread pull eligibility. Later slices added the
formation ritual, progression, group abilities/rites, the exit lifecycle (#519
— voluntary leave, rank-gated kick, and below-2 auto-dissolution, all soft),
and the two-axis authority model (#1027 — `CovenantRole` for power, `CovenantRank`
for administrative authority; see "Two Orthogonal Authority Axes" below).

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
When active membership later drops below 2, the covenant auto-dissolves
immediately (soft) — see the "Covenant Exit Lifecycle (#519)" design decision
below.

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
  (set at combat setup). Slice E implemented combat-side precedence:
  `precedence_role_for_combat` returns the engaged Battle role over the Durance
  role whenever both are active — Battle wins unconditionally (no war-context
  flag). This is set as the default in combat `add_participant`/`join_encounter`.

**Surfaces NOT gated by engagement** (persistent character properties):
- Thread anchor cap — additive (Slice G / #517): `max(covenant.level across all
  CCR rows for this role) × ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER` (covenant floor)
  `+ legend_earned_in_role // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR
  + days_held_in_role // ANCHOR_CAP_COVENANT_DAYS_DIVISOR` (personal investment).
- Thread weave gate — `has_ever_held(role)`.

Auto-set via scene context is wired in Slice B: `evaluate_scene_engagement`
fires at `move_object`, `ensure_scene_for_location`, and
`_ensure_scene_participation` subscription points. Manual engage/disengage
endpoints also landed in Slice B. Mission-driven engagement is post-MVP.

### Foundational Role Archetypes (for Durance covenants)

Three axes capture combat identity — **Sword** (offense), **Shield** (defense), **Crown**
(support). As of #2529 (ADR-0149) a role does not pick exactly one of these; it carries a
`sword_weight`/`shield_weight`/`crown_weight` blend (summing to 1 on primary roles) so a
role can be meaningfully hybrid. As the covenant or members level up, specialized
sub-roles unlock within a role's blend (e.g., Vanguard, Sentinel, Arbiter) — sub-roles
carry no weights of their own and delegate to their parent's blend via
`blend_weight_for(axis)`. Battle covenants and other types may have their own role sets.
Specific role names are authored content (`CovenantRole` rows).

### Combat Integration

- `CovenantRole.speed_rank` drives combat resolution order. Lower is faster.
  Combat reads the role directly from the per-character `CharacterCovenantRole`
  assignment — speed is **never denormalized** onto combat participants.
- Characters with no role default to `NO_ROLE_SPEED_RANK = 20` (slowest). NPCs
  default to `~rank 15`.
- See `docs/roadmap/combat.md` for the full combat resolution pipeline.

### Gear × Role Compatibility (Spec D §4.4, #985, #1174, #2533)

Gear compatibility governs two distinct seams:

**Weapon damage** (`_weapon_augmented_budget`, #985): per-slot marginal blend.
Compatible slot adds `role_bonus`; incompatible slot adds `max(0, role_bonus - gear_stat)`.
Routes through `get_modifier_total` → `covenant_role_bonus`.

**Armor soak** (`apply_equipped_armor_soak`, #1174): whole-character pool blend.
Worn armor is split into compatible vs incompatible buckets. The *resonant soak pool* =
facet + `covenant_role_base_total` + covenant-level (`covenant_level_bonus`) + mantle +
motif-style (role base × character level, summed once per character, not per slot). Final soak:

    compat_soak = int(compat_soak * gear_additive_fraction(character))
    soak = compat_soak + max(incompat_physical, resonant)

Compatible armor's physical soak adds directly to the final total; incompatible armor competes
with the resonant pool via `max` — at low levels physical armor wins; at higher levels
the resonant pool overtakes it. Durability wears only on armor whose physical soak
contributed. Compatibility is staff-authored existence-only data (`GearArchetypeCompatibility`)
— no boolean column, just row-presence.

**Defense-style gear substitution** (`gear_additive_fraction`, #2533, ADR-0149 Layer 3):
each engaged role may carry a `CovenantRoleDefenseProfile` authoring a `DefenseStyle`
(GEAR_SOAK/EVASION/BARRIER) and a `gear_additive_tenths` fraction (default 10 = fully
additive/legacy). `gear_additive_fraction(character)` takes the MAX fraction across the
character's engaged roles' resolved profiles (sub-role's own profile when present, else
its anchor's) and scales `compat_soak` once, before the blend above — no profile anywhere
→ fraction 1, byte-identical to pre-#2533 behavior. A vow whose style isn't GEAR_SOAK can
author a lower fraction so its own defense substitutes for gear rather than stacking with
it; gear counts once even when multiple engaged vows have profiles (the most
gear-friendly one governs). `VowGearScaling` — the per-(gear_archetype, role_archetype)
multiplier this layer was originally slated to use — is removed; the single authored
per-role fraction subsumes it.

### Magic Integration: COVENANT_ROLE Thread Anchors

`world.magic.constants.TargetKind` includes `COVENANT_ROLE`. Characters can
weave Threads anchored on a `CovenantRole` and invest resonance in them.

- **Weave gate:** the character must have **ever held the role** (active or
  ended) in any covenant. `CharacterCovenantRoleHandler.has_ever_held(role)`
  enforces this. Violations raise `CovenantRoleNeverHeldError`.
- **Anchor cap formula** (Slice G / #517): additive — `max(covenant.level
  across the character's all-time CharacterCovenantRole rows for this role) ×
  ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER` (covenant floor, the prior Slice A
  behaviour) `+ legend_earned_in_role // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR
  + days_held_in_role // ANCHOR_CAP_COVENANT_DAYS_DIVISOR` (personal investment).
  Cap is a persistent character property — independent of current engagement.
  Derive-on-read; the personal terms are 0 for a fresh holder, so the covenant
  floor preserves the original behaviour.
- **Pull eligibility** (Slice A §3.6): COVENANT_ROLE Thread pull effects fire
  only when the character is currently engaged with a covenant where they
  hold the anchored role. Mismatch raises `CovenantRoleNotEngagedError`
  (subclass of `InvalidImbueAmount`). Out-of-context, the Thread is dormant.
- **Court regard modulation (#1831) — SHIPPED.** For Court (`COVENANT_ROLE`)
  threads specifically, a pull's numeric payload can additionally be empowered
  by the covenant leader's signed `NpcRegard` (#1717) for the pull's live
  target: `court_regard_modulation` (`world/magic/services/pull_modulation_court.py`)
  resolves the leader's persona for the servant's engaged Court membership
  anchored on the thread, reads their regard for the target, and empowers the
  pull when the effect row's `ThreadPullEffect.regard_polarity` matches the
  regard's sign (OFFENSIVE ⇔ disfavored target, PROTECTIVE ⇔ favored target,
  NEUTRAL ⇔ either). This rides the magic app's target-aware pull seam
  (`apply_target_modulation`, dispatched on `thread.target_kind`) — see
  `docs/systems/magic.md` for the full mechanism. The combat-UI picker flags a
  Court thread `COURT_LEADER_NO_STAKE` when no candidate effect would ever be
  empowered against the chosen target.

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
    `name`, `slug`, `covenant_type`, `sword_weight`/`shield_weight`/`crown_weight`
    (combat-identity blend, #2529, ADR-0149), `speed_rank`, `description`.
    Unique `(covenant_type, name)`.
  - `CharacterCovenantRole` — per-character membership row.
    `character_sheet`, `covenant` FK (PROTECT, related_name=`memberships`),
    `covenant_role`, `engaged` boolean, `joined_at`/`left_at`. Partial
    unique constraint `covenants_one_active_role_per_covenant` on
    `(character_sheet, covenant)` where `left_at IS NULL`. `clean()`
    enforces engagement invariants.
  - `GearArchetypeCompatibility` — existence-only join (CovenantRole ×
    `world.items.constants.GearArchetype`). Row present = additive
    compatibility; absent = marginal blend (see §5.6 for the marginal
    semantics shipped in #985).
  - `CovenantRoleBonus` (#985) — authored config: FK `covenant_role`, FK
    `modifier_target` (`mechanics.ModifierTarget`), `bonus_per_level`
    SmallInt, unique per (role, target). `role_base_bonus_for_target(role,
    target, char_level)` returns `char_level × bonus_per_level`; no row → 0.
    Admin-registered. Default authoring empty → no live numeric effect until
    staff author rows.
  - `CovenantRank` (#1027) — per-covenant administrative authority tier
    (the rank ladder). Fields: `covenant` FK (CASCADE, `related_name="ranks"`),
    `name` (max 60, player-chosen), `tier` (PositiveInt; lower = higher
    authority, 1 = top), `description` (optional flavor text),
    `can_invite` bool, `can_kick` bool, `can_manage_ranks` bool. Unique
    `(covenant, tier)` and `(covenant, name)` enforced by DB constraints.
    `Meta.ordering = ["covenant", "tier"]`. See "Two Orthogonal Authority
    Axes" above for the full model contract.

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
  - **Rank ladder (#1027):** all require `actor.rank.can_manage_ranks=True`;
    raise `NotAuthorizedToManageRanksError` otherwise. The lock-out invariant
    (`_assert_keeps_a_manager`) is applied atomically inside each operation.
    - `create_rank(*, covenant, actor, name, tier, can_invite, can_kick, can_manage_ranks)`
    - `rename_rank(*, rank, actor, name)`
    - `set_rank_capabilities(*, rank, actor, **flags)` — raises
      `LastManagerRankError` if the change would leave no active manager.
    - `reorder_ranks(*, covenant, actor, ordered_rank_ids)` — atomically
      rewrites tier values to match the supplied ordering.
    - `delete_rank(*, rank, actor, reassign_to)` — moves affected memberships
      to `reassign_to` before deletion; raises `CrossCovenantRankError` if
      `reassign_to` belongs to a different covenant, `LastManagerRankError` if
      deletion would remove the last manager seat.
    - `assign_rank(*, membership, actor, rank)` — promotes/demotes a member.
    - `transfer_top(*, covenant, actor, new_top_membership)` — moves tier=1
      rank to a different member.

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
  - `CannotKickEqualOrHigherRankError` (#1027) — actor's tier is not strictly
    lower than target's tier.
  - `NotAuthorizedToKickError` (#1027) — actor's rank lacks `can_kick`.
  - `NotAuthorizedToManageRanksError` (#1027) — actor's rank lacks
    `can_manage_ranks`.
  - `LastManagerRankError` (#1027) — proposed change would leave the covenant
    with zero active members who can manage ranks.
  - `CrossCovenantRankError` (#1027) — rank and membership belong to different
    covenants.
  - `CannotKickSelfError` — self-kick attempt.
  - `IncompleteRankReorderError` (#1027) — `ordered_rank_ids` does not cover all
    covenant ranks.
  - `CannotTransferToDepartedMemberError` (#1027) — attempted to transfer top rank
    to a departed member.

- **REST API** (`/api/covenants/`):
  - `GET /covenants/` — `CovenantViewSet` (read-only). Non-staff scoped to
    covenants where the user has an active membership; staff see all.
    FilterSet: `covenant_type`, `is_active`. Detail endpoint exposes
    `member_count` + `is_active`.
  - `GET /character-roles/` — `CharacterCovenantRoleViewSet` (read-only).
    Non-staff scoped to character sheets the user currently plays via the
    active RosterTenure chain. Staff see all. Serializer exposes
    `covenant` (PK), `engaged`, nested `rank`, and `viewer_capabilities`
    block (`can_invite`/`can_kick`/`can_manage_ranks` for the requesting
    user's own active membership).
  - `GET /gear-compatibilities/` — `GearArchetypeCompatibilityViewSet`
    (read-only, no pagination — small lookup table). Filterable by
    `covenant_role` and `gear_archetype`.
  - Engage/disengage actions + `RitualSessionViewSet` landed in Slice B.
    Voluntary leave + rank-gated kick (with below-2 auto-dissolve) landed
    in #519; kick re-gated on `CovenantRank` capability + tier precedence
    in #1027 (see "Two Orthogonal Authority Axes" above).
  - `CovenantRankViewSet` (#1027) at `/api/covenants/ranks/`:
    - `GET/POST /ranks/` — list / create (create requires `can_manage_ranks`).
    - `GET/PATCH/DELETE /ranks/{pk}/` — retrieve / partial-update / delete
      (write requires `can_manage_ranks`).
    - `POST /ranks/reorder/` — bulk tier reorder.
    - `POST /ranks/{pk}/assign-member/` — assign a member to this rank.
    - `POST /ranks/{pk}/transfer-top/` — move the top rank to a member.

- **Selectors** (`world.covenants.selectors`):
  - `resolve_actor_membership(*, covenant, character_sheets, capability=None)` — first
    active membership in `covenant` among `character_sheets` carrying `capability` (a rank
    flag: `can_kick` or `can_manage_ranks`), or any active membership when `None`. Shared by
    the covenant viewsets and the Actions (one copy, not two).
  - `get_active_memberships(*, character_sheet)` — all active (`left_at IS NULL`) memberships
    with `covenant`, `rank`, and `covenant_role` pre-fetched.

- **Telnet Actions** (`actions/definitions/covenants.py`, #1346) — seven REGISTRY Actions,
  all `target_type=SELF`, thin wrappers over `world.covenants.services`. `CovenantError`
  subclasses surface as `ActionResult(success=False, message=exc.user_message)`:
  | Class | Key |
  |---|---|
  | `EngageCovenantMembershipAction` | `engage_covenant_membership` |
  | `DisengageCovenantMembershipAction` | `disengage_covenant_membership` |
  | `LeaveCovenantAction` | `leave_covenant` |
  | `KickCovenantMemberAction` | `kick_covenant_member` |
  | `AssignCovenantRankAction` | `assign_covenant_rank` |
  | `TransferTopRankAction` | `transfer_covenant_top_rank` |
  | `StandDownBattleCovenantAction` | `stand_down_battle_covenant` |

- **Telnet Command** (`commands/covenant.py`, #1346) — `CmdCovenant` (`covenant`) routes a
  leading subverb to the Action above via `action.run()`. Namespaced to avoid bare-key
  collisions (mirrors `CmdCombat`/`CmdDuel`). Bare `covenant`/`covenant list` renders the
  caller's memberships.

- **Ritual adapters** (`commands/ritual_adapters.py`, #1346) — per-ritual draft/join adapter
  registry keyed on `ritual.service_function_path`. Adapters translate flat `key=value` tokens
  from `CmdRitual._handle_draft`/`_handle_join` into typed `DraftParse`/`JoinParse` structures:
  - `CovenantInductionAdapter` — `covenant=<name>` on draft → COVENANT session reference;
    `role=<name>` on join → COVENANT_ROLE participant reference. Wired to
    `"world.covenants.services.induct_member_via_session"`.
  - `BannerCallAdapter` — `covenant=<name>` on draft → COVENANT session reference; no join
    tokens. Wired to `"world.covenants.services.rise_battle_covenant_via_session"`.
  - `SoulTetherAdapter` (pre-existing, moved here from inline CmdRitual) — `role=` /
    `resonance=` / `writeup=`.
  - `RitualDraftAdapter` (base no-op) — returned for unregistered rituals; preserves
    prior behavior for plain SINGLE_ACTOR rituals.

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
  - `covenant_role_bonus(sheet, target)` (Slice A, marginal semantics #985):
    iterates `currently_engaged_roles()` × equipped items and SUMs marginal
    contributions — compatible slot: adds `role_bonus`; incompatible slot: adds
    `max(0, role_bonus - gear_stat)`. Returns 0 when no roles engaged. Stacks
    additively across covenant types (Durance + Battle).
  - `role_base_bonus_for_target(role, target, char_level)` (#985): reads
    `CovenantRoleBonus`; returns `char_level × bonus_per_level`; 0 if no row.
  - `item_mundane_stat_for_target(item, target)` (#985): returns
    `item.effective_weapon_damage` / `item.effective_armor_soak` for the seeded
    target names; 0 otherwise.

- **Items** (`world.items`):
  - `GearArchetype` enum lives in `world.items.constants` and is the join
    target for `GearArchetypeCompatibility`.
  - `is_gear_compatible()` is the gate consulted by the gear×role math.

- **Combat** (`world.combat`):
  - `CombatParticipant.covenant_role` FK → `CovenantRole`.
  - Combat resolution order sorts by `speed_rank`; characters without a
    role fall back to `NO_ROLE_SPEED_RANK = 20`.
  - Combat-side precedence between Durance and Battle is implemented (Slice E):
    `precedence_role_for_combat` returns the engaged Battle role over Durance
    whenever both are active; this feeds `CombatParticipant.covenant_role` in
    `add_participant`/`join_encounter`. Modifier bonuses still stack additively.

### What Slice B Added

- **`RitualSession` primitive in `world/magic`** — multi-participant ritual
  coordination (draft/accept/decline/fire/cancel lifecycle), discriminator-M2M
  `RitualSessionReference` for typed FK references, factory-driven Ritual rows
  (no data migrations). Participation rules: `SINGLE_ACTOR`, `BILATERAL`,
  `OPEN_ENROLLMENT`. Session-level role choices propagate through `reference_kind`
  to the fired service.
- **Covenant ritual wrappers** — `create_covenant_via_session` and
  `induct_member_via_session` thin shims around Slice A services;
  `CovenantFormationRitualFactory` and `CovenantInductionRitualFactory` build the
  backing Ritual rows. **Reachability fixed in #2114** — until then these factories
  were called only from tests, so `ritual draft "Covenant Formation"` failed on a
  real server; `wire_covenant_lifecycle_rituals()` (`world.magic.factories`) now
  seeds Formation/Induction plus Call the Banners/Mentor's Vow/Renew the
  Oath/Organization Induction from `seed_magic_dev()`, reachable via the Big Button.
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

### Durable Design Decision: Covenant Exit Lifecycle (#519)

The covenant exit lifecycle now exists (issue #519 was the dedicated design
session the earlier "languish" constraint reserved this for). All exits are
**soft** — nothing is ever hard-deleted, so a covenant persists inactive and is
resurrectable:

- **Voluntary leave** — `leave_covenant` ends the calling member's active
  membership (stamps `left_at`); the membership row is retained for history.
- **Rank-gated kick** — `kick_member` lets a member whose `CovenantRank` has
  `can_kick=True` remove a member of a **strictly lower tier** (lower tier number
  = higher authority). Equal or higher tier cannot be kicked. The removed
  membership is soft-ended (`left_at`). See "Rank Ladder (#1027)" below for the
  full two-axis model.
- **Immediate auto-dissolution** — when active membership drops below 2 (whether
  by leave or kick), the covenant auto-dissolves immediately: `dissolved_at` is
  stamped and remaining active memberships are soft-ended. No grace period. The
  covenant record persists (dormant, resurrectable), consistent with the
  no-hard-delete rule.

### Durable Design Decision: Two Orthogonal Authority Axes (#1027)

**`CovenantRole` and `CovenantRank` are ORTHOGONAL and must NEVER be merged.**
This is a standing invariant — do not add `is_leadership` or any authority flag
back to `CovenantRole`, and do not encode combat/role bonuses onto `CovenantRank`.

- **`CovenantRole`** = the **power** a member wields on behalf of the covenant
  (Sword/Shield/Crown combat-identity blend weights, `speed_rank`, `CovenantRoleBonus`
  Thread pulls). `CovenantRole` has no `is_leadership` field — authority is on
  `CovenantRank`.
- **`CovenantRank`** (new in #1027) = **administrative authority** over the
  covenant. Per-covenant, player-named ordered tiers with integer `tier`
  (1 = top authority), capability flags (`can_invite`, `can_kick`, `can_manage_ranks`),
  and optional flavor `description`. `CharacterCovenantRole.rank` FK holds each
  member's current authority tier. Rank is role-agnostic and per-person.

The separation means a member's combat power (role) and their covenant authority
(rank) are independently managed: a powerful Sword can be a junior member; a quiet
Shield can be a senior administrator.

#### Rank Ladder

- Formation builds a **default two-tier ladder**: top rank "Founder" (all three
  capability flags true) + base rank "Member" (no flags). The designated founder(s)
  are seated at the Founder rank; other members default to Member. Passing
  `flat=True` to `create_covenant` produces a single-rank covenant (no authority
  distinctions).
- Each covenant's ladder is **player-named** — staff/players rename tiers via
  `rename_rank` after formation.
- Kick precedence: actor's `rank.can_kick` must be True AND `actor.rank.tier` must
  be **strictly less than** `target.rank.tier` (lower tier number = higher authority).
  Equal or higher tier is always refused (`CannotKickEqualOrHigherRankError`).
- A lock-out invariant (`LastManagerRankError`) guarantees the covenant always
  retains at least one active member whose rank has `can_manage_ranks=True`. Any
  rank management operation that would violate this is refused atomically.
- Invite gating: `can_invite` flag (no invite endpoint exists yet — induction
  remains ritual-driven via `RitualSession`; the flag is reserved for a direct
  invite flow post-MVP).

#### Rank Management Service Functions

All require the actor's `rank.can_manage_ranks=True`; raise
`NotAuthorizedToManageRanksError` otherwise:

- `create_rank(*, covenant, actor, name, tier, can_invite, can_kick, can_manage_ranks)`
- `rename_rank(*, rank, actor, name)`
- `set_rank_capabilities(*, rank, actor, **flags)`
- `reorder_ranks(*, covenant, actor, ordered_rank_ids)` — atomically rewrites all
  tier values to match the supplied ordering.
- `delete_rank(*, rank, actor, reassign_to)` — moves all members on the deleted
  rank to `reassign_to` before deletion; cross-covenant reassign raises
  `CrossCovenantRankError`.
- `assign_rank(*, membership, actor, rank)` — promotes or demotes a member.
- `transfer_top(*, covenant, actor, new_top_membership)` — moves the top
  (tier=1) rank to a different member.

#### API

`CovenantRankViewSet` at `POST/GET/PATCH/DELETE /api/covenants/ranks/` (CRUD) with
additional actions: `POST /ranks/reorder/`, `POST /ranks/{pk}/assign-member/`,
`POST /ranks/{pk}/transfer-top/`. `CanManageCovenantRanks` permission class gates
write operations. Membership serializer exposes nested `rank` + a
`viewer_capabilities` block (can_invite/can_kick/can_manage_ranks for the requesting
user's own active membership).

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
- Exit lifecycle (voluntary leave, leader-gated kick, below-2 auto-dissolve) —
  DONE (#519; soft-only)

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

### Slice D — Covenant progression + Story integration (SHIPPED)

Combines the original Slice D (covenant XP / leveling) with the surviving
half of Slice C (covenants can be tied to Stories; story participation is
where XP comes from). Sworn objective stays free-text per the design
decision above.

**What landed:**

- **`NarrativeCategory.COVENANT`** — new narrative category for covenant
  level-up messages, so level milestones surface in the narrative feed.
- **`CovenantLevelThreshold`** — staff-authored legend→level mapping table.
  Each row maps a `min_legend` score to a `level` integer. The curve lives
  entirely in authored data; the service recomputes `Covenant.level`
  whenever the summary changes.
- **`CovenantLegendCredit`** (in `world/societies`) — per-deed-per-covenant
  snapshot created when a `LegendEntry` is created and the character holds
  any active membership in that covenant. One row per (legend_entry,
  covenant) pair; additive across engaged covenants.
- **`CovenantLegendSummary`** — PostgreSQL materialized view (no Django
  migration; managed separately) summing `total_legend` and `deed_count`
  per covenant. Refreshed atomically by `recompute_covenant_level`.
- **`credit_engaged_covenants`** service — fan-out called from `LegendEntry`
  creation: iterates all engaged memberships for the character at the moment
  of deed, writes one `CovenantLegendCredit` snapshot per covenant, then
  calls `recompute_covenant_level` for each affected covenant.
- **`recompute_covenant_level`** service — refreshes the materialized view,
  reads the new `total_legend`, walks `CovenantLevelThreshold` rows to find
  the highest threshold met, updates `Covenant.level`, and emits a
  `NarrativeMessage(category=COVENANT)` on level-up.
- **Sub-role fields on `CovenantRole`** — `parent_role` (self-FK, nullable),
  `resonance` (FK → `magic.Resonance`), `unlock_thread_level` (PositiveIntegerField, 0 for
  primary roles, >0 for sub-roles). Together these encode the sub-role lattice: a sub-role is
  a `CovenantRole` with a non-null `parent_role`. Uniqueness: `(covenant_type, name)` still
  enforced; `(parent_role, resonance, unlock_thread_level)` ensures each slot is unique.
  Additional nullable sub-role-only FKs: `discovery_achievement` (→ `achievements.Achievement`)
  and `codex_entry` (→ `codex.CodexEntry`) for the discovery beat.
- **Runtime sub-role resolution (derive-on-read)** — `resolve_effective_role(*, character, role)`
  in `world.covenants.services` derives the effective sub-role at read time from the character's
  COVENANT_ROLE thread level, without mutating the stored membership row. The membership row
  always stores the parent role; `CharacterCovenantRoleHandler.currently_engaged_roles()` returns
  the resolved sub-role. `anchor_role_in(covenant)` returns the stored parent for consumers that
  need the anchor identity.
- **`fire_subrole_discoveries(*, thread, starting_level, new_level)`** in
  `world.covenants.discovery` — the discovery beat, hooked into `spend_resonance_for_imbuing`.
  On threshold crossing: grants the sub-role's `discovery_achievement` (+ global-first `Discovery`
  row), unlocks `codex_entry` (`CharacterCodexKnowledge(KNOWN)`), and sends a
  `NarrativeMessage(category=COVENANT)` (gamewide on first-ever; personal otherwise). Idempotent.
- **Beat consequence pool framework** — `LEGEND_AWARD` added to
  `ConsequenceEffectType`; `ConsequenceEffect` gains `legend_amount`
  (IntegerField) and `award_covenant` FK (nullable, → `Covenant`).
  `ResolutionContext` extended with `participants`, `beat`, `scene`, `story`.
  `apply_pool_deterministically` handles non-weighted pool application
  (all-consequences-at-once). `handle_legend_award` in
  `world/mechanics/services` calls `credit_engaged_covenants` for each
  participant with the consequence's `legend_amount`.
- **`Story.covenant` FK** — nullable FK on `Story` declaring the storyline's
  owning covenant. Beat resolution now passes `story` through
  `ResolutionContext` so consequence handlers can read it.
- **API surface** — `CovenantLevelThresholdViewSet` (staff-only, read-only); serializer
  additions for `parent_role`, `resonance`, `unlock_thread_level` on
  `CovenantRoleSerializer`; `covenant` FK on `StorySerializer`.
  `CharacterCovenantRoleSerializer` exposes `covenant_role` (resolved effective sub-role,
  derive-on-read) and `anchor_role` (stored parent role). The `promote` action on
  Sub-role promotion is derive-on-read; `CharacterCovenantRoleViewSet` has no `promote` action.

**Not in Slice D (explicitly out-of-scope per spec):**

- Authored sub-role content (Vanguard of Flame, Sentinel of the Deep, etc.)
  — sub-role rows are empty; authoring is future staff work.
- Frontend UI for promotion flow, legend totals dashboard, threshold curve
  editor.
- Higher-tier sub-role promotions (sub-role → sub-sub-role).
- `GLOBAL`-scope `LEGEND_AWARD` (awards to all covenant members regardless
  of scene presence) — only `SCENE`-scope is wired.
- Mission-driven covenant XP (missions reference Situations, not Beats —
  separate integration point).

**Group-ability unlocks** at covenant level remain in Slice F.

### Slice E — Battle Covenants + Durance × Battle stacking (SHIPPED)

Battle covenants gained their own lifecycle primitives and the combat-side
precedence rule was implemented. A character can be simultaneously engaged
in a Durance covenant and a risen Battle covenant; modifier bonuses sum
additively while combat speed precedence goes to the Battle role.

**What landed:**

- **Type-gated Battle-only fields on `Covenant`** — `battle_binding`
  (`BattleBinding` TextChoices: `STANDING` = banner/unit covenant that can
  rise again; `CAMPAIGN` = one-time event covenant that dissolves when
  concluded) and `is_dormant` (bool). `Covenant.clean()` enforces: BATTLE
  requires a binding; DURANCE forbids binding/dormancy; only STANDING
  covenants may be dormant.
- **"Call the Banners" rise ritual** — `BattleCovenantRiseRitualFactory`
  (a `Ritual` reusing the Slice-B `RitualSession` primitive,
  `ParticipationRule.FORMATION`, SERVICE dispatch) + service
  `rise_battle_covenant_via_session` (flips a dormant STANDING battle
  covenant risen and auto-engages accepted participants, fires a
  `NarrativeMessage`). Complementary `stand_down_battle_covenant` service
  sets dormancy and clears participant engagement.
- **Dormancy-aware engagement gate** — `can_engage_durance_membership`
  renamed to `can_engage_membership` (`world.covenants.handlers`); a BATTLE
  membership is only engageable when its covenant is risen (not dormant).
- **Combat-side precedence** — `precedence_role_for_combat(character_sheet)`
  (`world.covenants.services`) returns the engaged Battle role over the
  Durance role. Feeds `CombatParticipant.covenant_role` as the default in
  combat `add_participant`/`join_encounter`, which is the FK that
  `get_resolution_order` already reads. Battle wins unconditionally whenever
  both types are engaged — there is no war-context flag. Modifier bonuses
  continue to stack additively (unchanged).
- **Integration test** —
  `src/world/combat/tests/test_covenant_stacking_integration.py`: character
  engaged in both a Durance and a risen Battle covenant; covers simultaneous
  engagement, Battle speed precedence, dormancy blocking, and Durance fallback.

**Deferred (future seams):**

- ~~Structured `Story` link for CAMPAIGN dissolution~~ — **SHIPPED (#759/#1185).**
  A dedicated `Covenant.campaign_story` FK names the defining story; completing
  that story (via the new `complete_story` primitive) dissolves the linked
  CAMPAIGN covenant through the existing `dissolve_covenant` path. STANDING
  covenants are untouched. This also required building the story-completion
  primitive itself (#1185): `complete_story` + `POST /stories/{id}/complete/`
  set `Story.status=COMPLETED`/`completed_at` and honestly foreclose in-flight
  progress (new `ProgressStatus.FORECLOSED`) rather than orphaning or
  falsely-completing it. (Returning-player wrap-up of foreclosed threads is a
  tracked follow-up.)
- Battle auto-engage on roster join (Slice B §629 hook).
- Battle covenant frontend (#518).
- Group abilities (#516, Slice F).

### Slice F — Covenant Rites (group-activated buff rituals) — SHIPPED

Group-activated covenant **rites**: authored rituals gated by **covenant level
≥N** AND **≥N engaged members present**, where the gathered members renew their
vows and each participant gains a temporary **role-aware, level-banded** buff for
the coming battle — stacking on top of their individual covenant role bonuses,
scaled by turnout. A member who arrives mid-battle is **folded into the active
rite and re-empowers everyone** (severity recomputed upward for all participants,
ratchet-only). The buff is swept when the combat encounter ends.

Reuses the Slice B `Ritual`/`RitualSession` substrate (the rite is a SERVICE
ritual; the session coordinates) + the conditions system (`apply_condition`,
`UNTIL_END_OF_COMBAT`). Models:

- **`CovenantRite`** — authored sidecar O2O on `Ritual`, carrying the gate + buff
  config (`min_covenant_level`, `min_members_present`, `base_severity`,
  `severity_per_extra_participant`, `max_severity`). Has a `package_for(role,
  covenant_level)` method that returns the correct `ConditionTemplate` for a given
  role/level combination.
- **`CovenantRiteRolePackage`** (#753) — through model binding a `ConditionTemplate`
  to a `(rite, covenant_role, min_covenant_level)` triple. `package_for` selects
  the highest band whose `min_covenant_level ≤ covenant.level`; falls back to
  `rite.granted_condition` when no band matches (unmapped role or level too low).
- **`CovenantRiteInstance`** — the live fired rite, scoped to a combat encounter.
- **`CovenantRiteParticipant`** (#753) — through model (M2M between
  `CovenantRiteInstance` and `CharacterSheet`) that records each participant's own
  `granted_condition`. Late-join rescale and combat-end sweep act on each
  participant's OWN recorded condition rather than a single shared template.

`wire_covenant_rite_content()` seeds the "Renew the Oath" reference rite plus the
following role/level-banded stat packages (all effects `scales_with_severity=True`).
**Reachability fixed in #2114** — until then this helper was called only from tests;
`wire_covenant_lifecycle_rituals()` (`world.magic.factories`) now calls it from
`seed_magic_dev()` so the rite (Ritual + `CovenantRite` sidecar + packages together)
exists in a real deploy, not only under test setup:

| Role | Level band | Condition | Stats buffed |
|---|---|---|---|
| (default / unmapped) | any | Oathbound Resolve | willpower, composure, stability |
| Sword Vanguard (`sword-vanguard`) | ≥1 | Oathbound Fury I | strength, presence |
| Sword Vanguard (`sword-vanguard`) | ≥4 | Oathbound Fury II | strength, presence, wits |
| Shield Bulwark (`shield-bulwark`) | ≥1 | Oathbound Bulwark | stability, stamina |
| Crown Luminary (`crown-luminary`) | ≥1 | Oathbound Grace | composure, charm |

The `ConditionModifierEffect.scales_with_severity` flag (also added in #753)
causes `get_condition_modifier_total` to multiply each effect's `value` by the
condition's `effective_severity`, so higher turnout → higher modifier totals for
everyone.

**What the buff pipeline looks like end-to-end:**

1. `fire_session(session)` → `perform_covenant_rite(session)` — resolves each
   beneficiary's role via their active `CharacterCovenantRole`; calls
   `rite.package_for(role, covenant.level)` to select the right template; creates
   one `CovenantRiteParticipant` row per beneficiary; calls
   `bulk_apply_conditions(applications)`.
2. Mid-combat arrival → `evaluate_scene_engagement` → `fold_arrival_into_active_rites`
   — newcomer's template is selected by role/level; all prior participants'
   conditions are rescaled upward via `advance_condition_severity`.
3. Combat end → `cleanup_completed_encounter` → `complete_rites_for_encounter`
   — iterates `participant_records` (each with its own `granted_condition`);
   removes that specific template via `remove_condition`.

**Consumption note:** `get_condition_modifier_total` is consumed by the magic
power-resolution pipeline (`world/magic/services/techniques.py` line ~303) for
the multiplier stage of technique casting. Covenant rite buffs therefore
mechanically amplify a character's next spell/technique — the buff is live, not
computed-but-unconsumed. A follow-up issue (#TBD) should verify this path is
exercised in combat integration tests.

This is deliberately **not** "every member is granted an identical castable
power at covenant level N" (rejected as anti-individualization). Per-**role**
unique powers ship via the existing `Thread`-on-`COVENANT_ROLE` +
`ThreadPullEffect` machinery (**#751**, delivered): the tier-0 passive
application surface is `CharacterThreadHandler.passive_capability_grants()`
(engagement-gated, derive-on-read), folded into the capability read in
`world/conditions/services.py`; a reference per-`(role,resonance)` catalog is
seeded by `wire_covenant_role_powers_catalog()`. Two holders of the same role
anchoring different Resonances unlock different capabilities — the
individualization lever. **#783** (delivered) folds condition-sourced stat
buffs into `TraitHandler._get_stat_modifier`, so a rite buff now raises
effective trait values and stat checks, not only the technique multiplier.

### Slice G — Use-based Thread mechanics

- **Use-based anchor cap (#517) — SHIPPED.** The COVENANT_ROLE anchor cap is now
  additive: `max_covenant_level_for_role(role) × ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER`
  (covenant component — the prior Slice A behaviour, kept as a non-zero floor) plus
  `legend_earned_in_role // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR` plus
  `days_held_in_role // ANCHOR_CAP_COVENANT_DAYS_DIVISOR` (personal-investment
  components). Derive-on-read with **no new model and no migration**: tenure from
  existing `CharacterCovenantRole.joined_at`/`left_at` via
  `CharacterCovenantRoleHandler.days_held_in_role`; legend from Slice D
  `CovenantLegendCredit` rows via `world.societies.services.get_character_role_legend`
  (per-character, distinct-entry, active deeds only). The three divisor/multiplier
  knobs are admin-tunable constants in `world.magic.constants`. Because the covenant
  component is a use-independent floor, a fresh holder keeps a non-zero cap and can
  develop the thread immediately — so the `has_ever_held` weave gate is not an
  experience↔access catch-22 (sub-role promotion stays reachable).
- **Use-based weave gate — FUTURE.** Tehom's "force people to actually use the
  role before they could weave threads into it" — replacing/augmenting today's
  `has_ever_held` gate with a tenure/legend threshold — remains future work
  (out of scope for #517, which changed only the cap).

### Cross-cutting (post-Covenants)

- **Thread situational gating for non-COVENANT_ROLE kinds** — bringing
  RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE / FACET into the same
  "in-action" model that Slice A added for COVENANT_ROLE. Project-wide
  Thread-discipline work, not Covenant-specific.
- **Frontend UI (remaining)** — covenant-Story linkage UI (Slice D). Covenant
  browser, engage/disengage controls, and formation/induction flows landed in
  Slice B. Battle-covenant state (dormant/rise/stand-down), group-ability/rite
  triggers, per-member role-power display, and the sub-role promotion dialog
  landed in **#518** (`frontend/src/covenants/components/` +
  `CovenantDetailPage`, backed by the `/powers/` + `/stand_down/` endpoints).
  (No
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
- **Spec (Slice A):** `docs/architecture/items-fashion-mantles.md`
  — the design that landed the role/gear/Thread integration.
- **Spec (Slice B):** `docs/architecture/covenants-slice-b-design.md`
  — the design for the RitualSession primitive, Soul Tether BILATERAL retrofit,
  formation/induction wrappers, engagement auto-triggers, and frontend pages.

## Notes

- The Slice A spec is `docs/architecture/covenants-slice-a.md`
  and the implementation plan is
  `docs/superpowers/plans/2026-05-10-covenants-slice-a-implementation.md`.
- The Slice B spec is `docs/architecture/covenants-slice-b-design.md`
  and the implementation plan is
  `docs/superpowers/plans/2026-05-10-covenants-slice-b-implementation.md`.
- The COVENANT_ROLE anchor cap formula reads from `covenant.level` via the
  membership table (additive formula, derive-on-read). When covenant-level XP
  changes `Covenant.level`, the cap scales naturally without changing call sites.
- Forward-looking nods elsewhere in the roadmap: `gm-system.md` references
  "Covenants stub" as a prerequisite (now understated — should read
  "Covenants Slices A+B"); `seed-and-integration-tests.md` task 2Q
  authors the canonical CovenantRole seed set so combat resolution order
  becomes meaningful.
- The "Frontend UI" bullet in Cross-cutting is delivered by Slice B (covenant
  browser, engage/disengage, formation/induction ritual flow) plus **#518**
  (battle-covenant state, group-ability/rite triggers, role-power display,
  sub-role promotion). What remains: sworn-objective tracker, advanced
  dissolution flows.

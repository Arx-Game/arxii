# Covenants

Magically-empowered group oaths with roles, gear compatibility, a per-covenant rank
ladder, and (as of #1165) a Mentor's Vow bond system for level-mismatched parties.

**Standing invariant:** `CovenantRole` = combat power (SWORD/SHIELD/CROWN blend
weights, speed_rank, Thread pulls). `CovenantRank` = administrative authority
(invite/kick/manage). These two axes are orthogonal — never re-merge them.

## Models

### Core covenant models

- **`CharacterCovenantRole`** — per-character membership row; `left_at IS NULL` =
  currently active. Fields include `covenant` FK, `covenant_role` FK, `engaged`
  boolean, `rank` FK → `CovenantRank`.
- **`GearArchetypeCompatibility`** — existence-only join: which `CovenantRole`s are
  compatible with which `GearArchetype` values (read-only authored content).
  Lore-repo content as of #2533 (`NaturalKeyMixin` NK `["covenant_role",
  "gear_archetype"]`, `covenants.geararchetypecompatibility` in `CONTENT_MODELS`).
- **`CovenantRole.sword_weight` / `.shield_weight` / `.crown_weight`** (#2529, ADR-0149)
  — `DecimalField`s (max_digits=4, decimal_places=3) forming the combat-identity blend.
  Weights are stored on primary roles only and sum to 1; sub-roles carry all-zero
  weights and delegate via `blend_weight_for(axis) -> Decimal`, which reads from
  `parent_role` when set. Replaced the single-value `archetype` field (SWORD/SHIELD/
  CROWN enum) — a role can now be meaningfully both a striker and a rallying voice.
  Authored blend values are lore-repo content (`NaturalKeyMixin`, `covenants.covenantrole`
  in `content_export.py`'s `CONTENT_MODELS`); arxii's own seeds carry only
  placeholder-pure 1/0/0 blends for the three canonical roles.
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
  char_level)` returns `char_level × bonus_per_level`; no row → 0. Lore-repo content
  as of #2533 (`NaturalKeyMixin` NK `["covenant_role", "modifier_target"]`,
  `covenants.covenantrolebonus` in `CONTENT_MODELS`).
- **`VowStatScaling`** (#2022) — authored config: one row per
  `(CovenantRole, ModifierTarget)` with `bonus_per_level` scaling by the
  **COVENANT_ROLE thread level** (not character level, which `CovenantRoleBonus`
  already handles). `vow_stat_scaling_bonus(sheet, target)` returns
  `thread_level × bonus_per_level`; no row → 0. The mechanical heart of "solo
  darkness" — a deepened vow is a substantially stronger character. When the vow
  dims (#2051), the scaling drops to 0. This is ADR-0149 Layer 3's stat-power pillar
  and stayed unaffected by the #2533 rework; as of #2533 it rides the lore-repo
  content pipeline too (`NaturalKeyMixin` NK `["covenant_role", "modifier_target"]`,
  `covenants.vowstatscaling` in `CONTENT_MODELS`) — a wiring-proof test shows
  thread-level scaling aggregating into `equipment_walk_total` end-to-end.
- **`VowGearScaling`** — **REMOVED in #2533.** Formerly authored config keyed on
  the removed `CovenantRole.archetype` field (`(gear_archetype, role_archetype)`
  → `thread_level_multiplier`), short-circuited to a flat 0 by #2529 because it was
  never seeded in a real game. ADR-0149's Layer 3 decided its fate: rather than
  re-key a second per-archetype gear multiplier onto the new blend model, the single
  authored fraction on `CovenantRoleDefenseProfile.gear_additive_tenths` (below)
  subsumes what `VowGearScaling` would have done — one dial per role instead of a
  full `(gear_archetype × role_archetype)` matrix. The model, its migration
  (`covenants.0031_delete_vowgearscaling`), `vow_gear_scaling_bonus`, and both its
  call sites in `world.mechanics.services` (`equipment_walk_total` and
  `equipment_walk_total_unblended`) are gone.
- **`DefenseStyle`** (`TextChoices` in `world.covenants.constants`, #2533) — how a
  covenant vow defends: `GEAR_SOAK` (armor is the defense), `EVASION` (not being
  there is the defense), `BARRIER` (force/warding is the defense). Code-defined
  vocabulary (not lore-repo content) per the shared-vocabulary ruling — ADR-0149
  Layer 4's situational perks (#2536) key on these labels, and the 2026-07-20 niche
  ruling requires each style to have distinct shine-situations in that perk set
  (exact tuning numbers are secondary to that coverage).
- **`CovenantRoleDefenseProfile`** (#2533) — per-role defense tuning: `covenant_role`
  (OneToOne, CASCADE, `related_name="defense_profile"`), `style` (`DefenseStyle`),
  `gear_additive_tenths` (PositiveIntegerField, default 10 = fully additive/legacy
  behavior). One row per `CovenantRole`, including sub-roles — the model imposes no
  parent/sub-role constraint; whether a sub-role's row replaces or extends its
  anchor's is a resolution-time decision (`gear_additive_fraction`, see "Combat
  Seams" below), not a model-level restriction. Lore-repo content (`NaturalKeyMixin`
  NK `["covenant_role"]`, `covenants.covenantroledefenseprofile` in
  `CONTENT_MODELS`).
- **`CovenantRoleActionScaling`** (#2529, ADR-0149; replaced `ArchetypeActionScaling`)
  — authored config: one row per `(covenant_role, action_key)` with a
  `thread_level_multiplier` (Decimal). Natural-key content
  (`covenants.covenantroleactionscaling` in `CONTENT_MODELS`). Read by
  `covenant_role_action_scaling_bonus(character, action_key)` at the combat action
  resolution seam — sums `thread_level × multiplier` across the character's engaged
  roles that have a row for the action, normalizing engaged (possibly resolved
  sub-)roles to their anchor (parent) role before lookup, since rows and COVENANT_ROLE
  threads both key on the anchor. Rows are authored per-role now, not per-archetype:
  seed content gives Bulwark (SHIELD) an interpose row and Luminary (CROWN) a rally
  row; the Vanguard's old `cast_technique` row is not recreated — that scaling moved to
  the always-on `covenant_role_blend_power_term` power term
  (`world.magic.services.power_terms`, see `docs/systems/magic.md`).
- **`CovenantRoleTechniqueSpecialty`** (#2443, ADR-0149's 2026-07-20 amendment; **Layer 2**
  of the vow-power model) — one row per `(covenant_role, function)`, `function` drawn
  from `magic.TechniqueFunction` (a shared fine-grained vocabulary also consumed by
  Layer 4's situational perks, #2536). `multiplier_tenths` (integer-tenths, default 10 =
  ×1.0) scales the boost for that function while the role is engaged. Unlike the blend
  weights, rows are valid on **both primary roles and sub-roles** — a sub-role's rows ADD
  to the parent's rather than replacing them, so a specialized (promoted) member reads as
  strictly more specialized than an unpromoted one. Read by
  `covenant_role_specialty_power_term` (`world.magic.services.power_terms`, see
  `docs/systems/magic.md`). Lore-repo content
  (`covenants.covenantroletechniquespecialty` in `CONTENT_MODELS`).
- **`VowSituationalPerk`** (#2536, ADR-0151/ADR-0152/ADR-0153; **Layer 4** of the vow-power model
  — "the point of vows") — the authoring model for deterministic, situational bonuses:
  `covenant_role` FK (anchor OR sub-role, ADD semantics like `CovenantRoleTechniqueSpecialty`
  above — no restriction to primary-only), `name` (the announced label, e.g. "Scout's
  Instinct"), `beneficiary` (`PerkBeneficiary`: `SELF`/`COVENANT_ALLIES`/`WHOLE_GROUP` —
  group-granting perks are first-class, not an edge case), `effect_kind` (`PerkEffectKind`: all
  four values are live — `POWER_BONUS`/`CHECK_BONUS` shipped slice 1; `TIER_FLOOR`/
  `BOTCH_IMMUNITY` fire in `perform_check`'s outcome resolution as of slice 2, see "Outcome
  guarantees" below), `magnitude_tenths` (integer-tenths, `PositiveIntegerField` — no negative
  magnitudes anywhere in this table; a vow's weakness is the absence of a perk, never a malus),
  `announce_template` (player-facing line with `{holder}`/`{subject}` placeholders), an optional
  `check_type` FK (`CHECK_BONUS` scope; null = any check — `clean()` rejects a `check_type` on a
  non-`CHECK_BONUS` row), and an optional `floor_success_level` (`SmallIntegerField`, canonical
  −10..+10 `success_level` scale — `TIER_FLOOR`-only, `clean()`-required on `TIER_FLOOR` rows and
  rejected on every other `effect_kind`, ADR-0152). Natural key `(covenant_role, name)`,
  lore-repo content (`covenants.vowsituationalperk` in `CONTENT_MODELS`).
  Three scope columns narrow WHEN a fired perk applies (#2536 slice 3, ADR-0153 — Court/Battle
  scoping, distinct from a `Situation`, which asks whether the game state itself holds):
  `mission_category`/`mission_template` (FKs to `missions.MissionCategory`/`MissionTemplate`,
  `SET_NULL`, `CHECK_BONUS`-only — `clean()` rejects either on any other `effect_kind`) and
  `battle_action_kind` (`BattleActionKind` CharField, blank-default, valid on `CHECK_BONUS` **or**
  `POWER_BONUS` — `clean()` rejects it on `TIER_FLOOR`/`BOTCH_IMMUNITY`). Every non-empty scope
  column on a row must match (AND); an empty scope always matches — see `perk_scope_matches`
  below.
- **`SituationRequirementMixin`** (#2623, ADR-0154) — abstract mixin shared by
  `VowSituationalPerkSituation`/`VowSituationalPerkRung`; carries four typed, nullable/blank
  parameter columns (Situation Parameters): `threshold_percent` (0-100, percent-shaped floors —
  aura-axis floor, ally-health fraction), `count_threshold` (count-shaped floors — surrounded
  lock count, minimum affection), `affinity` (`AffinityType` axis for attacker typing),
  `origin_side` (`SituationOriginSide.OURS`/`THEIRS`, blank = side-blind). No JSON (ADR-0007) —
  every knob is a real column. Which situation reads which params — and requires which — is
  `SITUATION_PARAM_SPECS` (`perks/constants.py`); the mixin's `clean()` enforces both directions
  (an authored param the situation doesn't read is rejected; a required param missing is
  rejected), mirroring the per-effect-kind gating on `VowSituationalPerk.clean()`. All-null/blank
  rows behave byte-identically to pre-#2623 (the old module-constant defaults) — parameterless
  rows are the parameterless default of a parameterized family, not a breaking change. `.params`
  builds the frozen, hashable `SituationParams` dataclass (`perks/context.py`) an evaluator reads.
- **`VowSituationalPerkSituation`** — `(perk FK, situation choice)` join plus the mixin's four
  param columns; every attached situation must hold (AND composition). `situation` is drawn from
  `world.covenants.perks.constants.Situation`, a code-defined library (see
  `world.covenants.perks`'s module docs below) — attaching situations to a perk (and tuning their
  params) is a content edit; adding a NEW situation to the library is a code change (one
  evaluator + one enum value + a `SITUATION_PARAM_SPECS` entry). Natural key `(perk, situation)`
  (unchanged by #2623 — one row per situation per perk; multi-row same-situation composition is
  out of scope), content.
- **`VowSituationalPerkRung`** — `(perk FK, rung_number, extra_situation, magnitude_tenths)` plus
  the mixin's four param columns — escalation tiers on top of a perk's base situations (e.g. a
  "Last Bulwark" perk that intensifies further when allies are hurt, further still against
  Primal attackers). A rung can re-require its `extra_situation` at a TIGHTER parameter than the
  base row (#2623) — e.g. base `ALLY_LOW_HEALTH` at the module default (50%), rung 1 at
  `threshold_percent=25`. Resolution is strictly cumulative: rung N's required
  `(situation, params)` pairs = the perk's base pairs ∪ the extra pairs of rungs 1..N, so a
  higher rung can never fire without every lower rung's condition also holding; the highest
  qualifying rung's magnitude REPLACES the base (never sums with it). `clean()` enforces
  `rung_number >= 1`; contiguity is not enforced (resolution handles gaps). Natural key
  `(perk, rung_number)`, content.

**`world.covenants.perks`** (the logic modules — models above live in `covenants.models`,
migration graph, per the "no new app" ruling; import direction still honors ADR-0010, perk
modules import combat/checks contexts at function level, never the reverse):

- **`constants.py`** — `Situation`/`PerkEffectKind`/`PerkBeneficiary`/`SituationOriginSide`
  `TextChoices`, plus the `SituationParamSpec`/`SITUATION_PARAM_SPECS` contract (#2623,
  ADR-0154). `Situation` still ships 14 values as of slice 3 (#2536, ADR-0153): slice 1's 9 plus
  `CHAMPION_DUEL` (Battle wiring, Task 3), `COMBAT_OPENED_FROM_PARLEY`/`AMBUSH_UNDERWAY`
  (origin-marker addition, Task 4), `ALLY_INTERCEPTED_FOR_ME` (declared-guard, Task 5), and
  `ATTACKER_AFFINITY` (defense-side seam, Task 6; originally Abyssal-only, renamed and
  parameterized to all three `AffinityType` axes by #2623, ADR-0154) — see each value's own docstring entry for its
  evaluator's data source, its Situation Parameters, and any v1 approximation.
  `SITUATION_PARAM_SPECS` (#2623) names, per situation, which of the four `SituationRequirementMixin`
  columns are ALLOWED and which are REQUIRED — `ATTACKER_AFFINITY` requires `affinity`;
  `ALLY_LOW_HEALTH`/`SURROUNDED`/`TARGET_FAVORABLY_DISPOSED` allow (but don't require) their
  threshold; `AMBUSH_UNDERWAY`/`COMBAT_OPENED_FROM_PARLEY` allow `origin_side`; every other
  situation allows none (an authored param on one of those rejects at `clean()`).
- **`context.py`** — `SituationContext` (frozen dataclass: four required fields — `holder`,
  `subject`, `target`, `resolution` — plus three optional slice-3 fields (ADR-0153), all
  defaulting to `None`/byte-identical to pre-slice-3 behavior when unset: `mission` (the live
  `MissionInstance` for a mission-driven check, Court scoping), `battle_action_kind` (the
  declared `BattleActionKind` for a warfare roll, Battle scoping), and `attacker` (the attacking
  entity — a `CombatOpponent` or ObjectDB-backed attacker — populated ONLY on a defense-side
  resolution; `None` on every offense-side one, the defense-side seam). See the class docstring
  for the full field contract and the missing-field-returns-False convention.
- **`evaluators.py`** — `SITUATION_EVALUATORS` registry (`register(situation)` decorator,
  mirrors `magic.services.power_terms`'s `_PROVIDERS` registry pattern) + one evaluator per
  `Situation` value (14 as of slice 3). Every evaluator is a pure read (one query or a
  cached-handler read, never a write, never a query per situation-per-perk).
- **`services.py`** — `applicable_perks(subject, *, effect_kind, resolution, target, attacker=None)
  -> list[FiredPerk]`, the beneficiary evaluation point every delivery seam calls (see the
  module's own extensive docstring for the exact candidate-set rules, the two-different-answers
  "covenant-mate" split, and the tested query ceiling). `effect_kind` accepts a single kind or a
  `tuple[str, ...]` (slice 2) — a tuple fetches every listed kind in one call, same fixed query
  ceiling either way; the outcome-guarantee seam below uses this to fetch `TIER_FLOOR` +
  `BOTCH_IMMUNITY` together. `attacker` (slice 3, ADR-0153) threads the defense-side attacking
  entity into every candidate holder's `SituationContext`, defaulting to `None` for every
  offense-side caller. `perk_scope_matches(perk, ctx, *, mission_category_ids=None) -> bool`
  (slice 3) — every non-empty scope column on `perk` must match `ctx` (AND); shared by both
  fired-perk providers below. `mission_category_ids_for(ctx)` hoists the mission's authored
  category-id set ONCE per resolution (a review fix — the naive per-perk-call form issued one
  categories query per fired perk); callers checking more than one mission-scoped perk against
  the same `ctx` MUST call this first and pass the result through `perk_scope_matches`'s
  `mission_category_ids` kwarg. `announce_fired_perks(fired, *, subject, location)`, the
  dual-dispatch presentation-contract seam (see "Presentation contract" below).
  `dormant_perk_firings(subject, *, effect_kind, resolution, target, mission=None,
  battle_action_kind=None, attacker=None) -> list[FiredPerk]` / `announce_dormant_perks(dormant,
  *, subject)` (slice 3, Task 7, ruling 2) — see "Dormant-vow messaging" below.

**Delivery seams:** `POWER_BONUS` (slice 1) rides a conditional power-term provider
(`vow_situational_power_term`, `world.magic.services.power_terms` — see `docs/systems/magic.md`);
`CHECK_BONUS` (slice 1) rides `perform_check`'s optional `situation_ctx` parameter
(`world.checks.services._situational_perk_check_bonus`, scoped by `perk.check_type`, null = any
check). Both scale a fired perk's `magnitude_tenths` by
`total_thread_level_across_all_kinds(sheet)`, the same thread-level axis Layers 1-2 use, and
truncate the same way (`Decimal` sum, `int()` truncation). As of slice 3 (ADR-0153), both also
filter their fired set through `perk_scope_matches` before scaling — a `mission_category`/
`mission_template`/`battle_action_kind` scope column that doesn't match `situation_ctx` drops the
firing even though its `Situation`s all held.

**Court/Battle scoping + defense-side seam (slice 3, ADR-0153):** `situation_ctx` now reaches
mission checks — all six mission `perform_check` call sites thread
`world.missions.services._situation.mission_situation_ctx(character, instance)`
(`SituationContext(mission=instance, ...)`, `None` when the character has no `CharacterSheet`) —
and Battle warfare rolls — `BattleTechniqueResolver.__call__`/`resolve_battle_technique`
(`world.battles.resolution`) thread `_battle_situation_ctx(character, declaration.action_kind)`
(`SituationContext(battle_action_kind=..., ...)`) into `perform_check`/`use_technique`. On the
defense side, `world.combat.services.resolve_npc_attack` threads a `SituationContext(attacker=
opponent_action.opponent, resolution=CombatRoundContext(participant), ...)` into the defender's
real `perform_check` — the only defense-check site doing so in v1, making CHECK_BONUS/
TIER_FLOOR/BOTCH_IMMUNITY perks (including `ATTACKER_AFFINITY`-gated ones) live on defense rolls
for the first time. See ADR-0153 for why each of these is a `SituationContext` field/threading
addition rather than a parallel pipeline.

**Outcome guarantees (slice 2, ADR-0152):** `TIER_FLOOR`/`BOTCH_IMMUNITY` also ride
`perform_check`, but AFTER the outcome is determined (rolled or test-rig forced), via
`world.checks.services._apply_outcome_guarantees`. Both are ABSOLUTE — no thread-level scaling,
no thread-level gate (ungated ruling, 2026-07-20) — unlike `POWER_BONUS`/`CHECK_BONUS` above.
`TIER_FLOOR` guarantees `success_level >= perk.floor_success_level`; `BOTCH_IMMUNITY` binds only
when the raw outcome is a botch (`success_level <= world.checks.constants
.BOTCH_SUCCESS_LEVEL_MAX`, the centralized botch-boundary constant) and floors it at the
least-bad non-botch level. Both fetch through `applicable_perks(effect_kind=(TIER_FLOOR,
BOTCH_IMMUNITY), ...)` — one call, the tuple form above; slice 3 threads `attacker=situation_ctx
.attacker` through this call too, so a defense-side guarantee can key on `ATTACKER_AFFINITY`. The
replacement outcome is the current `ResultChart`'s lowest outcome at/above the effective floor,
falling back to the global `CheckOutcome` table when the chart has no row there, or a no-op when
no such outcome is authored anywhere (never invents rows). `announce_fired_perks` fires only for
the binding perk(s), only when the outcome actually changed — a guarantee that was eligible but
never bound stays silent (no announce-on-fire spam).

**Dormant-vow messaging (slice 3, Task 7, ruling 2, ADR-0153) — the "loud OFF state":** a
disengaged vow says so out loud, at the exact moment it would have answered, instead of silently
doing nothing. `dormant_perk_firings` enumerates the subject's own active-but-DISENGAGED
memberships (`_dormant_self_candidates`, the inverted mirror of `_self_candidates` — never a
co-present mate's disengagement, only the subject's own), runs the same `_PerkResolver`
situation evaluation as the live path plus the slice-3 scope filter, and returns the set that
WOULD have fired if the vow were engaged. `announce_dormant_perks` delivers the exact line
`"your vow lies dormant — {perk.name} would have answered here"` to the HOLDER ALONE — a
narrator-authored WHISPER-mode `Interaction` (receiver-scoped to the subject's primary persona,
sent directly to `subject.character` rather than resolved via `push_interaction`'s
writer-location lookup — the narrator persona's own location is unrelated) plus a direct
`subject.character.msg(text)` telnet companion — NEVER the room, deliberately unlike
`announce_fired_perks`'s room broadcast for live firings (see ADR-0153 for why). Wired into all
three fired-perk seams (`_situational_perk_check_bonus`, `_apply_outcome_guarantees`,
`vow_situational_power_term`), each making one dormant pass right after its own live
`applicable_perks` call — including the wholly-disengaged case where the existing "no engaged
role" cheap-exit guard would otherwise skip announcing entirely. For outcome guarantees, a
dormant `TIER_FLOOR`/`BOTCH_IMMUNITY` perk announces ONLY when it WOULD have bound against the
RAW outcome (its floor exceeds the raw `success_level`) — never merely because a disengaged
guarantee perk exists. Zero extra queries when the subject has no disengaged active membership
(reads the same cached `character.covenant_roles.active_memberships` list the live path's call,
made immediately before, has already warmed).

**Presentation contract (ruling 1, HARD):** a firing perk must be a loud, visible moment in BOTH
clients. `announce_fired_perks` dual-dispatches per firing — a persisted, Narrator-authored
`OUTCOME` `Interaction` broadcast over the WS interaction payload (the same machinery
`combat.interaction_services.broadcast_action_outcome` uses, including its `scene=` link —
resolved via `get_active_scene(location)` — so a perk announce appears in scene-log replay like
the precedent it's modeled on) PLUS a direct `location.msg_contents(text)` text companion so bare
telnet renders the identical line. `broadcast_action_outcome` alone is WS-only and was verified
insufficient for this path — see ADR-0151 for why it isn't reused as-is. The telnet companion
calls `location.msg_contents` directly rather than `flows.service_functions.communication
.message_location` — `message_location` resolves its broadcast room from its caller's own
location, not from an explicit `location` argument, and this function has no single acting
character reliably co-located with the room a perk fires in (a group-beneficiary firing may name
a `holder` elsewhere); `location` itself is the one value guaranteed correct (see the function's
own docstring; a review cycle initially shipped this seam building a caller state from the
Narrator's own persona, whose location is unrelated to `location` and broke telnet delivery
silently — never repeat that shape). Each rendered line is `"{perk.name}: {announce_template
rendered with holder/subject}"`. Called from inside each delivery provider (never from
`applicable_perks` itself) exactly once per real resolution — see ADR-0151's "call-site
discipline" section for the no-double-announce proof.

- **`CovenantRoleGiftGrant`** (#2022) — through model for
  `CovenantRole.granted_gifts` M2M to `magic.Gift`. Carries
  `unlock_thread_level` — the COVENANT_ROLE thread level at which the gift's
  techniques become available while engaged (0 = always while engaged).
- **`CovenantRole.granted_capabilities`** (#2022) — M2M to
  `conditions.CapabilityType`. Read directly by `passive_capability_grants()`
  in `handlers.py` alongside the existing `ThreadPullEffect`-based capability
  grants. Capabilities apply while the role is engaged; drop automatically when
  the vow dims.
- **`CovenantRank`** — per-covenant administrative authority tier. Fields: `covenant`
  FK (CASCADE, `related_name="ranks"`), `name` (max 60, player-chosen), `tier`
  (PositiveInt; 1 = top authority), `description`, `can_invite` bool, `can_kick` bool,
  `can_manage_ranks` bool, `can_lead_rituals` bool (may lead this covenant's group
  rituals), `can_request_gm` bool (#2119 — may post an open `GroupStoryRequest` ask
  for a GM; deliberately separate from `can_invite`, see stories.md's "Player→GM
  recruitment loop"). Unique `(covenant, tier)` and `(covenant, name)`. Ordered by
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
    `seed_mentor_bond_defaults()` in factories.py, called from
    `wire_covenant_lifecycle_rituals()` (`world.magic.factories`, #2114) as part of
    `seed_magic_dev()` — reachable in a real deploy, not only under test setup.
    Staff-tunable in Django admin (re-running the seed resets to authored defaults).

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
  inactive only if `MentorBondConfig` has never been seeded at all (e.g. a DB that
  predates #2114 and hasn't re-run `seed_magic_dev()`) — a fresh deploy always seeds it.

### Mentor's Vow ritual service

- **`establish_mentor_bond_via_session(*, session: RitualSession) -> MentorBond`** —
  the service function wired to `MentorsVowRitualFactory` (in `world.magic.factories`).
  The ritual is a consensual BILATERAL_SERVICE ritual; the session's leader and
  co-performer are the two bond parties. Unpacks the session, identifies which
  participant is mentor vs. sidekick based on band position, and calls
  `establish_mentor_bond`.

### The Sphinx of Black Quartz — vow-suitability oracle (#2640, ADR-0157)

`src/world/covenants/sphinx.py` — a read-only report re-running the same kit∩demand join
`covenant_role_specialty_power_term` uses, but as a verdict instead of a resolution-time
bonus. No writes anywhere; never gates anything (soft-gate ruling — a player may swear a
vow the Sphinx warned about).

- **`judge_vow(sheet, role) -> SphinxVerdict`** — one character × one role.
  - Demand = `role`'s (+ `role.parent_role`'s, when judging a sub-role) `CovenantRoleTechniqueSpecialty`
    functions, UNION the creator-functions demanded by `situation`s attached to `role`'s
    (+ parent's) **SELF**-beneficiary `VowSituationalPerk` rows (base `situations` + rung
    `extra_situation`s) that appear in `SITUATION_CREATOR_FUNCTIONS`.
  - Supply = the sheet's known-technique function tags (`CharacterTechnique` →
    `Technique.cached_function_tags`, one prefetch, no N+1).
  - **`SphinxTier`** (`world.covenants.constants`) — `TAKES` (every demand covered, or the
    role is unauthored and makes no demands — an unauthored vow cannot reject), `DORMANT`
    (≥1 covered, ≥1 not — "the vow would lie dormant in places"), `NOT_YET` (0 covered —
    paired with a shopping list).
  - `SphinxVerdict.shopping_list` — up to 3 learnable `Technique` rows per uncovered
    function (`can_learn_technique` passes, or the technique is in the sheet's active
    tradition's `TraditionGiftGrant.signature_techniques` pool), excluding techniques
    already known.
- **`SITUATION_CREATOR_FUNCTIONS: dict[str, frozenset[str]]`** (`world.covenants.perks.constants`)
  — code-defined: which `TechniqueFunction` casts can CREATE each DB-state `Situation` (the
  `TARGET_DISTRACTED`/`TARGET_SWAYED_BY_ALLY` provenance mapping run in reverse). v1 rows:
  `TARGET_SWAYED_BY_ALLY`/`TARGET_DISTRACTED` → `{CHARM, DISTRACTION}`,
  `TARGET_FAVORABLY_DISPOSED` → `{CHARM}`. A situation absent here demands nothing (positional/
  encounter states). Extending it is a deliberate one-line change.
- **`audit_vow_coverage() -> list[SphinxCoverageRow]`** — the staff instrument (build-order
  FIRST per the spec): every active anchor `CovenantRole` (`parent_role IS NULL`) × every
  active `Tradition`, comparing the role's specialty-function demand set (situation demands
  excluded — they read live per-character DB state, not a catalog's technique pool) against
  the union of function tags over the tradition's `TraditionGiftGrant.signature_techniques`.
  `coverage` is `"full"`/`"partial"`/`"none"`. Rendered at `_sphinx/` (`admin_sphinx_audit`,
  staff-only, linked from the Game Setup hub) via `templates/admin/sphinx_audit.html`.

## Telnet Surface

### CmdCovenant (`covenant`, #1346)

`src/commands/covenant.py` — one `ArxCommand` routes a leading subverb to the matching
covenant Action via `action.run()`, sharing the same service layer as the web viewsets.

| Subverb | Action key | Effect |
|---|---|---|
| `covenant [list]` | — | List the caller's memberships (hub) |
| `covenant engage [<covenant>]` | `engage_covenant_membership` | Engage a role for the current scene |
| `covenant disengage [<covenant>]` | `disengage_covenant_membership` | Disengage a role |
| `covenant leave [<covenant>]` | `leave_covenant` | Voluntarily end membership |
| `covenant kick <char> [in <covenant>]` | `kick_covenant_member` | Rank-gated removal |
| `covenant rank <char> <rank> [in <covenant>]` | `assign_covenant_rank` | Promote/demote a member |
| `covenant transfer <char> [in <covenant>]` | `transfer_covenant_top_rank` | Transfer the top rank |
| `covenant standdown [<covenant>]` | `stand_down_battle_covenant` | Return a risen STANDING Battle covenant to dormancy |

Supply the covenant name when the character belongs to more than one. `standdown` is STANDING
Battle covenants only; `engage`/`disengage` are gated by the same `can_engage_membership` logic
the web uses. `CovenantError` subclasses surface as `ActionResult(success=False)` with a
`user_message`.

### Induction and Banner-Call Rise via CmdRitual

Covenant **induction** (adding a new member) and the **banner-call rise** (raising a dormant
STANDING Battle covenant) are session-driven ceremonies that go through `CmdRitual` with
adapter-dispatched token parsing (`src/commands/ritual_adapters.py`):

**Induction:**
1. Initiator: `ritual draft "Covenant Induction" invite=<char> covenant=<name>` — drafts a
   session; the `CovenantInductionAdapter` emits a session-level COVENANT reference.
2. Inductee: `ritual join <id> role=<covenant role name>` — the adapter emits a COVENANT_ROLE
   reference the induction service reads to assign the role.
3. Initiator: `ritual fire <id>` — calls `induct_member_via_session`, which creates the
   `CharacterCovenantRole` row.

**Banner-call rise:**
1. Initiator: `ritual draft "Call the Banners" invite=<char>[,<char>] covenant=<name>` —
   `BannerCallAdapter` emits a session-level COVENANT reference; no join tokens are required.
2. Members: `ritual join <id>` — simply accept (no role kwargs needed).
3. Initiator: `ritual fire <id>` — calls `rise_battle_covenant_via_session`, which flips the
   covenant risen and auto-engages all accepted participants.

### CmdSphinx (`sphinx`, #2640)

`src/commands/sphinx.py` — `sphinx <vow name>` renders the same three-tier verdict as the
REST endpoint (both call `judge_vow` directly; no parallel logic). v1: invocable anywhere
(Academy-room anchoring is presentation/content, not mechanics). Output prose: "The vow
will take." / "The vow would lie dormant in places: ..." / "The vow will not take — yet.
Seek: ...".

### Selectors (`world.covenants.selectors`)

`src/world/covenants/selectors.py` — shared read-only lookups used by the covenant viewsets
and the Actions (one copy, not two):

- `resolve_actor_membership(*, covenant, character_sheets, capability=None) -> CharacterCovenantRole | None`
  — first active membership in `covenant` among `character_sheets` that carries `capability`
  (a rank flag such as `can_kick` or `can_manage_ranks`), or any active membership if `None`.
- `get_active_memberships(*, character_sheet) -> list[CharacterCovenantRole]`
  — all active (`left_at IS NULL`) memberships for one character sheet, with related covenant,
  rank, and covenant_role pre-fetched.

## Induction Round-Trip

The covenant induction flow is wired end-to-end through the UI:

1. **Draft** — initiator opens `RitualSessionDraftDialog`; the COVENANT reference is
   set so `assert_initiator_can_induct` can validate the initiator's rank at draft time.
2. **Candidate accepts with role** — `RitualSessionResponseDialog` renders the
   `candidate_only` `CovenantRolePickerField` (from `input_schema.participant_fields`),
   resolves the COVENANT reference from `session.session_references` to populate the
   role picker's `covenant_type` filter, and converts the `emits_reference: "COVENANT_ROLE"`
   field value into a typed `RitualSessionReference` in the accept request's `references`
   array.
3. **Initiator fires** — `POST /api/magic/ritual-sessions/{id}/fire/` dispatches the
   induction service function, which reads the COVENANT_ROLE reference and calls
   `assign_covenant_role` to create the `CharacterCovenantRole` row.

**Test coverage:** `RitualInductionRoundTripTests`
(`src/world/magic/tests/test_session_views.py`) covers the full draft → accept-with-role
→ fire → `CharacterCovenantRole` created backend path. Frontend component tests in
`frontend/src/rituals/__tests__/RitualSessionPages.test.tsx` cover the role-picker
rendering, `emits_reference` → `references` conversion on accept, and `candidate_only`
field hiding for the initiator.

## Covenant of the Court (#1589)

A `CovenantType.COURT` covenant models a single powerful master and the servants/apprentices sworn
to them across a ≥1-tier power gulf. See ADR-0057 (amended 2026-06-30) for the design rationale.

### Model additions

- **`Covenant.leader`** — FK → `character_sheets.CharacterSheet` (`null=True`,
  `on_delete=SET_NULL`, `related_name="led_courts"`). Required for COURT, forbidden for other
  types (enforced in `Covenant.clean()`). The structural analogue of `campaign_story` on Battle
  covenants. An NPC master is an account-less `CharacterSheet` seated as the `is_leader` founder.

- **`CourtPact`** — per-(Court, servant) sworn-fealty bond.
  - `covenant` FK (PROTECT, `related_name="court_pacts"`)
  - `servant_sheet` FK → `CharacterSheet` (PROTECT, `related_name="court_pacts"`)
  - `granted_pull_cap` (PositiveSmallIntegerField) — master-set ceiling on the servant's
    Court-role thread pull level. A servant with no active pact has an effective cap of 0 and
    cannot pull their Court-role thread.
  - `sworn_at` (auto DateTimeField), `released_at` (null = still active)
  - Partial-unique constraint `uniq_court_pact_active`: at most one active pact per
    `(covenant, servant_sheet)`. Released pacts are retained as an audit trail.
  - Custom queryset: `.active()` → `released_at__isnull=True`.

### Services (`world.covenants.services`)

- **`swear_court_pact(*, covenant, servant_sheet, granted_pull_cap) -> CourtPact`** — creates an
  active pact. Raises `CourtPactExistsError` if an active pact already exists for the pair.
- **`release_court_pact(*, pact) -> None`** — soft-releases by setting `released_at = now()`.
- **`active_court_pact_for(*, covenant, servant_sheet) -> CourtPact | None`** — returns the single
  active pact or `None`.

### Gulf enforcement (`world.covenants.mentorship`)

`assert_membership_level_allowed` (COURT arm) enforces the ≥1 power-tier gulf before a servant
may join. Uses `power_tier_for_level(level) -> int` (`world/covenants/power_tier.py`): levels
1–5 → tier 1, 6–10 → tier 2, 11–15 → tier 3, etc. (band width = `TIER_ONE_MAX_LEVEL` = 5).
Raises `CourtGulfViolationError` if `power_tier_for_level(servant) >= power_tier_for_level(leader)`.
This check runs before the `MentorBondConfig` gate so it fires even without a seeded config.

### Mission-driven engagement (`world.covenants.court_missions`)

`has_active_court_mission(*, character_sheet, covenant) -> bool` — single `.exists()` query;
True iff the character participates in an ACTIVE `MissionInstance` whose
`source_offer.role.faction_affiliation_id` matches `covenant.organization_id`. A `NULL`
`source_offer` (legacy/staff-seeded runs) never matches — correct behavior.

`can_engage_membership` (COURT branch in `world/covenants/handlers.py`) gates engagement on this
predicate. `_auto_engage_court` in `services.py` auto-engages newly inducted Court servants when
the predicate is satisfied. Battle covenants use `not is_dormant` as their gate; the Court
mission-gate is new dedicated machinery.

### Continuous vow enforcement (#2051)

`revalidate_engagements(*, character_sheet, room)` in `services.py` re-runs
`can_engage_membership` for each engaged `CharacterCovenantRole`. On failure,
`clear_engaged_membership` dims the vow (max health recompute + cache flush) and
emits a notice: "Your vow dims — the covenant is not with you." COURT vows
re-validate by their own arm (master's business stays lit); BATTLE re-checks
dormancy only.

Wired into two departure seams:
- **`move_object`** (`flows/service_functions/movement.py`): captures the origin
  room before the move, then revalidates the mover at the destination AND each
  remaining origin-room occupant with an engaged covenant role (hot-path
  short-circuit: skips occupants with no engaged role — no DB query).
- **`finish_scene_full`** (`scenes/scene_admin_services.py`): invalidates the
  room's active-scene cache (the scene is no longer active) and revalidates
  remaining occupants — Durance vows dim when the scene they were tied to ends.

Auto-engage on next qualifying arrival already exists, so power relights the
moment the covenant reunites.

### Pull-cap enforcement (`world.magic.services.threads`)

`compute_anchor_cap` delegates to `_bound_covenant_role_cap_by_court_grant` for
`TargetKind.COVENANT_ROLE` threads on COURT covenants. This bounds the anchor cap by the
servant's `granted_pull_cap` from the active `CourtPact`. No pact → cap 0 → the grant is the gate.

### Grant negotiation (#1718)

`granted_pull_cap` is no longer fixed at swearing-in. Two channels raise it:

- **Formal petition** — a new `OfferKind.COURT_GRANT` offer (auto-provisioned per
  Court via `world.covenants.court_grant.ensure_court_grant_role`, which is
  `@transaction.atomic` with a `select_for_update()` re-fetch of the `Covenant`
  row so two concurrent negotiation attempts for the same Court can't both pass
  the "role not yet provisioned" check), riding the existing
  `NPCServiceOffer`/effect-handler pipeline. The effect handler
  (`world.npc_services.effects.raise_court_grant`) rolls a shared "Court Grant
  Petition" check (eased by the master's `NPCStanding.affection`) and, on
  success, raises the grant up to `court_grant_ceiling(...)` via
  `raise_court_pact_grant`, which is strictly monotonic
  (`CourtGrantNotMonotonicError` on any attempted decrease; raising to the
  current cap is a harmless no-op).
- **Emergency thread-bond draw** — not a standalone Action. It's an optional
  `beseech=<n>` token on the existing `cast`/`clash` pull-declaration grammar
  (`commands/combat.py`), resolved by the shared, combat-agnostic
  `_resolve_emergency_draw(sheet, cast_pull)` helper
  (`world.combat.pull_helpers`). That helper is called from both the in-combat
  path (`commit_combat_pull`) and the non-combat immediate-cast path
  (`world.magic.services.techniques._charge_cast_pull`), so the draw works
  whether or not the master is in the scene. **Web (non-telnet) support does
  not exist** — `world/scenes/action_serializers.py::_validate_cast_pull` →
  `world.combat.pull_helpers.build_cast_pull_declaration` has no
  `beseech_bonus` parameter; only the telnet grammar parses `beseech=`.
  The requested bonus is clamped to `min(requested_bonus,
  court_grant_ceiling(...) + CourtGrantConfig.emergency_draw_max_bonus)` — the
  config field bounds how far the draw may exceed the ceiling, not the raw
  bonus — for one pull only, never persisted to `Thread.level`, at the cost of
  debt on any amount past the ceiling.

`court_grant_ceiling(*, covenant, servant_sheet) -> int`
(`world.covenants.court_grant`) = `base_headroom + affection // affection_divisor
+ completed_court_mission_count // mission_divisor - outstanding_debt(...)`,
floored at 0, all tunable via the `CourtGrantConfig` singleton
(`get_court_grant_config()`).

Debt and the consecutive-failed-petition streak generalize onto `NPCStanding`
(`world.npc_services`), not `CourtPact` — `NPCStanding.debt` /
`debt_baseline_affection` / `debt_baseline_missions_completed` /
`consecutive_failed_petitions`, plus the generic services
`incur_npc_debt`/`outstanding_debt`/`record_petition_outcome`
(`world.npc_services.services`) — so any future "petition an NPC" feature can
reuse the same substrate. `consecutive_failed_petitions` crossing
`CourtGrantConfig.petition_failure_escalation_threshold` fires
`CourtGrantConfig.escalation_consequence_pool` (a standard `ConsequencePool`,
same machinery as trap/clash/stakes resolution).

Pull-effect scaling by thread level (`thread_level_multiplier`,
`world.magic.services.threads`) was corrected alongside this feature: level 0
keeps the old floor of `Decimal(1)`; levels 1–9 now ramp linearly from 0.1 to
1.0 (`Decimal(level) / Decimal(10)`) instead of sitting flat at the old
floor — levels 1–9 score *below* the old flat-1.0 floor, a deliberate
tradeoff so a thread crossing the level-10 milestone doesn't score worse than
level 9 did; level ≥ 10 is unchanged (`Decimal(level // 10)`).

See ADR-0085 for why the debt/streak fields live on `NPCStanding` rather than `CourtPact`.

### Directed-offer summonses — the master's wishes (#2050)

A Court master (or any NPC role) can direct a mission offer at a *specific*
servant via an `OfferSummons` (`world.npc_services.summons`). The servant sees
the summons in their journal and can accept (delegating to `resolve_offer` →
`issue_mission`, with court engagement + grant-ceiling credit flowing as today)
or decline. Declining — or letting the summons lapse — drops affection
(`SUMMONS_REFUSAL_AFFECTION_DELTA`) and bumps
`NPCStanding.consecutive_refused_summons`; crossing
`CourtGrantConfig.summons_refusal_escalation_threshold` fires the master's
escalation pool via `apply_pool_deterministically` (the no-check precedent).
Debt is never the price of disobedience — ADR-0102.

Creation is GM/staff-driven (web API + mid-scene "Give mission" dialog). The
expiry cron (`npc_services.summons_expiry`, 5-minute sweep) treats timeout as a
refusal. See ADR-0102 for the full design.

### Fealty ceremony

`induct_member_via_session` (the ritual fire-handler) was extended for COURT covenants: after
creating the `CharacterCovenantRole`, it calls `swear_court_pact` with `granted_pull_cap` read
from `participant_kwargs` and emits a servant-spotlight narration alongside the induction message.

### Exceptions (added in `world.covenants.exceptions`)

- `CourtGulfViolationError` — servant's power tier is not strictly below the leader's.
- `CourtPactExistsError` — an active pact already exists for `(covenant, servant_sheet)`.
- `CourtGrantNotMonotonicError` — a grant raise would lower an existing `CourtPact.granted_pull_cap` (#1718).

### Test coverage

`src/world/covenants/tests/integration/test_court_e2e.py` — full E2E journey: create Court,
induct servant (gulf enforced), swear pact, mission-driven engage, pull-cap bounded, dissolve
(last servant leaves → Court auto-dissolves).

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

### Defense styles + gear substitution (#2533, ADR-0149 Layer 3)

`gear_additive_fraction(character)` (`world.covenants.services`) returns the MAX
`gear_additive_tenths` fraction (as `Decimal`, e.g. `Decimal("0.3")`) across the
character's engaged roles' resolved `CovenantRoleDefenseProfile` rows. Per engaged
role, the profile resolves to the role's own row when present, else its anchor's;
no engaged role has a profile at all → `Decimal(1)` (legacy fully-additive
behavior, byte-identical to pre-#2533). One batched query over the role + parent
pks — no per-role query loop.

`apply_equipped_armor_soak` (`world.combat.services`, #1174) applies the fraction
to the COMPATIBLE armor bucket only, once, right after the role-compatibility
split and before the compatible-additive/incompatible-max blend:

    compat_soak = int(compat_soak * gear_additive_fraction(character))
    soak = compat_soak + max(incompat_physical, resonant)

The resonant pool and the incompatible-`max` branch are untouched — gear is
physical and counts once; a character holding multiple engaged vows gets the most
gear-friendly one's fraction, not a stack of fractions. Durability still wears on
every compatible piece whose (now-scaled) soak contributes to the result,
unchanged from #1174.

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

  Both `covenant_role` and `anchor_role` nest `technique_specialties` (#2443, Layer 2) —
  the role's `CovenantRoleTechniqueSpecialty` rows, prefetched via
  `Prefetch(..., to_attr="cached_technique_specialties")` on the ViewSet queryset. The
  frontend's `specialtySummaryForMembership` (`CovenantDetailPage.tsx`) unions both,
  with the resolved (`covenant_role`) row winning on a same-function collision.
- `GET|POST /api/covenants/ranks/` — list / create ranks
- `GET|PATCH|DELETE /api/covenants/ranks/{pk}/` — retrieve / update / delete
- `POST /api/covenants/ranks/reorder/` — bulk tier reorder
- `POST /api/covenants/ranks/{pk}/assign-member/` — assign member to rank
- `POST /api/covenants/ranks/{pk}/transfer-top/` — move top rank to member
- `GET /api/covenants/roles/sphinx/?role=<id-or-slug>` (#2640) — the Sphinx of Black
  Quartz's verdict (`SphinxVerdictSerializer`) for the requesting account's own active
  character against `role`. Self-character only; read-only; never gates.

## Follow-ups

- **Health scaling (#1256)** — `max_health` is not currently level-derived (it is
  `base_max_health + thread_addend`); Path-level-driven health is deferred to #1256.
- **Abyssal master/apprentice display labels** — the Mentor's Vow mechanic is flavor-neutral
  in the model layer. Thematic display labels (e.g. "Abyssal master/apprentice") are a
  future display-label layer with no model surface in v1.
- **Graduation auto-dissolve** — `begin_declaration_phase` dissolves graduated bonds;
  a separate async/background path for non-combat graduation is a follow-up.
- **Court deferred items** — the convince-the-master economy, enemy-of-master substrate,
  per-instance authored roles, and active capability surge were deliberately NOT built in #1589;
  they are follow-up design items.
- **Vow power, four-layer model (ADR-0149)** — #2529 shipped Layer 1 (the SWORD/SHIELD/
  CROWN blend + always-on baseline power term); #2443 shipped **Layer 2**
  (`CovenantRoleTechniqueSpecialty` + `covenant_role_specialty_power_term`, keyed on
  the shared `magic.TechniqueFunction` vocabulary — see ADR-0149's 2026-07-20 amendment
  and `docs/systems/magic.md`); #2533 shipped **Layer 3** (`DefenseStyle` vocabulary +
  per-role `CovenantRoleDefenseProfile`, the `gear_additive_fraction` substitution rule
  at the armor-soak seam, and `VowGearScaling`'s removal — see "Combat Seams" above); and
  #2536 slice 1 (ADR-0151) shipped the **Layer 4** machinery — the situation library +
  registry, `VowSituationalPerk` authoring models, `POWER_BONUS`/`CHECK_BONUS` delivery, and
  the dual-dispatch presentation contract (see "Layer 4: Situational Perks" above), whose
  first perk set must give every `DefenseStyle` a distinct shine-situation (2026-07-20 niche
  ruling); #2536 slice 2 (ADR-0152) shipped the **outcome-guarantee** resolution —
  `floor_success_level` on `VowSituationalPerk`, the centralized `BOTCH_SUCCESS_LEVEL_MAX`
  constant, multi-kind `applicable_perks`, and `TIER_FLOOR`/`BOTCH_IMMUNITY` wired into
  `perform_check` (see "Outcome guarantees" above) — plus the covenant-mate reversal (ally
  group-perks now scope on membership + co-presence, not the mate's own `engaged` flag);
  #2536 slice 3 (ADR-0153) shipped the final **Layer 4** wave — three scope columns
  (`mission_category`/`mission_template`/`battle_action_kind`) + `perk_scope_matches`, Court
  (all six mission check sites) and Battle (warfare-roll) `situation_ctx` threading, five new
  `Situation` values (`CHAMPION_DUEL`, `COMBAT_OPENED_FROM_PARLEY`, `AMBUSH_UNDERWAY`,
  `ALLY_INTERCEPTED_FOR_ME`, `ATTACKER_AFFINITY`), the defense-side seam
  (`SituationContext.attacker` + `resolve_npc_attack` threading), and dormant-vow messaging
  (the "loud OFF state", ruling 2) — see "Court/Battle scoping + defense-side seam" and
  "Dormant-vow messaging" above. **Layer 4 is complete; #2536 is closed.** #2623 (ADR-0154)
  followed up with parameterized situation requirements: `SituationRequirementMixin`'s four
  typed columns (`threshold_percent`/`count_threshold`/`affinity`/`origin_side`) on both
  `VowSituationalPerkSituation` and `VowSituationalPerkRung`, the `SITUATION_PARAM_SPECS`
  per-situation allowed/required contract, the Abyssal-only attacker-typing situation's rename
  to `ATTACKER_AFFINITY` (now authorable against all three `AffinityType` axes), and
  `CombatEncounter.initiated_by_pc_side` — the new initiator-side capture `origin_side`-
  parameterized situations read (stamped `True` at CREATE by every PC-cast encounter path;
  `False` is admin/GM-stampable in v1, honestly `NULL`-heavy until an NPC-initiated-encounter
  service exists). All 14 pre-#2623 situation rows behave byte-identically (parameterless =
  the parameterless default of each parameterized family).

## Integrates With

- Magic (`COVENANT_ROLE` Thread anchor cap = `current_level × 10`, bounded for COURT roles by
  `CourtPact.granted_pull_cap` via `_bound_covenant_role_cap_by_court_grant`; `MentorsVowRitualFactory`;
  `spend_resonance_for_imbuing` hooks `fire_subrole_discoveries` after each imbue)
- Missions (`has_active_court_mission` queries `MissionInstance` + `NPCServiceOffer` + `NPCRole`
  + `faction_affiliation` to gate COURT engagement)
- Mechanics (`covenant_role_bonus` in modifier walk; `level_override` via `bond_adjusted_level`)
- Items (`gear_archetype` on `ItemTemplate`)
- Combat (`apply_equipped_armor_soak` + `_weapon_augmented_budget`; `gear_additive_fraction`
  scales the compatible-armor bucket, #2533; `compute_party_profile` via `effective_combat_level`)
- Achievements (`CovenantRole.discovery_achievement` FK; `grant_achievement` on sub-role
  threshold crossing; `Discovery` row created on first-ever earner)
- Codex (`CovenantRole.codex_entry` FK; `CharacterCodexKnowledge(status=KNOWN)` created per
  roster_entry on threshold crossing)
- Narrative (`send_narrative_message(category=COVENANT)` for gamewide / personal discovery
  announcements; `active_player_character_sheets()` from `world.roster.selectors` selects
  gamewide recipients on first-ever discovery)

## Source

`src/world/covenants/`

- `models.py` — all covenant + mentor bond + CourtPact models
- `handlers.py` — `CharacterCovenantRoleHandler`; `currently_engaged_roles()` calls
  `resolve_effective_role` (defined in `services.py`) per row; `can_engage_membership` (COURT arm)
- `services.py` — covenant lifecycle + `resolve_effective_role` + `establish_mentor_bond_via_session`
  + `swear_court_pact` / `release_court_pact` / `active_court_pact_for` + `induct_member_via_session`
  (extended for COURT)
- `selectors.py` — `resolve_actor_membership` / `get_active_memberships`; shared by viewsets
  and the covenant Actions
- `discovery.py` — `fire_subrole_discoveries` (sub-role discovery beat)
- `mentorship.py` — `effective_combat_level` and Mentor's Vow math; `assert_membership_level_allowed`
  (COURT gulf arm)
- `court_missions.py` — `has_active_court_mission` (mission-driven engagement predicate)
- `power_tier.py` — `power_tier_for_level` (gulf enforcement helper)
- `factories.py` — `seed_resonance_subrole_slice`, `SubroleCovenantRoleFactory`
- `exceptions.py` — all exceptions

`src/actions/definitions/covenants.py` — seven covenant lifecycle REGISTRY Actions

`src/commands/covenant.py` — `CmdCovenant` telnet namespace

`src/commands/ritual_adapters.py` — `SoulTetherAdapter`, `CovenantInductionAdapter`,
`BannerCallAdapter` + `get_adapter(ritual)` registry lookup

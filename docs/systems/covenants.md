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
  boolean, `rank` FK → `CovenantRank`, `is_secondary` boolean (#2641 — see "Secondary
  vows" below), `standing` (`MembershipStanding.CORE`/`MINOR`, #2992 — see "Minor
  covenant membership" below), and `sworn_as` (#4208, ADR-4208): the **sworn face**,
  the `Persona` the vow was sworn under, one of the character's own and PRIMARY or
  ESTABLISHED (a temporary mask cannot swear; `clean()` and `services.resolve_sworn_face`
  both refuse a foreign or temporary face). Presentation only: the mechanics of the vow
  (engaged bonuses, COVENANT_ROLE thread pulls, command tiers, the Durance gate) stay
  keyed on the sheet. `add_member` and `assign_covenant_role` take `sworn_as`, the
  character's active persona when not given; a founder swears under the face worn at
  the founding; `change_role`'s replacement row keeps the face; the induction ritual
  reads the candidate's active persona when it fires (`RitualSessionParticipant` stays
  sheet-keyed). A row saved with no face named gets the primary (`save()`), so the
  column is NOT NULL; the three migrations 0212-0214 added it nullable, backfilled every
  existing vow to the primary face, then made it required. Readers: the sheet's
  covenant block follows the presented face (`docs/systems/character_sheets.md`, "Ties
  visibility"), `CharacterCovenantRoleSerializer.display_name` names the sworn face
  (never "Character #n"), and the telnet `sheet/covenant` section, self-only, marks a
  vow sworn under another of your own faces "(as Robert)".
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
  `(CovenantRole, ModifierTarget, focus_pick)` (the pick is null for the base vow, #4783;
  `vow_stat_scaling_unique_role_target`, NULLS NOT DISTINCT) with `bonus_per_level` scaling by the
  **COVENANT_ROLE thread level** (not character level, which `CovenantRoleBonus`
  already handles). `vow_stat_scaling_bonus(sheet, target)` returns
  `thread_level × bonus_per_level`; no row → 0. Rows on an engaged role's anchor role count too
  (#4783), and on a maneuver-effect target the level is the shown level (see below). The mechanical heart of "solo
  darkness" — a deepened vow is a substantially stronger character. When the vow
  dims (#2051), the scaling drops to 0. This is ADR-0149 Layer 3's stat-power pillar
  and stayed unaffected by the #2533 rework; as of #2533 it rides the lore-repo
  content pipeline too (`NaturalKeyMixin` NK `["covenant_role", "modifier_target",
  "focus_pick"]`, `covenants.vowstatscaling` in `CONTENT_MODELS`) — a wiring-proof test shows
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
  covenant vow defends: `GEAR_SOAK` (armor is the defense; labelled "Mitigation" since
  #4759, stored value still `gear_soak`), `EVASION` (not being there is the defense),
  `BARRIER` (force/warding is the defense). Also read by `CombatStyle.defense_style`
  (see "Vow focus picks and combat styles" below). Code-defined
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
- **Maneuver effects through `VowStatScaling`** (#4783, ADR-4783-A; **removed**
  `CovenantRoleActionScaling`, `CovenantScaledAction` and
  `covenant_role_action_scaling_bonus`, which #2529 and #4739 built to scale Interpose, Rally
  and Rally's surge intensity per vow thread level; the rows were placeholders and were
  discarded by owner ruling 2026-10-31). A vow now makes a maneuver stronger the way it makes
  a stat stronger: a `VowStatScaling` row whose `modifier_target` is in the "maneuver_effect"
  category (scoped to one effect such as "Charge: damage", or to a kind such as "partial
  protection, any maneuver"). `effect_value(sheet, key)`
  (`world/mechanics/effect_targets.py`) adds that target's modifier total to the effect's
  catalog base value. See `docs/systems/mechanics.md` "Maneuver effects" for the catalog and
  the five maneuvers' wiring. Vow scaling reads the holder's engaged PRIMARY roles only. Two rules are specific to vows:
  (1) `vow_stat_scaling_bonus` looks up rows on both an engaged role and its anchor role, so a holder who graduated to a
  sub-role keeps rows authored on either, and they sum; the thread level is always read from
  the anchor's thread. (2) On a maneuver-effect target the bonus multiplies the SHOWN thread
  level (stored level // 10), because an effect is in natural units (damage, percent, hops,
  morale) while stats are stored x10; every other category keeps the stored level. The Rally
  roll line notes a surge intensity above 100% as "surge +N" (stored on
  `DramaticSurgeRecord.vow_scaling`). A vow's old "Surges given" row is gone: author a row
  on a target scoped to "Rally: surge intensity" instead.
- **`CovenantRoleTechniqueSpecialty`** (#2443, ADR-0149's 2026-07-20 amendment; **Layer 2**
  of the vow-power model) — one row per `(covenant_role, function)`, `function` drawn
  from `magic.TechniqueFunction` (a shared fine-grained vocabulary also consumed by
  Layer 4's situational perks, #2536). `multiplier_tenths` (integer-tenths, default 10 =
  ×1.0) scales the boost for that function while the role is engaged. Unlike the blend
  weights, rows are valid on **both primary roles and sub-roles** — a sub-role's rows ADD
  to the parent's rather than replacing them, so a specialized (promoted) member reads as
  strictly more specialized than an unpromoted one. Read by
  `covenant_role_specialty_power_term` (`world.magic.services.power_terms`, see
  `docs/systems/magic.md`), and since #4747 (ADR-4747-A) by `caster_vow_step`: a sized buff
  or debuff cast by a holder whose first engaged vow specializes in the technique's function
  counts one size step stronger at her vow thread's shown level, scaled by the same
  `multiplier_tenths` (the larger when role and sub-role both match; a secondary vow's tenths
  times `SecondaryVowConfig.potency_tenths / 10`), never tapered. Points only. Lore-repo content
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
  `VowSituationalPerkSituation`/`VowSituationalPerkRung`/`VowAddedEffect`; carries five typed,
  nullable/blank parameter columns (Situation Parameters): `condition_property` (#4759, nullable
  FK to `mechanics.Property`, read only by the two condition-property situations), `threshold_percent` (0-100, percent-shaped floors —
  aura-axis floor, ally-health fraction), `count_threshold` (count-shaped floors — surrounded
  lock count, minimum affection), `affinity` (nullable FK to `Affinity` for attacker typing),
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
  ADR-0154). `Situation` ships 22 values as of #2664: slice 1's 9 plus
  `CHAMPION_DUEL` (Battle wiring, Task 3), `COMBAT_OPENED_FROM_PARLEY`/`AMBUSH_UNDERWAY`
  (origin-marker addition, Task 4), `ALLY_INTERCEPTED_FOR_ME` (declared-guard, Task 5), and
  `ATTACKER_AFFINITY` (defense-side seam, Task 6; originally Abyssal-only, renamed and
  parameterized to all three affinity rows by #2623, ADR-0154) from #2536 slice 3, plus
  `ON_CHOSEN_GROUND` (#2646 — see "Chosen Ground" below) — see each value's own docstring entry
  for its evaluator's data source, its Situation Parameters, and any v1 approximation.
  #4759 slice 1 added `TARGET_HAS_CONDITION_PROPERTY`, `ENEMIES_WITH_CONDITION_PROPERTY_NEARBY`
  (both require `condition_property`, allow `count_threshold`) and `TARGET_LOW_HEALTH` (allows
  `threshold_percent`); slice 3 wired their evaluators, see "Target-state situations" below
  [BUILT & WIRED]. The `situation`/`extra_situation` columns are 48 characters wide for them.
  `SITUATION_PARAM_SPECS` (#2623) names, per situation, which of the five `SituationRequirementMixin`
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
  `Situation` value (22 as of #2664). Every evaluator is a pure read (one query or a
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
co-present mate's disengagement, only the subject's own), runs the same situation evaluation (`_PerkResolver`, via its
`SituationCheck`) as the live path plus the slice-3 scope filter, and returns the set that
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
telnet renders the identical line. `broadcast_action_outcome` was WS-only when this was built
(see ADR-0151 for why it wasn't reused); it reaches telnet itself since #4640, but takes an
encounter, which a perk firing outside a fight does not have. The telnet companion
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
  Lore-repo content (NK `["covenant_role", "gift"]`,
  `covenants.covenantrolegiftgrant` in `CONTENT_MODELS`, #2847).
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

### Secondary vows (#2641, ADR-0159)

A character may hold a SECONDARY vow — `CharacterCovenantRole.is_secondary=True` —
alongside their PRIMARY (`is_secondary=False`) vow, at most one engaged of each per
(character_sheet, covenant type). Fills a group gap or enables a hybrid fantasy;
never a replacement for a real specialist (the specialist-supremacy invariant).

- **Exclusivity** — `_another_same_type_engaged_exists` and the
  `set_engaged_membership` un-engage loop are both scoped by `is_secondary`, so
  engaging a new PRIMARY never un-engages an already-engaged SECONDARY of the same
  type, and vice versa. The covenant-scoped SUPREME/Champion guards are NOT scoped
  by `is_secondary` — a secondary engaged Champion row still trips them.
- **Engage-time validation** (`validate_secondary_engage_rules`, called from both
  `CharacterCovenantRole.clean()` and `set_engaged_membership`) — a secondary
  requires an engaged primary of the SAME covenant type
  (`SecondaryVowRequiresEngagedPrimaryError` otherwise), must not share its ANCHOR
  role with that primary (`SecondaryVowSameAnchorError` — "no same-vow secondary":
  doubling down on one vow is allocation, not a second vow), and its COVENANT_ROLE
  thread level is capped at the primary's (`SecondaryVowThreadExceedsPrimaryError`
  — a missing thread on either side counts as level 0). `set_engaged_membership`
  gains a keyword-only `as_secondary: bool = False` that stamps the flag before
  validation.
- **Layer split** — chassis layers (Layer 1 combat-identity blend, Layer 3
  defense/gear/stat scaling) read ONLY `currently_engaged_primary_roles()`; a
  secondary membership never contributes to them (zero chassis leak). Layer 2
  (technique specialty) and Layer 4 (situational perks) read
  `currently_engaged_roles_with_flags()` / the perk candidate gatherers'
  `is_secondary`-tagged `FiredPerk`s, and scale a secondary-sourced contribution by
  `SecondaryVowConfig.potency_tenths / 10` (via the shared
  `sum_potency_scaled_magnitudes` / the Layer 2 partition-and-scale helpers) —
  situational, never raw. `covenant_level_bonus` (mechanics app) is a conservative
  extra flip: not one of the four layers proper, but chassis-shaped, so it stays
  primary-only too.
- **Depth stays primary-only** — a secondary membership resolves at its ANCHOR
  role only (`currently_engaged_roles_with_flags`, `currently_engaged_roles`, and
  the Layer 4 candidate gatherers `_self_candidates`/`_ally_candidates`/
  `_ally_sub_role_candidates`) — no sub-role graduation, no deep rungs, no
  signature, no unique name. Outcome guarantees from a secondary-sourced
  `TIER_FLOOR` firing bind one tier weaker (`floor_success_level - 1`);
  `BOTCH_IMMUNITY` is deliberately left unweakened (no numeric field to soften).
- **`SecondaryVowConfig`** (pk=1 singleton, `potency_tenths` default 6 = ×0.6, the
  ratified batch-2 F-2 seed) — lazy-created via `secondary_vow_config()`
  (`world.covenants.services`, `cached_singleton()` + `get_or_create` fallback —
  unlike `MentorBondConfig`'s fail-loud seeded pattern, this dial ships with a
  sane default so no pre-launch seeding step is required). Staff-tunable in admin.
- **Typed exceptions** (`world.covenants.exceptions`) —
  `SecondaryVowRequiresEngagedPrimaryError`, `SecondaryVowSameAnchorError`,
  `SecondaryVowThreadExceedsPrimaryError`.

### Minor covenant membership (#2992, ADR-0213)

`CharacterCovenantRole.standing` (`MembershipStanding.CORE`/`MINOR`) is a third,
orthogonal membership axis — alongside `CovenantRole` (power) and `CovenantRank`
(authority) — answering "how fully is this character sworn in." CORE is today's
full member (default). MINOR is a guest standing that reuses the secondary-vow
machinery (#2641, ADR-0159) rather than adding a parallel guest tier — see
ADR-0213 for the rationale.

- **DURANCE-only** — `CharacterCovenantRole.clean()` raises
  `MinorStandingDuranceOnlyError` if a MINOR row's covenant is not
  `CovenantType.DURANCE`.
- **Secondary lane only** — `set_engaged_membership` raises
  `MinorStandingRequiresSecondaryEngageError` up front when a MINOR-standing
  membership tries to engage with `as_secondary=False`, before any other
  engage-time work runs. `clean()` mirrors this at the model layer.
- **Solo-secondary waiver** — `validate_secondary_engage_rules` normally requires
  an engaged PRIMARY of the same covenant type before a secondary may engage
  (`SecondaryVowRequiresEngagedPrimaryError`). A MINOR-standing row is the one
  exception: when no primary is engaged, a MINOR row's secondary vow may stand
  alone — "a guest's minor vow may be their only lit vow." Every other secondary
  rule (anchor-role exclusivity, thread-level cap) still applies once a primary
  exists.
- **Level-band bypass** — `add_member(..., standing=MembershipStanding.MINOR)`
  skips `assert_membership_level_allowed` entirely (the Vow gate protects the
  full swearing a guest never took). `swear_core` re-runs the gate when
  upgrading a MINOR row to CORE.
- **Standing transitions** — `swear_core(*, membership)` upgrades MINOR → CORE
  (no-op on an already-CORE row); `step_back_to_minor(*, membership)` steps a
  CORE member down to MINOR, first un-engaging a primary-lane engagement (a
  MINOR row may only hold the secondary lane) — rank is untouched by either.
- **Two-pass auto-engage** (`_auto_engage_durance`) — co-presence auto-engage now
  fills two independent lanes: the PRIMARY slot from CORE-standing memberships
  (existing behavior), then — independently — a vacant SECONDARY slot from
  MINOR-standing memberships. Manual engagement sticks per lane; a fill no-ops
  when that lane already has an engaged row for the Durance type.
- **Co-presence counts a minor guest** — a lone core member with an engaged
  minor guest is no longer "dark" for co-presence purposes; a Minor Member
  credits legend fully while engaged (no code needed — legend credit is already
  engagement-driven, not standing-gated).
- **Induction + API** — the induction session gains a `standing` select field
  (defaults CORE); `CharacterCovenantRoleSerializer` exposes `standing` on the
  membership payload. Re-inducting an existing MINOR row upgrades to CORE via
  `swear_core` only when the session's `standing` pick is CORE; picking MINOR
  again is a no-op — the existing row is returned unchanged, with no
  level-band re-check and no `COVENANT_SWORN` act.
- **Typed exceptions** (`world.covenants.exceptions`) —
  `MinorStandingRequiresSecondaryEngageError`, `MinorStandingDuranceOnlyError`.

## Handlers

- `character.covenant_roles` (`CharacterCovenantRoleHandler`):
  - `has_ever_held(role)` — True if the character has ever held this role (active or ended).
  - `currently_held_role_in(covenant)` — active role in the specified covenant, or None.
  - `currently_engaged_roles()` — list of **resolved (effective) roles** for every
    active+engaged membership (PRIMARY and SECONDARY). Calls `resolve_effective_role` per
    PRIMARY row: if the character's COVENANT_ROLE thread qualifies for a resonance sub-role,
    the sub-role is returned instead of the parent. A SECONDARY row resolves at its stored
    ANCHOR role only (#2641 — no sub-role graduation). Non-layer callers (eligibility gates,
    precedence fallbacks) use this; chassis (Layer 1/3) callers use
    `currently_engaged_primary_roles()` instead, and Layer 2/4 callers use
    `currently_engaged_roles_with_flags()`. Consumers that must key on the stored anchor
    identity should use `anchor_role_in()` instead.
  - `currently_engaged_primary_roles()` (#2641) — resolved roles for engaged PRIMARY
    (`is_secondary=False`) memberships only; sub-role graduation is unrestricted (primary
    depth has no cap). Read by every chassis (Layer 1/3) consumer.
  - `currently_engaged_roles_with_flags()` (#2641) — `(role, is_secondary)` pairs for every
    active+engaged membership. PRIMARY rows resolve like `currently_engaged_primary_roles()`;
    SECONDARY rows resolve at the anchor only. Read by Layer 2's
    `covenant_role_specialty_power_term`.
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

- `add_member(*, covenant, character_sheet, role, standing=MembershipStanding.CORE) ->
  CharacterCovenantRole` — creates the active membership row; MINOR standing bypasses
  the level-band gate (see "Minor covenant membership" above).
- `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
- `end_covenant_role(role_assignment) -> None`
- `swear_core(*, membership) -> None` — upgrades MINOR to CORE (re-runs the level-band
  gate); no-op for CORE rows (#2992).
- `step_back_to_minor(*, membership) -> None` — steps CORE down to MINOR, un-engaging
  a primary-lane engagement first; no-op for MINOR rows (#2992).
- `leave_covenant(*, membership) -> None` — soft-ends the membership. Covenants never
  dissolve from attrition (#2992, ADR-0042 amendment) — the covenant persists at any
  active-member count, including zero. Idempotent; raises `LastManagerRankError` if the
  member holds the last `can_manage_ranks` rank and ≥1 other active member would remain.
- `kick_member(*, target, actor) -> None` — actor's rank must have `can_kick=True`
  and `actor.rank.tier < target.rank.tier` (lower tier = higher authority); raises
  `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError`.
  Same no-attrition-dissolve rule as `leave_covenant` (#2992, ADR-0042 amendment).
- `is_gear_compatible(role, archetype) -> bool` — existence-only join lookup
- `role_base_bonus_for_target(role, target, char_level) -> int` (in
  `world.mechanics.services`) — reads `CovenantRoleBonus`; returns
  `char_level × bonus_per_level`; 0 if no row
- **Rank management** — all require `actor.rank.can_manage_ranks=True`:
  `create_rank`, `rename_rank`, `set_rank_capabilities`, `reorder_ranks`,
  `delete_rank`, `assign_rank`, `transfer_top`. Lock-out invariant:
  `LastManagerRankError` if an op would leave zero active managers.
  `set_member_rank(*, membership, rank)` (#4229) is `assign_rank`'s write with the actor
  check left out; staff edit mode calls it directly. The cross-covenant and lock-out
  rules still hold.

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
- **`establish_mentor_bond(*, covenant, mentor_sheet, sidekick_sheet, staff_override=False)
  -> MentorBond`** — atomically determines `adjusted_party` (exactly one must be out of
  band), enforces the `max_sidekicks_per_mentor` cap (counts all active bonds where this
  character is the mentor in this covenant), and creates the `MentorBond`. Raises
  `MentorBondError` on constraint violations. `staff_override` (#4229, staff edit mode)
  bonds a pair that breaks the band rule anyway, the sidekick as the adjusted party; the
  cap still holds.
- **`mentor_band_problem(*, covenant, mentor_sheet, sidekick_sheet) -> str`** — why the
  pair breaks the band rule, else "". `establish_mentor_bond` raises it; staff edit mode
  shows it on the bond's row.
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
    function, excluding techniques already known. "Learnable" = the sheet already owns
    the technique's `Gift` (#2700) — `learn_technique`'s own first gate, so every row is
    something the character can actually go and learn. Replaced the former
    `can_learn_technique` path-style filter, which both recommended techniques from
    unowned gifts and hid ones the character's own path had granted (ADR-0167).
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
| `covenant deposit <amount> [in <covenant>]` | `deposit_covenant_funds` | Move coppers purse → covenant treasury (any active member, #2992) |
| `covenant withdraw <amount> [in <covenant>]` | `withdraw_covenant_funds` | Move coppers treasury → purse (rank-gated, #2992) |

Supply the covenant name when the character belongs to more than one. `standdown` is STANDING
Battle covenants only; `engage`/`disengage` are gated by the same `can_engage_membership` logic
the web uses. `deposit`/`withdraw` resolve the caller's own membership and pass it directly via
the `membership` kwarg — see "Covenant Treasury" below. `CovenantError` subclasses surface as
`ActionResult(success=False)` with a `user_message`.

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
induct servant (gulf enforced), swear pact, mission-driven engage, pull-cap bounded, and
attrition persistence (last servant leaves → the Court persists, `dissolved_at` stays unset —
#2992, ADR-0042 amendment removed the attrition auto-dissolve; only formation still enforces
the two-founder floor).

## Covenant Treasury (#2992)

`src/world/covenants/treasury.py` — minimal wiring of the `OrganizationTreasury`
(`world.currency`) that every Covenant's auto-created `Organization` already carries.
Covenant treasury authority derives from `CharacterCovenantRole`, not
`OrganizationMembership` — the societies-side generic-org membership services still
refuse covenant orgs.

### Services

- **`covenant_treasury(covenant) -> OrganizationTreasury`** — the covenant's shared
  purse; lazy-created on its backing `Organization` via
  `world.currency.services.get_or_create_treasury`.
- **`deposit_covenant_funds(*, membership, amount, reason="") -> CurrencyTransfer`** —
  any ACTIVE member (core or minor) moves coppers from their purse into the covenant
  treasury. Raises `NotAnActiveCovenantMemberError` for a departed membership,
  `CovenantTreasuryTransferError` if the underlying `transfer()` rejects it (e.g.
  insufficient funds).
- **`withdraw_covenant_funds(*, membership, amount, reason="") -> CurrencyTransfer`** —
  a spend-ranked active member draws coppers from the treasury into their purse.
  Authority: `membership.rank.tier <= treasury.spend_rank_max` (rank 1 is top; default
  `spend_rank_max=1` = the Founder tier only) — raises
  `NotAuthorizedToSpendCovenantTreasuryError` otherwise. Piloted-only by construction
  (action-driven, never automated).

### Actions and dispatch

`DepositCovenantFundsAction` (key `deposit_covenant_funds`) / `WithdrawCovenantFundsAction`
(key `withdraw_covenant_funds`) — REGISTRY Actions in `actions/definitions/covenants.py`,
thin wrappers over the treasury services above (not `world.covenants.services` — the
treasury lives in its own module). Both actions share a `_resolve_actor_membership(actor,
kwargs)` helper handling two call shapes: telnet passes a genuine `CharacterCovenantRole`
instance under the `membership` kwarg (`isinstance()`-gated, so a bare id under that key
from a malformed/forged web POST is never trusted as a resolved instance); the web dispatch
path instead resolves the ACTOR'S OWN active membership from `kwargs["covenant_id"]` — a
client can never name someone else's membership from the wire. Shared by telnet
`CmdCovenant`'s `deposit`/`withdraw` subverbs (see "Telnet Surface" above) and the web
`TreasuryPanel` (`frontend/src/covenants/components/TreasuryPanel.tsx`).

### API and frontend

`CharacterCovenantRoleSerializer` exposes `standing` on the membership payload;
`CovenantSerializer.get_treasury_balance` exposes a member-gated `treasury_balance` field
(non-members see `null`) via the shared `_resolve_viewer_membership` helper, which reads
`Account.cached_covenant_memberships` (#3597); the list endpoint passes its page aggregates
and treasury balances to the serializer as explicit context. The frontend
renders a Minor Member badge and the `TreasuryPanel` deposit/withdraw controls; a rejected
dispatch (e.g. a rank-unauthorized withdrawal) surfaces through `dispatchTreasuryResult`,
which throws on `success === false` so the mutation's `onError` fires instead of silently
clearing the input on a business-rule rejection.

### Exceptions

`CovenantTreasuryError` (base) → `NotAnActiveCovenantMemberError`,
`NotAuthorizedToSpendCovenantTreasuryError`, `CovenantTreasuryTransferError` — see
"Exceptions" below.

## Target-state situations (#4759 slice 3) [BUILT & WIRED]

Situations that read the state a target is in, so one character's condition or hold is
another's trigger. All live in `world.covenants.perks.evaluators` and fire through
`applicable_perks` like every other situation.

- **"The target"** is `SituationContext.target`'s character when the action has a sheet-backed
  target; otherwise, in combat, the opponent the subject declared as this round's focused
  target (`_subject_focused_opponent`, the `TARGET_IS_BOSS` read). An NPC `CombatOpponent`
  never fills `ctx.target`, so this fallback is what makes the situations work against mooks.
- **"Carries a property"** means an active (unresolved, unsuppressed) `ConditionInstance` whose
  template's `properties` OR whose current stage's `properties` include the row's
  `condition_property`. Whoever laid the condition does not matter.
- **`TARGET_HAS_CONDITION_PROPERTY`** - the target carries the property. `count_threshold`,
  when set, is the minimum `effective_severity` (stage multiplier applied) of that condition.
- **`ENEMIES_WITH_CONDITION_PROPERTY_NEARBY`** - at least `count_threshold` (default 1)
  distinct opponents near the subject carry the property. "Near" is `SURROUNDED`'s scope: an
  ACTIVE opponent holding an ACTIVE `EngagementLock` on the subject. One query.
- **`TARGET_LOW_HEALTH`** - the focused opponent's `health_percentage` (or, with none, a sheet
  target's `CharacterVitals.health_percentage`) is below `threshold_percent`, default
  `ALLY_LOW_HEALTH_FRACTION` (50%).
- **`ENEMY_HELD_BY_ALLY`** now also counts two more hold shapes (`_holder_sheet_ids_on_opponent`):
  an active clash-lock condition (`ConditionTemplate.is_clash_lock`) on the opponent whose
  `source_character` is a covenant-mate, and an ACTIVE LOCK/SUSTAINING `Clash` on the opponent
  that a mate started (`initiator`) or contributed to (`ClashContribution`). LOCK/ESCAPING
  does not count: that is the enemy holding a PC. Mate scoping is unchanged (one batched
  `CharacterCovenantRole` query over every candidate, subject excluded).

## Vow added effects (#4581, ADR-4581-A) [BUILT & WIRED]

A vow can add staff-authored effects to a technique cast: "when my ally casts a Weaken
against a boss, once a fight, it also burns the target", "my own Hold also slows the held
enemy", "a Cleanse cast near me also treats the wound". It is payload, the same shapes a
technique carries itself, authored in plain Django admin. Slice 1 of #4573; the workbench,
vow board, vow page and spellbook vow section are #4565 and do not exist yet.

### Models (`world.covenants.models`, authored content registered in `CONTENT_MODELS` for export, except the treatment child)

- **`VowAddedEffect`** (the header; `NaturalKeyMixin`, `SituationRequirementMixin`) -
  `covenant_role` FK (anchor OR sub-role, CASCADE), `function`
  (`magic.TechniqueFunction`), optional `gift` / `technique` FKs narrowing it (never both,
  a DB `CheckConstraint`), `cast_context` (`VowEffectContext`: `ANY` / `IN_COMBAT` /
  `OUT_OF_COMBAT`), `situation` (+ the mixin's four typed parameter columns, blank = none),
  `beneficiary` (`PerkBeneficiary`: `SELF` / `COVENANT_ALLIES` / `WHOLE_GROUP`),
  `frequency` (`VowEffectFrequency`: `EVERY_CAST` / `ONCE_PER_ROUND` / `ONCE_PER_FIGHT`),
  `unlock_thread_level` plus `severity_per_thread_level`, `duration_per_thread_level`,
  `damage_per_thread_level`, and `upgrades` (self-FK, `RESTRICT`, `related_name=
  "upgraded_by"`). Natural key is the nine scope fields; a `UniqueConstraint(nulls_distinct=
  False)` holds it, and a second one holds "one upgrade per base per role"
  (`covenant_role` + `upgrades`). `cached_effect_summary` (plain-words line, below) and four
  `PrunedCachedProperty` payload lists: `cached_applied_conditions`,
  `cached_removed_conditions`, `cached_treatments`, `cached_damage_profiles`.
- **Four payload children**, each with `effect` FK (CASCADE), `RelatedCacheClearingMixin`
  (`related_cache_fields = ["effect"]`, so a child save or delete clears the header's cached
  list on a running server): `VowAddedEffectAppliedCondition` and
  `VowAddedEffectRemovedCondition` (both on `magic.AbstractAppliedCondition`; the removal
  child adds `remove_all_stacks` and `cure_power_multiplier`, which the shared removal seam
  reads off every row), `VowAddedEffectTreatment` (`treatment_template`, `target_kind`,
  `minimum_success_level`, `mend_cap_fraction`; mirrors `TechniqueTreatment`. The fraction,
  #4600, is how far the vow's treatment may heal a wound, as a share of its damage: default
  0.75, above 0 and below 1 by constraint, between 0.01 and `NEVER_TO_FULL_FRACTION` by its
  field validators.
  A vow's treatment rides a cast as its own tending, so it carries its own fraction rather than
  borrowing the technique's), and `VowAddedEffectDamageProfile`
  (on `magic.AbstractDamageProfile`; one row per damage type plus at most one untyped).
  The header and the applied, removed and damage children are in `CONTENT_MODELS`; the
  treatment child is not, because `TreatmentTemplate` has no natural key (the same reason
  `magic.techniquetreatment` is absent).
- **`VowAddedEffectFiring`** (`world.combat.models`, play state, no natural key) - the
  combat ledger behind the two limits: `participant` FK (the HOLDER's `CombatParticipant`,
  not necessarily the caster), `effect` FK, `round_number`; unique on the three. A
  participant row is per encounter, so a new fight starts with an empty ledger.
- **`Situation.TARGET_IS_BOSS`** (`perks/constants.py`, evaluator in `perks/evaluators.py`):
  the opponent the SUBJECT declared as this round's focused target is a BOSS-tier
  `CombatOpponent` (Elite and Hero Killer do not count). One query; False outside combat or
  with no declared opponent. It lives in the shared registry, so a situational perk can use
  it too.

### Authoring rules (`clean()`)

A header form validates before its inline rows exist in the admin, so a rule that reads a
child lives on the child and reads `self.effect`.

| Rule | Where | Error key |
|---|---|---|
| `ONCE_PER_ROUND` / `ONCE_PER_FIGHT` need `IN_COMBAT` (the limit is a fight's ledger) | header | `frequency` |
| gift and technique both set | header (friendly twin of the DB check) | `technique` |
| a narrowing `technique` must carry the row's `function` tag | header | `technique` |
| `upgrades` names itself, a different `function`, or a row that is neither on this role at a lower `unlock_thread_level` nor on this role's `parent_role` | header | `upgrades` |
| an `upgrades` row more limited than its base (`EVERY_CAST` < `ONCE_PER_ROUND` < `ONCE_PER_FIGHT`), which would leave a holder worse off for qualifying | header | `frequency` |
| context set away from `IN_COMBAT` while saved damage children exist | header | `cast_context` |
| a damage child on an effect whose `cast_context` is not `IN_COMBAT` | damage child | non-field |
| an applied condition whose category `alters_behavior` (consent, ADR-4581-A) | applied child | `condition` |
| removal knobs that mean nothing on a removal row (severity, duration, stack count) off their defaults (`validate_inert_removal_knobs`, shared with `TechniqueRemovedCondition`) | removed child | the knob field |
| situation parameters the situation does not read, or that it requires (`SituationRequirementMixin.clean`) | header | the parameter field |

An upgrade onto a parent-role row does not compare unlock levels.

### Who holds a row, and which rows fire

`world.covenants.added_effects` is the read seam. Holders are the ones situational perks use
(`vow_holder_candidates`): the caster's own engaged vows (anchor role plus resolved sub-role;
a secondary vow's anchor only) and every co-present covenant ally's vows. A row rides a cast
when its `beneficiary` counts for that holder (`SELF` and `WHOLE_GROUP` on the caster's own
vow, `COVENANT_ALLIES` and `WHOLE_GROUP` on an ally's).

`vow_added_effects_for_cast(subject, technique, *, resolution, target) ->
list[FiredVowEffect]` runs these steps in order:

1. The technique's function tags (none: `[]`, no query).
2. The holder candidates (none: `[]`, no query).
3. One `VowAddedEffect` query with the four payload prefetches (none: `[]`).
4. Per-holder gates: beneficiary, gift / technique narrowing, `cast_context`, the holder's
   COVENANT_ROLE thread level on the vow's anchor role reaching `unlock_thread_level`
   (`vow_holder_thread_levels`, one query), and the row's situation last
   (`SituationCheck`, because it may query).
5. **The upgrade rule**: a live row whose `upgrades` names another live row of the same
   holder replaces it. A sub-role's row replaces its parent role's; a later-unlock row
   replaces the earlier one. Every other row adds. An upgrade that fails a gate leaves its
   base in place.
6. **The frequency ledger**, in combat only: a `ONCE_PER_ROUND` row already in the ledger
   for this round, or a `ONCE_PER_FIGHT` row in the ledger for this fight, is dropped. One
   ledger query, and only when a live row is limited. This runs AFTER step 5, so a spent
   once-per-fight upgrade still suppresses its base: the base never comes back because its
   upgrade is used up.
7. Dedupe on `(holder, row)`: one holder fires one row at most once per cast (anchor plus
   resolved sub-role, primary plus secondary, a `WHOLE_GROUP` row seen from both sides). When
   one holder reaches a row through both a primary and a secondary candidate, the primary
   fires (no potency scaling), whatever order the candidates came in. Two different holders
   of the same vow each fire it once.
8. **Scaling**: each level above `unlock_thread_level` adds the row's
   `severity_per_thread_level`, `duration_per_thread_level` and `damage_per_thread_level`.
   A row from a SECONDARY vow has each bonus multiplied by
   `SecondaryVowConfig.potency_tenths` and floor-divided by 10 (ADR-0159).

`FiredVowEffect` (`world.covenants.types`) carries `effect`, `holder`, `is_secondary` and the
three bonuses. Every cast in the game calls this, so the order keeps the common cast cheap: a
technique with no function tag, or a caster with no engaged vow and no co-present holder,
issues no `VowAddedEffect` query.

The other seams in the module:

- `apply_vow_effect_payloads(fired, *, technique, success_level, eff_intensity,
  targets_by_kind, source_character, scene, soulfray_consented=False)` hands each fired row's
  applied conditions, treatments and removed conditions to the technique payload seams in
  `world.magic.services.condition_application` (the row-override and bonus kwargs, see
  `docs/systems/magic.md`). It runs in two passes: every row's conditions and treatments,
  then every row's removals. Both cast paths call it after the technique's own treatments and
  before the technique's own removals, so every treatment in the cast runs before any
  removal. SELF is always mapped to the caster. `technique` stays the provenance on
  everything applied. A team-lane condition row ignores the severity and duration bonuses.
  An applied condition whose category `alters_behavior` is skipped here (and logged), as well
  as refused in authoring: a category can gain the flag, or a condition can move category,
  after the row was saved, and consent folding never sees a vow row (ADR-4581-A).
- `vow_damage_profiles(fired)` pairs each fired row's damage profiles with its
  `damage_bonus`; combat's `_apply_damage` runs them through the same per-target loop as the
  technique's and signature's profiles, the bonus added to the budget right after the weapon
  augment. A vow damage profile receives the caster's weapon augment and a CHARGE
  maneuver's damage bonus exactly as a technique's or signature's profile does.
- `record_vow_effect_firings(fired, *, encounter)` spends the limited rows: one
  `CombatParticipant` query for the holders, one `bulk_create`; no query when no fired row is
  limited.
- `vow_added_effects_on_technique(sheet, technique)` is the static view for #4565's display:
  the sheet's own engaged vows' rows that match the technique's function and narrowing, with
  no cast-dependent filter (not unlock level, context, situation or frequency), and it does
  NOT filter by `beneficiary`, so a display tells a row riding the sheet's own casts from one
  riding its allies' by reading `beneficiary`. **[BUILT, NOT WIRED]** pending #4565.
- `effect_rides_technique(effect, technique, technique_functions) -> bool` and
  `techniques_ridden_by(effect) -> QuerySet[Technique]` (#4880) are the one catalog match
  between a row and the techniques it rides: the row's `function` among the technique's
  function tags, then the gift or technique narrowing when set. The cast path's
  `_live_rows` and the static view call the predicate; the vow page's "Techniques this vow
  rides" rail reads `techniques_by_function(functions)` (one query, every catalog technique
  per function tag) and narrows it with the predicate. `payload_prefetches()` is the four payload prefetches
  shared by the cast path and the vow page's summary lines.

### Where it runs

- **Combat** (`CombatTechniqueResolver`): `_fired_vow_effects` reads the rows after the ward
  check, so a ward-bounced cast computes nothing and spends nothing. The damage, then the
  conditions / treatments / removals, then the ledger write all use the one `fired` list.
- **Out of combat** (`world.scenes.cast_services._resolve_and_pose_cast`): the same read with
  `resolution=None`, the payloads applied over the cast's own resolved targets. No ledger
  write: no limited row can fire there, the rules above hold `ONCE_PER_ROUND` and
  `ONCE_PER_FIGHT` to `IN_COMBAT`.
- **Success gate, one rule for both paths:** vow rows apply only on casts at success level 1
  or higher, and limited rows are spent only on such casts. A failed or partial cast
  neither uses nor spends a row, a row authored at `minimum_success_level=0` never lands on a
  sub-success cast, and a ward-bounced cast spends nothing; the holder keeps a limited row for
  the next cast.
- **NPC targets:** conditions go to the `ObjectDB` targets the resolvers already produce, so
  a vow's enemy condition lands on an NPC opponent. `apply_technique_treatments` skips a
  target with no `CharacterSheet` (an NPC opponent) instead of raising mid-round.

### Known limits (stated, not hidden)

- **AREA / FILTERED_GROUP casts:** vow damage reaches every resolved opponent, while the
  row's `situation` is checked against the cast's primary target only (the limit situational
  perks document at `_resolve_primary_target_sheet`).
- **Out of combat, vow payload results are applied but not yet narrated in the pose.** The
  vow's condition, treatment or removal lands; the cast pose does not mention it. A known
  gap.
- A treatment still raises for a sheetless CASTER; the vow seam passes a PC caster.
- A once-per-round or once-per-fight limit is per holder, per row, tracked through the
  holder's `CombatParticipant`.

### Summary line and admin

`summarize_vow_added_effect` (`world.covenants.added_effect_summary`) is built only from
the row's own fields: enum labels, the names of the rows it points at, and the payload
clauses a technique sentence uses (`render_payload_clauses`, see `docs/systems/magic.md`).
`VowAddedEffect.cached_effect_summary` returns it, for example "From thread 3. On covenant
allies' Weaken casts, in a fight, when Target Is a Boss, once a fight: Deals Fire damage."
A bare row reads "... Adds nothing yet." `VowAddedEffectAdmin` is the authoring surface (the
header with four inlines, `OneRowPerFormSet`, a read-only summary column and field); the
`CovenantRole` admin carries a read-only `VowAddedEffectInline` listing each added effect's
summary with a link to its own page.

### The dividing line

- **Specialties** (`CovenantRoleTechniqueSpecialty`, Layer 2) add cast power for matching
  functions, and step a matching sized buff by `multiplier_tenths` of one size at the vow
  thread's level (#4747). **Situational perks** (`VowSituationalPerk`, Layer 4) add a numeric bonus or
  outcome guarantee with an announced line. A **vow added effect** adds payload: conditions,
  strips, treatments or damage riding the cast. A numeric bonus with an announce line stays a
  perk; a condition or damage rider is an added effect (a perk kind would carry six columns
  only one kind reads, ADR-4581-A).
- The five `CovenantRole` switches (`grants_insight`, `reveals_weakness`, `prepares_ground`,
  `calls_out_windups`, `enhances_assessment`) stay code-owned riders and are untouched.
- Consent folding in `world/magic/services/targeting.py` is untouched: a behavior-altering
  condition is refused at authoring time (see the rule table), not at cast time.
- The perk refactor behind this exposed `VowHolderCandidate`, `vow_holder_candidates`,
  `vow_holder_thread_levels` and `SituationCheck` in `world.covenants.perks.services`.
  `SituationCheck` owns the per-resolution situation-evaluation cache (keyed
  `(situation, params, holder_pk)`); `_PerkResolver` now delegates to one.

## Vow focus picks and combat styles (#4759, ADR-4759)

Slice 1 of #4759 added the authoring schema and admin. Slice 2 (#4806) wires focus picks
into play [BUILT & WIRED]: a payload row whose `focus_pick` is set fires only for a holder
who chose it (see "Focus picks in play" below). Combat styles are [BUILT & WIRED] since
slice 5 (#4809): `world.covenants.defense.defense_style_for` reads them (see "Combat style
decides defense" under Combat Seams).

### Models (`world.covenants.models`)

- **`VowFocusPick`** (`NaturalKeyMixin` NK `(covenant_role, name)`, `CreditedContent`,
  `covenants.vowfocuspick` in `CONTENT_MODELS`) - one entry in a vow's pick catalog:
  `covenant_role` (CASCADE, `related_name="focus_picks"`), `pick_level` (1 to 3), `name`
  (unique per role), `description`, `value` (default 4, a placeholder point score until the
  simulator sets it). Valid on anchor roles and sub-roles.
- **`VowFocusPickLimit`** (NK `(pick, kind)`, `CreditedContent`, in `CONTENT_MODELS`) - one
  limit on a pick: `kind` (`FocusPickLimitKind`: `SELF`/`TARGET`/`SETTING`/`TIMING`/
  `EXPOSURE`/`COST`), `frequency_tenths` (1 to 10, default 10), `reduction` (default 0),
  `description`. One limit per kind per pick. `clean()` refuses a reduction on a frequency
  kind and a frequency other than 10 on `EXPOSURE`/`COST`, so no authored number is ignored.
- **`VowFocusPickConfig`** (singleton pk=1, like `SecondaryVowConfig`) - `budget_per_level`
  (default 4). Lazy-created by `focus_picks.vow_focus_pick_config()`.
- **`CharacterVowFocusPick`** (play state) - `character_role` (FK `CharacterCovenantRole`,
  CASCADE, `related_name="focus_picks"`), `pick` (CASCADE), `chosen_at`; unique
  `(character_role, pick)`. `clean()` runs `validate_character_focus_pick`.
- **`focus_pick`** (nullable FK, RESTRICT) on `VowAddedEffect`, `VowSituationalPerk` and
  `VowStatScaling` (#4783 moved it here from the removed `CovenantRoleActionScaling`). Null is
  the base vow. Each `clean()` refuses a pick from
  another role (`focus_pick_role_error`). `focus_pick` joined the `vow_added_effect_scope_unique`
  and `vow_stat_scaling_unique_role_target` keys (NULLS NOT DISTINCT) and both natural keys,
  so a picked row may repeat a base row's scope. `CovenantRoleTechniqueSpecialty` gets no link:
  the specialty is the vow's base identity.
- **`CombatStyle`** (NK `name`, `CreditedContent`, in `CONTENT_MODELS`) - `name`,
  `description`, `defense_style` (`DefenseStyle`), `armor_share_tenths` (0 to 10, default 10).
  A character's style is `CharacterSheet.combat_style` (nullable, PROTECT); it replaces the
  vow's `CovenantRoleDefenseProfile` (ADR-4759, read by `defense_style_for` since #4809).
  Since #4884 (slice 2 of #4844) a style also has `skill` (nullable one-to-one to a
  Magic-category `Skill`, PROTECT, one style per skill), `hit_stat` (nullable FK to a stat
  `Trait`, PROTECT), `taught_by` (M2M `Tradition`, `related_name="combat_styles"`) and
  `compatible_roles` (M2M `CovenantRole`, the vows it works with). **`CombatStyleGear`**
  (NK `(style, gear_archetype)`, unique, in `CONTENT_MODELS`) lists the kinds it fights with:
  weapon kinds (`WEAPON_ARCHETYPES`) are its attack profile, armor kinds
  (`ARMOR_ARCHETYPES`) its defense profile; its choices are those two sets only
  (`COMBAT_STYLE_GEAR_CHOICES`), never jewelry, clothing or other gear. The style admin page edits them all (gear kinds
  as an inline). Required content (TUNING): a style with no skill, no hit stat or no weapon
  kind, and an active Tradition that teaches no style.

### Price and choice rules (`world.covenants.focus_picks`)

- `pick_price(pick) -> int` - `max(1, floor(value x product(frequency_tenths / 10)) - sum(reduction))`.
  The product runs over `SELF`/`TARGET`/`SETTING`/`TIMING` limits, the sum over
  `EXPOSURE`/`COST`. Integer arithmetic; never stored. Value 4 with no limit is 4; with one
  `TARGET` limit at 5 it is 2. The formula itself is `price_for(value, limits)`, which the
  vow page (#4880) calls with the value and limits an unsaved edit would leave, to warn
  holders before the save.
- `shown_vow_level(membership) -> int` - the shown COVENANT_ROLE thread level, read on the
  anchor role through `services._covenant_role_thread_level` and `shown_thread_level`.
- `validate_character_focus_pick(choice)` - raises `ValidationError` naming the reason when
  the membership is secondary, the pick is not in the held role's, its anchor's or its
  resolved sub-role's catalog (`resolve_effective_role`), the pick level is above the shown
  vow level, or the level's chosen prices exceed `budget_per_level`.

- `chosen_pick_ids_by_holder(holder_ids) -> dict[int, set[int]]` - each holder's chosen
  pick ids, keyed by CharacterSheet pk, from one query; only memberships the holder has not
  left count. A holder with no pick is absent.
- `holder_has_pick(focus_pick_id, holder_id, chosen) -> bool` - True for a row with no pick
  (the base vow), else only when the holder chose it.

### Focus picks in play (#4806, slice 2)

Four readers apply `holder_has_pick` per (holder, row), and each reads the chosen picks
only when a row it fetched carries a pick, so a vow without picks costs no extra query:

- `added_effects.vow_added_effects_for_cast` - a gate in `_live_rows`, next to the unlock
  level. An unchosen pick row is not live, so a base row it `upgrades` stays for that
  holder. `vow_added_effects_on_technique` (the static view) lists a pick row only for a
  sheet that chose it.
- `perks.services._resolve_candidate_perks` - skips a pick perk for a holder who did not
  choose it, so `applicable_perks` and `dormant_perk_firings` both respect picks.
- `mechanics.services.vow_stat_scaling_bonus` - drops a pick `VowStatScaling` row the holder
  did not choose before summing, on a stat target and on a maneuver-effect target alike (so
  `effect_value` honours picks too).

The Sphinx catalog (`sphinx.py`) still lists every perk on a role, picked or not.

### Admin

CovenantRole admin carries a `VowFocusPickInline` with a read-only computed price; the
`VowFocusPick` admin has its limits inline and the price. `focus_pick` is an autocomplete on
the added effect, situational perk and vow stat scaling admins, and `condition_property` on the
situation and rung inlines and the added effect admin. `CombatStyle`, `VowFocusPickConfig`
and `CharacterVowFocusPick` (staff set picks until a player picker exists) have their own
admins; `combat_style` is on the CharacterSheet admin.

The vow page (`_vow_builder/<pk>/`, #4880, slice 2 of #4843) authors one vow's own fields,
technique specialties, focus picks by level and each pick's limits in one save, shows every
payload row as one line with its stock admin form in the popup, the budget per level and
the techniques the vow rides, and warns before a save that changes what live holders spend.
It is opened from a "Vow page" column and object tool on `CovenantRole` and the Combat
roles panel's vow picker. See `src/web/admin/CLAUDE.md` "Vow page".

Five Required content flags (#4906, `web/admin/tuning/combat_role_flags.py`) list a vow
with no picks, a holder over budget at a level, a pick with no payload row, and conditions
that are landed but never read or read but never landed, each linked to the vow page or
the condition's combo map, on the Missing combat content page (`_combat_content/`). Flags
only; nothing is refused for them.

## Enums / Constants

- **`MentorBondAdjusted`** (`TextChoices` in `world.covenants.constants`) —
  `MENTOR` / `SIDEKICK`: which party the encounter-scaling adjustment is applied to.
- **`MembershipStanding`** (`TextChoices` in `world.covenants.constants`, #2992) —
  `CORE` / `MINOR`: the durable membership tier. See "Minor covenant membership" above.
- **`VowEffectContext`** / **`VowEffectFrequency`** (`TextChoices` in
  `world.covenants.constants`, #4581) - where a vow added effect may fire (`ANY` /
  `IN_COMBAT` / `OUT_OF_COMBAT`) and how often one holder may fire it (`EVERY_CAST` /
  `ONCE_PER_ROUND` / `ONCE_PER_FIGHT`). See "Vow added effects" above.
- **`FocusPickLimitKind`** (`TextChoices`, #4759) - `SELF` / `TARGET` / `SETTING` / `TIMING`
  (priced by frequency) and `EXPOSURE` / `COST` (priced by a flat reduction), grouped by
  `FOCUS_PICK_FREQUENCY_LIMIT_KINDS` / `FOCUS_PICK_REDUCTION_LIMIT_KINDS`. See "Vow focus
  picks and combat styles" above.

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

### Combat style decides defense (#4809, slice 5 of #4759)

`world.covenants.defense`:

- `defense_style_for(character) -> DefenseResolution` (`style`, `armor_share_tenths`,
  `from_combat_style`). Resolution order: the character's `CombatStyle`, then the engaged
  PRIMARY vow profile from `engaged_primary_defense_profile`, then `(None, 10, False)`, the
  legacy behavior.
- `engaged_primary_defense_profile(character)` is the profile chooser, shared with
  `gear_additive_fraction` below: it picks the highest `gear_additive_tenths`, the first on a
  tie, and a sub-role falls back to its anchor's row.
- `NpcHitDefense` / `npc_hit_defense(...)` is the context `resolve_npc_attack` sets for a
  barrier or mitigation defender. `barrier_absorb_fraction(character)` rolls the barrier
  ward's check (called by `absorb_pool`). `mitigation_leak(character, soaked)` and
  `mitigation_tuning()` read `MovementConfig.mitigation_level_gap_cap` and
  `mitigation_leak_percent`, falling back to the field defaults when there is no row.

The behavior is documented in `docs/systems/COMBAT_DEFENSES.md`, "Defense styles".

### Style skill and hit stat on the rolls (#4884, slice 2 of #4844)

`world.covenants.style_fit`:

- `style_fit_for_attack(character, weapon_archetype) -> StyleFit` (a Strike always names
  its kind, bare hands being `UNARMED`; None is a technique cast with no weapon in hand,
  which skips the weapon test and keeps only the vow test) and
  `style_fit_for_defense(character) -> StyleFit` (every worn armor kind,
  `worn_armor_kinds`). `StyleFit(style, lapse: StyleLapse | None, lapse_note)` with
  `counts`, `hit_stat_name` and `extra_traits(check_type, counted)` (the style skill as an
  `ExtraTraitTerm`, weight 1, while it counts, and never when the roll already counts that
  trait through the check type's rows or another term, such as a technique skill that is
  also a style's skill).
- The bonus lapses on an attack when the weapon kind is not one of the style's weapon
  kinds, on a defense when any worn armor kind is not one of its armor kinds, and on both
  when a held vow (each engaged PRIMARY role; a sub-role counts by itself or its anchor) is
  not in `compatible_roles`. No vow held never lapses. `StyleLapse` (WEAPON, ARMOR, VOW)
  and `STYLE_LAPSE_GEAR_WORDS` live in `world.covenants.constants`.
- A lapse drops the style skill only: the hit stat and the defense type still apply, and
  the style's armor share is unchanged (owner rulings, 2026-11-01). No style, or a style
  with no active skill, adds no style term and no lapse line.
- Readers: `CombatTechniqueResolver.roll_check_with_breakdown` (the shared attack-roll
  seam: Strike, technique, joust) adds the term; a Strike also hits with `hit_stat`
  (`_stat_override`), a technique keeps its weapon's stat. `resolve_npc_attack` adds it to
  the PC defense roll and hands it to a barrier's re-roll (`NpcHitDefense.extra_traits`).
  A combat cast's TRAIT thread pulls (`pull_helpers._with_style_skill`) see the style
  skill's trait while it counts.
- The Strike records the style at roll time on `ConsequenceOutcome` (`style_name`,
  `style_skill_rating`, `style_lapse_note`, `stat_from_style`) and its hit-roll breakdown
  shows "the style's hit stat" and a style row, "style skill" with the rating or struck
  through (`RollLine.lapsed`) with the reason (`strike.style_roll_line`).
- The PC defense roll (`world.combat.services.npc.defense_roll`): `resolve_npc_attack`,
  handed the NPC action's `get_npc_action_interaction` factory, records one
  `ConsequenceOutcome` for the defender on that Narrator ACTION interaction
  (`record_defense_roll`), keeping `against_label` (the attacker), the defense skill rating,
  the style fields and `armor_share_tenths` at roll time. `defense_roll_breakdowns` lays it
  out ("Defense against <attacker>", defense skill, style skill or lapse, "Armor, N of 10",
  then the result). `ConsequenceOutcome.combat_roll_kind` (`CombatRollKind`: HIT, DAMAGE,
  DEFENSE, in `world.checks.constants`) says which roll a row is; both builders and the
  bystander rule key on it, so they never claim each other's rows. A check constraint
  (`consequence_outcome_style_snapshot_shape`) holds the style snapshot to no style, a
  counted style (rating, no lapse) or a lapsed one (reason, no rating).
  `combat_roll_breakdowns` (`world.checks.serializers`) serves both builders, defender and
  staff only; any other viewer gets a combat roll row without its modifiers or their total,
  and a defense row without its summary. An automatic dodge's bonus is recorded as a
  "Dodge" contribution. The result line names the roll's outcome, then the damage
  ("Partial Success, 8 damage"). A barrier's re-roll records no row. Every defended NPC
  blow now mints the NPC action's interaction (before, only a survivability roll did), and
  `create_npc_action_interaction` pushes it live, the way a PC's action row is.
- Every combat roll row records `ConsequenceOutcome.combat_round` (the Strike and defense
  recorders pass it; any other combat row reads it from the scene's encounter), and the
  turn panel's Last Outcome card shows every roll of the newest round.
- Not yet: `is_gear_compatible` still reads the vow's `GearArchetypeCompatibility` (slice
  3 re-keys it with the data migration).

### Defense styles + gear substitution (#2533, ADR-0149 Layer 3)

`gear_additive_fraction(character)` (`world.covenants.services`) returns the MAX
`gear_additive_tenths` fraction (as `Decimal`, e.g. `Decimal("0.3")`) across the
character's engaged PRIMARY roles' resolved `CovenantRoleDefenseProfile` rows
(#2641 — a secondary vow's defense profile never substitutes for gear). Per
engaged role, the profile resolves to the role's own row when present, else its
anchor's; no engaged role has a profile at all → `Decimal(1)` (legacy
fully-additive behavior, byte-identical to pre-#2533). One batched query over the
role + parent pks — no per-role query loop.

With no combat style (#4809), `apply_equipped_armor_soak` (`world.combat.services`,
#1174) applies the fraction to the COMPATIBLE armor bucket only, once, right after the role-compatibility
split and before the compatible-additive/incompatible-max blend:

    compat_soak = int(compat_soak * gear_additive_fraction(character))
    soak = compat_soak + max(incompat_physical, resonant)

The resonant pool and the incompatible-`max` branch are untouched — gear is
physical and counts once; a character holding multiple engaged vows gets the most
gear-friendly one's fraction, not a stack of fractions. Durability still wears on
every compatible piece whose (now-scaled) soak contributes to the result,
unchanged from #1174.

### The Insight rider (#2645)

The Know need's (scout/loremaster vows) once-per-fight ace. `InsightTableEntry`
(NK `["name"]`, `covenants.insighttableentry` in `CONTENT_MODELS` — lore-repo
content, never seeded in arxii) is a curated table of large, narrowly-scoped,
ONE-ROUND effects: `prose` (announced reading, `{caster}`/`{target}`
placeholders), `condition` FK → `conditions.ConditionTemplate` (PROTECT —
author a one-round `default_duration_value` on the condition itself),
`target_kind` (`InsightTargetKind`: SELF/ALLY/TEAM), `weight`
(weighted-random draw), `is_active`. **Never instant-win** — enforced
editorially by curation of the `condition` rows, not an engine check.

`CovenantRole.grants_insight` (BooleanField) is the rider flag — an engaged
role grants it, and a sub-role without its own grant rides an engaged
parent's (mirrors every other role-scoped flag in this table).
`CombatParticipant.insight_used` (`world.combat.models`) is the once-per-
encounter stamp — a per-encounter row needs no reset machinery.

`world.covenants.insight.maybe_produce_insight(caster_sheet, technique,
resolution_participant) -> bool` is the rider service, hooked into
`world.combat.services._resolve_pc_action` right after a focused technique
cast resolves (`_maybe_produce_insight_for_cast`, best-effort/failure-
isolated like the sibling `_maybe_suggest_entrance_dramatic_moment`). Fires
when: the resolved technique carries the PERCEPTION `magic.TechniqueFunctionTag`;
the caster has an active engaged `CharacterCovenantRole` whose role (or that
role's parent) has `grants_insight=True`; and the participant hasn't used
their Insight this encounter. On success: draws a weighted-random active
entry, resolves targets by `target_kind` (ALLY → the cast's declared
`CombatRoundAction.focused_ally_target`, falling back to the caster; TEAM →
every ACTIVE `CombatParticipant` in the encounter; SELF → the caster),
applies the entry's condition via `conditions.services.apply_condition`
(`source_character=caster`), announces the entry's prose on BOTH channels
(`combat.interaction_services.broadcast_action_outcome` for the WS payload +
a direct `encounter.room.msg_contents` call for telnet parity — mirrors
`world.combat.escalation`'s room-wide surge narration), and stamps
`insight_used=True`.

Distinct in weight from the light "Look out!" callout (#2637): the callout
is frequent/small/names-no-counter; the Insight is rare/large/specific. Not
a `VowSituationalPerk` — the Insight is a single random draw gated by a
boolean role flag, not the deterministic Layer 4 perk machinery above.

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
- `MinorStandingRequiresSecondaryEngageError`, `MinorStandingDuranceOnlyError` (minor
  covenant membership, #2992 — see "Minor covenant membership" above)
- `CovenantTreasuryError` (base) → `NotAnActiveCovenantMemberError`,
  `NotAuthorizedToSpendCovenantTreasuryError`, `CovenantTreasuryTransferError`
  (covenant treasury, #2992 — see "Covenant Treasury" above)

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
  to `ATTACKER_AFFINITY` (now authorable against all three affinity rows), and
  `CombatEncounter.initiated_by_pc_side` — the new initiator-side capture `origin_side`-
  parameterized situations read (stamped `True` at CREATE by every PC-cast encounter path;
  `False` is admin/GM-stampable in v1, honestly `NULL`-heavy until an NPC-initiated-encounter
  service exists). All 14 pre-#2623 situation rows behave byte-identically (parameterless =
  the parameterless default of each parameterized family). **#2646** followed up with a 15th
  situation, `ON_CHOSEN_GROUND` — "the fight was won yesterday": a new `room_features
  .PreparedGround` model (OneToOne `prepared_by` — one active prepared ground per character;
  re-preparing elsewhere MOVES it, never stacks a second row) recorded by `world.covenants
  .perks.services.record_ground_preparation_from_cast`, a RIDER (no new player verb) on an
  out-of-combat standalone cast of a PERCEPTION-tagged technique, gated on a new
  `CovenantRole.prepares_ground` data-authored flag on an active engaged role and on the caster
  NOT currently being an active `CombatParticipant` anywhere. `world.combat.chosen_ground
  .compute_on_chosen_ground` stamps the new `CombatEncounter.on_chosen_ground` at CREATE time
  (mirroring `is_champion_duel`'s shape exactly) in the three PC-vs-NPC encounter-creation seams
  — `seed_or_feed_encounter_from_cast`, `create_lethal_duel`, `open_place_encounter` —
  whenever the encounter's room holds a `PreparedGround` whose preparer is physically present;
  `create_pvp_duel` deliberately never stamps it (PvP is never lethal).

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
- `treasury.py` — `covenant_treasury`, `deposit_covenant_funds`,
  `withdraw_covenant_funds` (#2992)
- `added_effects.py` / `added_effect_summary.py` - the vow added effect read seam and the
  plain-words summary (#4581)
- `exceptions.py` — all exceptions

`src/actions/definitions/covenants.py` — nine covenant lifecycle REGISTRY Actions (seven
membership/rank lifecycle actions + `DepositCovenantFundsAction`/`WithdrawCovenantFundsAction`,
#2992)

`src/commands/covenant.py` — `CmdCovenant` telnet namespace

`src/commands/ritual_adapters.py` — `SoulTetherAdapter`, `CovenantInductionAdapter`,
`BannerCallAdapter` + `get_adapter(ritual)` registry lookup

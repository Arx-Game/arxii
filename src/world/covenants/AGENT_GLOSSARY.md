# Covenants glossary

**Covenant**:
A magically-empowered group oath — a blood-bound pact that binds its members under shared roles and goals. It is a per-kind extension of an `Organization` (a `Covenant` always has a backing org and shares its pk), scoped by a `CovenantType`.
_Avoid_: guild, faction, party.

**Covenant of the Durance**:
The `CovenantType.DURANCE` covenant — the default, life-journey kind of oath, distinct from a battle covenant. "Covenant of the Durance" is the display label of that type.
_Avoid_: a Durance, durance covenant.

**War Covenant / Covenant of Battle**:
The `CovenantType.BATTLE` covenant — an oath sworn to a martial cause. A STANDING one can stand down into dormancy and *rise again* through a "call the banners" rise ritual; a CAMPAIGN one dissolves when its defining story concludes.
_Avoid_: setting active=true / "activating" a covenant (a dormant covenant rises via ritual, it is not flipped on).

**Covenant of the Court**:
The `CovenantType.COURT` covenant — a master/servants oath: a single powerful leader and the servants/apprentices/acolytes sworn to them across a wide power gulf (by design ≥1 power tier), explicitly not a co-adventuring party (e.g. "the Court of Shadows" serving the Shadowlord). Lets a peerless puissant hold a covenant role. (ADR-0057.)
_Avoid_: retinue covenant (descriptive only), guild, household, mentor bond.

**Court Pact**:
The per-(Court covenant, servant) sworn-fealty bond (`CourtPact` in `world/covenants/models.py`).

**Court summons**:
A directed-offer summons from a Court master's role targeting a specific
servant (#2050). The servant accepts (starting the mission run with court
engagement + grant-ceiling credit) or declines (dropping affection + bumping
the refusal streak). Three refusals fire the master's escalation pool. The
primitive is generic on `npc_services` — any `NPCRole` can direct an offer; the
Court layer contributes its escalation config (`CourtGrantConfig
.summons_refusal_escalation_threshold` / `.summons_refusal_escalation_pool`).
See ADR-0102.
Active while `released_at IS NULL`; at most one active pact per `(covenant, servant_sheet)`
(partial-unique constraint). Carries `granted_pull_cap` — the master-set ceiling on the servant's
Court-role thread pull level. A servant with no active pact has an effective cap of 0 and cannot
pull their Court-role thread at all; the grant is the gate. Sworn via `swear_court_pact`; released
via `release_court_pact`; queried via `active_court_pact_for`.
`granted_pull_cap` is negotiable post-swearing (#1718) via a formal petition
(`OfferKind.COURT_GRANT`) or an emergency thread-bond draw — both monotonic, never decreasing.
_Avoid_: mentor bond, patron, indenture.

**Court mission / mission-driven engagement**:
The engagement gate for a Court servant: `can_engage_membership` is True iff EITHER (a)
`has_active_court_mission(character_sheet, covenant)` — the character is a
participant in an ACTIVE `MissionInstance` whose `source_offer.role.faction_affiliation`
matches the Court's backing organization — OR (b)
`has_regarded_target_present(character_sheet, covenant)` — a persona the
Court's leader holds a nonzero `NpcRegard` opinion of (favorable or hostile) is
co-present in the servant's current scene (#1717). Both are scene-wide, not
per-technique or per-target — a servant may only engage their Court role while
on active business for the Court's org, or while someone their master cares
about is right there with them.
_Avoid_: mission assignment (use "Court mission").

**Court Regard Pull Modulation**:
The Court covenant's stake in the magic app's Pull Target Modulation seam
(#1831): a Court servant's COVENANT_ROLE thread pull can be empowered by scaling
off the Court leader's signed `NpcRegard` (#1717) for the pull's live target,
sign-directed by the pull effect's authored Regard Polarity (offensive/protective/
neutral). Full entry: magic app glossary ("Regard Polarity", "Court Regard
Modulation", "Pull Target Modulation").
_Avoid_: regard bonus (ambiguous — regard itself is signed, but the polarity
match is what gates empowerment, not the raw value).

**Covenant Role**:
The combat-power axis of membership: a role's Sword/Shield/Crown combat-identity blend (`sword_weight`/`shield_weight`/`crown_weight`, summing to 1 on primary roles — not a single archetype pick, #2529, ADR-0149), speed_rank, role bonuses, and COVENANT_ROLE Thread-pull eligibility. Orthogonal to authority.
_Avoid_: rank, position, office, archetype (retired single-enum field).

**Technique Specialty**:
A role's per-vow reward for casting techniques carrying a specific `magic.TechniqueFunction` label (`CovenantRoleTechniqueSpecialty`, NK `(covenant_role, function)`, `multiplier_tenths`) — **Layer 2** of ADR-0149's four-layer vow-power model. Unlike the combat-identity blend above, valid on both primary roles AND sub-roles, and a sub-role's rows ADD to the parent's rather than replacing them (a specialized/promoted member reads as strictly more specialized). Read by `covenant_role_specialty_power_term` (`world.magic.services.power_terms`). See the magic app glossary's "Technique Function" for the shared vocabulary. (#2443, ADR-0149's 2026-07-20 amendment.)
_Avoid_: conflating with the combat-identity blend (a coarser SWORD/SHIELD/CROWN axis) or with role-granted specialized technique *variants* (`CharacterTechnique.role_source`, a different #2022 mechanism).

**Defense Style**:
`DefenseStyle` (`world.covenants.constants`, #2533, ADR-0149 Layer 3) — how a covenant vow
defends: GEAR_SOAK (armor is the defense), EVASION (not being there is the defense), BARRIER
(force/warding is the defense). Code-defined vocabulary, not lore-repo content — Layer 4's
situational perks (#2536) key on these labels, and each style must have a distinct
shine-situation in that perk set (2026-07-20 niche ruling; exact tuning numbers are secondary).
_Avoid_: defense type, defense mode, archetype.

**Defense Profile**:
`CovenantRoleDefenseProfile` (#2533) — the per-`CovenantRole` row carrying a role's Defense
Style plus `gear_additive_tenths`, the fraction of COMPATIBLE armor soak that stays additive
with the vow's own defense (default 10 = fully additive/legacy). Read via
`gear_additive_fraction(character)`, which takes the MAX fraction across a character's engaged
roles' resolved profiles (sub-role's own profile when present, else its anchor's) and scales the
compatible-armor bucket once in `apply_equipped_armor_soak` (#1174). Superseded `VowGearScaling`
as the mechanism for a vow's defense to substitute for gear rather than stack with it.
_Avoid_: gear profile, armor profile, VowGearScaling (removed model).

**Situation**:
A code-defined label (`world.covenants.perks.constants.Situation`, a `TextChoices`) naming a precise, testable game-state condition a `VowSituationalPerk` can key on — e.g. `AT_RANGE`, `TARGET_DISTRACTED`, `ALLY_LOW_HEALTH`. Each value has exactly one registered evaluator (`world.covenants.perks.evaluators.SITUATION_EVALUATORS`, signature `(SituationContext) -> bool`). Adding a new Situation to the library is a code change (one enum value + one evaluator); attaching an existing Situation to a perk is a content edit forever after (#2536, ADR-0151, ruling 5).
_Avoid_: condition (that's `conditions.ConditionInstance`, a different, stateful applied-effect system a Situation evaluator may READ but never IS), trigger (Situations are polled/evaluated, not event-subscribed).

**Situational Perk**:
`VowSituationalPerk` — a `CovenantRole`-authored, deterministic bonus that fires when its attached Situations all hold (AND composition) for the ACTING character's resolution moment (a cast or a check), never on the perk-holder's own timer — **Layer 4** of ADR-0149's four-layer vow-power model, "the point of vows." Carries a `beneficiary` (SELF/COVENANT_ALLIES/WHOLE_GROUP — group-granting perks are first-class, not an edge case), an `effect_kind` (all four values live: POWER_BONUS/CHECK_BONUS shipped slice 1; TIER_FLOOR/BOTCH_IMMUNITY wired slice 2 — see Outcome Guarantee), an `announce_template`, and (TIER_FLOOR-only) a `floor_success_level`. Valid on both primary roles and sub-roles — a sub-role's perks ADD to the anchor's, mirroring Technique Specialty's ADD semantics, never Layer 1's anchor-only rule. No negative magnitudes anywhere (`PositiveIntegerField` — structural): a vow's weakness is the absence of a beneficial perk in that situation, never a malus. (#2536, ADR-0151/ADR-0152.)
_Avoid_: proc, buff (both imply chance or unconditional — a Situational Perk is deterministic and conditional by design), trait.

**Perk Rung**:
`VowSituationalPerkRung` — an escalation tier on top of a `VowSituationalPerk`'s base Situations (e.g. a defense perk that intensifies further when allies are hurt, further still against Abyssal attackers). Resolution is strictly cumulative: rung N's required Situations = the perk's base Situations ∪ the extra Situations of rungs 1..N, so a higher rung can never fire without every lower rung's condition also holding; the highest qualifying rung's `magnitude_tenths` REPLACES the base value (never sums with it). (#2536, ADR-0151.)
_Avoid_: tier (ambiguous with power/opposition tiers elsewhere), level (that's thread level, a different scaling axis Perk Rungs sit on top of, not instead of).

**Outcome Guarantee**:
A `TIER_FLOOR` or `BOTCH_IMMUNITY` `VowSituationalPerk` firing and raising a `perform_check` outcome to an authored floor — Apostate's can't-botch principle (ruling 3): a character's specialization shouldn't be able to botch at the thing their vow is for. ABSOLUTE, never thread-scaled and never thread-gated (unlike `POWER_BONUS`/`CHECK_BONUS`, which do both) — a low-thread holder's guarantee is exactly as reliable as a high-thread holder's. Resolved by `world.checks.services._apply_outcome_guarantees`, called AFTER the outcome is determined (both the rolled and test-rig forced paths), and announces only when it actually altered the outcome (not merely eligible). (#2536 slice 2, ADR-0152.)
_Avoid_: bonus, buff (both imply an additive numeric change — a guarantee is a floor substitution, never additive).

**Tier Floor**:
`PerkEffectKind.TIER_FLOOR` — an Outcome Guarantee kind: the resolved `success_level` cannot land below the perk's authored `floor_success_level` (canonical −10..+10 scale, `VowSituationalPerk`-only field, `clean()`-required on TIER_FLOOR rows and rejected on every other `effect_kind`). The replacement outcome is the current `ResultChart`'s lowest outcome at/above the floor, falling back to the global `CheckOutcome` table, or a no-op if none is authored. (#2536 slice 2, ADR-0152.)
_Avoid_: result tier, OutcomeTier (retired enum — see `world.magic.services.sanctum_install`'s historical `CRITICAL_FAILURE_SUCCESS_LEVEL`; do not resurrect the name for this field).

**Botch Immunity**:
`PerkEffectKind.BOTCH_IMMUNITY` — an Outcome Guarantee kind sharing `TIER_FLOOR`'s floor mechanism with no field of its own: it binds only when the raw outcome is already a botch (`success_level <= world.checks.constants.BOTCH_SUCCESS_LEVEL_MAX`, the centralized botch-boundary constant) and floors it at the least-bad non-botch level (`BOTCH_SUCCESS_LEVEL_MAX + 1`). Never suppresses a botch silently — it downgrades to a plain failure and announces the perk that did it. (#2536 slice 2, ADR-0152.)
_Avoid_: crit immunity, botch protection (both suggest prevention rather than the downgrade-after-the-fact this mechanism actually performs).

**Beneficiary (perk)**:
The `PerkBeneficiary` axis on a `VowSituationalPerk` (SELF / COVENANT_ALLIES / WHOLE_GROUP) deciding who benefits when the perk fires at ANOTHER character's resolution moment: SELF fires only for the perk-owning holder's own actions; COVENANT_ALLIES fires for a co-present covenant-mate's action but structurally excludes the holder's own; WHOLE_GROUP fires for both. "Covenant-mate" here means a non-departed role (`left_at__isnull=True`) in a covenant the ACTING character is actively engaged in, AND physical co-presence for this resolution (same combat encounter / same active Scene) — the CANDIDATE mate's own `engaged` flag is irrelevant (#2536 reversal, Tehom 2026-07-20, ADR-0152: a KO'd or disengaged mate still in the fight keeps contributing group perks, so losing allies mid-encounter never weakens the survivors — no death-spiral); the ACTING character's own engagement is still required (stark-power rule, untouched). A member sharing a covenant but not co-present, or who left the encounter (FLED/REMOVED), does not extend or receive group-beneficiary perks (#2536, ADR-0151/ADR-0152 — see `world.covenants.perks.services`'s module docstring for the deliberately different provenance-situation rule).
_Avoid_: recipient, target (Situation's own `target` field is the acting character's action target, an unrelated concept — do not conflate).

**Perk Scope**:
A `VowSituationalPerk` column narrowing WHEN a fired perk applies, distinct from a Situation
(which asks whether the game state itself holds): `mission_category`/`mission_template` (FKs,
CHECK_BONUS-only) and `battle_action_kind` (`BattleActionKind` CharField, CHECK_BONUS or
POWER_BONUS only) — `clean()` rejects each column authored outside its valid `effect_kind`
set. Every non-empty scope column on a row must match (AND); an empty scope always matches.
Checked by `perk_scope_matches` (`world.covenants.perks.services`), the single seam both fired-
perk delivery providers filter through. (#2536 slice 3, ADR-0153.)
_Avoid_: filter, condition (both are used elsewhere for different mechanisms — Scope is
specifically these three typed columns, not a general predicate).

**Champion Duel (situation)**:
`Situation.CHAMPION_DUEL` — holds when the SUBJECT is a participant in a `CombatEncounter` whose
`is_champion_duel` flag is True, stamped exclusively by `world.battles.services
.open_champion_duel` (never by the siege-engine skirmish path, which shares the same duel
helper but carries no Champion-role requirement). A Situation, not a Perk Scope — see ADR-0153
for why. (#2536 slice 3, Battle wiring.)
_Avoid_: duel scope, battle scope (this is evaluated as game state, not authored as a scope
column).

**Combat Opened From Parley**:
`Situation.COMBAT_OPENED_FROM_PARLEY` — holds for the entire lifetime of a `CombatEncounter`
whose `opened_from_parley` flag is True, stamped by `world.combat.cast_seed
.seed_or_feed_encounter_from_cast` only when it CREATES (never feeds) an encounter from a
hostile cast landing inside an active, non-Battle-backed Scene — "this fight started as a
conversation that turned hostile." v1 approximation: the flag never clears once set, even long
after the fight's opening moment has passed. (#2536 slice 3, Task 4.)
_Avoid_: ambush (a related but narrower/stricter situation — see Ambush Underway below; the two
are not synonyms, `opened_from_parley` alone is one of two OR'd triggers for it).

**Ambush Underway**:
`Situation.AMBUSH_UNDERWAY` — holds only during ROUND 1 of a `CombatEncounter` that opened as a
surprise: either `opened_from_parley` is True, or a round-1 `CombatRoundAction` with
`from_entrance=True` exists (a dramatic technique-entrance opener, #2183). False from round 2
on regardless of how the fight opened — a documented v1 approximation trading precision for
zero new polling machinery. (#2536 slice 3, Task 4.)
_Avoid_: surprise round, first strike (neither is this codebase's vocabulary for the mechanic).

**Ally Intercepted for Me**:
`Situation.ALLY_INTERCEPTED_FOR_ME` — holds when a covenant-mate of the HOLDER, co-present in
the SUBJECT's encounter, has an armed (`is_ready=True`) INTERPOSE declaration THIS round
targeting the subject specifically or guard-anyone (`focused_ally_target=None`). Ratified v1
judgment call: DECLARED-guard semantics — "the guarded moment is the situation," it does not
wait for the interpose to actually intercept damage (see ADR-0153 for the rejected
fired-marker-persistence alternative). Uses the same covenant-mate batching Ally Low Health
uses (one declarations query + one batched membership query, no queries in loops). (#2536
slice 3, Task 5.)
_Avoid_: guarded, protected (too generic — this is specifically an ARMED DECLARATION, not a
resolved block).

**Attacker Affinity**:
`Situation.ATTACKER_AFFINITY` (renamed from its original Abyssal-only situation, parameterized
#2623) — holds
when the DEFENSE-side `SituationContext.attacker` is typed to the row's authored `affinity` axis
(required Situation Parameter, one of `AffinityType.CELESTIAL/PRIMAL/ABYSSAL` — no longer
hardcoded to Abyssal). A `CombatOpponent` with a non-empty authored `affinity` matching the row's
axis is definitional (checked first, `threshold_percent` ignored); otherwise falls back to a
reachable `ObjectDB`'s `CharacterAura` — with `threshold_percent` set, that axis's Decimal
percentage must be ≥ the threshold; unset, the aura's `dominant_affinity` must equal the axis
(the pre-#2623 behavior, now the parameterless default). `None` — and this Situation False — on
every offense-side resolution, where `attacker` is never populated. The first Situation to read
the Defense-Side Seam (below). (#2536 slice 3 Task 6; renamed + parameterized #2623, ADR-0154.)
_Avoid_: attacker abyssal (superseded name — the family now covers all three axes, not only
Abyssal); target abyssal/target affinity (Situation's `target` field is the acting character's
OWN action target — an unrelated concept on offense; `attacker` is the incoming threat on
defense).

**Chosen Ground (situation)**:
`Situation.ON_CHOSEN_GROUND` — holds when the SUBJECT is a participant in a `CombatEncounter`
whose `on_chosen_ground` flag is True — "the fight was won yesterday." Mirrors Champion Duel's
shape exactly: one cached FK read off the resolution's participant, False outside combat.
Stamped exclusively at encounter-CREATE time by `world.combat.chosen_ground
.compute_on_chosen_ground`, called from the three PC-vs-NPC encounter-creation seams
(`seed_or_feed_encounter_from_cast`, `create_lethal_duel`, `open_place_encounter`) — never by
`create_pvp_duel` (PvP is never lethal). True iff the encounter's room holds a `Prepared
Ground` whose preparer is physically present there. (#2646.)
_Avoid_: home field, terrain advantage (this codebase's term is Chosen Ground / Prepared
Ground, not a generic RPG "home turf" bonus).

**Prepared Ground**:
`world.room_features.models.PreparedGround` — a room a character has readied as their
battleground ahead of time. Plain FK to `RoomProfile` (a room may hold several characters'
prepared grounds) but `prepared_by` is a OneToOne to `CharacterSheet` — one active prepared
ground per character; re-preparing elsewhere MOVES the row (`update_or_create`), never stacks
a second one. Recorded by `world.covenants.perks.services
.record_ground_preparation_from_cast` — a RIDER on an out-of-combat standalone cast of a
PERCEPTION-tagged technique by a character holding an active engaged `CharacterCovenantRole`
whose `covenant_role.prepares_ground` flag is set (data-authored — not every role prepares
ground). "The vow never hands you a new verb": this is not a new player action, it answers to
an existing one (the cast). Consumed by Chosen Ground's evaluator via `CombatEncounter
.on_chosen_ground`. (#2646.)
_Avoid_: scouted location, home base (this codebase's term is Prepared Ground).

**Defense-Side Seam**:
The evaluation point making situational perks reachable on a defender's OWN roll, not only the
attacker's: `SituationContext.attacker` (populated only here, `None` on every offense-side
resolution) threaded by `world.combat.services.resolve_npc_attack` into the defender's real
`perform_check` call — the ONLY defense-check site doing so in v1. Reuses the existing
`applicable_perks`/`_PerkResolver`/delivery-seam machinery rather than a parallel defense
pipeline (see ADR-0153's rejected alternative). Makes CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY
perks — including `ATTACKER_AFFINITY`-gated ones — fire on defense for the first time. (#2536
slice 3, Task 6, ADR-0153.)
_Avoid_: defense pipeline (there is no separate one — that was the rejected design).

**Situation Parameters / `SituationParams`**:
The typed knobs authored on ONE situation-requirement row (`VowSituationalPerkSituation` or
`VowSituationalPerkRung`), carried via `SituationRequirementMixin` (`world.covenants.models`,
#2623): `threshold_percent` (0-100, percent-shaped floors — aura-axis floor, ally-health
fraction), `count_threshold` (count-shaped floors — surrounded lock count, minimum affection),
`affinity` (`AffinityType` axis selector for attacker typing), `origin_side`
(`SituationOriginSide` — see below). Which situation reads which params — and which it
REQUIRES — is `SITUATION_PARAM_SPECS` (`world.covenants.perks.constants`); the mixin's `clean()`
enforces both directions, mirroring the per-effect-kind gating already on
`VowSituationalPerk.clean()`. Null/blank on every field = the pre-#2623 parameterless behavior
(the evaluator's module-constant default) — parameterless rows are byte-identical to before
#2623, not a breaking change. `.params` (a property on the mixin) builds the frozen, hashable
`SituationParams` dataclass (`perks/context.py`) an evaluator actually reads; `_PerkResolver`
keys its evaluation cache on `(situation, params, holder_pk)` so a rung can re-require the same
situation at a tighter parameter than its base row. See ADR-0154.
_Avoid_: situation config, situation options (this codebase's term is Situation Parameters,
plural columns on the requirement row itself — not a separate config object).

**`SituationOriginSide`**:
The `TextChoices` (`world.covenants.perks.constants`, #2623) an `origin_side` Situation
Parameter takes: `OURS` ("our side sprang it") or `THEIRS` ("their side sprang it"), blank =
side-blind (today's pre-#2623 behavior). Read by `AMBUSH_UNDERWAY`/`COMBAT_OPENED_FROM_PARLEY`
against `CombatEncounter.initiated_by_pc_side` (below) — `OURS` requires
`initiated_by_pc_side is True`, `THEIRS` requires `is False`, and a `NULL` initiator with a
non-blank `origin_side` means the situation does not hold (direction unprovable, never guessed).
v1 side model: the subject is always a PC, so PC-side = "ours" — a PvP refinement is out of
scope until PvP encounters thread perks at all. See ADR-0154.
_Avoid_: attacker side, defender side (this axis is about who OPENED the encounter, not who is
attacking/defending within it — a different question from `SituationContext.attacker`).

**`initiated_by_pc_side`**:
`CombatEncounter.initiated_by_pc_side` (`world.combat.models`, #2623) — `BooleanField(null=True)`
recording who sprang a fight: `True` = a PC participant's action opened it, `False` = the
opposing side did, `NULL` = unknown/undirected (duels, battles, staff-opened). Stamped `True`
unconditionally by `world.combat.cast_seed.seed_or_feed_encounter_from_cast` at CREATE — every
verified encounter-creation path today is PC-cast, so no code path can stamp `False` yet; that
gap is recorded honestly in ADR-0154 rather than papered over with an invented NPC-aggression
system. `False` is admin/GM-stampable in v1 (exposed in combat admin); the first
NPC-initiated-encounter service to land stamps it at creation. Read by `origin_side`-parameterized
situations (above).
_Avoid_: aggressor, first_mover (this codebase's field name is `initiated_by_pc_side` — a
PC/NPC-side fact, not a per-participant aggressor flag).

**Dormant Vow**:
An active `CharacterCovenantRole` membership that is currently DISENGAGED — the vow still
exists, but its Situational Perks do not fire while it sits unengaged. Ruling 2's "loud OFF
state" (#2536 slice 3, Task 7, ADR-0153): rather than silently doing nothing, a dormant vow
that WOULD have answered a resolution announces so — see Dormant Perk Firing below. A mate's
own dormancy is invisible to this mechanism entirely (only the SUBJECT'S OWN disengaged
memberships are ever dormant-checked — never a co-present ally's).
_Avoid_: inactive covenant, un-sworn (a dormant VOW is still sworn and still active — only its
`engaged` flag is False; do not conflate with "setting active=true" language the War Covenant
entry above already warns against for a different mechanic).

**Dormant Perk Firing**:
The result of `dormant_perk_firings` (`world.covenants.perks.services`) — every
`VowSituationalPerk` on the subject's own Dormant Vow(s) that WOULD have fired (same
`_PerkResolver` situation evaluation plus the Task-1 Perk Scope filter) had the role been
engaged. `announce_dormant_perks` delivers the exact line `"your vow lies dormant —
{perk.name} would have answered here"` to the HOLDER ALONE (a WHISPER-mode `Interaction` +
direct telnet `.msg()`) — NEVER the room, deliberately unlike `announce_fired_perks`'s room
broadcast for a LIVE firing (see ADR-0153 for why: a live firing is a spectacle for the scene, a
dormant notice is a private diagnostic for the one player it concerns). Wired into all three
fired-perk delivery seams, right after each one's own live `applicable_perks` call. Zero extra
queries when nothing is disengaged. (#2536 slice 3, Task 7, ADR-0153.)
_Avoid_: fired perk, live firing (the opposite concept — a Dormant Perk Firing is exactly the
firing that did NOT happen).

**Covenant Rank**:
The administrative-authority axis of membership: a per-covenant tier on the rank ladder (lower tier number = higher authority) whose capability flags gate invite / kick / manage / lead-rituals / request-gm. Orthogonal to Role. `can_lead_rituals` gates who may perform Covenant Sanctification and future covenant-led group rites (#708).
_Avoid_: role, level.

**GM Request (rank capability)**:
`CovenantRank.can_request_gm` (#2119) — the authority to post an open, broadcast
`GroupStoryRequest` asking any registered GM to run a story for the covenant.
Deliberately a *separate* flag from `can_invite`: admitting a member into the
covenant and petitioning an outside GM for oversight are different decisions,
and conflating them would let a recruiter unilaterally commit the covenant to
outside authority. See `world/stories/AGENT_GLOSSARY.md`'s "Group Story
Request" for the request lifecycle this flag gates.
_Avoid_: can_invite (a distinct, narrower authority — see above), recruiter flag.

**Command Tier**:
The battle-command hierarchy axis of a `CovenantRole` (`command_tier`, #1710) — a
third axis alongside Role (combat power) and Rank (administrative authority),
settable only on `CovenantType.BATTLE` roles. See the battles app glossary for the
full Supreme/Subordinate Commander vocabulary.
_Avoid_: is_leadership (removed under #1027 — do not revive), rank.

**Champion (role flag)**:
`CovenantRole.is_champion_role` (#1710) — marks a Battle covenant role as eligible
to open/answer a single-combat duel for the covenant. See the battles app glossary
for "The Champion."
_Avoid_: duelist role, hero role.

**Mentor's Vow / Mentor Bond**:
A consensual bond pairing a higher-level mentor with a lower-level sidekick so a level-mismatched party scales fairly; the `MentorBond` record is active while `dissolved_at` is null.
_Avoid_: master/apprentice (a future flavor display-label only, with no model surface), patron, sponsor.

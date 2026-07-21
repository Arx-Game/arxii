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

# Missions glossary

**Mission**:
An authored branching graph of decision nodes a character undertakes, drawn from a `MissionTemplate` and run as a `MissionInstance` (the live run, whose state is just its current node plus durable snapshots and recorded deeds — no state blob). The umbrella term for the system; "Mission" names the concept, with template-vs-instance distinguishing the static graph from a play-through.
_Avoid_: quest, job, task.

**MissionTemplate**:
An authored mission: the static node graph (entered at its single entry node) plus its availability metadata — level band, risk tier, draw weight, arc scope, and visibility. The reusable definition that `MissionInstance` runs.
_Avoid_: mission definition, quest template.

**Mission Deed**:
A `MissionDeedRecord` — one recorded consequential act taken within a mission run, attributed to the acting participant's character (moral and narrative consequence follows the actor). Its structured payouts are stored as child `MissionDeedRewardLine` rows rather than a dict.
_Avoid_: deed log, mission action, consequence record.

**Mission Report**:
The after-action step that pays out a mission (#1753). A run that has someone to report to reaches `RESOLVED` at resolution instead of `COMPLETE`, then pauses until the reporter returns to a co-located report-to **Functionary** (the `report_to_role`, #1766) and reports — at which point money is delivered and the run transitions `RESOLVED → COMPLETE`. A run with no report target completes directly at resolution (legend spreads, no coin). Lives in `world.missions.services.report`.
_Avoid_: turn-in, hand-in, mission payout.

**Report Style**:
How the reporter frames the account when reporting (`ReportStyle`), modulating the payout — legend stays flat; only money and fame/prestige move. **Humble** (understate): +1 Bene resonance, lower fame/prestige, baseline money. **Accurate** (neutral): the promised money + fame/prestige. **Embellished** (aggrandize): a manipulation check against the giver (charm + Persuasion, +Manipulation specialization if held) — success doubles the money, raises fame/prestige, grants +1 Insidia; only offered to a reporter with Persuasion. **Mostly-accurate** (omit incriminating): dodges criminal/society consequences; inert until heat lands (#1765), so not offered yet.
_Avoid_: spin, brag, framing.

**Mission Risk Acknowledgement**:
A `MissionRiskAcknowledgement` row (#1770 PR4) — the accepting persona's on-record "yes, I know this job is dangerous," keyed on (offer, persona) with the template's `risk_tier` snapshotted. Required by `issue_mission` for any template at or above `MISSION_RISK_ACK_TIER` (`world.missions.constants`); missing → the typed `MissionRiskUnacknowledgedError`, which the `npc_resolve` action turns into an informed-consent prompt re-run with `acknowledge_risk=yes`. The mission sibling of combat's `EncounterRiskAcknowledgement` (#777 gate).
_Avoid_: risk waiver, danger consent (consent is the ADR-0024 app), risk opt-out.

**Tale**:
A `MissionRunTale` (#2047) — a player-authored epilogue for a mission run. Free text, one per participant per run, written after the run reaches a terminal status (RESOLVED/COMPLETE/ABANDONED). Permissive-canonicity policy (ADR-0105): canon by default, never parsed for mechanics, never content-gated. On legend-minting runs, the tale seeds the author's `LegendDeedStory` for unstoried `LegendEntry` rows linked to the run's deeds.
_Avoid_: epilogue writeup, story log, mission journal entry (the journal is the ledger; the tale is the narration).

**Non-canonical fabrication**:
An elaboration in a tale that exceeds the character's demonstrated capability. In-world braggadocio — the character told a taller tale than the truth. Not a moderation case; the world reacts accordingly. The braggadocio rule is the containment mechanism (see ADR-0105).
_Avoid_: lie, fabrication, moderation case.

**Support Move**:
A flavored action a co-located participant can declare at a group beat, fanned from their own capabilities (via the ownership oracle, plus predicate-tree legs for distinction/trait combos). A declaration takes the place of the helper's pick/vote in the group flow. The helper rolls their own check; on success the easing enters the resolving check via `perform_check(extra_modifiers=...)`, and on failure a complication can fire on the helper via the existing consequence pipeline. See ADR-0106.
_Avoid_: assist, teamwork action, stat donation (helping is drama, not a bonus transfer).

**Assist Pattern**:
A `MissionAssistPattern` catalog row that auto-offers support moves wherever the run context + qualifier match. Density comes from these patterns; authored gems on specific nodes add to or suppress them. Qualifying moves light up; `rumored` ones show a veiled tease to the whole party.
_Avoid_: assist template, support catalog entry, mission perk.

**Rumored**:
A support move marked with `rumor_text`; the whole party sees the veiled tease even if no one present is qualified. Discovery is part of the fun — the journal shows an unseen-approaches count after resolution.
_Avoid_: hint, foreshadow, locked move (it's a teaser, not a gate).

**Easing**:
Bonus banked on a successful support check, injected into the resolving check via the `extra_modifiers` argument of `perform_check`. Additive aid: it stacks onto the primary actor's roll rather than replacing it.
_Avoid_: assist bonus, donated stat, flat buff (it's banked on a helper's own roll, not a stat hand-off).

**External-Act Beat**:
A `MissionOption` with `option_kind=OptionKind.EXTERNAL_ACT` and `required_act` set to an `ExternalAct` (`TECHNIQUE_CAST`, `THREAD_WOVEN`, `COVENANT_SWORN`, `world.missions.constants`). Presented like any option (its authored framing shows) but never pickable — it resolves only when the player performs the real, non-mission act it names. `satisfy_external_act(character_sheet, act)` (`world.missions.services.external_acts`) is called directly from `weave_thread`, `create_covenant`/`induct_member_via_session`, and `use_technique` after each succeeds (log-and-continue, savepoint-guarded, per ADR-0112); durable acts (`THREAD_WOVEN`/`COVENANT_SWORN`) also fast-forward at `enter_node` when already true, but `TECHNIQUE_CAST` is transient and never fast-forwards. See ADR-0112.
_Avoid_: quest chain, onboarding engine, tutorial system.

**Tutorial Chain**:
The seven-`MissionTemplate` new-player arc (`world.seeds.game_content.tutorial.seed_tutorial_dev`, the `"tutorial"` seed cluster) walking a level-1 character through room-trigger and examine-driven grants, an NPC-offered External-Act Beat, a Notice Board pickup, a Directed Summons follow-on, a covenant vow, and a Legend-Risk Floor job. Each template gates the next via the ordinary `has_completed_mission` predicate leaf on `availability_rule` — chain progress is nothing but `MissionInstance` rows; there is no dedicated tutorial-progress model or status. See ADR-0112.
_Avoid_: quest chain, onboarding engine, tutorial system.

**Notice Board**:
A `MissionGiver` with `giver_kind=GiverKind.BOARD` (#2044) — an examinable object (physically placed in a room; the giver's `target` is the board object, not the room) that lists every eligible posting for the viewer at once (preview-then-take), rather than rolling or auto-granting a single offer. `mission take <n>` (telnet, `CmdMission._handle_take`) and `POST /api/missions/boards/<pk>/take/` re-run eligibility before granting.
_Avoid_: bulletin board, job board, quest board.

**Directed Summons**:
An `OfferSummons` (`world.npc_services.models`, #2050) — a master/NPC-role's wish aimed at one specific persona, riding `NPCServiceOffer`'s existing offer rails (accept delegates to `resolve_offer` → `issue_mission`, eligibility + risk-ack intact). Authored as a `MissionOptionRouteReward` with `sink=DeedRewardSink.FOLLOW_ON_SUMMONS` (`contract_holder_only=True`, a `followon_offer` FK, optional `followon_message`/`followon_expiry_hours`) on a route — the mechanism the tutorial chain uses to hand T4's completion to T5's tutor offer. Declining or lapsing is a recorded act, not a silent no-op.
_Avoid_: quest referral, follow-up mission, forced summons (accepting still goes through the normal offer/consent path).

**Legend-Risk Floor**:
The `LEGEND_RISK_FLOOR_TIER` (4 = HIGH, `world.missions.constants`) gate: any `MissionOptionRouteReward` with `sink=LEGEND_POINTS`, or `MissionRenownAward` with legend-paying risk, requires its parent `MissionTemplate.risk_tier` to be at or above the floor — enforced at `clean()`/save time, not just convention. Keeps Legend rare and earned rather than a routine payout on a low-stakes job; the tutorial chain's final template (risk_tier=4) is the only rung that pays Legend Points. See ADR-0107.
_Avoid_: legend gate, high-risk requirement, legend minimum (it's a hard floor, not a soft recommendation).

**Co-Presence (Solo-Darkness) Guard**:
The structural warning-not-lockout stance for legend-tier content (ADR-0107): a solo character can always attempt legend-risk work, but the system is honest that it is "warned-lethal solo" — no party-size gate blocks the attempt, but covenant vow power stays continuously co-presence-enforced (`revalidate_engagements`/`can_engage_membership` dim a vow the instant a covenant-mate leaves the room or the scene ends, `world.covenants`) and the mission surface's `Legend-Risk Floor` keeps the highest payouts tied to the tier where the game is upfront about the danger. Not a mission-specific mechanism — the missions system is one of its consumers via the risk-tier floor.
_Avoid_: solo lockout, party-size gate, solo penalty (there is no penalty or lockout — only honest lethality and a lit-vow requirement).

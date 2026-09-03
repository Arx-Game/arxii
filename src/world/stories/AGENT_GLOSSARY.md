# Stories glossary

**Story / Chapter / Episode / Beat / Transition**:
The narrative hierarchy: a **Story** is a top-level campaign container with a scope and maturity; a **Chapter** is a major arc within it; an **Episode** is a node in the episode DAG; a **Beat** is a boolean predicate attached to an episode (the gateable unit of progress); and a **Transition** is a first-class directed edge between episodes, fired automatically - the lowest authored `(order, pk)` eligible edge, never a runtime GM pick (#3565, ADR-0258; the retired mode was called GM Choice). Episodes are nodes and Transitions are edges - a Story progresses by satisfying Beats to make Transitions eligible.
_Avoid_: campaign (Story), arc (Chapter), session/scene (Episode), objective/flag (Beat), branch/link (Transition), GM choice (routing is never a runtime pick, #3565).

**Beat predicate**:
`Beat.predicate_type` (`BeatPredicateType`) - what an auto-evaluated Beat is
actually gated on: `GM_MARKED` (no auto-evaluation), `CHARACTER_LEVEL_AT_LEAST`,
`ACHIEVEMENT_HELD`, `CONDITION_HELD`, `CODEX_ENTRY_UNLOCKED`,
`STORY_AT_MILESTONE`, `AGGREGATE_THRESHOLD` (write-path triggered, not
`evaluate_auto_beats`), `OUTCOME_TIER` (the default; graded by a scenario run,
encounter, battle, or decisive check), `FACTION_STANDING_AT_LEAST` (reads
`SocietyReputation`/`OrganizationReputation.value`), and `NPC_REGARD_AT_LEAST`
(#3570; reads `NpcRegard`, the NPC's signed opinion of the character's
persona). Three memories can each hold "how an NPC feels about a character"
and only one backs this last predicate type: `NpcRegard` (the notable-NPC
opinion axis, `world.npc_services`, read by `NPC_REGARD_AT_LEAST`) is distinct
from `NPCStanding.affection` (the functionary disposition track,
`adjust_npc_affection`, ADR-0085) and from the relationships affection track
(`CharacterRelationship`/`RelationshipTrackProgress`, `SHIFT_AFFECTION`) - a
beat authored against the wrong memory silently never flips.
_Avoid_: predicate (name the specific type), regard/standing used
interchangeably (they are different memories with different writers).

**Session prep**:
What a GM authors on a Beat, ahead of the table, so `RunBeatAction` can
instantiate it into the live scene in one press: an **opponent line**
(`BeatOpponentLine` - creature template x count x position hint) or a
**staged template** (`BeatStagedTemplate` - situation XOR challenge template)
on a SITUATION beat, or, on an ENCOUNTER beat, either a freeform roster of
opponent lines or a whole **staged battle** (`BeatStagedBattle` - a battle-map
blueprint, region, party side, and `BeatStagedBattleUnit` lines by
template/side/place) - never both on the same beat (server-enforced XOR,
#3569). "Prep" names the row set; "session prep" names the workflow of
authoring it before play.
_Avoid_: encounter roster (ambiguous with the live `CombatEncounter`), battle
prep (staged battle is the specific term), pre-stage without naming which of
the three rows.

**Routing report**:
The authoring-time check on an episode's outbound transitions, before any
session ever runs them (`services/routing.py::routing_report`/
`routing_reports_for_episodes`, `RoutingReport`, #3563). A **dead end** is a
beat's FAILURE, its EXPIRED when it has a deadline, or a stake's LOSS that no
outbound transition accepts - at runtime that outcome would pause the run at
the frontier mid-session. An **ambiguity** is a pair of outbound transitions
whose requirement sets never contradict, so both could be eligible at once and
the lowest `(order, pk)` one silently wins. The report is **advisory**: it
never blocks saving, resolving, or running, and an episode with no outbound
transitions gets an empty report by design. It surfaces as `routing_problems`
on the episode payloads and `routing_ambiguous` on detail, GM-only.
_Avoid_: readiness (that is the stakes contract), validation error (the report
never blocks).

**Scenario / Scenario Graph**:
A SITUATION or TASK Beat's body is the same authored option -> check -> tier -> consequence
-> next graph that already runs missions (`MissionTemplate`/`MissionNode`/`MissionOption`/
`MissionOptionRoute`, `world.missions` - see that app's glossary) - not a second, story-local
option engine (#3565, ADR-0258). **Scenario** is the GM-facing name for this on the story side
(the story author page's "Design scenario" action, the scene's Scenario Card/rail section);
**scenario graph** is the code and glossary term for the shared primitive itself, used whether
the wrapper is a story beat or a mission. `StoryScenario` (below) is the ownership link that
makes a scenario a *story's own* scenario rather than staff-authored catalog content.
_Avoid_: mission (reserve for a scenario graph in its quest wrapper - `MissionTemplate`'s giver
economy - see Mission in the missions glossary), GM choice (the runtime pick this replaces),
option engine (there is exactly one, shared).

**StoryScenario**:
The ownership link (`world.stories.models.StoryScenario`) between a `Story` and the
`missions.MissionTemplate` a Lead GM authored as one of their beats' bodies - `story` FK +
`template` O2O (`related_name="story_scenario"`), read via `template.story_scenario.story` so
`world.missions` never imports `Story` (ADR-0010, #3565). A story-owned template is created
RESTRICTED with zero draw weight and excluded from boards/opportunities, so it never surfaces
as a public quest; the link is immutable after creation - a scenario is never re-parented.
_Avoid_: mission ownership, scenario link (StoryScenario is the specific model name).

**Era**:
A temporal metaplot tag (player-facing "Season N") that stories and events are stamped against, with exactly one ACTIVE era enforced at a time. It is a temporal label, not a parent in the Story/Chapter/Episode hierarchy.
_Avoid_: season, age, epoch.

**Story Maturity**:
The authoring-completeness of a single Story / Chapter / Episode node — `StoryMaturity`: PITCH, OUTLINE, or PLOT. Per-node and orthogonal to runtime progress status, with no cross-node ordering constraint; it is how finished the authoring is, not where play has reached.
_Avoid_: draft state, completeness, stage.

**Progress Status**:
The finer-grained state of a progress pointer (`ProgressStatus`: ACTIVE, WAITING_FOR_GM, RESTING, COMPLETED, FORECLOSED). `is_active` stays True for ACTIVE / WAITING_FOR_GM / RESTING; COMPLETED and FORECLOSED clear it.
_Avoid_: progress state, pointer status.

**FORECLOSED**:
The honest terminal `ProgressStatus` for a progress run still in flight when its story is concluded — distinct from COMPLETED (which means the run genuinely reached an ending). It exists so an unfinished thread is never falsely reported done, nor left orphaned in a live state.
_Avoid_: cancelled, abandoned, completed.

**Resting Conclusion**:
The player-facing `Episode.resting_conclusion` text shown when a progress pointer RESTS at that episode — a deliberately non-final pause-point ending. Required before an episode can be promoted to PLOT maturity.
_Avoid_: ending, pause text.

**Story Note**:
An append-only, never-player-visible OOC authorial note attached to a Story — general notes and future-idea seeds for the next author. Distinct from per-node pitch/`description` text; not promotable and not editable through the API.
_Avoid_: GM note, comment, pitch.

**Story Scope**:
Which kind of subject a Story progresses for — `StoryScope`: UNASSIGNED (the default, not yet placed), CHARACTER (personal), GROUP, or GLOBAL. It selects the progress-pointer type, and an UNASSIGNED story rejects progress creation until it is assigned a scope.
_Avoid_: level, reach, audience.

**Stake**:
One named wager on a Beat's stakes contract (`Stake` model, #1770) — what is actually at risk (a character, an NPC, a location, a faction relationship, an item, a campaign track, or a custom subject), authored with a `player_summary` shown to players at opt-in and a `severity` (`StakeSeverity`, SETBACK..REMOVAL) denormalized from a `StakeTemplate` at creation. Distinct from `Beat.risk` (the tier-level declaration a Stake concretizes) and from a `StakeResolution` (what happens to the Stake on a given outcome — identified together by `column` + `Outcome Key`, not `column` alone since #1760).
_Avoid_: wager, bet, consequence (use Stake for the thing at risk, StakeResolution for what happens to it).

**Stakes Contract**:
The full authored bundle backing a staked Beat: its `Beat.risk` + `Beat.target_level` declaration, one or more `Stake` rows, and each Stake's `StakeResolution` rows (WIN/LOSS/WITHDRAWAL branches). "The contract" is complete when `validate_stakes_readiness` reports it ready; see `docs/systems/stakes.md` for the full model and lifecycle.
_Avoid_: wager sheet, risk sheet.

**Severity**:
`StakeSeverity` (SETBACK/COSTLY/GRAVE/DIRE/REMOVAL, 1-5) — how bad losing (or how good winning) a single Stake is. `RiskCalibration.severity_ceiling` caps the worst severity any one Stake may carry at a given risk tier; `severity_floor_total` is the minimum summed severity across a beat's Stakes (no fake stakes). REMOVAL is the character-loss band.
_Avoid_: danger level, magnitude (Magnitude is a separate `societies` renown axis).

**Fuse / Chain Rule**:
The reachability rule (#1770) that a risk tier below EXTREME is only honest if losing the beat can plausibly cascade into a character-removal outcome, even when this beat doesn't stake removal directly. `RiskCalibration.max_fuse_hops` bounds how many failure-gated `Transition` hops the BFS walk (`_jeopardy_reachable`) may take to find a downstream beat that offers removal; EXTREME's `max_fuse_hops=0` means the beat itself must offer it. PITCH-maturity episodes never count toward the walk.
_Avoid_: escalation ladder (that's `StakeResolution.escalates_to_risk`, a related but separate authored field), removal chain.

**Effective Risk**:
What a stakes contract actually pays out on for the party currently running the scene — `compute_effective_risk(declared_risk, target_level, party_average_level)`, decaying an over-leveled party's declared risk toward NONE and giving an under-leveled party a bounded one-tier upgrade. Read via `effective_risk_for_beat(beat)`, which prefers the open `StakeContractActivation.effective_risk` and falls back to the raw `Beat.risk`. Distinct from `Beat.risk` (the GM's declared, unscaled risk).
_Avoid_: adjusted risk, scaled risk.

**Activation** (stakes contract):
The `StakeContractActivation` row locking a beat's stakes contract at scene start — snapshots `declared_risk`/`declared_target_level`/`party_average_level`, computes and freezes `effective_risk`, and (while `resolved_at IS NULL`) blocks any edit to the beat's Stakes/StakeResolutions. At most one open activation per beat (partial unique constraint). Not to be confused with activating/engaging a Covenant Role, or any other domain's "activation."
_Avoid_: lock (use Activation for the row; "lock" for the behavior it enforces), snapshot.

**Stake Outcome**:
The per-stake resolution audit + routing row (`StakeOutcome`, #1770 PR2) - which column a Stake resolved at, how it was decided (`StakeOutcomeMethod`: MACHINE grading in the completion tail is the only method since #3561 retired the GM Constrained Pick), and which authored `StakeResolution` branch fired (null when no branch was authored for the column). Exactly one StakeOutcome per stake (unique constraint) - transition routing reads it. `resolved_by` / `gm_notes` are historical audit fields from before #3561 - a pre-#3561 row resolved by a GM's pick still shows who and their notes, but every row since is machine-graded with both blank. Distinct from `BeatCompletion` (the beat-level ledger row) and from `StakeResolution` (the authored branch itself).
_Avoid_: stake result, stake completion, GM pick / Constrained Pick (retired #3561 - stakes are always machine-graded now).

**Outcome Key**:
The `StakeResolution.outcome_key` slug (#1760) - an open, designer-authored vocabulary naming *which* branch a resolution is, within one Stake's one `StakeResolutionColumn`. Lets a stake author multiple named branches sharing a polarity (e.g. two distinct LOSS branches, `"destroyed"` and `"captured"`); blank is the column's single plain/default branch and is what every pre-#1760 `StakeResolution` row carries (backward compatible). `column` + `Outcome Key` together - not `column` alone - identify one authored branch (unique `(stake, column, outcome_key)`); machine grading resolves both from the completing beat's outcome and the completion's own `outcome_key` (#3561).
_Avoid_: sub-branch, variant (reserve "branch" for the `StakeResolution` row itself; Outcome Key is the naming dimension that distinguishes branches sharing a column).

**Named Branch**:
A `StakeResolution` row whose `Outcome Key` is non-blank - the second (or
third...) authored branch sharing a `Stake`'s column, distinguished from the
column's plain/default branch by its key. Reached by key match, never by a
runtime GM decision (#3561, ADR-0259): `_branch_for_column` selects a named
branch when the completing beat's own `outcome_key` equals it, falling back
to the plain branch (or the column's first authored branch) when it doesn't.
Readiness (`_named_branch_problems`, #3561) flags two authoring gaps: a
column with a named branch but no plain default, and a named key no option
of the beat's scenario declares.
_Avoid_: sub-branch, variant (see Outcome Key's note - "branch"/"named
branch" name the `StakeResolution` row; Outcome Key names the field that
distinguishes it).

**Beat Outcome Key**:
`Beat.outcome_key`/`BeatCompletion.outcome_key` (#3565) - the `MissionOption.key` of the
scenario option that ended the run which resolved an OUTCOME_TIER beat, denormalised at
completion; blank for combat, battle, decisive-check, and GM-marked completions.
`TransitionRequiredOutcome.required_outcome_key` routes on it, the same shape the Stakes
`Outcome Key` above used first (#1760) - but a different field on a different model, naming
which scenario ending fired rather than which stake branch fired.
_Avoid_: outcome key alone when the Stakes `Outcome Key` is also in scope (name the model);
option key (that's `MissionOption.key`, the source value this field denormalises).

**Withdrawal Column**:
The `StakeResolutionColumn.WITHDRAWAL` branch — what happens to a Stake when the party walks away from the wager instead of winning or losing it. Fired machine-side when a combat encounter ends FLED/ABANDONED, via `resolve_stakes_for_withdrawal` (#3559); stakes without an authored WITHDRAWAL branch still record an empty (`resolution=None`) StakeOutcome (audit honesty). The beat's own outcome is left untouched (still open) - a withdrawal never completes the beat.
_Avoid_: flee branch, retreat outcome.

**Objective-First Grading**:
The rule (#3559) that no OUTCOME_TIER beat ever waits on a GM ruling to close - three structural replacements stand in for the deleted `BeatOutcome.PENDING_GM_REVIEW`. `beat_for_scene_conclusion` scopes a concluded fight or battle to at most one gradable beat (its explicit `story_beat`, else the scene's `running_beat` only when that beat is itself the objective). An outlier roll clamps to the best authored tier of the same polarity (`clamp_tier_to_pool`) instead of parking the beat. A missing `EncounterOutcomeMapping`/`BattleOutcomeMapping` row is required content, reported on the admin sentinel (#3444), not a fallback state. The same "objective-first" principle applies one layer down inside a scenario (#3565, ADR-0258): a fight spawned by an ENCOUNTER scenario option grades that option's route (`CombatEncounter.scenario_deed`), never a beat directly - see the missions glossary's ENCOUNTER Option entry.
_Avoid_: pending review, GM review queue, parked beat.

**Reward Line**:
One authored win payout on a stake's branch (`StakeRewardLine`, #1770 PR3) — a `sink` (`StakeRewardSink`: MONEY or RESONANCE), an `amount` (a money-equivalent scalar paid to EACH completion participant, ALL_EQUAL), and a `resonance` FK when the sink is RESONANCE. Hangs off a WIN-column `StakeResolution` (WIN-only, enforced in clean() + serializer); paid by `_apply_stake_rewards` only under a ready, effective-risk-bearing Activation, with the Reward Band re-checked at pay time. Distinct from missions' `MissionDeedRewardLine` (deed-anchored; stakes deliberately reuse the sink *services*, not the deed router).
_Avoid_: reward row, payout entry, deed line.

**Reward Band**:
The per-tier `RiskCalibration.reward_floor`/`reward_ceiling` window (#1770 PR3) that the summed WIN-column Reward Line amounts across a beat's stakes must fall inside for the contract to be ready (`_reward_band_problems`). Out-of-band totals mark the contract UNREADY (auto-downgrade, pillar 7) — never an authoring rejection. `reward_ceiling == 0` means banding is unconfigured for that tier and both checks are skipped.
_Avoid_: reward cap (the band has a floor too), payout limit.

**Stakes Summary**:
The one player-visible wire shape for a beat's stakes contract (#1770 PR4) — `{declared_risk, effective_risk, is_ready, stakes: [{id, player_summary, severity, severity_label}]}`, built by `stakes_summary_for_beat` (`world.stories.serializers`) and served at `GET /api/beats/{id}/stakes-summary/` and as `combat_stakes` on the consent-prompt serializers. What is wagered is visible; branch contents (`StakeResolution`) are never part of the shape (pillar 9).
_Avoid_: stakes preview, contract dump (a summary never includes resolutions).

**Boundary Check** (stakes):
The screen `check_stake_boundaries(stakes, character_sheets) -> StakeBoundaryReport` (`world.stories.services.boundaries`, #1770 PR4), run at authoring time (existing stakes + the candidate write) and at every activation/commit call site; call sites gate on `report.cleared` (allowed AND no pending sign-off). Backed by the real per-player boundary registry since #1771 (`world.boundaries` — Hard Line / Advisory `PlayerBoundary` rows matched by `ContentTheme`, `TreasuredSubject` rows matched by specific-entity identity and gated by `TreasuredSignoff`; see `world/boundaries/AGENT_GLOSSARY.md` and `docs/systems/boundaries.md`), no longer the PR4 allow-all stub. `blocked_reason_private` is staff/audit only — a player's boundary is never surfaced to the GM or other players (ADR-0033, ADR-0086); callers show only a generic "stakes could not be presented" failure.
_Avoid_: consent check (that's the ADR-0024 social-consent app; a boundary is a content limit, not a per-action consent), veto.

**Opt-in / Commit Step** (stakes):
The moment a player commits to a staked scene and the contract activates (#1770 pillar 9): entering combat (duel creation, hostile-cast seed/feed — surfaced via `combat_stakes` on the consent prompt), accepting a risky mission (`MissionRiskAcknowledgement` + the `acknowledge_risk` two-phase inside `npc_resolve`), or a GM's room-visible `declare_stakes` action in freeform play. The summary shown at this step is the Stakes Summary above.
_Avoid_: consent gate (see Boundary Check note), buy-in.

**Protected Subject**:
A `StoryProtectedSubject` row (#2001) declaring that a story asset — NPC, item,
faction, or freeform subject — is load-bearing for a story and structurally
guarded from actors external to that story. Generalizes the old
`StoryNPCDependency` (NPC-only) to the full `StakeSubjectKind` vocabulary,
reusing `Stake`'s typed-subject-FK shape (`subject_sheet`/`subject_item`/
`subject_society`/`subject_organization`/`subject_label`, exactly one
populated). Story-declared narrative-structure protection — distinct from a
player-declared `TreasuredSubject` (see ADR-0098 / `docs/systems/custody.md`).
Every enforcement point (the NPC-fate death guard, `StakeSerializer` staking
validation, `StakeResolution` writer fire-time recheck, `add_opponent`
spawning) funnels through the single `check_subject_custody` seam
(`world.stories.services.custody`) rather than checking independently.
_Avoid_: NPC dependency, load-bearing NPC (Protected Subject is the general term now).

**Custody Clearance**:
A `CustodyClearance` row (#2001) — a requesting GM's permission ask to act on
another story's `Protected Subject` at a given `CustodyScope`
(APPEAR < HARM < REMOVE, weakest→strongest; an active clearance clears every
scope at or below the one it was granted for). `CustodyClearanceStatus`
(PENDING/GRANTED/DENIED/ESCALATED, + a soft `revoked_at` on a GRANTED row) is
the lifecycle; the protecting story's Lead GM grants/denies a PENDING request
(no staff bypass — staff act only through escalate→resolve, never posing as
the custodian), the requester may escalate a DENIED or stale-PENDING request
to staff, and staff (or the custodian) may revoke a GRANTED clearance.
Requested via either a `protected_subject` pk (once known) or the
identity path (`subject_kind` + typed ref, ADR-0099) — the latter is the only
self-serviceable door for a GM who was only ever told the custodian's
username, never the internal pk (see `docs/systems/custody.md`).
_Avoid_: permission request, custody request, access grant.

**Custody Verdict**:
The result of `check_subject_custody` (`CustodyVerdict`, `world.stories.types`)
— `allowed` plus, when blocked, `requires_scope` and `custodian_gm_username`
(routing info for a clearance request). `protecting_subject_id` is
internal/audit-only and never player-serialized — a blocked actor learns only
"under another story's custody — request clearance from GM `<name>`," never
the protecting story, beat, or reason (mirrors the boundaries privacy
posture, ADR-0033/ADR-0086).
_Avoid_: custody check result, permission verdict.

**Impact Tier**:
`Story.impact_tier` (`ImpactTier`: TABLE / REGIONAL / WORLD, default TABLE,
#2003) — the story-side *canon review* axis: how far a story touches the
shared world, authored by the story's Lead GM at pitch time and frozen once a
review is CLEARED. Distinct from `Beat.risk` (declared danger/reward
magnitude) and `StakesLevel` (GM combat access scope) — see ADR-0067's
disambiguation table and ADR-0101. TABLE is never reviewed; REGIONAL
auto-clears for EXPERIENCED+ GMs (`GMLevelCap.auto_clear_regional`); WORLD
requires staff sign-off before its staked beats pay.
_Avoid_: stakes level, risk tier, scope (scope is the CHARACTER/GROUP/GLOBAL subject axis; impact tier is the review axis).

**Canon Review**:
A `CanonReview` row (#2003) — a staff review of a WORLD-tier story's
canon-touching content before it pays. One PENDING review per story (partial
unique); `CanonReviewStatus` (PENDING → CLEARED / CHANGES_REQUESTED). The gate
is auto-downgrade-not-block (pillar-7 pattern): an unreviewed WORLD-tier
story's staked beats are UNREADY → effective risk NONE (the scene still runs,
nothing pays) via `validate_stakes_readiness`'s canon-review problem. Requested
(or, for an auto-clearing REGIONAL GM, system-cleared) by
`ensure_canon_review_for_story` (#3304) whenever the web/telnet `story impact`
setters or the beat-driven escalation heuristic raise a story's effective
tier — a system-cleared row stamps `reviewer=None`,
`notes="auto-cleared by GM level cap"` rather than skipping the row, so
trust-based clearance stays auditable. Surfaced on the staff
`StaffWorkloadView` pending-queue (rendered as `PendingCanonReviewsPanel` on
`StaffWorkloadPage`) and decided via the `canonreview` telnet command or
`CanonReviewViewSet` web verbs.
_Avoid_: sign-off (that's `TreasuredSignoff` / custody), approval gate.

**Surrender** (GM):
A Lead GM releasing oversight of a story — `surrender_character_story(gm, story)`
(#2004) clears `primary_table` so the story enters "seeking GM" state,
mirroring the player-side `detach-from-table`. Stamps GM activity and notifies
the affected player via a narrative SYSTEM message. Wired via
`POST /api/stories/{id}/surrender/` and `story surrender <story-id>` telnet.
_Avoid_: abandon, drop (use surrender for the GM-side release; detach for the player-side).

**Group Story Request**:
A `GroupStoryRequest` row (#2119) — a covenant officer's open, **broadcast** ask for a GM
to run a story for their covenant, visible to the whole GM pool. `GroupStoryRequestStatus`
(PENDING/ACCEPTED/WITHDRAWN — no DECLINED, since a broadcast ask has no single decliner);
one PENDING request per covenant (partial unique constraint). Distinct from `StoryGMOffer`,
which is *directed* at one specific GM and requires a pre-existing player-owned CHARACTER
story — a Group Story Request has no story yet; claiming it (`claim_group_story_request`)
is what creates the GROUP-scope `Story`, seating the covenant's active members at the
claiming GM's table via the existing `join_table` seam (no `GMTableMembership` schema
change). Gated by the covenant's `can_request_gm` rank capability (see
`world/covenants/AGENT_GLOSSARY.md`).
_Avoid_: story offer (that's `StoryGMOffer`, a directed CHARACTER-scope offer), recruitment post.

**Idle Table**:
An ACTIVE `GMTable` whose GM's `last_active_at` is older than a staff-tunable
threshold (`IDLE_TABLE_THRESHOLD_DAYS`, default 14) or null — surfaced on
`StaffWorkloadView`'s `idle_tables` section and a weekly cron summary
(`_run_idle_table_summary`). Reassignment drives the existing
`transfer_ownership` service. `last_active_at` is stamped by
`touch_gm_activity` from every GM-verb service.
_Avoid_: stale table (staleness is a story-progress concept; idle is a GM-activity concept).

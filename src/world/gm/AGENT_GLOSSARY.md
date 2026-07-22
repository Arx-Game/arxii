# GM glossary

**GM / Storyteller**:
A player approved to run stories for others, identified by a `GMProfile` and a trust/permission `GMLevel`. The canonical term throughout the codebase is "GM"; a Lead GM is the GM assigned to and authoring a given story.
_Avoid_: Storyteller, Dungeon Master, DM, game master.

**GMProfile**:
A player's GM identity — one per account, carrying their `GMLevel`, approval date, and approver. Created when a `GMApplication` is approved; GM-level permission checks query this model.
_Avoid_: GM account, GM record.

**GMTable**:
A GM's working group: a named set of players (via their personas) engaging with a set of stories, with an ACTIVE/ARCHIVED lifecycle. The unit that owns GROUP-scope story progress and anchors Lead-GM permission checks.
_Avoid_: party, group, campaign.

**GMTableMembership**:
A player's presence at a `GMTable`, pinned to a specific `Persona` (never a temporary mask) rather than to a CharacterSheet. Supports soft-leave via `left_at` so membership history outlives a persona, with one active membership per (table, persona); it is not a privacy mechanism, since the underlying character stays walkable.
_Avoid_: seat, table member, participant.

**Assistant GM (AGM)**:
A GM (`GMProfile`) who has claimed a single `agm_eligible` beat session to run, seeing only that beat's internal description plus the Lead GM's framing — not the rest of the story. The claim lifecycle lives in the stories app as `AssistantGMClaim` (REQUESTED → APPROVED/REJECTED/CANCELLED → COMPLETED); AGM is a per-beat role, not a separate identity from GMProfile.
_Avoid_: co-GM, helper GM, sub-GM.

**GM Level**:
A GM's trust tier (`GMProfile.level`, the `GMLevel` enum: STARTING/JUNIOR/GM/EXPERIENCED/SENIOR), canonical since #2000 (ADR-0097) — the single source of GM trust; supersedes the dead `PlayerTrust.gm_trust_level` field, which was removed. Ordered via `GM_LEVEL_ORDER`/`gm_level_index`; consumed by `stories.BeatSerializer`'s risk gate, `stories.StakeSerializer`'s custom-stakes gate, and `combat.StakesLevelRequirement.minimum_gm_level`.
_Avoid_: GM trust level (on PlayerTrust — that field is gone), trust score.

**Level Cap**:
`GMLevelCap` — one staff-tunable row per `GMLevel`, holding what a GM at that level may author: `max_beat_risk` (the highest `RenownRisk` beat tier), `allow_custom_stakes` (template-null Stakes), `allow_global_scope_authoring`. Seeded via `world.gm.factories.seed_default_gm_level_caps`. A GM with no `GMLevelCap` row (or no `GMProfile`) falls back to the most restrictive read (`RenownRisk.NONE` / `False`).
_Avoid_: trust cap, permission cap.

**Promotion**:
A staff-only, audited change to a GM's `level` via `world.gm.services.promote_gm` (covers both promotion and demotion — the function name is the historical verb). Every call writes a `GMLevelChange` row (`old_level`, `new_level`, `changed_by`, `reason`); nothing else may write `GMProfile.level`. Reachable via `GMProfileViewSet.promote` (`IsAdminUser`) or telnet `gmtrust promote <account>=<level> reason=<why>`.
_Avoid_: demotion (as a separate concept — same service, same audit row), level change (ambiguous with the `GMLevelChange` model name — use "promotion" for the act).

**Evidence Summary**:
`GMEvidenceSummary` (`world.gm.types`) — the read model `gm_evidence_summary(profile)` builds for a staff reviewer deciding on a promotion: stories currently running, beats completed by risk tier, feedback by trust category (`CategoryFeedback`), and the GM's `GMLevelChange` audit trail. Reachable via `GMProfileViewSet.evidence` (`IsAdminUser`) or telnet `gmtrust evidence <account>`.
_Avoid_: track record (informal; use the type name in code/docs), review packet.

**Situation Kind**:
`SituationKind` — the cross-cutting scenario taxonomy tag (#2127, e.g. "Chase", "Negotiation") a GM finds by name/description in a per-type browse (`FindSituationAction`, `setsituation find <term>`). Not a reuse of `mechanics.ChallengeCategory` or `checks.CheckCategory` (those are per-app display groupings); a `SituationKind` is the shared label that lets checks/difficulty/pool guidance stay consistent across every per-type listing. Gates its own visibility via `minimum_gm_level` (breadth gating, Decision 9) — a GM below that tier never sees the kind, even on an exact name match. Deliberately holds no FK to `mechanics.SituationTemplate` (ADR-0010: `gm` depends on `mechanics`, never the reverse) — a browse matches templates and kinds independently by the same search term.
_Avoid_: scenario tag, situation category (collides with `ChallengeCategory`), situation type.

**Check Fit**:
`CheckTypeSituationFit` — a through-row proving a `checks.CheckType` fits a `SituationKind`, with `fit_notes` explaining why. The "translatable across contexts" record (Decision 1): the same check can be proven to fit more than one kind.
_Avoid_: check mapping, check association.

**Difficulty Guide**:
`SituationDifficultyGuide` — an authored `DifficultyChoice` band recommendation for a `SituationKind` at a given `RenownRisk` tier, with `guidance_text`. Targets the live band surface a GM actually picks (`InvokeCatalogCheckAction`'s `difficulty` kwarg) — never `ChallengeTemplate.severity`, which is baked into pre-authored content at authoring time and never touched by a live GM (Decision 6).
_Avoid_: severity guide, difficulty rating.

**Pool Guide**:
`ConsequencePoolGuide` — advisory text (`selection_criteria`, `is_default`) on which `ConsequencePool` fits a `SituationKind`. ADVISORY ONLY (Decision 7): nothing anywhere reads this row to select, compose, or write a live `consequence_pool` FK — staff keeps authoring `ActionTemplate.consequence_pool` / `ActionTemplateGate.consequence_pool` / `SituationTrapLink.consequence_pool` by hand in admin. The single most guarded piece of guidance text in the catalog, since a live pool *binding* (as opposed to advisory text about one) is exactly the "if u fail u die lol" invention Arx I failed on.
_Avoid_: pool binding, pool selector (implies live application — this never applies anything).

**Catalog Suggestion**:
`CatalogSuggestion` — a GM's proposed catalog growth (a new `SituationKind`, a check fit, a difficulty guide, or — at EXPERIENCED+ trust — a pool guide), routed through `world.staff_inbox` exactly like a `GMApplication`. Reuses `player_submissions.SubmissionStatus` (OPEN/REVIEWED/DISMISSED, Decision 8) rather than a new enum. `proposal_kind` is tiered by the submitting GM's `GMLevel` (`PROPOSAL_KIND_MIN_LEVEL`, Decision 9) — STARTING/JUNIOR may propose NEW_SITUATION/CHECK_FIT/OTHER only; GM+ additionally DIFFICULTY_GUIDE; EXPERIENCED+ additionally POOL_GUIDE. Staff acceptance is a manual admin action that separately authors the real catalog row(s) — accepting a suggestion never auto-creates them.
_Avoid_: catalog proposal (use the model name), suggestion (ambiguous outside this context).

**Story Area**:
`StoryArea` (#2450, epic #2436 slice 3) — a GM's ownership claim on a
`GridOrigin.STORY` `Area`: a private build-and-run space on the shared grid
substrate, layered on the #2436/#2449 world-builder canvas but gated by GM trust
(`MinimumGMLevelPrerequisite`) rather than the staff flag. A sidecar per ADR-0010
(`areas` stays dependency-free; `gm` points at it), capped per `GMLevel`
(`GMLevelCap.max_story_areas`). The row survives a staff promotion to AUTHORED as
provenance, but cap counting filters on `area__origin=STORY` so a promoted area
stops counting toward the GM's limit. Never exported to the lore repo (only
`origin=AUTHORED` rows export) and excluded from the player-facing
`AreaViewSet`/`RoomProfileViewSet`.
_Avoid_: GM area, story zone, personal area.

**Story Room Grant**:
`StoryRoomGrant` (#2450) — a GM-issued, consent-first access grant naming a room
(story-area room or temp scene room) and a character. Gates the JOIN action only
(`join_story_room`/`leave_story_room`, telnet `joinroom`/`leaveroom`) — once
inside, movement between rooms rides ordinary exits, unaffected by the grant (see
ADR-0141). `return_location` is captured on join and cleared on leave; revoke is
a plain row delete (a grant carries no story-significant history worth
preserving). Deliberately not a GM-summon — the character dispatches their own
join.
_Avoid_: room invite, access token, room pass.

**Temp Scene Room**:
A disposable `InstancedRoom` a GM spins up for a one-off beat
(`spin_up_scene_room`, telnet `sceneroom <name> = <description>`) via the
pre-existing #1349-era instanced-room lifecycle (`world.instances.services
.spawn_instanced_room`), distinguished from a mission/player instance by
`InstancedRoom.gm_owner`. Closing it (`close_scene_room`, `sceneroom close
<#id>`) returns every joined character per their `StoryRoomGrant` before
completing the instance; deliberately non-atomic and retryable, since a blocked
return (`move_to` failure) must not silently orphan a character or fake an
atomic rollback around non-DB side effects (messaging, scene bookkeeping).
Never publicly listed, like every instanced room.
_Avoid_: scene instance (ambiguous with `world.instances` generically), pop-up
room, GM scratch room.

**GM Story Reward**:
The XP a GM earns (via `world.gm.services.award_gm_story_reward`, `ProgressionReason
.GM_STORY_REWARD`) for running stories for other players — the opposite direction from
"Rewards and Gating" above (a GM granting rewards to players). Fires at four
convergence points that ride real, reviewable story artifacts (never self-attested):
a GM-marked beat, a resolved episode, a completed story, and a positive story-feedback
rating on GM performance. Scaled by players served (never a flat amount) and capped
per event and per `GameWeek` (`GMWeeklyRewardTracker`); every award value lives on the
`GMRewardConfig` singleton, never a module constant (#2123).
_Avoid_: GM payout, GM stipend, session pay.

**Table Update Request** (`TableUpdateRequest`, #2631, ADR-0155):
A player's proposed sheet change awaiting their table GM's yes/no sign-off — always a
concrete change (a profile-prose rewrite or a distinction add/rank-up/remove) with a
player `Reason:`, never a prompt for the GM to write content. Routed through
`GMTableMembership` (no table → no requests, by design). Kind payloads live on 1:1
details models (`ProfileTextRequestDetails`, `DistinctionChangeRequestDetails`); prose
applies at approval; distinction approval creates-and-approves a
`distinctions.SheetUpdateRequest` on the #2628 engine (XP auto-debits atomically — no
separate accept step). Reviewable by staff or any GM whose table the requesting persona
actively sits at (#2631 ruling), never by a GM the player has no table with.
_Avoid_: job, +request, ticket, petition (that's `player_submissions`' staff inbox).

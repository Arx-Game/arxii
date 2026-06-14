# Missions & Living Grid

**Status:** engine + authoring + play loop SHIPPED (code-verified 2026-06-11); reward sinks / discovery / multiplayer surface are the open gaps
**Depends on:** Checks, Mechanics (Challenges), Conditions, Areas, Instances, Traits, Skills, Distinctions, Societies, NPC Services

## Overview
Missions are branching narrative quest chains — the primary way characters interact with the living world. A character receives a mission with broad objectives, makes decisions at branching points gated by different skills and traits, and the consequences reshape the world around them.

## Key Design Points (current architecture)
- **Mission = authored graph**: `MissionTemplate` → `MissionNode` (pick-list of options) → `MissionOption` (BRANCH or CHECK) → `MissionOptionRoute` (outcome-tier-keyed, optionally randomized via weighted `Candidate`s). No engine arbitration — the player picks, pick+check routes.
- **Two option sources**: authored predicate-gated options, and CHALLENGE-source options that reference one `mechanics.ChallengeTemplate` and fan out per qualifying `ChallengeApproach`.
- **Gating is predicate-trees** (predicate evaluator + leaf-resolver registry), not the older Application+Property eligibility sketch.
- **Front doors**: NPC givers via the unified `NPCServiceOffer(kind=MISSION)` (#686), or trigger givers (`MissionGiver`: ROOM_TRIGGER on entry / ENVIRONMENTAL_DETAIL on examine — NPC-giver kind retired in favor of NPC services).
- **No scratch state**: state = node position + per-entry `MissionNodeSnapshot` + real consequences already applied.
- **Legend split**: Legend *Points* are mechanical; the Legend *Entry* (player retelling) is narrative and never parsed for mechanics.
- **Cooperative**: participant set on the instance; moral consequence follows the actor; contract-holder alone bears cooldown/standing/failure.
- **NOT using the Flows system** — missions own their specific behavior.

## What Exists (code-verified 2026-06-11)
- **Engine (`world/missions/`), Phases 0–5b + play loop**: full model graph, predicate gating, resolution (`resolve_option` → check → tier routing → consequence), multi-participant orchestrator (COINFLIP/VOTE/JOINT with combined routing — engine only, see gaps), terminal reward emission + deferred-payout cron, renown award emission (LIVE — fires `fire_renown_award`), Mission→Beat seam (record-stub).
- **Quest journal + in-progress persistence (#889)**: `/api/missions/journal/` + `JournalPage`/`BeatCard` React play surface; node→room binding (ANYWHERE/ANCHOR/ROOMS) with compass disclosure; durable deed history.
- **Visibility (#870)**: `MissionTemplate.visibility` (`OPEN`/`RESTRICTED`) — **the old `access_tier` name is retired**; predicate-evaluated via `template_visible_to`.
- **Authoring (Phases A–E + create UI all merged)**: Mission Studio (`/staff/missions/`) — browser, create-from-scratch, node/option/route/candidate/reward CRUD, canvas DAG editor, predicate builder, copy/copy-subtree, staff `assign` power. Trigger-giver dispatch + staff editor (#863/#868); NPC roles + offers editor (#861).
- **Deed knowledge (#902)**: mission-terminal awards grant the party witness knowledge of the deeds born from the run (bystanders deliberately excluded).

## Open Gaps (from the 2026-06-10 code audit; #923 economy work closes the money one)
- **Reward sinks are stubs**: `world/missions/integrations/` — money/beat record in-memory; rumor/crime_watch raise. Money lands via economy sub-issue #932; renown is already real.
- **No discovery surface**: no browse/board endpoint — players find missions only via NPC interaction or room triggers.
- **Abandon**: #1023 ✅ shipped — `play.abandon_mission` + `MissionJournalViewSet.abandon` let the contract holder walk away from an `ACTIVE` run (→ `ABANDONED`, frees the cap slot, keeps the giver cooldown). Auto-**expiry** was intentionally dropped (missions are private; persisting until abandoned is fine) — `EXPIRED` stays a defined-but-unused status for a possible future GM action.
- **Multiplayer engine unwired**: JOINT/VOTE/COINFLIP orchestration is built + tested but not attached to the API — solo-only live (invite/party surface: #887).
- **Per-candidate overrides STORED BUT UNCONSUMED** (Phase D wires per-candidate emission; the mission roulette reveal #933 couples to it).
- **Instanced play**: `spawn_instanced_room` wiring is #886 (prison/ransom #931 is its flagship consumer).
- **Trigger-giver target picker**: #882. **Categorical room binding**: #888.
- **POOL count policy**: #726 ✅ shipped — `offer_policy.mission_pool_count` scales the POOL slate by NPC standing (stranger → 1, trusted → 5, wired into the live interaction render); `has_completed_mission` predicate leaf gates chained missions; `MissionOfferDetails.draw_priority` surfaces chain/high-stakes offers ahead of the general pool.
- **Offer-policy enrichment**: #1020 ✅ shipped — org-reputation folded into the count (`max(npc_standing, org)` when the role fronts an org); Era arc-replace draws active-season offers (`created_in_era` + `percent_replace`) ahead of the general pool, behind explicit chains. Ordering/bands live in `npc_services/constants.py` for playtest retuning.
- **Zero seed content**: a fresh DB has no missions (part of the seed/content pass).

## Notes
- The 2026-05-18/05-22 design + implementation plans remain the architecture of record (option-level challenge attachment is the decision-of-record).
- Historical Phase-B deviation notes (single `MissionGiver.target` FK, the `access_tier` minimal gate later renamed to `visibility` by #870) are preserved in git history of this file; the deploy-note about defaulting templates to staff-only carried into `visibility`'s `RESTRICTED` default.

# Missions & Living Grid

**Status:** engine + Phase A authoring landed; Phase B in progress
**Depends on:** Checks, Mechanics (Challenges/Situations), Conditions, Areas, Instances, Traits, Skills, Distinctions, Societies

## Overview
Missions are branching narrative quest chains — the primary way characters interact with the living world. Think Crusader Kings event chains: a character receives a mission with broad objectives, makes decisions at branching points gated by different skills and traits, and the consequences reshape the world around them.

## Key Design Points
- **Mission sources:** Guild/quest-giver NPCs, found objects on grid, encountering ongoing situations in public rooms
- **Branching decision trees:** Each decision point offers multiple approaches appealing to different character builds. A high-charm character might seduce their way past a guard; a stealthy one picks the lock. Distinctions and unique traits unlock special options. Decision points map to **Applications** (Capability + Property = eligibility) which the system uses to generate available approaches automatically
- **Challenge resolution at decision points:** Uses the Challenges/Situations system in the mechanics app. Each decision point is a Challenge with Properties; the system matches character Capabilities via Applications to surface available approaches
- **Instanced moments:** Missions can spin up private instances (e.g., luring an NPC to a private room) using the instances system
- **World consequences:** Mission outcomes ripple outward — a city goes on high alert, a character becomes wanted, crime gangs gain territory, a war front shifts
- **Player retelling:** The system provides facts and outcomes; players write the dramatic retelling for bonus legend. Encourages creative expression
- **Designed for solo AND small groups:** While the Living Grid allows solo play, missions are enhanced with other players. Shared missions let groups experience things together and build relationships
- **Randomly generated elements:** NPC targets, locations, complications — keeps missions feeling fresh
- **Legend and reputation:** Dangerous missions grant legend. Mission outcomes feed into society reputation
- **NOT using the Flows system:** Individual mission logic rather than the abstracted Flows engine — missions need specific, tailored behavior

## What Exists
- **Areas app:** 9-level spatial hierarchy with materialized views for efficient path queries
- **Instances app:** Temporary instanced room lifecycle management with scene preservation
- **Checks:** Full check resolution pipeline with trait-to-rank conversion, result charts
- **Challenges/Situations (mechanics app):** ChallengeTemplate, ChallengeInstance, SituationTemplate, SituationInstance, ChallengeApproach — atomic problems with Properties, severity, resolution types, and approach matching via Applications. Situations compose Challenges with dependencies and narrative framing. Mission stages will map directly to SituationInstances
- **Properties & Applications (mechanics app):** PropertyCategory, Property, Application — the eligibility layer that connects character Capabilities to Challenge approaches. The system auto-generates available actions based on what a character can do vs. what a Challenge requires
- **Capability sources:** TechniqueCapabilityGrant (magic), TraitCapabilityDerivation (mechanics), ConditionTemplate capabilities (conditions) — multiple sources feed into the action generation pipeline
- **Conditions:** Persistent state tracking with stage progression, now with Properties M2M for integration with the Challenge system
- **No mission-specific models exist** — but the Challenge/Situation infrastructure provides the foundation for mission stages
- **MISSIONS ENGINE (now built — `world/missions/`):** `MissionTemplate`/`MissionNode`/`MissionOption`/`MissionOptionRoute`(+`Candidate`/`Reward`)/`MissionInstance`/`MissionParticipant`/`MissionNodeSnapshot`/`MissionDeedRecord`/`MissionGiver`(+`Cooldown`)/`MissionDeedRewardLine`/`MissionRewardQueue`. Full Phase-0–5b runtime: predicate evaluator + leaf resolver registry, multi-participant orchestrator (COINFLIP/VOTE/JOINT with combined routing), front-door availability + offer pipeline, journal, terminal reward emission, deferred-payout cron, Mission→Beat seam (`Beat.required_mission` is live; the Beat-completion engine itself is stubbed). Design + plan in `docs/plans/2026-05-18-missions-design.md` + `2026-05-18-missions-implementation.md`.
- **MISSION AUTHORING TOOLING — Phase A landed (PR #492):** `MissionOption(source_kind=CHALLENGE)` with `challenge` FK fans out per qualifying `ChallengeApproach` exactly like the now-retired AFFORDANCE option fanned out per binding; `challenge_options_for_character` is the expansion service; `ChallengeApproach.auto_succeeds`/`is_default` flags. Affordance system fully retired. Design + plan in `docs/plans/2026-05-22-mission-authoring-tooling-{design,implementation,findings}.md`. Phases B/C/D/E pending — B (model extensions) in progress; C (predicate leaf-resolver expansion); D (DRF API); E (React Mission Studio).
- **Phase B in progress — recorded deviations:**
  - **B2** uses plain `MissionGiver.clean()` instead of the plan's `DiscriminatorMixin`. The mixin requires "exactly one typed FK is set" per discriminator value, which doesn't fit ROOM_TRIGGER (no typed FK — `location` IS the trigger) and conflicts with the loose-validation policy that lets "drafty" givers (kind set, target unset) pass at the model layer. `MissionGiver.is_publishable` (property) is the boolean signal the authoring UI / admin surface uses to gate the "ready for live audience" transition — i.e. the operator flipping a template's `access_tier` from `STAFF_ONLY` to `OPEN`. **Runtime enforcement in `offer_missions` is intentionally deferred to Phase D**, where it can be designed alongside the broader visibility/permission tiers; today `is_publishable` is consumed only by authoring/admin layers. Behavior unchanged from before this batch; storage shape matches the plan.
  - **B7** ships a single `MissionTemplate.access_tier` audience gate (`AccessTier` TextChoices: `OPEN`/`STAFF_ONLY`, default `STAFF_ONLY`) instead of the plan's full draft/publish working-copy fork. Rationale: per-author in-flight protection is already provided by `MissionNodeSnapshot` (every accepted mission pins its node state), so the only remaining need is "let staff test an authored mission before players see it" — handled cleanly by audience gating without forking the graph. `offer_missions` excludes `STAFF_ONLY` templates from non-`is_staff_observer` characters. The enum is intentionally minimal; richer tiers (society membership, GM-level, distinction-gated, etc.) defer to a dedicated permission brainstorm.
    - **DEPLOY NOTE:** migration `0021` adds the field with default `STAFF_ONLY` — every pre-existing `MissionTemplate` row becomes staff-only after migration. No pre-existing authored content exists today (the missions app is in dev), but if it ever does, the deploy needs an operator pass to flip live missions to `OPEN`. There is intentionally no data migration auto-converting `is_active=True` rows to `OPEN`: the audit step (a human confirming each formerly-live mission is still ready for the live audience) is the point of the gate.

## What's Needed for MVP
- Mission model — definition, metadata, rewards; stages map to SituationTemplates
- Mission instance tracking — active missions per character, progress, decisions made; stage instances map to SituationInstances
- Decision tree composition — branching points use SituationChallengeLinks with dependencies; gating uses Applications and prerequisite keys
- NPC generation for missions — random targets, quest givers, complications
- World consequence system — how mission outcomes affect grid state, society territory, alerts
- Mission reward distribution — legend, reputation, XP, items, codex entries
- Mission discovery — how characters find/receive missions (quest givers, found objects, grid events)
- Shared mission support — multiple players on the same mission instance
- Player retelling system — writing summaries for bonus legend
- Mission UI — web interface for tracking active missions, making decisions, viewing outcomes

## Notes

**Roadmap doc lag (2026-05-22):** the Overview / Key Design Points / What's
Needed for MVP sections below were written before the missions engine was
built and don't reflect the current architecture (predicate-tree gating
instead of Application+Property eligibility, CHALLENGE-source options
instead of mission-stages-as-SituationInstances, etc.). The two bullets
added to "What Exists" are accurate; the rest is overdue for a fuller pass.

# Arx II Roadmap

> For AI agents and developers: this is the big-picture view of what needs to be built
> for Arx II to reach MVP and start alpha playtesting. Each domain links to a stub file
> with more detail. Check those stubs before starting work on any system.
>
> **Planned-but-unbuilt systems** (designed/intended, no code yet — battles, mounts, companions,
> ships, the spell system, racial framework, dreamstates, …) are recorded in
> [`planned-systems.md`](planned-systems.md) so design intent stops getting lost. **Current
> player-reachability** of built capabilities is tracked in
> [`../audits/2026-06-25-player-reachability-coverage.md`](../audits/2026-06-25-player-reachability-coverage.md).

---

## What Is Arx II?

Arx II is a **web-first multiplayer RPG** — an MMO designed for collaborative roleplay at
a scale no tabletop game or traditional MUSH can achieve. Hundreds of adventuring parties
share one persistent world where every player's actions affect everyone else. The React
frontend is the primary interface; telnet is a secondary compatibility goal.

The game has three interconnected gameplay pillars. Most systems span all three — these are
loose conceptual groupings, not rigid boundaries.

### The Three Pillars

1. **Living Grid** — Characters roam the world solo or in small groups, taking missions,
   interacting with rooms and objects, and changing the world through their actions. A
   character might assassinate a target for their guild, protect a caravan, go harvesting,
   or fight in a war — and the consequences ripple outward.

2. **Character Relationships** — Players RP together, develop relationships, grow emotionally,
   strengthen bonds that improve combat effectiveness, share secrets, and discover magic through
   their connections. This is the heart of the game — MUSH players already love relationship RP,
   and our systems mechanically reward it.

3. **GM Tables** — Staff and volunteer GMs run stories for players. Each GM manages a "table"
   of PCs, overseeing their story arcs and adventures. GMs level up with trust, gaining the
   ability to run higher-impact stories. One staffer coordinates all GMs to maintain a single
   connected world.

## Design Principles

These are **hard requirements**, not aspirations. If a system doesn't meet these, it ships
broken regardless of technical correctness.

- **Engagement is survival.** The game lives or dies on social energy. If players aren't having
  fun and falling in love with their characters and the world, the self-sustaining RP ecosystem
  collapses. Systems must actively create fun, not just be mechanically correct.

- **Reward what players already enjoy.** RP, relationships, creative writing, dramatic moments —
  these are what MUSH players do naturally. Our systems give mechanical rewards for them.

- **Escape valves everywhere.** Encourage dramatic intensity and rivalry, but always provide easy
  de-escalation and opt-out. Players must never feel trapped or obligated. When drama stops being
  fun, there must be an easy exit.

- **No PVP killing.** This frees us from symmetrical balance concerns and lets us optimize for
  "feels cool" rather than "perfectly fair." Combat is always Players vs. the Bad Guys.

- **Heroic by design.** Systems should consistently set the stage for breakthrough moments — being
  battered down, on the edge of defeat, then breaking through to become who you were meant to be.
  Think superhero team-up arcs, not grindy attrition.

- **Web-first UX.** Design for modern web interfaces with interactive components, visual feedback,
  and responsive layouts. Don't design around text-command-and-response patterns. Let telnet
  support follow where it can.

For the day-to-day rules that flow from these pillars — player respect
hard rules, cooperative-RP constraints, risk visibility, GM authority
limits, IC-vs-UI placement, etc. — see [`design-tenets.md`](design-tenets.md).

## System Domains

| Domain | Status | Summary |
|--------|--------|---------|
| [Character Creation & Identity](character-creation.md) | skeleton | 11-stage CG flow, backstory, appearance, species, paths. CG-world content now seedable (#1333); admin Game Setup hub for clone hosts. |
| [Character Progression & XP](character-progression.md) | in-progress | XP, skills, path steps, Audere Majora, power tiers, the Durance |
| [Magic System](magic.md) | in-progress | Affinities, resonances, gifts, techniques, threads, spells |
| [Capabilities & Challenges](capabilities-and-challenges.md) | in-progress | Properties, capabilities, applications, action generation, challenges, situations |
| [Combat](combat.md) | in-progress | Party combat (Phases 1–9 + clash + web UI + escalation/passives/aftermath complete; NPC-tier gap tracked), battle scenes, duels |
| [Missions & Living Grid](missions.md) | not-started | Branching narrative quests, world consequences, CK-style events |
| [Crafting, Fashion & Economy](crafting-economy.md) | not-started | Crafting, fashion-resonance loop, housing, shops, domains, ships |
| [Items & Equipment](items-equipment.md) | not-started | Worn items, body slots, item stats, fashion integration |
| [Rooms, Buildings & Estates](rooms-and-estates.md) | skeleton | What ownership of rooms/buildings/estates unlocks — servants, decoration, vaults, special-purpose rooms |
| [Relationships & Bonds](relationships.md) | in-progress | Relationship types, situational mods, soul tethers, party bonds |
| [RP Interaction & Scenes](rp-scenes.md) | in-progress | Rich text editor, action-attached poses, scene engagement, three-mode round framework |
| [Events](events.md) | **MVP complete** | Scheduled RP gatherings, calendar, invitations, room modifications |
| [Stories & GM Tables](stories-gm.md) | in-progress | Story arcs, GM tables, trust tiers, time reconciliation |
| [Codex & Knowledge](codex.md) | in-progress | Lore repository, character-scoped knowledge, research, secrets |
| [Investigation & Discovery](investigation-discovery.md) | in-progress | Clue model, room search, passive triggers, collaborative research projects, gating, rescue-as-clue — core loop shipped; trigger sources + journal UI remain |
| [Journals & Expression](journals.md) | in-progress | IC writing, praises/retorts, freeform tags, weekly XP rewards. Action-backed (#1350): web+telnet (`CmdJournal`/`CmdGoal`) converge on `action.run()` |
| [Societies & Organizations](societies.md) | in-progress | Societies, organizations, reputation, legend, alter egos |
| [Achievements & Discoveries](achievements.md) | in-progress | Achievement tracking, first-to-discover, stat tracking, chains |
| [OOC Social & Community](ooc-social.md) | in-progress | Kudos, friend tracking, visibility controls, engagement tools |
| [World Clock & Scheduled Systems](world-clock.md) | in-progress | Game clock, scheduler, weather, timed emits, holidays, rate limit resets |
| [Tooling](tooling.md) | in-progress | Player building tools, GM tools (level-gated), staff tools |
| [Covenants](covenants.md) | in-progress | Roles, speed ranks, gear compatibility, Thread anchor + API shipped — covenant entity / lifecycle / formation ritual still post-MVP |
| Vitals | in-progress | CharacterVitals model; #521 shipped the sheet surface — VitalsPanel on the character sheet over an owner/staff-gated `GET /api/vitals/<id>/`, FatigueBars extraction wiring the formerly-unmounted fatigue display (FatigueStatusView removed) — needs non-combat integration |
| [GM System](gm-system.md) | in-progress | Phases 0-3 complete: identity, tables, roster/invites. Phase 4 dissolved into Stories; Phase 5 UI deferred until after Stories |
| [Staff Inbox & Player Submissions](staff-inbox.md) | in-progress | Staff frontend complete; player-facing submission forms pending (Phase 5b) |

### Cross-cutting initiatives

- [Seed Mechanism + Integration Test Coverage](seed-and-integration-tests.md) — making the project clonable and every L1 user story regression-tested. Three phases: magic completeness → integration test framework expansion → seed for clone use. Audit at `docs/audits/2026-04-26-seed-and-integration-coverage-audit.md`. **Sequenced before broad UI work.** Phase 3's cluster-master relocation (3.2, #1220) is done — masters now live in `src/world/seeds/game_content/`, with a compatibility facade in `integration_tests/game_content/`. The "Phase B #1221 makes them tunable" follow-on also shipped: admin-hosted Game Tuning & Game Ops dashboards (`/admin/_tuning/`, `/admin/_ops/`) plus a superuser content-repo load surface — see [tuning.md](../systems/tuning.md) and ADR-0093.

### Recent Infrastructure Changes

- **Admin-hosted Game Tuning & Game Ops dashboards + content-repo load (#1220/#1221, complete):**
  - **Game Tuning** (`/admin/_tuning/`, `admin_tuning`) — four HTMX-fragment panels: check-engine
    probability distributions (`web/admin/tuning/checks_analytics.py`), a consequence-pool inspector
    (`consequence_analytics.py`), condition danger ranking (`condition_analytics.py`), and a Monte
    Carlo party-vs-boss simulation form backed by `world.combat.simulation.run_party_vs_boss_simulation`
    (drives the real `resolve_round` pipeline inside rolled-back transaction savepoints — nothing
    persists).
  - **Game Ops** (`/admin/_ops/`, `admin_ops`) — five panels: progression/economy/story/reports
    analytics (`web/admin/tuning/metrics.py`) plus a refresh-on-demand Technical Health panel
    (`tech_health.py`: idmapper RAM, process RSS/CPU, open system errors, deploy SHA).
  - Superuser-only external content-repo load surface (`web/admin/content_load_views.py`,
    `CONTENT_REPO_PATH` env var) upserting into the DB via `core_management.content_fixtures`;
    linked from the Game Setup hub alongside both new dashboards.
  - Built on the existing `ArxAdminSite` with `django-htmx` + vendored `htmx.min.js`, not
    `django-unfold` (deviation from the original #1221 spec — see ADR-0093, which narrows
    ADR-0022's admin-hosted-not-React decision). Details: [tuning.md](../systems/tuning.md).

- **Scene-adaptive cast + three-mode round framework (#1351, complete):**
  - `SceneRoundMode` TextChoices (`OPEN` / `POSE_ORDER` / `STRICT`) on `SceneRound`. Social rounds
    default to `POSE_ORDER` (immediate, quorum-driven advancement). Danger rounds are `STRICT` (#1466).
    STRICT rounds gather declarations and resolve batch. `SceneRoundDefaultsConfig` (singleton pk=1)
    lets staff tune `default_mode`, `advance_quorum_pct`, `max_actions_per_round`,
    `per_target_repeat_lock`, and `anti_spam_seconds`.
  - `SceneActionDeclaration` is now a multi-action-per-round ledger: `is_immediate` bool, `target_persona`
    FK, no unique-per-round constraint. `actions_this_round` / `distinct_actors_this_round` helpers in
    `round_services.py`. `record_pose_order_action` + `advance_pose_order_round_if_quorum` for action-driven
    quorum. `scene_round_is_complete` / `maybe_resolve_scene_round` for STRICT social rounds.
  - `SceneRoundContext.is_declaration_open` now requires `mode==STRICT`. `is_repeat_blocked` branches
    on mode. `record_immediate_action` writes the POSE_ORDER ledger and advances quorum.
  - `ActionBackend.SCENE_ADAPTIVE` + `_dispatch_scene_adaptive` in `actions/player_interface.py`:
    anti-spam floor → `round_declaration` hook → `is_repeat_blocked` → immediate execution with
    pose-order side-effects.
  - `Action.round_declaration` hook in `actions/base.py` (default None). `CastTechniqueAction` returns
    a combat declaration when inside a `CombatRoundContext`, else None (immediate in social rounds).
  - `CastTechniqueAction` (key `"cast_technique"`, `actions/definitions/cast.py`) + soulfray consent
    gate via `confirm_soulfray_risk` / `SoulfrayPendingHandler` (`world/magic/offer_handlers.py`) +
    in-memory anti-spam + pending-cast store (`commands/pending_actions.py`).
  - Unified `cast` command (`CmdDeclareTechnique`, `commands/combat.py`; key `cast`): parses
    `cast <technique> [at <target>] [effort=<level>]`, emits a SCENE_ADAPTIVE `ActionRef`. The
    prior `CmdAttempt` in `commands/magic.py` was deleted.

- **ModifierTarget rename (Phase 1 complete):** `ModifierType` has been renamed to `ModifierTarget`
  across the entire codebase for clarity. Stat-category targets now have a `target_trait` FK for
  type-safe lookups. Remaining categories (action_points, development, etc.) will get target FKs
  when their respective systems are built. See `src/world/mechanics/TECH_DEBT.md` for the tracking
  table.

### Critical Infrastructure Gap: Reactive Layer Activation

The flows/triggers system in `src/flows/` is a fully-implemented reactive engine —
`Event`, `TriggerDefinition`, `Trigger`, `TriggerRegistry`, `FlowDefinition`,
`FlowExecution` all exist with passing tests. But it has **no content**: no events
are emitted at most reactive moments, no FlowDefinitions or TriggerDefinitions live
in the database, and no system declares triggers to attach. This means the entire
architectural answer to "something happens when X" — curses, environmental hazards,
item reactions, divine wrath, allergies, contact effects, observer reactions —
**currently cannot be authored at all**, despite the machinery existing.

This gap was not previously called out in any roadmap doc and blocks reactive
features across every gameplay domain. It is scheduled to be addressed as
[Magic Scope #5.5 (Reactive Foundations)](magic-build-history.md), sequenced immediately after
Magic Scope #5. Mage scars are the wedge consumer; the resulting plumbing is
cross-cutting infrastructure that combat, items, environments, and missions all
inherit. **This work needs to follow Scope 5 sooner rather than later.**

### Status Key

- **skeleton** — Core structure and models exist, but major features are still missing
- **in-progress** — Some pieces are built, significant work ahead
- **not-started** — Nothing meaningful built yet

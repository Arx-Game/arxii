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
| [Combat](combat.md) | in-progress | Party combat (Phases 1–9 + clash + web UI, now including the GM lifecycle panel [#3067: create/spawn NPC/manual round control/ready-toggle] + escalation/passives/aftermath complete; NPC-tier gap tracked), battle scenes, duels — champion-duel/battle staging still telnet-first |
| [Missions & Living Grid](missions.md) | in-progress | Branching narrative quests, world consequences, co-op group beats, support moves |
| [Crafting, Fashion & Economy](crafting-economy.md) | in-progress | Crafting expressiveness arc (#2881) + market/fence + fashion cachet economy (#2959) shipped; housing purchase, p2p trade (#2990), harvesting (#2998) remain |
| [Items & Equipment](items-equipment.md) | in-progress | Worn items, body slots, layered coverage + Reveal (#2965) shipped; body markings (#2985) and visible-equipment web polish remain |
| [Rooms, Buildings & Estates](rooms-and-estates.md) | skeleton | What ownership of rooms/buildings/estates unlocks — servants, decoration, vaults, special-purpose rooms |
| [Relationships & Bonds](relationships.md) | in-progress | Relationship types, situational mods, soul tethers, party bonds |
| [RP Interaction & Scenes](rp-scenes.md) | in-progress | Rich text editor, action-attached poses, scene engagement, three-mode round framework |
| [Events](events.md) | **MVP complete** | Scheduled RP gatherings, calendar, invitations, room modifications |
| [Stories & GM Tables](stories-gm.md) | in-progress | Story arcs, GM tables, trust tiers, time reconciliation |
| [Codex & Knowledge](codex.md) | in-progress | Lore repository, character-scoped knowledge, research, secrets |
| [Investigation & Discovery](investigation-discovery.md) | in-progress | Clue model, room search, passive triggers, collaborative research projects, gating, rescue-as-clue — core loop shipped; trigger sources + journal UI remain |
| [Journals & Expression](journals.md) | in-progress | IC writing, praises/retorts, freeform tags, weekly XP rewards. Action-backed (#1350): web+telnet (`CmdJournal`/`CmdGoal`) converge on `action.run()`. Web frontend shipped (#2160): `/journals` page + in-scene sidebar tab |
| [Societies & Organizations](societies.md) | in-progress | Societies, organizations, reputation, legend, alter egos |
| [Achievements & Discoveries](achievements.md) | in-progress | Achievement tracking, first-to-discover, stat tracking, chains |
| [OOC Social & Community](ooc-social.md) | in-progress | Kudos, friend tracking, visibility controls, engagement tools |
| [World Clock & Scheduled Systems](world-clock.md) | in-progress | Game clock, scheduler, weather, timed emits, holidays, rate limit resets |
| [Tooling](tooling.md) | in-progress | Player building tools, GM tools (level-gated), staff tools |
| [Covenants](covenants.md) | in-progress | Roles, speed ranks, gear compatibility, Thread anchor + API shipped — covenant entity / lifecycle / formation ritual still post-MVP |
| Vitals | in-progress | CharacterVitals model; #521 shipped the sheet surface — VitalsPanel on the character sheet over an owner/staff-gated `GET /api/vitals/<id>/`, FatigueBars extraction wiring the formerly-unmounted fatigue display (FatigueStatusView removed) — needs non-combat integration |
| Wills & Estates | shipped | #1985: `world/estates` — wills (bequests/executors/testament), player-first timer-backed settlement (funeral / will-reading / sweeper doors, ADR-0133), intestacy cascade + escheat, debts-first execution, stolen-goods consent gate, inherited theft claims, Agreements sheet tab |
| Accusation counter-play | shipped | #1825 (ADR-0135): the full frame-job loop — `gossip smear` (one-move L1), crime evidence (gather/dispose/tamper — physical items), Workshop of Iniquity + FRAME_JOB projects (evidence-grown L3), hub counter-clues → LAB investigation → nullification + author-unmask, consentless refute vs consent-gated denounce (Tom/Bob/Fred rule), case-file produce/examine, Skulduggery rename + criminal specializations. Lethality + enforcement shipped, see Justice row below; achievements → #2377 |
| [Justice](../systems/justice.md) | shipped | Local law + persona pursuit heat (#1765), lifecycle (#1826: lie low/bribe/pardon/wanted boards), pipeline (#2492: guard encounters → captivity → captive-initiated trial), and sentence enforcement (#2378, ADR-0233): daily sweep (`sentence_sweep_tick`) serves brig terms and carries out/voids terminal sentences past their rescue window; EXILE (`ExileDecree` + heat pin riding the existing pursuit ladder) and breach-of-exile re-capture; CONFISCATION into brig-backed custody (`room_features.brig_services`); per-society `SentenceLadderRung` escalation; the terminal fork (EXECUTION behind ADR-0023's unchanged lethal wall, BANISHMENT the new non-lethal terminal); verdict/brig-visitation notifications + a `tidings` VERDICT feed item; wanted-board public marks + my-case sentence fields. **HUMILIATION (#2378 follow-up, ADR-0236, 2026-08-27):** two-layered — a PERMANENT physical brand (`mint_humiliation_brand`, documented no-op seam pending TehomCD's scar substrate) atop a TEMPORARY reputational layer (the mechanics-only prestige hit, persisted + restored exactly at `HUMILIATION_TERM_DAYS` by the sweep's `_sweep_humiliation_restores` leg, plus a persona-scoped examine/profile explanation, `active_humiliation_mark` → `PersonaSerializer.humiliation_mark`). Verdict-notification audience (area-feed only) and public-records permanence ratified as-built, no code change. **Remains:** arena/trial-by-combat mechanics (`ARENA_TRIAL` rungs seeded but inert — TehomCD's combat substrate); magical-detection wiring for the `is_magically_concealed` seam (TehomCD); the humiliation brand's real minting (TehomCD's scar system); realm sentencing-ladder content, execution-method prose, and all other PLACEHOLDER copy in the sentencing paths, plus humiliation prose specifically (lore/Apostate pass) |
| [GM System](gm-system.md) | in-progress | Phases 0-3 complete: identity, tables, roster/invites. Phase 4 dissolved into Stories; Phase 5 UI deferred until after Stories |
| NPC Lifecycle (tier ladder) | shipped | #2827 all 5 phases: sheet-spine identity (ADR-0176), venue auto-staffing on building activation, instantiate-on-engagement with regional name cultures, dual-mode recruitment (in-place default + extraction), personality/aptitude layer, standing promotion/demotion + roster graduation. Content authoring (staffing profiles, name pools, personality vocabulary) pending — same #2692 sequencing. See `docs/systems/npc-lifecycle.md` |
| Mundane stealth (sneak/unsneak) | shipped | #3288 (ADR-0228): hidden identity, disclosed presence — sneak stance over the #1225 `Concealed` seam via the previously-uncalled `resolve_security_check(SNEAK)` oracle (upgraded to modifier-aware); per-room silent rolls with arrival re-rolls; one-way disclosure (anonymous arrival echo + room-derived `has_unseen_presence` on room_state, silent departures); guard contest replaces the per-entry dice tax; identity-free hidden-presence report path (server-side resolution, staff-eyes-only); `search` already pierces per-observer. Completes the burglary loop (locks #2176, theft #1909, guards #2178) |
| Tasking (covert orgs & spy networks) | shipped | #2820 all 5 phases: `world/tasking` dual-fulfillment primitive (NPC double-check offscreen resolution OR PC mission into one outcome table); covert org types with membership Secrets + parent-org spymaster oversight; org-held agents; listener posts (weekly buzz from mechanical residue only, ADR-0175) with in-person harvest collection; spy-vs-spy counterplay (suppress/flip/plant/detect/clear, `espionage` consent category); org board API + OrgPage panels. Content authoring (templates, covert org rows) pending — sequence with Tehom's #2692 pass. See `docs/systems/tasking.md`, ADR-0174/0175 |
| [Staff Inbox & Player Submissions](staff-inbox.md) | in-progress | Staff frontend complete; player-facing submission forms pending (Phase 5b) |

### Cross-cutting initiatives

- [Seed Mechanism + Integration Test Coverage](seed-and-integration-tests.md) — making the project clonable and every L1 user story regression-tested. Three phases: magic completeness → integration test framework expansion → seed for clone use. Audit at `docs/audits/2026-04-26-seed-and-integration-coverage-audit.md`. **Sequenced before broad UI work.** Phase 3's cluster-master relocation (3.2, #1220) is done — masters now live in `src/world/seeds/game_content/`, with a compatibility facade in `integration_tests/game_content/`. The "Phase B #1221 makes them tunable" follow-on also shipped: admin-hosted Game Tuning & Game Ops dashboards (`/admin/_tuning/`, `/admin/_ops/`) plus a superuser content-repo load surface — see [tuning.md](../systems/tuning.md) and ADR-0093.

### Recent Infrastructure Changes

- **Single-app collapse (#2906, complete):** every first-party Django app (66 `world.*`
  apps, plus 27 models folded in from `actions`/`flows`/`behaviors`/`evennia_extensions`/
  `web.admin` via an explicit `Meta.app_label`) collapsed into one: package `world`,
  label `arxii`. `world/` directories did not move - `world.magic`, `world.roster`, etc.
  still work as import paths and `just test-fast world.<app>` targets - but there is now
  one Django app, one `src/world/migrations/` history (102 files: 100 cost-weighted
  chunks carrying the 1,026 `CreateModel` operations, plus 2 tail migrations), and one
  `max_migration.txt` sentinel repo-wide. Measurement after the fact found the collapse
  alone was *not* the speed win the original hypothesis claimed - topologically inlining
  deferred FKs down from Django's 2,321 to the schema's true floor of 49 is what actually
  produced the ~1.3x faster fresh `migrate`, and the collapse's real payoff is that the
  floor without it stays at 1,153 (46 of the 68 pre-collapse apps shared one dependency
  cycle). The single `max_migration.txt` sentinel also raises merge-collision odds rather
  than lowering them, per CLAUDE.md's Git Workflow section. See ADR-0195 for the full
  decision, the rejected alternatives, and the consequences (dev DBs must be rebuilt and
  reseeded; `core.app_domains.domain_of()` now supplies the authoring-domain grouping
  `app_label` used to carry, for the admin index, the lore repo's `fixtures/<domain>/`
  layout, and the admin pin/exclude keys; model names must stay globally unique for
  `resolve_model_by_name`; `tools/build_schema.py` remains the right path for fresh-
  database bootstrap, migration-replay speed only matters for deploys that replay
  history). Also renamed
  `achievements.AchievementRequirement` to `AchievementStatRequirement` (Task 3) to
  disambiguate it from the pre-existing, distinct `progression.AchievementRequirement`.

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
    linked from the Game Setup hub alongside both new dashboards. Phase 2 (#2266, complete):
    extended past `stats`/`skills` to `npc_roles`, `items`, `building_kinds`,
    `decoration_kinds`; fixed `DecorationKind`/`ArchitecturalStyle` seeder rows that carried
    `PLACEHOLDER` in the *name* (silently orphaning the seeded row instead of being
    superseded by content); rooms/areas remain deferred (no natural key today). Game Setup
    inventory now also tracks `Trait` (the #944 Phase-1 domain had none) and
    `BuildingKind`/`DecorationKind`.
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

- **Durable character-selection foundation (#3412 slice 1, complete, ADR-0241):** the
  four-state model (logged out / logged in-no-selection / selected / puppeting) gets its
  state-2.5 substrate. Backend: `PlayerData.selected_entry` (nullable FK → `RosterEntry`,
  `SET_NULL`), sole mutator `world.roster.services.selection.set_selected_entry`
  (zero lifecycle/session/puppeting side effects by design), `POST
  /api/roster/entries/select/`, `selected_entry`/`selected_entry_id` added to `GET
  /api/user/`. Frontend: `gameSlice` mirrors the server fact (hydrated every account
  fetch, so a hard reload or a second device reproduces the same selection); app-wide
  `SelectedCharacterChip` in `Header` (portrait, reused `PersonaSwitcher`, "Enter the
  world" link, "step away" clear); `GamePage`'s mount-path effect auto-starts the
  session on arrival when a selection exists but nothing is puppeting yet — the one
  deliberate selection→presence crossing. Degradation sweep + hygiene fold-ins done in
  the same slice (fold in, don't file): tidings/wardrobe loading states, a mute-settings
  link, three message-tab fixes, notification badge routing, nine feed-kind labels,
  consent-notifier gating, and a second remedy on `RequireCharacter`'s zero-character
  guard. Slice 1 is deliberately chrome + substrate only — **no Hall page, no 2.5 act
  gates, no offscreen acts** (those are slices 2-3). See
  [roster.md](../systems/roster.md) for full model/service/endpoint/frontend detail and
  ADR-0241 for the rejected alternatives.
  - **Known seams for slice 2/3:** per-character narrative unread counts need a new
    backend filter/field — `narrative/views.py`'s unread queryset is account-only today,
    verified absent rather than assumed. `gameSlice`'s name-keyed shape (not
    `RosterEntry` id) is a deliberately deferred wart; the entry-id refactor touches an
    estimated 25 call sites and is out of this slice's scope. Migration-number and
    ADR-number collisions with in-flight PRs are expected and resolve at enqueue time
    per the standard recipe (`arx manage rebase_migration arxii` /
    renumber-at-merge) — not a defect of this slice.

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

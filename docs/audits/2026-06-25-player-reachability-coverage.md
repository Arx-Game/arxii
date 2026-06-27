# Player-Reachability Coverage Audit

**Date:** 2026-06-25 — **Tracking issue:** [#1328](https://github.com/Arx-Game/arxii/issues/1328)
**Supersedes:** `docs/audits/2026-06-21-telnet-driveability-ui-parity.md` (which measured telnet-vs-web
parity — the wrong axis; see "Why the reframe" below).
**Scope:** every player- and GM-facing *mutating* capability in the game apps, sorted by whether a
player (or table-running player-GM) can actually reach it. Built from a 13-part code sweep (six deep
journeys + seven app-cluster sweeps); the per-capability backing is the working ledger that produced
this doc.

> **This doc is never "done."** Coverage is tracked **per capability**, not per journey. No journey is
> marked complete; a journey is only ever "these capabilities are reachable, these are not yet." The
> ledger grows as journeys are walked and as new capabilities land.

---

## Why the reframe

The prior audit asked **"telnet vs web parity."** That measured the wrong thing. Two corrections:

1. **GMing is a player activity, not a staff-only lane.** Players run stories at tables they own — we
   *want* crowdsourced GMing; staff GM too and provide oversight. So "run a combat round," "mark a
   story beat," "spawn an NPC," "seat players at a table," "set a round's mode" are **player journeys**
   that must be drivable from the backend and covered by end-to-end tests — exactly like casting. The
   old audit's "GM steps are out of scope, a player never does them" exclusion erased an entire
   subsystem. It is wrong, and it is contradicted by code: scene-round GM control already ships as
   Actions with a telnet command and a 9-step GM E2E test (`test_scene_round_journey_e2e.py`).

2. **The real question is reachability, not which UI.** A telnet command and a web action both express
   *intent to use an action*; the active scene's rules (`SceneRound` OPEN/POSE_ORDER/STRICT, #1351)
   decide whether it resolves now, waits, or is blocked. Combat, a GM-run table, a private
   relationship scene, a dreamstate, an illusion, a ritual are all **varieties of one umbrella journey
   — the scene** — over that shared seam. What matters per capability is: *can a player reach it at
   all, and on which surface?*

Measured that way, the dominant failure mode is **not** missing telnet verbs. It is **built engines no
player can reach on any surface** (NO-SURFACE) and **designed systems with no code** (PLANNED-UNBUILT).
A built engine nobody can touch is a bigger "can a player do X?" hole than a missing telnet verb.

## Severity tiers

Ordered worst→best for "can a player do X?":

| Tier | Meaning | ~count |
|---|---|---|
| **PLANNED-UNBUILT** | Designed/intended; no service, model, viewset, Action, or command. | ~40 (+ unrecorded) |
| **NO-SURFACE** | Service/engine built and tested, but reachable from **no** UI (no viewset, no Action, no command). Built but dead. | ~50 |
| **WEB-ONLY** | Reachable on web (viewset/`@action`), but no telnet command and often not on the shared `action.run()` seam. Not yet E2E-testable backend-first. | ~55 |
| **TELNET+WEB** | Driveable both ways over `action.run()`. The goal. | ~30 |

> Severity rank: **PLANNED-UNBUILT ≈ NO-SURFACE > WEB-ONLY > TELNET+WEB.** PLANNED-UNBUILT systems are
> recorded in `docs/roadmap/planned-systems.md` (not the ledger below — they have no code to locate).

---

## The capability ledger (canonical backbone)

Each capability has exactly one row here; the journey-lens (next section) references rows rather than
re-listing them, so each row maps cleanly to one tracking issue. `tracked` = existing live issue, or
`untracked`. Tier marked in **bold**.

### Scenes & social RP (the umbrella)
- TELNET+WEB: say / pose / emit / whisper / mutter; consent request + accept/deny (#1338); endorse
  pose / scene-entry / style (#1340); fashion judge (#514); intimidate / persuade / deceive / flirt /
  perform; entrance + restore-sense; resolve entry-flourish (CmdFlourish — makes #1246 stale).
- WEB-ONLY: interaction reactions & favorites (#1341); mark-interaction-private (ADR-0033 privacy);
  Places join/leave (place_views); ephemeral scene collaborative summary submit/edit/agree (the ADR-0006
  keep-vs-discard agency); persona deed-spread + save-deed-story (#745 — and these bypass `action.run`,
  ADR-0001); scene start/finish + set-round-mode (telnet `scene round` exists; lifecycle partial).
- **PLANNED-UNBUILT (→ registry):** implicit/frictionless scene start (#1309); provisional EPHEMERAL
  keep/discard (#1309, ADR-0006); auto-close empty scene (#1361); **private scene variety**;
  **GM-run-table as a live scene mode**; **dreamstate / illusion scene varieties** (shared
  perception-override primitive); community pose-of-the-scene voting.

### Combat & duels
- TELNET+WEB: declare technique w/ effort/target/secondary (#1330); clash-commit (#1451); flee / cover
  / interpose / join / leave / ready / combo up-down / yield (#1453); PvP **duel** lifecycle —
  challenge / accept / decline / withdraw / acknowledge-risk (`duel <subverb>`, `CmdDuel`, #1492; was
  WEB-ONLY — telnet command added, only `yield` had reached telnet before via `combat yield`).
- **PLANNED-UNBUILT (→ registry):** soulfray-risk accept + fury commit (#1454); knockback + trap-in-combat
  (#1317); reactive interpose / DANGER-arming (#1316); shapeshift + combat profiles (#1111); ranged /
  reach / archery; mounts; verticality / flying.

### GMing / running a table  *(player activity — first-class journeys)*
- TELNET+WEB: scene-round set-mode (`scene round`); gemit / emit / pemit (staff perms).
- WEB-ONLY: **combat-encounter lifecycle** — create encounter, begin_round, resolve_round, add_opponent,
  opponent_defaults (difficulty), add/remove participant, pause, end; **story-runner** — create
  story/chapter/episode, **mark a beat**, resolve/promote episode, complete story, story OOC,
  transitions, scheduling, assistant-GM claims, story→table offers, Era advance/archive; **GM tables**
  (world/gm) — create/archive/transfer table, seat members, roster invites, GM applications; **mission
  authoring** (templates / assign / nodes / options / rewards).
- NO-SURFACE: `finalize_gm_character` (GM character/NPC authoring, unwired); trap
  **arming/placement** absent (only disarm exists). `set_the_stage` GM positioning is now
  TELNET+WEB (telnet `setstage`, #1498 — was WEB-ONLY).
- **PLANNED-UNBUILT (→ registry):** umpire check-modifier tooling; GM trust→risk leveling; live
  Situation/Encounter session resolvers; cross-table GM availability marketplace.

### Progression, skills & classes
- TELNET+WEB: leveling via "Ritual of the Durance" (CmdRitual draft/join/fire); Audere & Audere Majora
  intensity/tier crossing (#1344); imbue a thread (raises thread level); **deliberate skill-raising**
  (create/update/remove `TrainingAllocation` via `ManageTrainingAction` + `training` telnet command + `GET/PATCH/POST/DELETE /api/skills/training-allocations/`, and weekly `process_weekly_training` / `apply_weekly_rust` cron — #1488); **spend XP on a class-level or thread XP-lock unlock** (`PurchaseUnlockAction` + `progression unlock` telnet command + `POST /api/progression/unlocks/purchase/` — #1489).
- WEB-ONLY: progression rewards — claim kudos / cast-remove vote / random-scene / path-intent (#1348,
  also ADR-0001 bypass).
- **NO-SURFACE:** (none remaining in this category for progression/skills).
- **PLANNED-UNBUILT (→ registry):** **spell system** (learnable, path-independent); **post-CG Gift
  acquisition** (magic currently freezes at CG); trainer system; path discovery/research/switching;
  technique-designer consequence-pool catalog (#1320).
- **DESIGN-CLARIFICATION (not a build item):** whether/how magic checks use the path→**aspect**
  *competence* bonus (#1363). `Aspect`/`PathAspect`/`_calculate_aspect_bonus` are **built and live for
  checks generally**; magic checks only seed a placeholder `Arcana` aspect, so path investment does
  ~nothing for magic yet — the open question is whether it should. (Mapping resonance→aspect was
  *rejected* in closed #1357 as double-counting what `power_terms` already does.)

### Magic (beyond cast/ritual/imbue/thread/soul-tether, which are TELNET+WEB)
- TELNET+WEB: pose / scene-entry / style endorsements (resonance grants); restore-sense (talk-down).
- WEB-ONLY: technique authoring ("design a spell"); **alteration resolution** (clear a Mage Scar — and
  this *gates advancement*, so telnet players are blocked); CharacterResonance/Aura/Gift/Anima raw CRUD.
- TELNET+WEB: **sanctum** 7-op subsystem (install / homecoming / purging / weave / dissolve / absorb /
  sever) — `CmdSanctum` + `SanctumViewSet` both converge on `action.run()` (#1497).
- **PLANNED-UNBUILT (→ registry):** ResonanceGrantReversal (endorsements currently irreversible);
  multi-target per-target consent state machine (ADR-0045); soulfray progression (#712).

### Body-state: conditions, vitals, fatigue, action points
- TELNET+WEB: restore-sense (removes Berserk via check); **fatigue rest** (spend AP → Well Rested,
  `RestAction` + telnet `rest` + web `RestView` — both routes converge on the same action, #1491).
- **NO-SURFACE:** **condition treatment/heal** (`perform_treatment` — THE heal-another-character loop,
  built+tested, zero live callers; `restore_sense` covers only the narrow check-driven Berserk removal,
  not the general loop); suppress/unsuppress/clear conditions; vitals damage/bleed/heal (internal,
  combat-tick driven — by design).
- **PARALLEL-IMPL / wired (corrected — these are NOT no-surface):** fatigue **power-through /
  endurance-check** are *wired* (run on every round via `resolve_fatigue_collapse` ← action pipeline +
  `vitals.tick_round_for_targets`). Action-point `unbank()` is wired (codex teaching-cancel); regen
  *is* scheduled — but via a parallel cron reimplementation (`_apply_ap_regen`) rather than the model's
  `regenerate()` (ADR-0016 cleanup, not a missing scheduler); only `bank()` is dead.

### Threads, relationships & soul-tethers
- TELNET+WEB: weave / imbue / pull a thread (#1342); soul-tether burden/bear/entreat/consume/mire/
  rescue/dissolve/pleas (#1343).
- WEB-ONLY (telnet-parity, secondary): accept thread-weaving teaching offer (acquire the unlock); sever
  thread; cross-xp-lock. **Note:** thread *rename* is already web-wired via the default `ThreadViewSet`
  PATCH; the `update_thread_narrative` service is an unwired stub *duplicating* it — remove, don't wire.
- **NO-SURFACE:** **the entire relationship-building loop** — create_first_impression / create_development
  / create_capstone / redistribute_points (built+tested, reachable from neither UI, absent from #1328
  until now). Only register_grievance is wired.
- **PLANNED-UNBUILT (→ registry):** relationship mechanical-bonus consumed in checks; teamwork / combo /
  coordination gating; RelationshipUpdate service + decay/freeze; relationship consent/deceit safety
  (privacy MVP-gating); adventuring-party model; NPC reputation model.

### Covenants
- (none currently TELNET+WEB)
- WEB-ONLY (telnet gap, folds into #1346): engage/disengage/leave/kick/assign-rank/transfer-top,
  banner-call, stand-down, induct, AND rank-ladder authoring (create/rename/set-caps/reorder/delete —
  inside #1346's "rank commands" telnet scope).
- **Mostly WIRED — corrected:** found/charter is reachable via the **FORMATION ritual** (web #1313 /
  telnet #1346), not web-unreachable; **covenant rites** (Fury/Bulwark) are wired via the ritual surface
  (create a `CovenantRiteInstance`); **mentor bond** establish (Mentor's Vow ritual) AND dissolve (combat
  auto-graduation) are both wired; sub-role `end_covenant_role` is wired (leave/kick).
- **REFRAME → needs-design (design-open, not built work):** voluntary **disband** (covenants currently
  auto-dissolve below minimum — is manual disband wanted?); member **re-role** (`change_role` — via what
  ceremony?); `assign_covenant_role` may be superseded by `induct_member_via_session` (dead-code check).
- **PLANNED-UNBUILT (→ registry):** org-level ritual-leadership permissions (#708); society politics
  (army/military, territory, warfare, succession).

### Items, currency, crafting, fashion, character creation
- TELNET+WEB: get/drop/give/put/withdraw; use item; wear/remove/equip; apply-outfit/undress;
  look/inventory; home/recall; persona switch (#1347/#1481); fashion judge (#514).
- WEB-ONLY: crafting — facet attach/detach + style attach (**no `craft` command and no crafting Action
  at all**); outfit/slot CRUD; present-outfit (#514 — also a parallel-impl smell vs PresentOutfitAction);
  activate building permit (Action, no telnet); **all of character-creation** incl. GM application
  claim/approve/deny/request-revisions (web-first by design — recorded, not a defect);
  distinctions-on-draft.
- **NO-SURFACE:** **the entire currency economy** — transfer / mint-redeem instrument / work_chore /
  invest_in_business / sign-settle contract / extend-repay loan / fund_fame_display / treat_servants /
  record_contribution (only pay-ransom is web-wired; players can't earn/spend/give/invest in-game);
  finalize_gm_character; standalone distinction-secret mint/clear.
- **PLANNED-UNBUILT (→ registry):** item-creation pipeline (#1125 — engine only *attaches* facets);
  materials/harvesting; recipe acquisition; station durability/repair (#1234); store/vendor + trade /
  barter / auction (#923); ships/vessels; touchstone items/reagents (#707); Asset/**Companion** subsystem
  (#672 — includes animal companions); Aspects (placeholder concept).

### Space, movement & building
- TELNET+WEB: traverse exit; home; get/drop/give; look/inventory; edit owned room (CmdManageRoom +
  RoomEditAction, #1472 — room-editor HAS telnet parity).
- WEB-ONLY: move_to_position (Places sub-locations, no telnet); disarm_trap
  (#1051); activate_permit (raise a building). `set_the_stage` (GM) is now TELNET+WEB
  (telnet `setstage`, #1498).
- TELNET-ONLY: Dig/Open/Link/Unlink (Evennia builder cmds — room/exit *creation* has no web/Action).
- **NO-SURFACE:** property **transfer_ownership / grant_tenancy / end_tenancy** (the ownership half of
  property mgmt the room-editor doesn't fill); area/blueprint authoring (reparent_area, create_position,
  create_blueprint).
- **PLANNED-UNBUILT (→ registry):** door **lock/unlock** (CmdLock/CmdUnlock are stubs; LockAction/
  UnlockAction don't exist); trap **arming/placement**; verticality/aerial layer player surface.

### Knowledge & expression
- TELNET+WEB: register grievance (CmdGrievance + web, #1429).
- WEB-ONLY: clue **search/investigate** (SearchAction has no telnet command — telnet can't investigate
  at all); goals set/journal (#1350); journals write/edit/respond (#1350); player_submissions
  feedback/bug/report + staff triage/file-issue; narrative story-OOC / ack / mute-story.
- **NO-SURFACE:** secrets **authoring** (`author_player_flavor_secret` — unwired; *granting* secret
  knowledge IS wired via clue acquisition, #1334); goal apply-on-check (#940).
- **WIRED (corrected — NOT no-surface):** **achievements** — `grant_achievement`/`increment_stat` have
  many live callers (covenants/journals/relationships/soul-tether); achievements are auto-earned and
  intentionally have no manual grant/claim endpoint (#1297).
- **PLANNED-UNBUILT (→ registry):** clue collaborative-research (start/contribute); codex teaching
  accept/cancel (learn knowledge unreachable); secrets player-authoring beyond level-1 flavor.

### Social structures & collective play
- TELNET+WEB: tidings **read** (CmdTidings, #1450); persona set-active (#1347/#1481); NPC-service
  hire/commission/request (start/resolve/end — `actions.definitions.npc_services`, telnet `hire`, #1493);
  events full lifecycle (create/schedule/start/complete/cancel/invite — `actions.definitions.events` +
  telnet `event <subverb>`, #1499).
- WEB-ONLY: pay-ransom; roster family CRUD / mail / media / profile-picture; consent **master opt-out + per-category
  rules + standing whitelist** (telnet players can *be* targeted but can't opt out / set allowlists — privacy
  MVP-gating, ADR-0033); spread-deed / save-deed-story (#745).
- **NO-SURFACE:** captivity capture/escape/rescue/resolve + **demand_ransom (zero production callers)**
  (#931 CLOSED — wire-or-remove + telnet surface); create_solo_deed / create_legend_event /
  grant_deed_knowledge (effect-driven by design); roster approve/deny (admin-only) + hiatus/freeze/
  lifecycle (scheduler-only); events add-host / room-overlay; consent groups + visibility-mixin (admin-only).
- **ABSENT / needs-design (corrected — not just no-surface):** society **organization join/leave/promote**
  — these methods do **not exist** on `OrganizationMembership` (no views, no services; admin + factory
  only). Membership management is an absent player capability, not an unwired engine. **projects** has no
  web layer, but it's a *consumed framework* (buildings/clues drive `add_contribution`), not a missing
  player surface — only a gap if a journey needs direct project interaction.
- **PLANNED-UNBUILT (→ registry):** tidings **posting/reacting/commenting** (no model); persona
  mint/edit/delete (reserved for future IC flows); roster **release/end-tenure** (end_date set by
  nothing); projects activation service.

---

## Journey lens (the umbrella, referencing ledger rows)

A **scene** is the umbrella journey. Every variety runs the same `SceneRound` seam; the lens below
shows which ledger capabilities each variety exercises and where its gaps are. None is "done."

- **Scene — general RP:** say/pose/consent/endorse (✔ reachable) · reactions/favorites, mark-private,
  Places, keep-vs-discard summary (web-only / blind spots) · implicit start, provisional keep/discard
  (planned).
- **Scene — combat:** declare/clash/maneuvers (✔) · duel lifecycle (✔ telnet+web, #1492) · ranged,
  shapeshift, knockback (planned).
- **Scene — GM-run table:** scene-round set-mode (✔) · combat-round lifecycle, beat-marking, table
  seating (web-only) · umpire tooling, session resolvers (planned). *The whole GM table-running journey
  is currently undriveable backend-first.*
- **Scene — private / relationship:** say/pose (✔) · **the entire relationship loop**
  (first-impression→development→capstone) is NO-SURFACE · private scene variety is planned. *A scene
  where a relationship is tested and a capstone created cannot actually record that capstone today.*
- **Scene — ritual:** cast/ritual/imbue/session (✔). Most complete journey.
- **Scene — dreamstate / illusion:** planned varieties; share the perception-override primitive.

---

## Concrete bugs (fix-now, distinct from journeys)

These are mis-wirings, not coverage gaps — worth fixing directly:

1. **Roster `apply` is broken** — `apply` @action returns HTTP 204 *without* calling `.save()`; the
   working `RosterApplicationCreateSerializer` is referenced only in tests. The core
   character-acquisition loop has no functioning surface.
2. **`EmitAction` missing from the action registry** — it is wired to telnet `CmdEmit` but omitted from
   `actions/registry.py` `_ALL_ACTIONS`, so the web `execute_action` inputfunc cannot dispatch it.
   Telnet-only by accident, not design.
3. **Persona deed-spread / save-deed-story bypass `action.run()`** — they call
   `create_and_resolve_area_action` directly (ADR-0001 convergence gap) instead of being registry Actions.
4. ~~`RestView._get_character_sheet` uses implicit first-sheet selection (`RosterEntry…first()`) — an
   ADR/standards smell on the fatigue-rest path.~~ Fixed by #1491: `RestView` now routes through
   `RestAction.run(actor=current_character)`, which resolves the sheet from the authenticated actor.

## Stale-doc flags (fix-on-sight per "docs are directives")

- `ROADMAP.md:133-149` claims "no events are emitted / reactive features can't be authored" — **false**:
  `emit_event`/`TriggerDefinition` are wired in combat, conditions, positioning, magic (Milestone #4 closed).
- `ROADMAP.md:92` lists covenant entity/lifecycle as "post-MVP" — **built** (models + services + rise/
  stand-down rituals); the real gap is telnet/UI.
- `character-progression.md:51,146` "training system + skill rust not built" — **built and wired**
  (`TrainingAllocation`, `ManageTrainingAction`, `training` command, `/api/skills/training-allocations/`,
  `process_weekly_training`, `apply_weekly_rust`).
- `codex.md` "research project system needed" — partly **built** (`ResearchProject`, `CodexTeachingOffer`).
- **#1246 is stale-open** — `CmdFlourish` is built; its deferral premise is gone.
- **#537 closed** but the `TODO(research-gate)` in `technique_builder.py:168` is still a live permissive stub.

## Planned-but-unbuilt

Recorded in **`docs/roadmap/planned-systems.md`** — recorded design intent *and* the previously
unrecorded systems (battles/armies, mounts, animal companions, verticality, ranged/archery, aquatic +
drowning, vampires/sunlight, racial gifts & racial progression, Aspects, dreamstates, illusions). The
registry is the durable home so this intent stops getting silently lost; it is also explicitly
incomplete and is the capture surface going forward.

## What's next

- New `coverage-gap`-labelled issues, one per NO-SURFACE / WEB-ONLY gap (deduped against live issues,
  by-design items excluded), parented to #1328. See the proposed-issue list reviewed for this work.
- The bugs above filed/fixed directly.
- The stale docs corrected in the same PR.
- Planned systems recorded in the registry, not as issues.

# Telnet-Driveability & UI Dispatch-Parity Audit

**Date:** 2026-06-21
**Tracking issue:** [#1328](https://github.com/Arx-Game/arxii/issues/1328)
**Scope of this pass:** deep trace of the four priority loops — **magic casting, combat,
thread weaving, social scenes**. Remaining L1 stories (character creation, relationships,
codex, journals, progression, world clock) are a later broad pass.

## Why this audit exists

The goal is to make **telnet a first-class end-to-end testing surface** for whole user
stories. Telnet is pure backend, so driving a story through telnet commands yields a full
`command → … → service-function` integration test with no frontend in the loop. The premise
relies on an architectural invariant: **a telnet command and a web view are interchangeable
UIs over the same code underneath.** If that holds, "works in telnet" ⟹ "works for web
players." This audit measures where it actually holds — and where it doesn't.

## Headline finding

**The genuine UI-shared seam is `dispatch_player_action()`, not `action.run()`** — and the
telnet layer does not call it.

- The web's single dispatch endpoint `DispatchActionView` (`src/actions/views.py:48`) calls
  `dispatch_player_action()` (`src/actions/player_interface.py:78`), which routes by backend:
  - `REGISTRY` → `action.run()` (`player_interface.py:113` → `_dispatch_registry` `:150`)
  - `CHALLENGE` → `resolve_challenge()` (`player_interface.py:117` → `_dispatch_immediate_challenge` `:193`)
  - `COMBAT` → record a declaration (`_dispatch_clash_contribution` `:546`), resolved later by `resolve_round()`
- Telnet commands instead call `self.action.run()` **directly** (`src/commands/command.py:140`).
  That only reaches the `REGISTRY` path. There is **no telnet route to CHALLENGE or COMBAT**.

The docstring at `src/actions/base.py:25-26` — *"Commands (telnet) and the web dispatcher
both call `action.run()`"* — is therefore **misleading**: it is true only for REGISTRY
actions. Magic and combat never touch `action.run()`. **Fix-on-sight target.**

> **[ALREADY CORRECT — audit claim stale, verified #1337]** The `Action` class
> docstring (`src/actions/base.py`, ~lines 27–33) **already** describes the real seam
> and the three dispatch backends; it no longer says telnet calls `action.run()`
> universally. It reads: *"`action.run()` is the entry point for the **REGISTRY** path
> only. … the web frontend and telnet `DispatchCommand`s instead call
> `dispatch_player_action()`, which routes by backend: REGISTRY → `action.run()`,
> CHALLENGE → `resolve_challenge()`, COMBAT → `declare_action()`/`resolve_round()`.
> Magic and combat actions never reach `action.run()` directly."* No fix is needed; the
> "fix-on-sight" call above is itself stale. (History preserved; do not act on it.)

### There are three web dispatch families; telnet implements a slice of one

| # | Web dispatch family | Entry | Reaches | Telnet today |
|---|---|---|---|---|
| 1 | **Unified action dispatch** | `dispatch_player_action()` | REGISTRY→`action.run`, CHALLENGE→`resolve_challenge`, COMBAT→`declare_action`/`resolve_round`→`use_technique` | REGISTRY via `ArxCommand` → `self.action.run()`; COMBAT via `DispatchCommand` → `dispatch_player_action()` (`CmdDeclareTechnique`); non-combat magic via `ArxCommand` → `request_technique_cast` (`CmdAttempt`, RESOLVED #1332) |
| 2 | **Consent flow** | `SceneActionRequestViewSet` (`action_views.py:55`) → `create_action_request`/`respond_to_action_request` (`action_services.py:150/304`) → `start_action_resolution` | Targeted social actions (intimidate, persuade, …) with accept/deny gating | ❌ none |
| 3 | **Direct viewset→service** | dedicated viewsets/views → service fn (no action, no dispatcher) | thread weave/imbue/pull, rituals, outfits, narrative | ❌ none |

## Gap classification

| Class | Meaning | Fix |
|---|---|---|
| **G0 Converged** | Telnet command exists; web uses the *same* seam | None — telnet E2E is a valid web proxy today |
| **G1 Missing shell** | Web seam exists; no telnet command drives it | Add a thin command that calls the *same* seam |
| **G2 Divergent dispatch** | Telnet path and web path would be *different code* | Unify the seam |
| **G3 View-only** | Web reaches a service that has no action/dispatch layer (or a GM/system-only surface) | Decide if a player-facing telnet surface is wanted; if so, call the same service |
| **G4 Not buildable** | Story can't run end-to-end yet (missing seed/service) | Backend/seed gap → its own task |

> **Important nuance on G2:** for magic and combat the underlying *service* seam already
> converges (web reaches `use_technique`/`resolve_challenge` through `dispatch_player_action`).
> The divergence is only that **telnet doesn't call `dispatch_player_action` at all**. So the
> fix is not "make magic an Action subclass" (a large, risky refactor) — it is "let telnet
> commands call `dispatch_player_action()`, the same entry the web uses."

---

## Loop 1 — Social scenes

Freeform RP converges; mechanical social actions do not.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| Say text | `CmdSay` (`commands/evennia_overrides/communication.py:26`) | `dispatch_player_action`→REGISTRY→`SayAction.execute` | **YES** (both `action.run`) | `test_dispatch_social_round.py` | **G0** |
| Pose | `CmdPose` (`communication.py:160`) | same as above → `PoseAction.execute` | **YES** | `test_dispatch_social_round.py` | **G0** |
| Initiate social action (intimidate/…) | ❌ none | `SceneActionRequestViewSet.create` → `create_action_request` (`action_services.py:150`) | **NO** — web uses the *consent flow*, not `dispatch_player_action` | `test_targeted_action_e2e.py` | **G1** |
| Target accept/deny | ❌ none | `…/respond/` → `respond_to_action_request` (`:304`) | **NO** — no telnet consent surface | `test_targeted_action_e2e.py` | **G1** |
| Resolve + apply consequence | ❌ (only via consent path) | `respond_to_action_request` → `start_action_resolution` (`:470`) | resolution seam *is* shared; telnet can't reach it | `test_targeted_action_e2e.py` | **G3** |

**Trap:** the 8 social-action singletons exist (`actions/definitions/social.py`) and a naive
telnet command calling `action.run()` would resolve **immediately, skipping consent** — a
different semantic than the web. A telnet command must call `create_action_request()` (then a
telnet accept/deny calls `respond_to_action_request()`), matching the web consent flow.

**Verdict:** say/pose are telnet-driveable E2E today (G0). Mechanical social actions are
web-only; the minimal fix is telnet `intimidate`/`accept`/`deny` shells over the consent flow.

---

## Loop 2 — Magic casting

100% web-only; never uses `action.run()`; the seam is `dispatch_player_action()`.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| See available techniques | ❌ none | `get_player_actions` / `_combat_actions` (`player_interface.py`) | N/A | — | G3 |
| Declare cast (non-combat) | ✅ `attempt` (`CmdAttempt`, `commands/magic.py` — `ArxCommand`) | `SceneCastViewSet` → `request_technique_cast` → `use_technique` (`techniques.py:702`) | **YES** — both call `request_technique_cast` (same seam) | `test_noncombat_cast_telnet_e2e.py` | **RESOLVED (#1332)** |
| Declare cast (combat) | `cast`/`declare` (`commands/combat.py` — `CmdDeclareTechnique(DispatchCommand)`) | `dispatch_player_action`→COMBAT→`declare_action` (`combat/services.py:1494`) | **YES** — telnet calls `dispatch_player_action` (same seam) | `test_combat_ui_integration.py`, `test_combat_cast_telnet_e2e.py`, `test_combat_commands.py` | **G0** |
| Check + resonance env + effects | N/A (service) | `resolve_round`→`resolve_combat_technique` (`:707`)→`use_technique` (`techniques.py:702`) | **YES** — fully shared service orchestration | `test_magic_story_pipeline.py` | **G0** |
| Perform ritual | ✅ `ritual`/`perform` (`CmdRitual`) | `RitualPerformView` → `PerformRitualAction.run()` | **YES** — both converge on `perform_ritual` action | `test_ritual_telnet_e2e.py` | **RESOLVED (#1331)** |

> **Rituals (RESOLVED, #1331):** ritual performance is now a real `Action`
> (`actions/definitions/ritual.py`, key `perform_ritual`). The standalone
> `world.magic.actions.PerformRitualAction` executor was deleted; telnet
> (`CmdRitual`) and web (`RitualPerformView`) both call
> `PerformRitualAction.run()`, so the G3 "web bypasses actions" gap is closed for
> SERVICE + FLOW rituals. (Anima/SCENE_ACTION rituals dispatch elsewhere and are
> out of scope.)

**Verdict:** combat declare is telnet-driveable (G0) — `cast`/`declare`
(`CmdDeclareTechnique`) calls `dispatch_player_action()` with a COMBAT `ActionRef`, the same
seam the web uses. Non-combat declare is now also G0 (RESOLVED, #1332) — `attempt`
(`CmdAttempt`, `commands/magic.py`) is a thin `ArxCommand` shell that calls
`request_technique_cast()` directly, the same entry point the web viewset uses. The deep
orchestration (`use_technique`, ~15 steps: anima, soulfray, resonance environment, conditions,
story beats, achievements) is already service-tested.

> **Note on dispatch path:** the spec for #1332 proposed CHALLENGE via `DispatchCommand`,
> but CHALLENGE requires `challenge_instance_id` (it's for dungeon puzzles). Non-combat
> magic casts route through `request_technique_cast` → `use_technique` — no CHALLENGE
> backend involved. `CmdAttempt` is an `ArxCommand`, not a `DispatchCommand`.

---

## Loop 3 — Thread weaving

100% web-only; mostly **direct viewset→service** (family 3) — does not even reach
`dispatch_player_action`.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| Acquire THREAD WEAVING unlock | ❌ none | `teaching-offers/{id}/accept/` → `accept_thread_weaving_unlock` (`services/threads.py:548`) | service-only | `test_thread_weaving_acquisition.py` | **G1** |
| Weave a thread | ❌ none | `ThreadViewSet.create` → `weave_thread` (`services/threads.py:298`) | service-only | `test_resonance_services.py` | **G1** |
| Imbue (spend resonance, advance level) | ✅ `ritual Rite of Imbuing thread=<id> amount=<n>` (`CmdRitual`) | `RitualPerformView` → `PerformRitualAction.run()` → `spend_resonance_for_imbuing` | **YES** — both via `perform_ritual` action | `test_ritual_telnet_e2e.py` | **RESOLVED (#1331)** |
| Pull thread (in combat) | ❌ none | `ThreadPullCommitView` → `spend_resonance_for_pull` (`services/resonance.py:588`) | service-only | `test_thread_pull_pipeline.py` | **G3** |

**Verdict:** not telnet-driveable. The web path is *not an action* — it's viewsets calling
services directly. The services are self-contained convergence points; telnet shells can call
the **same services** for real parity. **Open question:** should imbue/pull be actions so the
cross-cutting `action.run` machinery (prerequisites, AP/fatigue, enhancements, events) applies
uniformly — or are they legitimately plain service calls? (See Open questions.)

---

## Loop 4 — Combat

100% web-only; declarations go through `dispatch_player_action` (COMBAT, deferred), resolution
is GM/system-triggered.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| GM starts encounter | ❌ none | `CombatEncounterViewSet.create` + `begin_declaration_phase` (`combat/services.py:1451`) | GM/system surface | `test_duels_integration.py` | G3 (correct) |
| Player declares technique/passives | ❌ none | `dispatch_player_action`→COMBAT→`record_declaration`→`declare_action` (`combat/services.py:1494`) → `CombatRoundAction` row | seam converges; no telnet | `test_combat_ui_integration.py` | **G1** |
| Commit to clash | ❌ none | `dispatch_player_action`→`_dispatch_clash_contribution` (`player_interface.py:546`) | seam converges; no telnet | `test_combat_ui_integration.py` | **G1** |
| GM resolves round | ❌ none | `…/resolve_round/` → `resolve_round` (`combat/services.py:3997`) → `use_technique` | service-only, GM-triggered | `test_duels_integration.py` | G3 (correct) |
| NPC selection / damage / conditions | N/A | threat-pool selection + damage services (internal to `resolve_round`) | service-only | `test_agency_integration.py` | G3 (correct) |

**Seed prerequisites (gate the test, G4 until met):** `CharacterVitals`, `CovenantRole`
(auto-assigned if absent), `ThreatPool`/`ThreatPoolEntry`, and `Technique.action_template.check_type`
populated. Factories exist for most.

**Verdict:** player declarations are the only missing player surface (G1); resolution is
correctly GM/system-only (G3). Combat is deferred (declare-then-resolve), so a telnet
`declare` command calling `dispatch_player_action()` records a declaration exactly like the
web. Minimal fix: a `CmdDeclareAction` plus a GM-only `start encounter` for test setup.

---

## Cross-cutting conclusions

1. **`dispatch_player_action()` is the seam to standardize on.** Routing telnet commands
   through it (instead of `self.action.run()` directly) instantly extends telnet to the
   CHALLENGE and COMBAT backends with no per-domain refactor.
2. **Consent-flow and direct-viewset systems need telnet shells that call the same
   service/flow** (`create_action_request`/`respond_to_action_request` for social;
   `weave_thread`/`spend_resonance_for_*` for threads) — not `action.run()`.
3. **No magic/combat story is telnet-driveable today**, so none can yet serve as a telnet E2E
   regression. The service-layer pipeline tests remain the only proof for those loops.
4. ~~**The `action.run` docstring is stale** and should be corrected to describe the real
   `dispatch_player_action` seam and the three dispatch families.~~
   **[ALREADY CORRECT — audit claim stale, verified #1337]** The `Action` docstring
   (`src/actions/base.py`, ~lines 27–33) already describes the REGISTRY-only role of
   `action.run()` and the three backends routed by `dispatch_player_action()`. No
   correction is needed.

## Recommended direction (for the build phase, not yet ratified)

- **Adopt `dispatch_player_action()` as the canonical "what any UI calls" seam.** Add a thin
  telnet base that calls it (carrying an `ActionRef`), so telnet rides the same backend
  routing as the web.
- **Pilot the first telnet-driven E2E on one loop** end-to-end, proving the pattern, then
  template it across the others. (Loop choice is the next open decision — magic is the north
  star but needs the most new surface; social/combat reuse `dispatch_player_action` most
  directly.)
- **Retire duplicative unit tests only after** a loop has a real telnet/web-seam E2E covering
  the behavior — and keep fast unit tests where they localize failures the E2E cannot.

## Open questions (for design)

- **RESOLVED (#1337):** Should thread imbue/pull and similar direct-viewset mutations
  **become actions** (so prerequisites/AP/enhancements/events apply uniformly), or stay
  plain service calls? **Answer:** they become **real `Action`s on `action.run()`** (the
  #1331 ritual template). The classification rule: *a player-facing state mutation with
  costs/prerequisites becomes an `Action`; GM/system-only surfaces (e.g. `resolve_round`,
  encounter setup) stay raw services with no player UI.* Worked example: `WeaveThreadAction`
  (`src/actions/definitions/threads.py`); `ThreadSerializer.create()` now calls
  `action.run()` so web + telnet converge (`CmdWeaveThread`, `src/commands/weave.py`). See
  Family 3 in [unified-player-action.md](../architecture/unified-player-action.md#10-telnet-convergence-convention--three-player-action-families-ratified-1337).
- **RESOLVED (#1337):** Should the **consent flow be reachable through
  `dispatch_player_action`** (a unified entry for *all* player actions), or remain a distinct
  viewset that telnet shells call directly? **Answer:** it stays at the **consent SERVICE
  seam** — telnet's `ConsentRequestCommand`/`CmdIntimidate` + generic `CmdAccept`/`CmdDeny`
  (`src/commands/consent.py`) call the same `create_action_request()` /
  `respond_to_action_request()` services the `SceneActionRequestViewSet` calls — **not**
  `dispatch_player_action()`/`action.run()`. Consent is an inherently two-party async
  protocol whose response half can't be a single dispatch call, and "needs consent" is a
  property of `ActionTemplate.consent_category`, not the Action. See Family 2 in
  [unified-player-action.md](../architecture/unified-player-action.md#10-telnet-convergence-convention--three-player-action-families-ratified-1337).
- For combat/magic seed prerequisites, which belong in a shared **combat seed module** so the
  E2E is writable without bespoke per-test wiring?

---

## Broad-pass inventory (follow-up sweep)

The four loops above were a *deep* trace. This section is the *broad* pass the original
scope deferred: a full sweep of the DRF surface (every `router.register`, `APIView`, and
`@action`) to find player-facing mutations with no telnet command. **Result: ~150
player-facing API mutations; only ~7 have any telnet command** (`wear`, `undress`, `use`,
`+block`/`+unblock`/`+mute`/`+unmute`, plus `say`/`pose`/`emit` via actions). Everything
mechanical is web-only.

### Two corrections to the deep trace above

1. **Combat was under-counted.** Loop 4 traced only *declare* and *clash-commit* (through
   `dispatch_player_action`). But `CombatEncounterViewSet` exposes ~13 *additional* direct
   `@action`→service player surfaces with no telnet path that **will not** be reached by the
   `dispatch_player_action` routing fix: `flee` (`declare_flee`, `combat/services.py:926`),
   `cover` (`declare_cover` `:975`), `interpose` (`declare_interpose` `:1028`), `yield`
   (`duels.yield_duel:303`), `join`/`leave` (`:852`/`:886`), `ready`, `upgrade_combo`/
   `revert_combo` (`:2523`/`:2642`). These need their own thin shells (family 3), not just
   the dispatch reroute.
2. **The dispatch-routing keystone is now its own issue** (foundation), not just the bullet
   in "Cross-cutting conclusions #1".

### Web-only clusters with no telnet surface (by domain)

| Domain | Representative web-only surfaces (seam) | Class |
|---|---|---|
| **Social consent** | `create_action_request` / `respond_to_action_request` (`scenes/action_views.py:55/195`) | G1/G3 |
| **Entrance + flourish** | `EntranceAction`; `resolve_entry_flourish_offer` (`magic/entry_flourish.py`) | G1/G3 |
| **Resonance endorsements** | pose / scene-entry / style (`magic/views.py:1053+`); fashion `FashionJudgementViewSet` (`items/views.py:1280`) | **RESOLVED — #1340** |
| **Interaction reactions** | `InteractionFavorite` / `InteractionReaction` / reaction windows (`scenes/`) | G3 |
| **Thread weave/imbue/pull** | `weave_thread` / `spend_resonance_for_imbuing` / `_for_pull` (`magic/services/`) | G1/G3 |
| **Soul-tether & sineating** | 8 APIViews: accept/dissolve/request/respond/rescue/stage-advance (`magic/views.py:1206–1461`) | G3 |
| **Audere / Audere Majora** | `resolve_audere_offer`; `cross_threshold` (`magic/audere*.py`) — the progression/"leveling" surface | G3 |
| **Multi-participant rituals** | `draft_session`/`accept`/`decline`/`fire` (`magic/services/sessions.py`) | G3 |
| **Covenant membership** | engage/disengage/leave/kick/rank; banner-call/stand-down (`covenants/services.py`) | G3 |
| **Persona / guise** | `set_active_persona` (`scenes/services.py:86`) | G3 |
| **Progression rewards** | `claim_kudos_for_xp`; `cast_vote`/`remove_vote`; random-scene; path-intent (`progression/views.py`) | G3 |
| **Missions** | resolve/abandon/group_pick/group_vote (`missions/views.py:497+`) | G3 |
| **Journals & goals** | `create_journal_entry`/`respond`; `CharacterGoalViewSet` (`journals/`, `goals/`) | G3 |

### Two named surfaces that don't map to code

- **Soulfray combat-consent** — no dedicated surface found (neither telnet nor web). Soulfray
  severity accumulates as a runtime side-effect of casting (`techniques.py:525`); entry appears
  automatic at Warp stage 3. Whether an explicit consent gate is intended is an open design
  question, tracked separately.
- **"Ritual of the Durance"** — no ritual by that name exists. "Durance" is a *covenant type*
  (`Covenant of the Durance`, the default/standing covenant). Level advancement actually rides
  **thread Imbuing** and **Audere Majora crossing**. Naming reconciliation tracked separately.

### Disposition

Tracked as journey-shaped children of the umbrella issue (telnet commands + one user-journey
E2E each, which then retires the unit tests it covers): two **foundation** issues (dispatch
routing; consent-flow / direct-viewset strategy), the per-domain **journey** issues above, and
two **design-clarification** issues (soulfray consent; durance naming). Existing combat (scope
widened), ritual-as-Action, and non-combat-cast journeys are reconciled into the same set. See
the umbrella issue for the live child map.

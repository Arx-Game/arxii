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

### There are three web dispatch families; telnet implements a slice of one

| # | Web dispatch family | Entry | Reaches | Telnet today |
|---|---|---|---|---|
| 1 | **Unified action dispatch** | `dispatch_player_action()` | REGISTRY→`action.run`, CHALLENGE→`resolve_challenge`, COMBAT→`declare_action`/`resolve_round`→`use_technique` | REGISTRY via `ArxCommand` → `self.action.run()`; COMBAT via `DispatchCommand` → `dispatch_player_action()` (`CmdDeclareTechnique`); CHALLENGE still G1 (#1332) |
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
| Declare cast (non-combat) | ❌ none | `dispatch_player_action`→CHALLENGE→`resolve_challenge` (`challenge_resolution.py`) | seam converges; no telnet | — | **G1** |
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

**Verdict:** combat declare is now telnet-driveable (G0) — `cast`/`declare`
(`CmdDeclareTechnique`) calls `dispatch_player_action()` with a COMBAT `ActionRef`, the same
seam the web uses. Non-combat (CHALLENGE) declare remains G1 (#1332). The deep
orchestration (`use_technique`, ~15 steps: anima, soulfray, resonance environment, conditions,
story beats, achievements) is already service-tested.

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
4. **The `action.run` docstring is stale** and should be corrected to describe the real
   `dispatch_player_action` seam and the three dispatch families.

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

- Should thread imbue/pull and similar direct-viewset mutations **become actions** (so
  prerequisites/AP/enhancements/events apply uniformly), or stay plain service calls?
- Should the **consent flow be reachable through `dispatch_player_action`** (a unified entry
  for *all* player actions), or remain a distinct viewset that telnet shells call directly?
- For combat/magic seed prerequisites, which belong in a shared **combat seed module** so the
  E2E is writable without bespoke per-test wiring?

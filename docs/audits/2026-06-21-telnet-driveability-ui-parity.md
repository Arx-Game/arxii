# Telnet-Driveability & UI Dispatch-Parity Audit

**Date:** 2026-06-21 — **refreshed 2026-06-23** against post-#1351 code.
**Tracking issue:** [#1328](https://github.com/Arx-Game/arxii/issues/1328)
**Scope of this pass:** deep trace of the four priority loops — **magic casting, combat,
thread weaving, social scenes**. Remaining L1 stories (character creation, relationships,
codex, journals, progression, world clock) are a later broad pass.

> **Refresh note (2026-06-23).** The original 2026-06-21 trace concluded that *"the genuine
> UI-shared seam is `dispatch_player_action()`, and the telnet layer does not call it."* **That
> thesis is now obsolete.** Three PRs landed since: **#1337/#1338** (social-consent telnet
> shells), **#1342** (thread weave/imbue/pull as real `Action`s), and **#1351** (the unified
> scene-adaptive `cast` + a fourth `SCENE_ADAPTIVE` dispatch backend). Telnet now reaches the
> dispatcher and `action.run()` across most of the four loops, and **a telnet E2E test already
> exists for nearly every one** (see "Existing telnet E2E coverage" below). This refresh rewrites
> every loop table against current code and re-scopes the follow-on to the genuine residual gaps.

## Why this audit exists

The goal is to make **telnet a first-class end-to-end testing surface** for whole user
stories. Telnet is pure backend, so driving a story through telnet commands yields a full
`command → … → service-function` integration test with no frontend in the loop. The premise
relies on an architectural invariant: **a telnet command and a web view are interchangeable
UIs over the same code underneath.** If that holds, "works in telnet" ⟹ "works for web
players." This audit measures where it actually holds — and where it doesn't.

## Headline finding (refreshed)

**Telnet now drives the dispatcher and `action.run()` across most of the four loops; the
question has shifted from "can telnet reach it?" to "*where* do telnet and web converge — and is
that point high enough to make a telnet E2E a valid web proxy?"**

There are now **four** dispatch backends (`actions/constants.py:61-64`): `REGISTRY`, `CHALLENGE`,
`COMBAT`, and `SCENE_ADAPTIVE` (new in #1351). The web write path is `DispatchActionView`
(`actions/views.py:48`) → `dispatch_player_action()` (`actions/player_interface.py:78`). Telnet
reaches the same dispatcher through `DispatchCommand` (`commands/command.py`), or `action.run()`
directly through `ArxCommand`, or — for a few domains — a shared **service** function.

The convergence point now **varies by loop**, and that is the whole story:

| Convergence altitude | Loops | Telnet E2E proves web? |
|---|---|---|
| **`action.run()` on the *same* Action** | say/pose (REGISTRY), thread weave, thread pull | **Yes** — identical code below the command |
| **`dispatch_player_action` → same declaration service** | combat technique declaration | **Yes** — both reach `record_declaration`/`declare_action` |
| **shared *service* only (UIs wrap it differently)** | magic standalone cast, thread imbue, social consent | **Partly** — proves the service & below, *not* each UI's wrapper |
| **web-only (no telnet)** | combat clash-commit + ~8 PC combat actions, teaching-unlock acquisition | **N/A** — gap |

The two service-only magic/thread cases are the subtle ones #1351/#1342 introduced and are the
main residual findings of this refresh (see Loops 2 and 3).

## Gap classification

| Class | Meaning | Fix |
|---|---|---|
| **G0 Converged** | Telnet command exists; web uses the *same* seam (action **or** a shared service) | None — telnet E2E is a valid web proxy today |
| **G1 Missing shell** | Web seam exists; no telnet command drives it | Add a thin command that calls the *same* seam |
| **G2 Divergent dispatch** | Telnet and web reach the goal through *different* actions/wrappers, converging only at a lower service | Decide whether to unify the upper wrapper, or accept the service as the contract |
| **G3 View-only / GM-only** | Web reaches a service with no action layer, or a GM/system-only surface | Decide if a player-facing telnet surface is wanted; if so, call the same service |
| **G4 Not buildable** | Story can't run end-to-end yet (missing seed/service) | Backend/seed gap → its own task |

---

## Loop 1 — Social scenes

Freeform RP and mechanical social actions both converge now. The consent flow gained telnet
shells in #1337/#1338, closing the gaps the original audit flagged.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| Say text | `CmdSay` (`commands/evennia_overrides/communication.py:26`) | `DispatchActionView`→`dispatch_player_action`→REGISTRY→`SayAction.run` (`player_interface.py:176`) | **YES** (both `action.run`) | `commands/tests/test_dispatchers.py` | **G0** |
| Pose | `CmdPose` (`communication.py:160`) | same → `PoseAction.run` | **YES** | `commands/tests/test_dispatchers.py` | **G0** |
| Initiate social action (intimidate/persuade/deceive/flirt/perform/entrance/…) | `CmdIntimidate`/`CmdPersuade`/`CmdDeceive`/`CmdFlirt`/`CmdPerform`/`CmdEntrance`/`CmdRestoreSense` (`commands/consent.py:114-194`) → `create_action_request` | `SceneActionRequestViewSet.create` (`action_views.py:118`) → `create_action_request` (`scenes/action_services.py:150`) | **YES** — same service (the ratified consent SERVICE seam, #1337) | `commands/tests/test_social_consent_e2e.py`, `integration_tests/pipeline/test_consent_telnet_e2e.py` | **G0** |
| Target accept/deny | `CmdAccept`/`CmdDeny` (`commands/consent.py:251/298`) → `respond_to_action_request` | `…/respond/` (`action_views.py:204`) → `respond_to_action_request` (`scenes/action_services.py:335`) | **YES** — same service | `test_social_consent_e2e.py` | **G0** |
| Resolve + apply consequence | (via accept) → `start_action_resolution` | same → `start_action_resolution` | **YES** — shared resolution pipeline | `integration_tests/pipeline/test_social_pipeline.py` | **G0** |

**Verdict:** social scenes are fully telnet-driveable (G0 throughout). Convergence is the consent
**service** seam by design (#1337): consent is an inherently two-party async protocol whose
response half can't be a single dispatch call, so telnet and web both call
`create_action_request` / `respond_to_action_request` directly rather than routing through
`action.run()`. This was the original audit's biggest correction and is now settled.

---

## Loop 2 — Magic casting

The unified scene-adaptive `cast` (#1351) made **telnet** ride a real `Action`. The **web
standalone-cast endpoint still does not** — it is the one place in this loop where the two UIs
converge only at the service.

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| Standalone cast (in *and* out of combat) | `cast`/`declare` (`CmdDeclareTechnique`, `commands/combat.py:32`, a `DispatchCommand`) → `dispatch_player_action`(SCENE_ADAPTIVE) → `CastTechniqueAction.run` (`actions/definitions/cast.py:30`, key `cast_technique`) → `request_technique_cast` | `SceneActionRequestViewSet.cast` (`action_views.py:322`) → `request_technique_cast` (`scenes/cast_services.py:558`) **directly** | **NO at the action level / YES at the service** — web bypasses `dispatch_player_action` *and* `CastTechniqueAction`; both meet at `request_technique_cast` | `integration_tests/pipeline/test_noncombat_cast_telnet_e2e.py`, `test_combat_cast_telnet_e2e.py` | **G2** |
| Combat declaration of the cast | same `cast` command — inside a DECLARING round `CastTechniqueAction.round_declaration` (`cast.py:117`) builds a COMBAT declaration | `dispatch_player_action`(COMBAT) → `record_declaration` → `declare_action` (`combat/services.py:1658`) | **YES** — both reach `record_declaration`/`declare_action` | `test_combat_cast_telnet_e2e.py`, `commands/tests/test_combat_commands.py` | **G0** |
| Check + resonance env + effects | N/A (service) | `resolve_round` → `resolve_combat_technique` → `use_technique` | **YES** — shared service orchestration | `world/magic/tests/integration/test_magic_story_pipeline.py` | **G0** |
| Perform ritual (SERVICE/FLOW) | `ritual`/`perform` (`CmdRitual`, `commands/ritual.py`) → `PerformRitualAction.run` | `RitualPerformView` (`magic/views.py:907`) → `PerformRitualAction.run` | **YES** — both via `perform_ritual` action | `test_ritual_telnet_e2e.py` | **G0** (RESOLVED #1331) |
| Multi-participant ritual session | `ritual draft/join/decline/fire` (`CmdRitual`) → `draft_session`/`accept_session`/`decline_session`/`fire_session` | session viewset → same services | **YES** — same services | `test_ritual_session_telnet_e2e.py` | **G0** (RESOLVED #1345) |

**The G2 cast finding (new since the audit).** #1351 introduced `SCENE_ADAPTIVE` →
`CastTechniqueAction`, giving the **telnet** cast anti-spam gating, POSE_ORDER quorum advancement,
`round_declaration` combat-deferral, and the soulfray-consent `PendingCast` re-dispatch
(`accept soulfray`). The **web** `cast` endpoint (`SceneActionRequestViewSet.cast`) calls
`request_technique_cast` directly and gets *none* of that wrapper — it returns a
`SceneActionRequest` for the frontend to handle soulfray its own way. So:

- A telnet cast E2E (`test_noncombat_cast_telnet_e2e.py`) proves `request_technique_cast` **and
  below**, plus the telnet wrapper — **but not** the web endpoint's wrapper.
- `CastTechniqueAction` is effectively **`[BUILT, NOT WIRED]` for the web**: it exists and is wired
  for telnet only. The `cast.py` docstring previously claimed both UIs converge on the action;
  that was corrected in this refresh.

Whether the web cast endpoint *should* route through `dispatch_player_action(SCENE_ADAPTIVE)` (to
inherit anti-spam/pose-order/soulfray uniformly) or whether anti-spam/pose-order are legitimately
telnet-pacing concerns the web handles differently is a **design question**, not an obvious bug —
see Follow-on.

**Verdict:** combat declaration, ritual performance, and ritual sessions are G0. Standalone cast
is G2 — telnet rides the action, web rides the service. The deep orchestration (`use_technique`:
anima, soulfray, resonance environment, conditions, story beats, achievements) is shared and
service-tested.

---

## Loop 3 — Thread weaving

#1342 turned weave/imbue/pull into real `Action`s. Weave and pull are now genuine `action.run()`
convergence (G0); imbue converges only at the service (G2); teaching-unlock acquisition is still
web-only (G1).

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| Acquire THREAD WEAVING unlock | ❌ none | `teaching-offers/{id}/accept/` → `accept_thread_weaving_unlock` (`magic/services/threads.py`) | service-only; no telnet | `magic/tests/test_teaching_offer_accept_view.py` | **G1** |
| Weave a thread | `CmdWeaveThread` (`commands/weave.py:29`) → `WeaveThreadAction.run` (`actions/definitions/threads.py:23`) | `ThreadSerializer.create` (`magic/serializers.py:867`) → `WeaveThreadAction.run` | **YES** — same action | `commands/tests/test_weave_command.py`, `integration_tests/pipeline/test_weave_telnet_e2e.py` | **G0** (RESOLVED #1342) |
| Imbue (spend resonance, advance level) | `imbue` (`CmdImbue`, `commands/imbue.py`) → `ImbueAction.run` (`actions/definitions/imbue.py:23`) → `spend_resonance_for_imbuing` (`magic/services/resonance.py:221`) | `RitualPerformView` → `PerformRitualAction.run` → (Rite of Imbuing CEREMONY service) → `spend_resonance_for_imbuing` | **NO at the action level / YES at the service** — telnet uses the `ImbueAction` *finisher*; web resolves imbuing through `PerformRitualAction`; both meet at `spend_resonance_for_imbuing` | `commands/tests/test_imbue_cmd.py`, `integration_tests/pipeline/test_weave_imbue_pull_journey_e2e.py` | **G2** |
| Pull thread (in combat) | `pull` (`CmdPull`, `commands/pull.py:28`) → `PullThreadAction.run` (`actions/definitions/pull.py:25`) → `spend_resonance_for_pull` (`magic/services/resonance.py:588`) | `ThreadPullCommitView` → `ThreadPullCommitRequestSerializer.create` → `PullThreadAction.run` | **YES** — same action | `commands/tests/test_pull_cmd.py`, `test_weave_imbue_pull_journey_e2e.py` | **G0** (RESOLVED #1342) |

**The G2 imbue finding (new since the audit).** Imbuing uses a **ceremony/finisher** split: a
player performs the *Rite of Imbuing* CEREMONY ritual (which creates a `PendingRitualEffect`), then
a **finisher** advances the thread. Telnet's finisher is `ImbueAction` (gated by a
`PendingRitualEffectPrerequisite`, `commands/imbue.py` → `actions/definitions/imbue.py`); the web
resolves the same end through `PerformRitualAction`'s CEREMONY service path. Two different actions
for one user goal, converging at `spend_resonance_for_imbuing`. This is a parallel-implementation
smell worth a deliberate decision (unify on one finisher action vs. accept the service as the
contract) — flagged in Follow-on, not asserted as a fix.

**Verdict:** weave and pull are telnet-driveable at the action seam (G0). Imbue is G2 (service
convergence). Teaching-unlock acquisition is the lone untouched G1 (no telnet shell yet).

---

## Loop 4 — Combat

Technique **declaration** converges (G0) via the #1351 SCENE_ADAPTIVE reshaping. Clash-commit and
the bundle of other PC combat actions remain web-only (G1); round resolution and encounter setup
are correctly GM/system-only (G3).

| Step | Telnet | Web dispatch | Same code? | Existing test | Class |
|---|---|---|---|---|---|
| GM starts encounter | ❌ none (GM) | `CombatEncounterViewSet` → `begin_declaration_phase` (`combat/services.py:1424`) | GM/system surface | `world/combat/tests/.../test_duels_integration.py` | **G3** (correct) |
| Player declares technique | `cast`/`declare` (`CmdDeclareTechnique`) → SCENE_ADAPTIVE → `round_declaration` → `record_declaration` (`combat/round_context.py:101→197`) → `declare_action` (`combat/services.py:1658`) | `DispatchActionView`→`dispatch_player_action`(COMBAT) → `record_declaration` → `declare_action` | **YES** — both reach `record_declaration`/`declare_action` | `test_combat_cast_telnet_e2e.py`, `test_combat_ui_integration.py` | **G0** |
| Commit to clash | ❌ none | `dispatch_player_action` → `_dispatch_clash_contribution` (`player_interface.py:627`) → `declare_clash_contribution` (`combat/services.py:4693`) | seam converges; no telnet shell | `test_combat_ui_integration.py` | **G1** |
| GM resolves round | ❌ none (GM) | `…/resolve_round/` → `resolve_round` (`combat/services.py:4454`) → `use_technique` | service-only, GM-triggered | `test_duels_integration.py` | **G3** (correct) |
| Other PC combat actions: `flee`/`cover`/`interpose`/`join`/`leave`/`ready`/`upgrade_combo`/`revert_combo` | ❌ none | `CombatEncounterViewSet` `@action`s → `declare_flee` (`combat/services.py:1004`), `declare_cover` (`:1053`), `declare_interpose` (`:1106`), join/leave/ready/combo services | seam converges; no telnet shells | `test_duels_integration.py`, `test_agency_integration.py` | **G1** |
| NPC selection / damage / conditions | N/A | threat-pool selection + damage services (internal to `resolve_round`) | service-only | `test_agency_integration.py` | **G3** (correct) |

**Seed prerequisites (gate the test, G4 until met):** `CharacterVitals`, `CovenantRole`
(auto-assigned if absent), `ThreatPool`/`ThreatPoolEntry`, and
`Technique.action_template.check_type` populated. Factories exist for most;
`test_combat_cast_telnet_e2e.py` already wires a working seed.

**Verdict:** technique declaration is G0 (the `cast` command reaches `declare_action` exactly like
the web COMBAT backend). The residual G1 surface is clash-commit plus the ~8 other PC combat
actions — each needs its own thin telnet shell calling the same service. Resolution and setup stay
GM/system-only (G3).

---

## Existing telnet E2E coverage (Deliverable 3 — already substantial)

The original audit said "no magic/combat story is telnet-driveable today." That is now false.
`src/integration_tests/pipeline/` already contains telnet-driven (`execute_cmd`-level) journey
tests for most loops:

| Loop | Telnet E2E test | Covers |
|---|---|---|
| Magic cast (non-combat) | `test_noncombat_cast_telnet_e2e.py` | `cast` (SCENE_ADAPTIVE) → anima debit, OUTCOME interaction, `TECHNIQUE_CAST` event |
| Magic cast (combat) | `test_combat_cast_telnet_e2e.py` | `cast` inside a DECLARING round → combat declaration |
| Ritual | `test_ritual_telnet_e2e.py` | `ritual`/`perform` → `PerformRitualAction` |
| Ritual session | `test_ritual_session_telnet_e2e.py` | `ritual draft/join/decline/fire` |
| Thread weave+imbue+pull | `test_weave_imbue_pull_journey_e2e.py`, `test_weave_telnet_e2e.py` | full ceremony/finisher journey |
| Social consent | `test_consent_telnet_e2e.py` | intimidate/accept/deny |
| Challenge dispatch | `test_challenge_dispatch_telnet_e2e.py` | CHALLENGE backend |
| Endorsement | `test_endorsement_journey_e2e.py` | pose/entry/style endorse (#1340) |
| Audere / Durance | `test_audere_telnet_e2e.py`, `test_durance_e2e.py` | progression surfaces |

So Deliverable 3 is mostly **done**; the remaining E2E work is narrow (clash-commit + PC combat
actions once shells exist, and a web-vs-telnet parity assertion for the two G2 cases).

## Cross-cutting conclusions (refreshed)

1. **Telnet has caught up to the dispatcher.** `DispatchCommand` lets telnet reach SCENE_ADAPTIVE,
   COMBAT, and CHALLENGE; the social/thread loops converge at shared services. The original "telnet
   never calls `dispatch_player_action`" finding is retired.
2. **Convergence altitude is the remaining variable.** Most loops now converge at `action.run()` or
   the declaration service (telnet E2E = valid web proxy). **Two cases converge only at the
   service** — magic standalone cast (G2) and thread imbue (G2) — because each UI wraps the service
   differently. A telnet E2E there proves the service, not the web wrapper.
3. **Residual G1 surface is small and combat-shaped:** clash-commit and ~8 PC combat actions
   (flee/cover/interpose/join/leave/ready/upgrade_combo/revert_combo), plus teaching-unlock
   acquisition. Each is a thin shell over an existing service.
4. **Telnet E2E coverage already exists** for nearly every loop (table above); the umbrella's
   Deliverable 3 is largely complete.

## Follow-on (re-scoped 2026-06-23)

Verified against current code; premises checked per `verify-against-code`. Distinguishes scoped
work from open design questions.

**Design questions (file as `needs-design`, not as ready work):**

1. **Web standalone-cast vs `CastTechniqueAction` (the G2 cast).** Should
   `SceneActionRequestViewSet.cast` route through `dispatch_player_action(SCENE_ADAPTIVE)` so the
   web inherits anti-spam / POSE_ORDER quorum / soulfray-`PendingCast` uniformly — or are those
   telnet-pacing concerns the web legitimately handles its own way? Today `CastTechniqueAction` is
   wired for telnet only. *Premise verified:* `action_views.py:392` calls `request_technique_cast`
   directly; `cast.py` is reached only by `CmdDeclareTechnique`.
2. **Imbue finisher unification (the G2 imbue).** Telnet uses `ImbueAction`; web resolves imbuing
   through `PerformRitualAction`. One user goal, two actions, converging at
   `spend_resonance_for_imbuing`. Unify on a single finisher action, or ratify the service as the
   contract? *Premise verified:* `actions/definitions/imbue.py:23` vs the CEREMONY path in
   `actions/definitions/ritual.py`.

**Scoped work (thin shells over existing services — G1):**

3. **Combat PC-action telnet shells:** clash-commit (`declare_clash_contribution`,
   `combat/services.py:4693`) and flee/cover/interpose/join/leave/ready/upgrade_combo/revert_combo
   (`CombatEncounterViewSet` `@action`s → their `declare_*`/encounter services). Each is a
   `DispatchCommand` or thin service shell, then a telnet assertion in `test_duels_integration`'s
   journey form.
4. **Teaching-unlock telnet shell:** a command over `accept_thread_weaving_unlock`
   (`magic/services/threads.py`) so the thread-weaving journey is driveable from acquisition.

**Verification work (close the G2 proof gap):**

5. For the two G2 cases, add a **web-path assertion** alongside the existing telnet E2E (POST the
   web cast / ritual-imbue endpoint and assert the same service outcome) so the parity is proven on
   *both* wrappers, not just inferred from the shared service.

**Likely already closed (verify before filing anything):** the original Disposition listed
per-domain journey children and two foundation issues (dispatch routing; consent strategy). The
dispatch-routing keystone shipped as #1351 (SCENE_ADAPTIVE); the consent strategy was ratified in
#1337; weave/imbue/pull shipped in #1342. Reconcile the umbrella's child map against this refresh
before opening new issues — most of the original deep-trace gaps are resolved.

# Unified Player Action Interface — Design

**Date:** 2026-05-17
**Status:** Design (brainstorm complete, pending spec review + user review)
**Domain:** Core (Tehom) — action interface, magic-in-combat, challenge resolution
**Branch:** `unified-action-interface`

## 1. Problem & Context

A player's character can currently take actions through **four disconnected
surfaces**, each grown independently:

1. **`src/actions/` registry** — stateless singleton `Action` dataclasses with a
   real dispatch path (`Action.run()`, `src/actions/base.py:108-160`). Used for
   equip / move / perceive / communicate via the WebSocket `execute_action`
   envelope (`src/server/conf/inputfuncs.py:55-121`) and the telnet `ArxCommand`
   shim (`src/commands/command.py:20-144`). **Has dispatch, no rich availability.**
   `get_actions_for_target_type` (`src/actions/registry.py:59-61`) has zero
   production callers.
2. **`world/mechanics.get_available_actions`** (`src/world/mechanics/services.py:603-658`)
   — rich capability / challenge / prerequisite / difficulty evaluation, exposed
   read-only at `GET /api/mechanics/characters/{id}/available-actions/`
   (`AvailableActionsView`, `src/world/mechanics/views.py:110-138`;
   route `src/world/mechanics/urls.py:30`). **Has rich availability, no dispatch
   path at all.**
3. **`world/scenes/action_availability.get_available_scene_actions`** — a third
   availability path, DB-driven via `ActionTemplate.objects.filter(category="social")`.
4. **Combat** — entirely bespoke: `declare_action` service
   (`src/world/combat/services.py:757`), ~~`DeclareActionSerializer`~~
   (retired in #987 — see below), `resolve_round` view
   (`src/world/combat/views.py:140`).

### The two diagnostic bugs (both confirmed at the view layer; service layer is wired)

- **#1 — magic-in-combat sever.** `resolve_round` view calls
  `services.resolve_round(encounter)` with **no kwargs**
  (`src/world/combat/views.py:149`). The service signature defaults
  `offense_check_type=None` (`src/world/combat/services.py:1977`).
  `_resolve_pc_action` (`src/world/combat/services.py:1720`) only calls
  `resolve_combat_technique` when `offense_check_type is not None`
  (the guard at `:1764-1773`); otherwise it **silently skips technique
  resolution** and applies only fatigue. Through the real API every declared
  spell deals **zero damage, zero conditions**. The service
  (`resolve_combat_technique`, `:431-483`) is fully wired and requires a
  non-optional `offense_check_type: CheckType`.
  Additionally `focused_ally_target` is hardcoded `None`
  (`src/world/combat/views.py:290`) and **absent from the (now-retired)
  `DeclareActionSerializer`**, so no self-cast / buff / ally-target technique
  could ever be declared via that path — though `declare_action` accepts the
  parameter. **Fixed in #987:** `focused_ally_target` is now accepted by the
  unified `/dispatch/` path (`dispatch_player_action` →
  `CombatRoundContext.record_declaration` → `_record_combat_declaration`).
- **#2 — challenge player-resolution path missing.** `resolve_challenge`
  (`src/world/mechanics/challenge_resolution.py:46-51`) is a solid resolution
  primitive, but there is **no player-facing dispatch endpoint** that calls it.
  Availability is read-only.

### The keystone

The unifying anchor is the resolved **`CheckType`**, not `ActionTemplate`.
`ActionTemplate` (`src/actions/models/action_templates.py`) carries a
**non-nullable `check_type` FK** (`:36`) and is referenced by
`Technique.action_template` (`src/world/magic/models/techniques.py`, nullable)
and `ChallengeApproach.action_template`
(`src/world/mechanics/models.py:784-834`).

> **Resolved during implementation (verified 2026-05-18):** `ActionTemplate`
> is NOT a universal spine. `ChallengeApproach.action_template` is **nullable**
> (`on_delete=SET_NULL`, *"When set, resolution uses this template's check_type
> and pool"*) — an optional *override*. `ChallengeApproach.check_type` is the
> **non-null, always-present** resolution anchor; `resolve_challenge` uses
> `approach.check_type` directly unless an `action_template` override is set.
> Therefore the always-present unifying field across all three backends is the
> resolved `CheckType`, sourced per-backend: combat →
> `technique.action_template.check_type`; challenge →
> `approach.action_template.check_type` if the override is set, else
> `approach.check_type`; registry → `template.check_type`. `action_template`
> is carried on the descriptor only when present (combat techniques, registry
> templates, override challenge approaches).

"CheckType belongs in the action layer, defined once" holds — realized via the
`CheckType` that every backend already resolves. The combat bug is still that
no code reads `technique.action_template.check_type`. This uses existing
fields, not a new abstraction.

Defense-side nuance: PC technique attacks have **no defense check** (opponent
soak is the sole mitigation). `defense_check_type` matters only for the NPC→PC
path. #1 is an **offense** check-type sourcing fix.

## 2. Scope & Boundaries

This initiative is the **player-facing interface**, not the systems that feed
it. Scope = "player does thing with their character."

### In scope

1. **On-demand unified availability** — "what can my character do right now,"
   recomputed every call (never cached). Merges live `ChallengeInstance`
   approaches (by location), combat-declarable actions (when the character has
   an active round context), and registry actions. Homogeneous descriptors.
2. **Unified dispatch** — one entry routing `{ref, kwargs}` to the correct
   backend.
3. **Check-type sourcing** — combat technique resolution derives
   `offense_check_type` from `Technique.action_template.check_type`;
   `action_template` becomes **required** for combat-usable techniques (explicit
   config error, no silent no-op, no "legacy"). Add `focused_ally_target` to the
   `/dispatch/` path. **This is the #1 fix.**
4. **Combat-agnostic tempo seam** — `get_active_round_context(character)`;
   combat is the sole implementor; no general-scene provider, no plugin
   framework.
5. **Single round declaration** per active round context, keyed on the
   `ActionTemplate` descriptor; **no polymorphic FK** on `CombatRoundAction`.
6. **Player challenge resolution path** — dispatch → `resolve_challenge` (the
   #2 player-facing piece).
7. **Cleanup of the superseded path** — delete the challenge-only
   `available-actions/` endpoint and repoint/remove its frontend call sites. A
   single dispatch envelope, no dual-format handling.

### Out of scope — seams noted, NOT designed

- **Consequence→challenge spawn** (`SPAWN_CHALLENGE` effect + handler) **and
  wiring combat resolution to run consequence pools at all.** Verified not
  built: `ConsequenceEffect.effect_type` has 10 `EffectType` values
  (`src/world/checks/constants.py`), none spawns a challenge;
  `_HANDLER_REGISTRY` (`src/world/mechanics/effect_handlers.py:401-412`) has no
  challenge-spawn handler; combat resolution never calls
  `select_consequence`/`apply_resolution`; every `ChallengeInstance.create()`
  is test-only. **Designed-around:** the on-demand read surfaces any
  `ChallengeInstance` regardless of origin, so this lands later with **zero
  interface change**.
- **GM challenge/situation/combat authoring & instantiation** (brother's
  domain). Tests use factories to establish preconditions.
- **The general non-combat turn/initiative provider.** Seam defined;
  implementation deferred. Turn resolution is explicitly a general scene concern
  ("not fastest-typist"), so the seam must not encode "round gating ⇔
  CombatEncounter exists."
- **challenge→beat / combat→story predicates** (handoff-excluded).

## 3. Architecture — Descriptor + Three-Backend Dispatch

**Home:** `src/actions/`. It already owns the registry, the `ActionTemplate`
model, and its own roadmap (`src/actions/CLAUDE.md:96-114`) names exactly these
missing pieces ("CharacterCapabilities facade," "On-Demand Action
Availability," generic dispatch). No new app. Challenge logic stays in
`world/mechanics`; `declare_action` service stays in `world/combat`. `src/actions/`
**aggregates and routes**; it does not absorb the backends.

**Spine — resolved `CheckType`.** Every player action descriptor resolves to a
`CheckType` (always present). `action_template` is carried only when it exists
(combat techniques, registry templates, override challenge approaches) — see
the keystone correction above.

**Descriptor — `PlayerAction` dataclass** (carries model instances, not bare
PKs; types in `src/actions/types.py`):

- `backend`: `CHALLENGE | COMBAT | REGISTRY | SCENE_ADAPTIVE` (TextChoices in
  `src/actions/constants.py`). `SCENE_ADAPTIVE` was added in #1351 for actions
  that work both in and out of a combat round (technique casts); see the
  "SCENE_ADAPTIVE Backend" section of `src/actions/CLAUDE.md` for its dispatch
  flow (anti-spam floor, `round_declaration` deferral, soulfray-pending gate).
- `check_type`: the resolved `CheckType` instance (always present; the unifying
  anchor, sourced per-backend per the keystone correction)
- `action_template`: the `ActionTemplate` instance or `None` (present for
  combat techniques / registry templates / override challenge approaches)
- `display`: name / icon / description (approach custom text, technique, or
  registry `Action`)
- `target_spec`: target type + eligible targets (from `Action.target_type`
  `src/actions/types.py:22-28`, or the approach)
- `difficulty`: existing `DifficultyIndicator` where the backend computes one
  (challenges do today), else `None`
- `availability`: prereq-met + reasons (reuses `get_available_actions`'
  existing prerequisite evaluation)
- `ref`: a typed, round-trippable **dispatch reference** — the only thing the
  client echoes back

**Availability read — `get_player_actions(character)`** (`src/actions/`):

1. Challenge approaches → delegate to `get_available_actions(character,
   character.location)`; adapt each `AvailableAction` into a `PlayerAction`.
2. Combat actions → only if `get_active_round_context(character)` is non-None:
   the techniques/maneuvers this participant may declare this round, each
   mapped through `Technique.action_template`.
3. Registry actions → `get_actions_for_target_type(...)` filtered by context
   (first production consumer of that registry function).

Recomputed every call. A consequence-spawned or GM-spawned challenge appears
on the next read with no special path.

**Dispatch — `dispatch_player_action(character, ref, kwargs)`** (`src/actions/`):

- Resolve `ref` → backend (immediately back to model instances).
- `CHALLENGE` → `resolve_challenge(character, challenge_instance, approach,
  capability_source)`.
- `COMBAT` → `declare_action(participant, …)`.
- `REGISTRY` → `get_action(key).run(actor, **kwargs)`.
- `SCENE_ADAPTIVE` (#1351) → anti-spam check, then `get_action(key)`; inside a
  combat round `action.round_declaration(ctx, …)` may defer it as a COMBAT
  declaration, otherwise `action.run(actor, **kwargs)` runs immediately (with a
  POSE_ORDER quorum / repeat-block check from the active scene round).
- Immediate vs. declaration-gated is decided by the tempo seam (§4), not the
  backend.

`ref` is the single wire-serialized structure (typed, at the API boundary):
`{backend, …identifying ids}` — no polymorphic model, no PK leakage into domain
code.

## 4. Tempo Seam & Single Declaration

**`get_active_round_context(character) → RoundContext | None`** lives in
`src/actions/`. Return type is the **abstract `RoundContext`** — the unified
dispatch never imports `CombatEncounter`. `RoundContext` is a concrete abstract
base class (inheritance over Protocol, per project rule) exposing:

- `round_id` — round identity
- `is_declaration_open` — bool
- `record_declaration(character, player_action, kwargs)`

**Combat is the sole implementor:** `CombatRoundContext` wraps an active
`CombatParticipant` (`src/world/combat/models.py:385-422`) whose
`CombatEncounter.status == DECLARING` (status enum
`DECLARING | RESOLVING | BETWEEN_ROUNDS | COMPLETED`,
`src/world/combat/models.py:27-88`). The combat-detection branch lives **inside
this one resolver**; a future general-scene provider is just another branch
here — nothing downstream changes. That is the anti-bolt-on guarantee, at the
cost of one function and one ABC.

**Dispatch behavior:**

- `get_active_round_context` → `None`: dispatch is immediate (challenge
  resolves now, registry runs now).
- Non-None: COMBAT/CHALLENGE dispatch is **declaration-gated**;
  `record_declaration` is called; nothing resolves until the round resolves
  (combat: the untouched GM `resolve_round`). Re-dispatching while
  `is_declaration_open` overwrites — structurally cannot spam.

**Single slot, no polymorphism:**

- A COMBAT declaration writes the existing `CombatRoundAction`
  (`src/world/combat/models.py:425-518`); `focused_action` stays narrowly typed
  to `Technique` — unchanged, no polymorphic FK.
- A CHALLENGE declared *during* a round is **deferred and resolved at round
  resolution** (consistent with "not fastest-typist"), stored in a
  **consumer-owned bridge** `RoundChallengeDeclaration` in **`world/combat`**
  (the round-slot consumer), keyed `(encounter, round, participant) →
  (ChallengeInstance, ChallengeApproach)` — a bridge table, not a cross-system
  or polymorphic FK. The combat side subscribes to the challenge primitive; the
  challenge models gain no FK back into combat.
- `record_declaration` enforces mutual exclusivity: declaring one kind clears
  the other → exactly one declared action per round. Passive slots
  (`physical_passive` / `social_passive` / `mental_passive`) remain combat's
  concurrency detail, surfaced as-is, never extended into the unbuilt
  multi-priority system.
- `resolve_round` is extended **only** to resolve declared challenges as a
  **post-pass after combat-action resolution within the same round** (clean
  separation: a challenge resolved this round does not retroactively alter that
  round's combat resolution; any challenge *spawned* by a consequence appears
  on the next round's on-demand read). Multiple declared challenges resolve in
  participant initiative order. Lifecycle / endpoints unchanged.

**Registry actions** (look / say / equip) are **not changed by this
initiative** — they keep current behavior in and out of combat. Whether any of
them costs a round is pre-existing combat-design, not this interface's concern.

## 5. The #1 Fix (Concrete)

- In `_resolve_pc_action` (`src/world/combat/services.py:1764`),
  `offense_check_type` is derived from
  `action.focused_action.action_template.check_type` — not received as `None`.
- The silent `if offense_check_type is not None` no-op guard is **deleted**. A
  combat-usable technique with no `action_template` is a configuration error
  that raises a typed exception, never a silent skip.
- Validation that a declared technique has an `action_template` is enforced by
  `CombatRoundContext._record_combat_declaration` inside the dispatch path
  (validation before calling `declare_action`). The former
  `DeclareActionSerializer` and the `/api/combat/{id}/declare/` view were
  **retired in #987**; `dispatch_player_action` →
  `CombatRoundContext.record_declaration` → `_record_combat_declaration` is now
  the single combat-declaration authority. [BUILT & WIRED]
- `focused_ally_target` is now accepted through the unified
  `/api/actions/characters/{id}/dispatch/` endpoint (the hardcoded `None` in
  the old `src/world/combat/views.py:290` is gone with the retired view).
  `declare_action` already accepted it; the fix was exposing it at the call
  site. [BUILT & WIRED]

## 6. Surfaces

Two endpoints under `src/actions/`:

- `GET …/actions/characters/{id}/available/` — the merged `PlayerAction` read.
- `POST …/actions/dispatch/` — `{ref, kwargs}`.

WebSocket `execute_action` inputfunc gains the unified `ref` form; a registry
`ref` is `{backend: REGISTRY, key}`, trivially adapted from today's
`{action: key}` envelope.

**Cleanup (in scope):** delete the superseded challenge-only
`available-actions/` endpoint (`AvailableActionsView`, route
`src/world/mechanics/urls.py:30`) and repoint/remove its **frontend call
sites**. The third availability path,
`world/scenes/action_availability.get_available_scene_actions` (the social
`ActionTemplate` query), is **also superseded** by `get_player_actions` and is
folded in: its social actions become `REGISTRY`/template-backed `PlayerAction`s
in the unified read, and `get_available_scene_actions` plus its callers are
deleted (no dead third path). Single dispatch envelope shape — no dual-format
handling retained.
`get_available_actions` the *service* stays (it is the challenge source);
only the endpoint is consolidated under `src/actions/`. Frontend changes must
pass `pnpm typecheck` and `pnpm lint`.

## 7. Error Handling

- A typed `ActionDispatchError` with a `user_message` property and a safe
  allowlist (the established `EventError` / `JournalError` / `ProgressionError`
  pattern). Never `str(exc)` in API responses.
- Serializers surface user-facing validation as 400s. Services raise typed
  errors only as defensive assertions (missing `action_template`, dead `ref`,
  wrong type) — not user-input validation.
- Permission checks via DRF permission classes (`IsCharacterOwner`-style), not
  inline try/except.

## 8. Testing

Factory-based seed (no fixtures), user-story integration tests **before any
UI** (seed-first rule):

1. **The #1 regression** — declare a damaging technique, resolve round, assert
   damage **and** conditions actually applied (this test would have caught the
   sever).
2. Self-cast / buff via `focused_ally_target`.
3. **Challenge-in-combat** — `ChallengeInstanceFactory` in the encounter room;
   assert it appears in `get_player_actions`; declare its approach; resolve
   round; assert it resolved in round order **and** that declaring it cleared a
   prior technique declaration (single-slot enforced).
4. **Outside combat** — challenge dispatch resolves immediately
   (`get_active_round_context` → `None`).

Full affected suites — `actions`, `world.combat`, `world.mechanics`,
`world.magic`, `world.checks` — run **without `--keepdb`** before push (matches
CI's fresh DB).

## 9. Open Questions / Deferred

- The general non-combat turn/initiative provider — interface defined here,
  implementation is a future initiative.
- Consequence→challenge spawn + combat consequence-pool wiring — separate
  initiative; this design is forward-compatible (on-demand read).
- Whether specific registry actions (e.g., equip) should cost a combat round —
  pre-existing combat-design question, untouched here.

## 10. Telnet Convergence Convention — Three Player-Action Families (ratified #1337)

Sections 1–9 design **Family 1**: the unified `dispatch_player_action()` interface
and its three dispatch backends (REGISTRY / CHALLENGE / COMBAT). That is the seam
for *most* player actions, but it is not the only one. The
[telnet-driveability audit](../audits/2026-06-21-telnet-driveability-ui-parity.md)
identified **three distinct player-action dispatch families**, each with its own
shared seam. The invariant — ratified in #1337 — is that **telnet converges with
the web on each family's own seam; there is never a forked telnet-only path**. The
correct seam differs by family; "use `action.run()`" is *not* the universal answer.

### Family 1 — Unified dispatch (REGISTRY / CHALLENGE / COMBAT)

- **Seam:** `dispatch_player_action()` (`src/actions/player_interface.py`). Routes by
  backend: REGISTRY → `action.run()`, CHALLENGE → `resolve_challenge()`, COMBAT →
  `declare_action()` (deferred, resolved by `resolve_round()`).
- **Telnet face:** `DispatchCommand` (`src/commands/command.py`) carries an
  `ActionRef` to `dispatch_player_action()` — the same entry the web's
  `DispatchActionView` uses. Pure-REGISTRY actions may instead use the simpler
  `ArxCommand` → `action.run()` shim (REGISTRY is the one backend `action.run()`
  reaches directly). Worked examples: `CmdDeclareTechnique` (combat cast/declare).

### Family 2 — Consent (two-party targeted social actions)

- **Seam: the consent SERVICE functions** `create_action_request()` /
  `respond_to_action_request()` (`src/world/scenes/action_services.py`) — **not**
  `action.run()` or `dispatch_player_action()`. The web's `SceneActionRequestViewSet`
  calls exactly these services; telnet calls the same ones.
- **Telnet face:** `ConsentRequestCommand` / `CmdIntimidate` (request half) plus the
  generic `CmdAccept` / `CmdDeny` (response half), all in `src/commands/consent.py`.
- **Why it stays at the service seam (not resolution / `action.run()`):** consent is
  an inherently **two-party async protocol** — request, then a *separate* accept/deny
  by the target — whose response half cannot be a single dispatch call. Whether an
  action "needs consent" is a property of `ActionTemplate.consent_category`, not of
  the `Action`. Convergence here is at the **service seam**, deliberately *before*
  resolution; a naive telnet command calling `action.run()` would resolve
  immediately and skip consent — a different semantic than the web.

### Family 3 — Direct-viewset player mutations (weave / pull / endorse / membership …)

- **Seam: a real `Action` on `action.run()`** (the #1331 ritual-as-Action template).
  Where the web historically reached a service directly through a dedicated viewset,
  the convention is to introduce a real `Action`, then re-point the web serializer at
  `action.run()` so web + telnet converge on the same action machinery
  (prerequisites, AP/fatigue, enhancements, events).
- **Worked example:** `WeaveThreadAction` (`src/actions/definitions/threads.py`). The
  web `ThreadSerializer.create()` (`src/world/magic/serializers.py`) now calls
  `WeaveThreadAction().run(...)` instead of `weave_thread()` directly; the telnet face
  is `CmdWeaveThread` (`src/commands/weave.py`). (Ritual performance — imbue/pull via
  `PerformRitualAction`, #1331 — is the other landed instance of this family.)
- **Family-3 classification rule (verbatim):** *a player-facing state mutation with
  costs/prerequisites becomes an `Action`; GM/system-only surfaces (e.g.
  `resolve_round`, encounter setup) stay raw services with no player UI.*

### Summary

| Family | Seam (telnet == web) | Telnet face | Why this seam |
|---|---|---|---|
| 1 — Unified dispatch | `dispatch_player_action()` | `DispatchCommand` (or `ArxCommand`→`action.run()` for pure REGISTRY) | One entry routes REGISTRY/CHALLENGE/COMBAT by backend |
| 2 — Consent | `create_action_request()` / `respond_to_action_request()` services | `ConsentRequestCommand`/`CmdIntimidate` + `CmdAccept`/`CmdDeny` | Two-party async protocol; response half can't be one dispatch call; "needs consent" lives on `ActionTemplate.consent_category` |
| 3 — Direct-viewset mutation | a real `Action` via `action.run()` | `CmdWeaveThread` (worked: `WeaveThreadAction`) | Player mutation with costs/prerequisites; GM/system-only surfaces stay raw services |

## 11. Verified Source Anchors

| Concept | Location |
|---|---|
| Registry API | `src/actions/registry.py:46-61` |
| `Action` dataclass / `run()` | `src/actions/base.py:17-54`, `:108-160` |
| `TargetType` | `src/actions/types.py:22-28` |
| `ActionTemplate.check_type` (non-null) | `src/actions/models/action_templates.py:36` |
| Not-Yet-Built roadmap | `src/actions/CLAUDE.md:96-114` |
| `get_available_actions` | `src/world/mechanics/services.py:603-658` |
| `AvailableActionsView` (to delete) | `src/world/mechanics/views.py:110-138`, `urls.py:30` |
| `get_available_scene_actions` (third path, to fold in + delete) | `src/world/scenes/action_availability.py` |
| `ChallengeApproach` (`application`, `check_type`, `action_template`) | `src/world/mechanics/models.py:784-834` |
| `ChallengeInstance` | `src/world/mechanics/models.py:984-1015` |
| `resolve_challenge` | `src/world/mechanics/challenge_resolution.py:46-51` |
| `declare_action` | `src/world/combat/services.py:757` |
| `resolve_round` service / `_resolve_pc_action` gate | `src/world/combat/services.py:1977`, `:1720`, `:1764-1773` |
| `resolve_combat_technique` | `src/world/combat/services.py:431-483` |
| `resolve_round` view / hardcoded `focused_ally_target` | `src/world/combat/views.py:140-149`, `:290` (hardcoded `None` removed in #987) |
| ~~`DeclareActionSerializer`~~ (retired in #987) | ~~`src/world/combat/serializers.py:355-386`~~ — deleted |
| `dispatch_player_action` → `CombatRoundContext.record_declaration` → `_record_combat_declaration` (sole declaration authority) [BUILT & WIRED] | `src/actions/dispatch.py`, `src/world/combat/round_context.py` |
| `CombatEncounter` / `CombatParticipant` / `CombatRoundAction` | `src/world/combat/models.py:27-88`, `:385-422`, `:425-518` |
| `Technique.action_template` (nullable) | `src/world/magic/models/techniques.py:225-351` |
| `execute_action` inputfunc | `src/server/conf/inputfuncs.py:55-121` |
| `ArxCommand` telnet shim | `src/commands/command.py:20-144` |
| `CheckType` model | `src/world/checks/models.py:31-55` |
| `ConsequenceEffect.EffectType` (no spawn) | `src/world/checks/constants.py` |
| `_HANDLER_REGISTRY` (no challenge spawn) | `src/world/mechanics/effect_handlers.py:401-412` |

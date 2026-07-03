# Actions — Self-Contained Game Actions

The action layer is the core unit of game behavior. Each action owns its full
lifecycle: prerequisites, execution, and events. Both telnet commands and the
web dispatcher call `action.run()` — the action handles everything.

## Architecture

```
Web:    frontend → websocket → action dispatcher → action.run()
Telnet: text → command.parse() → command.func() → action.run()
```

Actions call service functions directly (from `flows/service_functions/`).
They do not use the command system, dispatchers, or handlers.

## Key Files

- **`base.py`**: `Action` dataclass — base class with `run()`, `execute()`, `check_availability()`
- **`types.py`**: `ActionResult`, `ActionAvailability`, `ActionContext`, `TargetType`, `ActionInterrupted`
- **`models.py`**: `ActionEnhancement` — explicit FK model linking sources to base actions
- **`models/action_templates.py`**: `ActionTemplate` — includes `consent_category` (nullable FK →
  `SocialConsentCategory`). Social templates are tagged by staff (or the seed loader); uncategorized
  templates are gated only by the master `allow_social_actions` switch. See `docs/systems/consent.md`.
- **`effect_configs.py`**: FK-backed config models (`ModifyKwargsConfig`, `AddModifierConfig`, `ConditionOnCheckConfig`)
- **`effects/`**: Effect handler package — dispatch registry and typed handlers
- **`enhancements.py`**: `get_involuntary_enhancements()` — query function for auto-applied enhancements
- **`prerequisites.py`**: `Prerequisite` base class — `is_met(actor, target, context)`
- **`registry.py`**: Action lookup by key (`get_action`) and by target type (`get_actions_for_target_type`)
- **`definitions/`**: Concrete action implementations grouped by category
  (e.g. `alterations.py` — `ResolveAlterationAction`, key `"resolve_alteration"`,
  REGISTRY backend, `target_type=SELF`; resolves pending Mage Scars via library
  template or scratch authoring. Shared by telnet `CmdMageScar` and the web
  `PendingAlterationViewSet.resolve`, #1490;
  `ritual.py` — `PerformRitualAction`, key `"perform_ritual"`, the
  action.run() seam for SERVICE/FLOW ritual performance shared by telnet
  `CmdRitual` and the web `RitualPerformView`, #1331;
  `cast.py` — `CastTechniqueAction`, key `"cast_technique"`, the SCENE_ADAPTIVE
  seam for standalone technique casts — see "SCENE_ADAPTIVE Backend" below;
  `combat_maneuvers.py` (#1453/#1452, Succor #1744) — the non-cast/non-clash combat verbs as
  REGISTRY actions: `FleeAction`/`CoverAction`/`InterposeAction`/`SuccorAction`/`ReadyAction`/
  `UpgradeComboAction`/`RevertComboAction`/`JoinEncounterAction`/`LeaveEncounterAction` (keys
  prefixed `combat_`). `SuccorAction` (key `combat_succor`) wraps `declare_succor` — always
  names a specific ally (no "any ally" path, unlike Interpose).
  Each `execute()` resolves the actor's active `CombatParticipant`/encounter and calls the
  existing combat service; shared by telnet `CmdCombat` (`combat <subverb>`) and the web
  `CombatEncounterViewSet`. `yield` is not here — `YieldAction` (`duels.py`) is reused. The one
  new service is `toggle_action_ready`, extracted from the inline web `ready` toggle;
  `locations.py` — `RoomEditAction`, key `"edit_room"` (#1470), owner-gated
  (`IsRoomOwnerPrerequisite`) edit of the current room's name/description/public-listing via
  `world.locations.services.set_room_display_data`; shared by the telnet `room` family (`CmdRoom`)
  + web dispatch. Plus the #670 Room Builder family (all REGISTRY, `target_type=SELF`, thin over
  `world.buildings.room_services` / `world.locations.services`): `DigRoomAction` (`"dig_room"`),
  `ResizeRoomAction` (`"resize_room"`), `RemoveRoomAction` (`"remove_room"`), `LinkRoomsAction`
  (`"link_rooms"`), `UnlinkRoomsAction` (`"unlink_rooms"`), `RenameExitAction` (`"rename_exit"`),
  `PlaceRoomAction` (`"place_room"`, #670 PR2 — cosmetic map-grid re-placement for canvas drag),
  `SetBuildingStyleAction` (`"set_building_style"`, #1469 — dress the building in a style; default
  tier open, throwback tier gated on codex knowledge via `can_build_style`),
  `PlaceFixtureAction`/`RemoveFixtureAction` (`"place_room_fixture"`/`"remove_room_fixture"`,
  #1514 close-out — comfort fixtures over `place_decoration`/`remove_decoration`),
  `AssignRoomTenantAction` (`"assign_room_tenant"`), `EndRoomTenancyAction`
  (`"end_room_tenancy"`), `SetPrimaryHomeAction` (`"set_primary_home"`,
  `IsRoomTenantPrerequisite`), `CommissionDecorationAction` (`"commission_decoration"`),
  `StartExtensionAction` (`"start_building_extension"`). Structural verbs reuse
  `IsRoomOwnerPrerequisite`; success messages carry `Space: used/total`. Web-addressable
  anchors (#670 PR2): structural actions resolve an explicit `room_id` kwarg first
  (`_resolve_room`; `to_room_id` on link, `exit_id` on unlink/rename scoped to the anchor
  room) and fall back to `actor.location`; `IsRoomOwnerPrerequisite` reads `room_id` via
  the kwargs-via-context convention and gates on the *resolved* room. `set_primary_home`
  stays deliberately location-anchored (tenant verb);
  `personas.py` — `SetActivePersonaAction`, key `"set_active_persona"` (#1347), REGISTRY backend,
  `target_type=SELF`, kwarg `persona_id`; the single action.run() path for set-active shared by
  telnet `CmdPersona` and the web `PersonaViewSet.set_active`. Validates the persona belongs to
  the actor's own sheet; wraps `world.scenes.services.set_active_persona` (the sole mutator).
  Pose/sdesc reflection of the active persona is #1109's scope, not this action;
  `forms.py` — `ShiftFormAction` / `RevertFormAction`, keys `"shift_form"` / `"revert_form"`
  (#1111 slice 4), REGISTRY backend, `target_type=SELF`; thin wrappers around
  `world.forms.services.assume_alternate_self` / `revert_alternate_self`. Shift validates that
  `alternate_self_id` belongs to the actor's sheet and is **not** `in_control`-gated
  (forced/inadvertent shifts are the point). Revert **is** `in_control`-gated and surfaces
  `RevertBlockedError.user_message` as a failure `ActionResult`. Shared by telnet and the web
  dispatcher;
  `fatigue.py` — `RestAction`, key `"rest"` (#1491/#1524), REGISTRY backend, `target_type=SELF`;
  spend AP to gain `well_rested` for the next dawn reset. Gated by `CanRestPrerequisite`
  (own home only, not in combat). Wraps `world.fatigue.services.rest`; shared by telnet `CmdRest`
  and the web `RestView`;
  `npc_services.py` — `StartNPCInteractionAction` / `ResolveNPCOfferAction` /
  `EndNPCInteractionAction`, keys `"npc_start"`, `"npc_resolve"`, `"npc_end"` (#1493), REGISTRY
  backend, `target_type=SELF`; thin wrappers around `world.npc_services.services.start_interaction`,
  `resolve_offer`, and `end_interaction`. Shared by telnet `CmdHire` and the web
  `InteractionViewSet`;
  `relationships.py` (#1485) — the four positive relationship-building verbs, all REGISTRY backend:
  `CreateFirstImpressionAction` (key `"create_first_impression"`), `CreateDevelopmentAction`
  (`"create_development"`), `CreateCapstoneAction` (`"create_capstone"`, visibility defaults
  SHARED), `RedistributePointsAction` (`"redistribute_points"`). Each wraps its
  `world.relationships.services` counterpart; `linked_scene` defaults to the caller's active scene
  when the target is co-located. Shared `BaseRelationshipAction` reuses
  `HasCharacterSheetPrerequisite` from `actions.prerequisites`. Shared by telnet `CmdRelationship`
  (`relationship <subverb>`) and the web `RelationshipUpdateViewSet`; no consent gate (ADR-0024);
  `progression_rewards.py` (#1348) — the 7 progression-reward verbs, all REGISTRY backend,
  `target_type=SELF`: `ClaimKudosAction` (key `"claim_kudos"`; wraps `claim_kudos_for_xp`),
  `CastVoteAction` / `RemoveVoteAction` (keys `"cast_vote"` / `"remove_vote"`; wrap
  `cast_vote` / `remove_vote` in `services.voting`),
  `ClaimRandomSceneAction` / `RerollRandomSceneAction` (keys `"claim_random_scene"` /
  `"reroll_random_scene"`; wrap `claim_random_scene` / `reroll_random_scene_target` in
  `services.random_scene`), `SetPathIntentAction` / `ClearPathIntentAction` (keys
  `"set_path_intent"` / `"clear_path_intent"`; wrap `set_path_intent` / `clear_path_intent`
  in the new `world.progression.services.path_intent` module). Shared by telnet
  `CmdKudos` (`kudos`) / `CmdVote` (`vote`) / `CmdRandomScene` (`randomscene`, alias `rscene`) /
  `CmdPathIntent` (`pathintent`) and the web `ClaimKudosView` / `VoteViewSet` /
  `RandomSceneViewSet` / `PathIntentViewSet`; closes the ADR-0001 "web bypasses actions" gap
  for these reward capabilities;
  `scene_reactions.py` (#1341) — the three "upvote an interaction" REGISTRY actions, all
  `target_type=SELF`: `ToggleFavoriteAction` (key `"toggle_interaction_favorite"`, wraps
  `world.scenes.reaction_toggle_services.toggle_interaction_favorite`),
  `ToggleReactionAction` (`"toggle_interaction_reaction"`, wraps `toggle_interaction_reaction`),
  `ReactToWindowAction` (`"react_to_window"`, wraps `react_to_window` / `react_to_interaction`,
  picking the lazy-open path for `lazy_open` kinds). The two toggle viewsets call the toggle
  services these Actions wrap; `ReactionWindowViewSet` already called the window services directly
  and is unchanged — `ReactToWindowAction` wraps them so telnet reaches the same seam (web does not
  call it). Shared with telnet `CmdReact`.
  `covenants.py` (#1346) — seven REGISTRY actions, all `target_type=SELF`, thin wrappers over
  `world.covenants.services`; `CovenantError` → failure `ActionResult(exc.user_message)`:
  `EngageCovenantMembershipAction` (key `"engage_covenant_membership"`),
  `DisengageCovenantMembershipAction` (`"disengage_covenant_membership"`),
  `LeaveCovenantAction` (`"leave_covenant"`), `KickCovenantMemberAction` (`"kick_covenant_member"`),
  `AssignCovenantRankAction` (`"assign_covenant_rank"`),
  `TransferTopRankAction` (`"transfer_covenant_top_rank"`),
  `StandDownBattleCovenantAction` (`"stand_down_battle_covenant"`).
  Shared by telnet `CmdCovenant` (`covenant <subverb>`) and the web covenant viewsets (both
  converge on the same service layer). Covenant induction and banner-call rise reach their services
  through the `RitualSession` seam (`CmdRitual` + the adapter registry in
  `commands/ritual_adapters.py`) rather than direct Actions — the adapters translate telnet tokens
  into the typed `DraftParse`/`JoinParse` structures and the existing session services handle
  the rest.
  `events.py` (#1499) — the event lifecycle + invitee RSVP verbs, all REGISTRY backend,
  `target_type=SELF`: `CreateEventAction` (key `"event_create"`, acts as the caller's active persona),
  `ScheduleEventAction` / `StartEventAction` / `CompleteEventAction` / `CancelEventAction`
  (`"event_schedule"` / `"event_start"` / `"event_complete"` / `"event_cancel"`, account-authorized —
  pass `actor=None` + `account` kwarg; the host/GM/staff gate mirrors the DRF permission classes),
  `InviteToEventAction` (`"event_invite"`, account-authorized), `RespondInvitationAction`
  (`"respond_invitation"`, acts as the invitee's active persona). Each wraps its
  `world.events.services` counterpart; shared by telnet `CmdEvent` (`event <subverb>`) and the web
  `EventViewSet` / `EventInvitationViewSet`; no consent gate (ADR-0024).)
  `sanctum.py` (#1497) — 7 REGISTRY actions, all `target_type=SELF`, `category="magic"`,
  wrapping the existing sanctum services. Keys: `sanctum_install`
  (`perform_sanctification` + homecoming-offer link), `sanctum_homecoming`
  (`perform_homecoming_ritual` — sacrifice resonance to grow Sanctum's Homecoming pool),
  `sanctum_purging` (`perform_purging_ritual` — change Sanctum's consecrated resonance type,
  draining grown resonance as the cost),
  `sanctum_weave` (weave a SANCTUM-anchored thread: `slot=personal|covenant|helper`),
  `sanctum_dissolve` (`perform_dissolution`, soft-delete — see dissolution note below),
  `sanctum_absorb` (`absorb_sanctum_pool` — drain the weaver's pending weaving/owner-bonus
  pool into spendable resonance currency), `sanctum_sever` (retire a
  SANCTUM-anchored thread by name or id). Module-level helpers: `sanctum_in_room(location)`
  (returns active `SanctumDetails` for the room, excludes dissolved), `room_profile_for_location`
  (resolves `RoomProfile` from an Evennia location). Shared by telnet `CmdSanctum` and the
  web `SanctumViewSet` (`world/magic/views_sanctum.py`), which now dispatches all 7 ops
  through `Action().run(actor=request.user.puppet, ...)` (#1497).
  `battles.py` (#1592/#1710/#1712) — four REGISTRY actions, all `category="battle"`:
  `BeginBattleRoundAction` (key `"begin_battle_round"`, `target_type=AREA`, GM/staff),
  `ResolveBattleRoundAction` (`"resolve_battle_round"`, `target_type=AREA`, GM/staff;
  auto-concludes via `check_victory` when a side crosses threshold),
  `ConcludeBattleAction` (`"conclude_battle"`, `target_type=AREA`, GM/staff; natural win →
  timer → DEFENDER_MARGINAL default), `DeclareBattleActionAction` (`"declare_battle_action"`,
  `target_type=SELF`, player). `DeclareBattleActionAction` dispatches all 7
  `BattleActionKind` values through the same generic `action_kind`/`target_unit`/
  `target_ally`/`scope`/`target_place`/`target_side` kwargs it always had — #1712 added
  ROUT/RALLY/REPEL/HOLD with zero code changes to this action; all four new-kind
  validation (command scope, `PlaceScopeRequiredError`) lives in
  `world.battles.services.declare_battle_action`. `ChallengeChampionDuelAction`
  (`"challenge_champion_duel"`, `target_type=AREA`, player, #1710) rounds out the file,
  binding a `BattlePlace` to a lethal duel via `open_champion_duel`. Shared by telnet
  `CmdBattle` (`battle <subverb>`, `src/commands/battle.py`).
  `room_features.py` (#1234) — two REGISTRY actions, both `target_type=SELF`,
  `category="items"`: `StartRoomFeatureProjectAction` (key `"start_room_feature_project"`)
  — generic install/upgrade project starter for any PROJECT-mechanism `RoomFeatureKind`
  (LAB, Command Center, future kinds); three-way branch (no existing instance → fresh
  install, gated on `install_mechanism`; existing instance of the same kind → upgrade,
  level-gated; existing instance of a different kind → blocked, one-feature-per-room)
  creates a `ROOM_FEATURE_PROGRESSION` `Project` + `RoomFeatureProgressionDetails` row —
  funding/resolution reuse the existing generic Project machinery (`project/donate`,
  `scan_active_projects`). `RepairLabStationAction` (`"repair_lab_station"`) — thin
  wrapper over `world.items.crafting.station.repair_station_durability`; resolves the
  active LAB `RoomFeatureInstance` for the actor's room, gates on the same
  owner/tenant standing as install/upgrade (`can_modify_room_features`), and charges
  the actor's purse in coppers. Both gated by `_resolve_active_persona` +
  `can_modify_room_features`. Shared by telnet `CmdLabStation` (`station <subverb>`,
  `src/commands/crafting_station.py`) and the web `LabStationViewSet`
  (`/api/items/lab-stations/`).)

  **Dissolution is a soft-delete**: `perform_dissolution` sets `RoomFeatureInstance.dissolved_at`
  (nullable DateTimeField) rather than deleting the row. The `.active()` queryset manager
  excludes dissolved instances. SANCTUM-anchored threads are soft-retired (`retired_at`) on
  dissolution, never deleted. The `one_personal_per_character_sheet` DB UniqueConstraint on
  `SanctumDetails` was removed (cross-table partial-unique limitation); one-personal-per-founder
  enforcement now lives in the service layer (excluding dissolved rows). Re-sanctifying the
  same room after dissolution is a deferred follow-up.

## SCENE_ADAPTIVE Backend (#1351)

`ActionBackend.SCENE_ADAPTIVE` is a fourth dispatch backend (alongside CHALLENGE, COMBAT, REGISTRY)
for actions that work in **and** out of a combat round — such as technique casts. The canonical
implementation is `CastTechniqueAction` (`actions/definitions/cast.py`, key `"cast_technique"`).

### Dispatch flow (`_dispatch_scene_adaptive` in `player_interface.py`)

1. **Anti-spam check** — `commands.pending_actions.check_anti_spam(sheet_pk, anti_spam_seconds)`.
   If a cooldown remains, raises `ActionDispatchError(ANTI_SPAM_COOLDOWN)`. The cooldown length
   comes from `get_scene_round_defaults_config().anti_spam_seconds`.
2. **Registry lookup** — key resolved from `ref.registry_key`.
3. **Round context branch** (when `ctx` is not None):
   a. Call `action_obj.round_declaration(ctx, **run_kwargs)`. If the context's `is_declaration_open`
      is True and a `(PlayerAction, decl_kwargs)` tuple is returned, record the declaration and return
      `deferred=True` immediately (STRICT combat round path).
   b. Otherwise call `ctx.is_repeat_blocked(sheet, ref, target_persona)`. If True, raise
      `ActionDispatchError(ROUND_REPEAT_BLOCKED)`.
4. **Immediate execution** — `action_obj.run(actor, **run_kwargs)`.
5. **Side-effects** (only when `result.success`):
   - `mark_acted(sheet_pk)` — records the timestamp for the anti-spam floor.
   - `ctx.record_immediate_action(sheet, ref, target_persona)` — writes the POSE_ORDER ledger row and
     advances the quorum when `mode==POSE_ORDER`.

### `Action.round_declaration` hook (`base.py`)

Default returns `None` (always immediate). Override to declare into a round:

```python
def round_declaration(self, ctx: Any, **kwargs: Any) -> tuple[PlayerAction, dict[str, Any]] | None:
    ...
```

`CastTechniqueAction` returns a `(PlayerAction, decl_kwargs)` tuple when `ctx` is a
`CombatRoundContext` (so `cast` inside combat declares into the combat round), and `None` otherwise
(immediate execution in social scene rounds).

### Anti-spam floor + pending-cast store (`commands/pending_actions.py`)

In-memory (no DB) transient stores:

- `check_anti_spam(sheet_pk, seconds) -> float | None` — remaining cooldown or None.
- `mark_acted(sheet_pk)` — records the timestamp.
- `PendingCast` dataclass — stores `(technique_id, target_persona_id, kwargs)` for soulfray-gated
  re-dispatch.
- `register_pending(sheet_pk, pending)` / `pop_pending(sheet_pk)` / `peek_pending(sheet_pk)` —
  manipulate the pending cast store for the `SoulfrayPendingHandler` offer flow.

### `CastTechniqueAction` (`actions/definitions/cast.py`)

Key: `"cast_technique"`. Resolves a standalone technique cast via `request_technique_cast`
(`world.scenes.cast_services`). Soulfray consent gate:

- When `get_soulfray_warning` is non-None and `confirm_soulfray_risk=False`, the action registers a
  `PendingCast` and returns `success=False` — the dispatcher does NOT record anti-spam or advance the
  pose-order quorum. The actor is prompted to `accept soulfray` or `decline soulfray` (handled by
  `SoulfrayPendingHandler` in `world/magic/offer_handlers.py`).
- When `confirm_soulfray_risk=True` (set by the offer-accept path), the cast proceeds immediately.

## Prerequisites

`get_prerequisites()` is **load-bearing** — `run()` calls `check_availability()`
against all returned prerequisites after enhancements are applied and before
`execute()` is ever reached. A non-empty list is a hard gate, not advisory.

### kwargs-via-context convention

`check_availability()` receives `context={"kwargs": context.kwargs, "scene_data": sdm}`.
Prerequisites that need to inspect action-specific kwargs (e.g., the `item` kwarg
on `UseItemAction`) read them from `context["kwargs"]`:

```python
item_obj = (context or {}).get("kwargs", {}).get("item")
```

This lets a prerequisite see a second target or any other kwarg without being
coupled to the action's kwarg names by the base class.

### Prerequisite implementations (`prerequisites.py`)

- **`StaffOnlyPrerequisite`** — actor's account must be staff.
- **`HasCharacterSheetPrerequisite`** — actor has an attached `CharacterSheet`.
- **`HoldsItemPrerequisite`** — actor holds the `item` kwarg.
- **`ItemUsablePrerequisite`** — item template has `on_use_pool` (is usable); consumables
  must have charges remaining. Delegates to `ItemTemplate.is_usable`.
- **`OnUseTargetPrerequisite`** — enforces `ItemTemplate.on_use_target_kind`: null ⇒
  self-use only (external target rejected); set ⇒ requires a target of that kind,
  reachable and visible. Visibility is currently a same-location MVP proxy
  (`_is_visible_to`); a real perception/stealth system will replace it.

## Adding a New Action

1. Create a new class in the appropriate `definitions/` file (or create a new file)
2. Subclass `Action`, set `key`, `name`, `icon`, `category`, `target_type`
3. Override `execute(actor, context, **kwargs)` with the action's logic
4. Override `get_prerequisites()` if the action has prerequisites — these are enforced
   by `run()` before `execute()` is called; read extra kwargs via `context["kwargs"]`
5. Add the action instance to `_ALL_ACTIONS` in `registry.py` — **also add its
   key to `expected_keys` in `actions/tests/test_base.py`**
   (`ActionRegistryTests.test_all_expected_actions_registered` is an exact-match
   assertion; a new Action without the corresponding key addition fails it).
   This test lives in CI's backend-shard-3, not necessarily the shard your
   edited app runs in — running only your new test module passes locally, so
   run the whole `actions` suite (`arx test actions --sqlite`) after adding an
   Action or telnet command, not just your new module.
6. Write tests in `tests/`
7. (Optional) Create a telnet command in `commands/` that delegates to the action

**Concurrent-PR conflict on the registry:** when several "telnet journey" PRs
land around the same time, they typically all append to the same insertion
point in `_ALL_ACTIONS` and `expected_keys` — a near-guaranteed 3-way conflict
on sync-with-main. Resolution is mechanical: keep **both** sides' appends
(concatenate the two Action lists / two key sets), never drop either — dropping
one breaks the exact-match test. Verify post-merge with `just test-fast
actions`; a failure there means a key was dropped or duplicated.

## Enhancement System

### ActionEnhancement Model
Database entities (techniques, distinctions, conditions) modify base actions via
`ActionEnhancement` records. Each record links a source model (via explicit nullable FKs
with a type discriminator) to a base action key, with a voluntary/involuntary flag.
The `apply()` method dispatches all attached effect configs to their handlers.

### Effect Config Models (effect_configs.py)
Each effect type is a concrete Django model inheriting from `BaseEffectConfig`.
No JSONField — all parameters are proper typed columns with FK integrity.

- **`ModifyKwargsConfig`**: Apply a named transform (uppercase/lowercase) to an action kwarg
- **`AddModifierConfig`**: Set a key-value modifier in `context.modifiers`
- **`ConditionOnCheckConfig`**: Apply a condition gated by a check roll (immunity → difficulty → roll → apply/immunity)

All configs share `enhancement` FK and `execution_order` from the abstract base.

### Effect Handlers (effects/)
- **`registry.py`**: `apply_effects()` queries all config tables, merges by `execution_order`, dispatches to handlers
- **`kwargs.py`**: `handle_modify_kwargs()` — applies named transforms to kwarg values
- **`modifiers.py`**: `handle_add_modifier()` — sets context.modifiers entries
- **`conditions.py`**: `handle_condition_on_check()` — orchestrates immunity/check/apply flow
- **`base.py`**: Shared steps (`check_immunity`, `resolve_target_difficulty`, `apply_immunity_on_fail`)

### Adding a New Effect Type

1. Create a new concrete model in `effect_configs.py` inheriting from `BaseEffectConfig`
2. Import it in `models.py` for Django model discovery
3. Create a handler function in `effects/<name>.py`
4. Register the handler in `effects/registry.py` `_HANDLER_REGISTRY`
5. Add the related name to `_CONFIG_RELATED_NAMES`
6. Write tests in `tests/test_effects.py`
7. Run `arx manage makemigrations actions`

### ActionContext
A mutable execution context built by `Action.run()` and passed to the action's `execute()`.
Contains:
- `action`, `actor`, `target`, `kwargs`, `scene_data` — read context
- `modifiers` — unstructured dict for enhancement-added modifiers
- `post_effects` — callables run after execution
- `result` — set after execution completes

`context.kwargs` is also threaded into `check_availability()` as
`context={"kwargs": context.kwargs, "scene_data": sdm}` so prerequisites can read
action-specific kwargs (see "Prerequisites" above).

### Source Contract
Source models implement one method:
- `should_apply_enhancement(actor, enhancement) -> bool` — involuntary filtering

Sources only answer "does this actor have me right now?" The *effect* of the enhancement
lives on the config model rows attached to the `ActionEnhancement`, not on the source.

### Enhancement Flow in `run()`
1. Build `ActionContext` with SceneDataManager
2. Apply voluntary enhancements via `enh.apply(context)` → dispatches to handlers
3. Query and apply involuntary enhancements via `enh.apply(context)`
4. **Enforce prerequisites** — `check_availability()` is called against the
   post-enhancement kwargs; if any prerequisite is unmet, `run()` returns a failure
   `ActionResult` immediately (never reaches `execute()`). This is a hard gate, not
   advisory. See "Prerequisites" below for the kwargs-via-context convention.
5. Charge declarative AP + fatigue costs (`_charge_costs`) — fails if AP cannot be
   afforded.
6. Call `execute()` with context and kwargs
7. Run post-effects

## Social Template Actions Return an Honest `ActionResult`

`_SocialTemplateAction.execute()` (and subclasses like `EntranceAction`, in
`definitions/social.py`) return a plain `ActionResult` (success/message/data)
built by `_result_from_resolution`, **not** the richer `PendingActionResolution`
some code expects. The resolution object is stashed at
`result.data["resolution"]` — code that does
`result.main_result.check_result.success_level` after e.g. `PersuadeAction().run(...)`
raises `AttributeError: 'ActionResult' object has no attribute 'main_result'`.
Unwrap first: `resolution = result.data["resolution"]`, then
`resolution.main_result...`. (`main_result is None` means a paused resolution
that hasn't rolled its main step yet, which the success rule treats as not
having succeeded.)

**Side-effect wiring:** the shared `_resolve_template` helper (which already
runs `dispatch_effects`) is the right place for any post-resolution side effect
that should apply to *every* social template action
(Persuade/Intimidate/Deceive/Flirt/Perform/Entrance/RestoreSense). Wiring a
side effect into one `execute()` override only covers that one action — the
base `execute()` bypasses it.

## What's Not Built Yet

### SyntheticAction Model
Wholly new actions granted by database entities. Uses parameterized templates
or flow definitions for execution. Same source contract as enhancements.

### Event Emission
`Action.run()` has TODOs for emitting intent/result events. When implemented,
the action will emit events that triggers can respond to.

### CharacterCapabilities Facade
Unified query interface for checking character capabilities. Used by
prerequisites to evaluate "can this character do X right now?"

### On-Demand Action Availability
WebSocket endpoint for the frontend to request available actions for a
specific actor/target pair. Evaluates prerequisites on demand rather than
pre-computing for every entity.

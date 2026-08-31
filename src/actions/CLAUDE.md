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
  `combat_maneuvers.py` (#1453/#1452, Succor #1744, USE_ITEM/READY-pace #2120) — the
  non-cast/non-clash combat verbs as
  REGISTRY actions: `FleeAction`/`CoverAction`/`InterposeAction`/`SuccorAction`/
  `UseItemManeuverAction`/`ReadyAction`/
  `UpgradeComboAction`/`RevertComboAction`/`JoinEncounterAction`/`LeaveEncounterAction`/
  `RallyAction`/`DemoralizeAction`/`TauntAction`/`ParleyAction` (social maneuvers, #1590/#1591)/
  `ChargeAction`/`JoustAction` (mounted, #1843)/`EngageAction`/`DisengageAction`
  (engagement locks, #2020; telnet `combat engage`/`combat disengage` since #3396;
  the web affordance #3396 deferred to #3381 never landed there — tracked in #3447) (keys
  prefixed `combat_`). `SuccorAction` (key `combat_succor`) wraps `declare_succor` — always
  names a specific ally (no "any ally" path, unlike Interpose). `UseItemManeuverAction`
  (key `combat_use`, #2120) wraps `declare_use_item` — a primary maneuver (consumes the
  round's action slot); resolves the item by `item_instance_id` (web) or held-item name
  (telnet) and takes an optional ally/opponent target. `ReadyAction` calls
  `maybe_resolve_on_ready` after a toggle lands on ready=True (#2120) so `PaceMode.READY`
  encounters resolve the moment everyone is ready.
  Each `execute()` resolves the actor's active `CombatParticipant`/encounter and calls the
  existing combat service; shared by telnet `CmdCombat` (`combat <subverb>`) and the web
  `CombatEncounterViewSet`. `yield` is not here — `YieldAction` (`duels.py`) is reused. The one
  new service is `toggle_action_ready`, extracted from the inline web `ready` toggle;
  `gm_combat.py` (#1494, create #3388) — the GM combat-encounter lifecycle Actions, all
  REGISTRY, `category="combat"`: `CreateEncounterAction` (key `create_encounter`, #3388,
  `target_type=SELF`) resolves the actor's room's active scene via `get_active_scene()` and
  gates on `world.combat.permissions.can_create_encounter_for_scene` (staff/scene-GM/scene-
  co-owner — deliberately broader than the other seven actions below, which gate on
  `_actor_may_gm_encounter`, staff-or-`is_gm`-only, since they act on an *existing* encounter
  whose scene GM is presumably already settled); creates the `CombatEncounter` with an
  optional `pace_mode` kwarg (default `PaceMode.TIMED`) and calls the shared
  `world.combat.services.finalize_new_encounter` (room-defaulting + escalation-curve
  assignment) — the same tail the web `CombatEncounterViewSet.perform_create` calls, so
  telnet and web never diverge on what a freshly created encounter looks like.
  `BeginEncounterRoundAction` (`begin_encounter_round`, `target_type=AREA`) advances
  BETWEEN_ROUNDS → DECLARING; `ResolveEncounterRoundAction` (`resolve_encounter_round`)
  resolves the current DECLARING round; `AddOpponentAction` (`add_opponent`) spawns an NPC
  opponent from a `ThreatPool`; `AddEncounterParticipantAction`/
  `RemoveEncounterParticipantAction` (`add_encounter_participant`/
  `remove_encounter_participant`) enroll/mark-removed a PC; `PauseEncounterAction`
  (`pause_encounter`) toggles the round timer; `EndEncounterAction` (`end_encounter`)
  force-completes as ABANDONED; `PreviewOpponentDefaultsAction` (`preview_opponent_defaults`)
  previews a tier's scaling formula output without mutating state. Shared by telnet
  `CmdEncounter` (`encounter <subverb>`, `commands/encounter.py`) and the web
  `CombatEncounterViewSet`;
  `locations.py` — `RoomEditAction`, key `"edit_room"` (#1470, widened #2452),
  owner-or-tenant-gated (`IsRoomTenantPrerequisite`) edit of the current room's
  name/description/public-listing via
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
  `IsRoomTenantPrerequisite` — widened #2036 to owner-OR-tenant standing, not a direct
  tenancy row only), `TagRoomResonanceAction`/`UntagRoomResonanceAction`
  (`"tag_room_resonance"`/`"untag_room_resonance"`, #2036 — thin wrappers over
  `world.magic.services.gain.tag_room_resonance`/`untag_room_resonance`, same
  `IsRoomTenantPrerequisite` gate; tagging also requires the caller has claimed the
  resonance, mirroring the pose/scene-entry endorsement claimed-resonance check),
  `CommissionDecorationAction` (`"commission_decoration"`),
  `StartExtensionAction` (`"start_building_extension"`), and the #1930 condition family
  `SettleBuildingArrearsAction` (`"settle_building_arrears"`), `RefurbishBuildingAction`
  (`"refurbish_building"` — the priced condition restore; distinct from the
  `start_building_renovation` kind-swap), `PrepareBuildingAction` (`"prepare_building"` —
  `confirm` commissions the BUILDING_PREPARATION cleanup project, funded via
  `project/donate` + sped by `project/check` Household Command),
  `ToggleUltraUpkeepAction` (`"toggle_ultra_upkeep"`) — bare invocation returns the
  owner-only condition/arrears status + cost quote, `confirm=True` pays/commissions
  (thin over `world.buildings.condition_services`). Structural verbs reuse
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
  `covenants.py` (#1346) — nine REGISTRY actions, all `target_type=SELF`, thin wrappers over
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
  the rest. `DepositCovenantFundsAction` (`"deposit_covenant_funds"`) /
  `WithdrawCovenantFundsAction` (`"withdraw_covenant_funds"`, #2992) round out the file — thin
  wrappers over `world.covenants.treasury.deposit_covenant_funds`/`withdraw_covenant_funds`
  instead of `world.covenants.services` (the treasury lives in its own module): deposit is open
  to any active member (core or minor), withdrawal is gated by `membership.rank.tier <=
  treasury.spend_rank_max`. Shared by telnet `CmdCovenant`'s `deposit`/`withdraw` subverbs
  (which resolve the caller's own membership and pass the instance directly via the
  `membership` kwarg) and the web `TreasuryPanel` (`frontend/src/covenants/components/
  TreasuryPanel.tsx`), which dispatches through the generic action-dispatch endpoint with
  only `covenant_id`/`amount` (no membership id on the wire — REST kwargs are JSON-only,
  see the `objectdb_target_kwargs`/REST-dispatch note above). Both actions' shared
  `_resolve_actor_membership(actor, kwargs)` helper handles this dual shape: a genuine
  `CharacterCovenantRole` instance under `kwargs["membership"]` (telnet) is used as-is —
  gated by `isinstance()`, so a bare id under that same key (a malformed/forged web POST)
  is never trusted as a resolved instance — and otherwise falls back to resolving the
  ACTOR'S OWN active membership from `kwargs["covenant_id"]`; a client can never name
  someone else's membership from the wire.
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
  `motif_style.py` (#2030) — three REGISTRY actions, all `target_type=SELF`,
  `category="magic"`: `BindMotifStyleAction` (key `"bind_motif_style"`),
  `UnbindMotifStyleAction` (`"unbind_motif_style"`), `ListMotifStylesAction`
  (`"list_motif_styles"`). Thin wrappers over `world.magic.services.motif_style`
  (`bind_motif_style`/`unbind_motif_style`/`motif_style_bindings`). Shared by telnet
  `CmdMotif` (`commands/motif.py`, `motif <subverb>`) and the web `MotifStyleViewSet`
  (`world/magic/views_motif_style.py`).
  `gift_acquisition.py` (#2116) — 3 REGISTRY actions, all `target_type=SELF`,
  `category="magic"`, thin wrappers over previously-uncalled acquisition services:
  `PurchaseGiftUnlockAction` (key `"purchase_gift_unlock"`, kwargs `gift_unlock_id` +
  optional `teacher_tenure_id`; wraps `spend_xp_on_gift_unlock` — the XP gate, does not
  acquire the gift), `AcceptTechniqueOfferAction` (`"accept_technique_offer"`, kwarg
  `offer_id`; wraps `accept_technique_offer` — the acquisition step, implicitly acquires
  the gift on the first technique learned from it), `AcceptThreadWeavingOfferAction`
  (`"accept_thread_weaving_offer"`, kwarg `offer_id`; wraps the pre-existing
  `accept_thread_weaving_unlock`, giving it telnet parity — the web
  `ThreadWeavingTeachingOfferViewSet.accept` now dispatches through this same Action
  instead of calling the service directly). Shared by telnet `CmdLearn`
  (`commands/gift_learning.py`) and two new web endpoints (`POST
  /api/magic/gift-unlocks/purchase/`, `POST /api/magic/technique-offers/accept/`).
  `battles.py` (#1592/#1710/#1712/#1713/#2010) — nine REGISTRY actions, all `category="battle"`:
  `BeginBattleRoundAction` (key `"begin_battle_round"`, `target_type=AREA`, GM/staff),
  `ResolveBattleRoundAction` (`"resolve_battle_round"`, `target_type=AREA`, GM/staff;
  auto-concludes via `check_victory` when a side crosses threshold),
  `ConcludeBattleAction` (`"conclude_battle"`, `target_type=AREA`, GM/staff; natural win →
  timer → DEFENDER_MARGINAL default), `DeclareBattleActionAction` (`"declare_battle_action"`,
  `target_type=SELF`, player). `DeclareBattleActionAction` dispatches all 12
  `BattleActionKind` values through the same generic `action_kind`/`target_unit`/
  `target_ally`/`scope`/`target_place`/`target_side`/`target_fortification` kwargs it
  always had — #1712 added ROUT/RALLY/REPEL/HOLD, #1713 added BREACH/FORTIFY, #1714
  added REPOSITION, #1715 added SET_ENVIRONMENT, and #2007 added MOVE, all with zero
  new Action classes; all new-kind validation
  (command scope, `PlaceScopeRequiredError`, the #1713 Fortification target/ownership
  checks, `InvalidEnvironmentScopeError`/`MissingEnvironmentTargetError`) lives in
  `world.battles.services.declare_battle_action`. `ChallengeChampionDuelAction`
  (`"challenge_champion_duel"`, `target_type=AREA`, player, #1710) rounds out the file,
  binding a `BattlePlace` to a lethal duel via `open_champion_duel`. Shared by telnet
  `CmdBattle` (`battle <subverb>`, `src/commands/battle.py`) — every `BattleActionKind`,
  including SET_ENVIRONMENT, MOVE, and REPOSITION, has a matching `battle declare`
  subverb (#2007 wired REPOSITION's, which had been declarable through this Action
  since #1714 but never had a telnet subverb — a gap this doc used to paper over —
  and added MOVE's alongside it). Five more
  JUNIOR-trust GM actions (#2010 — the staging pipeline, thin wrappers over
  `world.battles.staging`): `CreateBattleAction` (`"create_battle"`, `target_type=SELF`
  — stages a new Battle, optionally cloning a catalog `BattleMapBlueprint` in the same
  call; also grants the creator `is_gm` on the battle's backing Scene),
  `StageBattleMapAction` (`"stage_battle_map"`), `SpawnBattleUnitsAction`
  (`"spawn_battle_units"`), `EnlistBattleParticipantAction`
  (`"enlist_battle_participant"`) — all `target_type=SELF`, battle-scoped, re-verifying
  `_actor_may_gm_battle` in `execute()` since `MinimumGMLevelPrerequisite` alone only
  proves general JUNIOR+ trust, not standing over the specific battle — and
  `BrowseBattleCatalogAction` (`"browse_battle_catalog"`, `target_type=SELF`, read-only,
  not battle-scoped). Shared by telnet `CmdBattle`'s `create`/`stage`/`spawn`/`enlist`/
  `maps`/`units` subverbs and the web `StagingPanel`
  (`frontend/src/battles/components/StagingPanel.tsx`) via the generic dispatch seam.
  See `docs/systems/battles.md#staging-2010` for the full contract.
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
  (`/api/items/lab-stations/`);
  `domains.py` (#2239) — four REGISTRY actions, all `target_type=SELF`,
  `category="domains"`, making the CG/seed-only domain services reachable in play:
  `AddDomainHoldingAction` (key `add_domain_holding`) and
  `StartDomainImprovementAction` (`start_domain_improvement`) — thin over
  `houses.services.add_holding`/`start_domain_improvement`, gated on
  `can_administer_domain` (an org leader OR the `domain-steward` office holder);
  `AppointDomainOfficeAction` (`appoint_domain_office`) and
  `VacateDomainOfficeAction` (`vacate_domain_office`) — leadership-only
  (`is_org_leader`), thin over `societies.office_services`. Each resolves its
  `domain_id`/`holding_kind_id`/`holder_persona_id` from a plain int (REST-safe,
  no ObjectDB FKs). Shared by telnet `CmdDomain` (`domain <subverb>`,
  `src/commands/domains.py`); a React domain panel is a separable follow-up (no
  existing domain UI to extend). The office's `feeds_check` trait is declared but
  not yet wired into the improvement check — see the `OrganizationOffice` note in
  `world/societies/CLAUDE.md`;
  `currency.py` (#1909) — the physical-cash face of the currency ledger, all
  `target_type=SELF`/`SINGLE`, `category="items"`: `WithdrawCoinsAction` (key
  `"withdraw_coins"`) mints a loose-coin cache via `mint_loose_cache`;
  `DepositCoinsAction` (`"deposit_coins"`) redeems any coin instrument (a loose
  cache or one of the six grand coins) back into the purse via
  `redeem_instrument` — deposit is redemption regardless of denomination;
  `GiveCoinsAction` (`"give_coins"`) hands coppers straight to a co-located
  recipient's purse via `transfer`. Telnet's `CmdGive` swaps to this action
  (instead of `GiveAction`) when the item-name text parses as money via
  `world.currency.constants.parse_coppers`. Alongside `PutInAction`/
  `TakeOutAction` in `items.py`: `StealAction` (`"steal"`) — the deliberate
  ownership-gate bypass wrapping `flows.service_functions.inventory.steal`,
  gated by `CanStealPrerequisite` (visibility = eligibility, delegates to the
  target-side `steal_permitted` predicate the service re-checks); the telnet
  `withdraw coins <amount>` grammar rides the existing `CmdWithdraw` (the
  `withdraw` command key was already spoken for by `TakeOutAction`) rather than
  a colliding new command. `SetContainerPolicyAction` (`"set_container_policy"`)
  — owner-only container access-policy set, wrapping
  `flows.service_functions.inventory.set_container_policy`. New telnet
  commands in `src/commands/currency.py`: `CmdDeposit` (`deposit <item>`),
  `CmdSteal` (`steal <item>` / `steal <item> from <container>`, mirrors
  `CmdGet`'s two grammars but always dispatches `StealAction`), `CmdSecure`
  (`secure <container>=<open|friends|owner_only>`).
  `evidence.py` (#1825) — the accusation counter-play's evidence verbs, all thin over
  `world.justice`: `GatherEvidenceAction` (`gather_evidence`) / `DisposeEvidenceAction`
  (`dispose_evidence`) wrap `justice.evidence` (Skulduggery checks; gather mints a real
  ItemInstance); `StartFrameJobAction` (`start_frame_job`) wraps
  `justice.frame_jobs.start_frame_job` (Workshop-of-Iniquity-gated FRAME_JOB project,
  consent-checked at start and re-checked at completion);
  `ProduceCaseEvidenceAction` (`produce_case_evidence`) / `ExamineEvidenceAction`
  (`examine_evidence`) wrap `justice.case_file` (authority-gated production; Scrutinize
  Evidence vs the stored tamper roll). All resolve plain-int `evidence_id`/`secret_id`
  kwargs themselves (REST shape). Telnet: `CmdEvidence` (`evidence <subverb>`) +
  `CmdFrame` (`frame`), `src/commands/social/evidence.py`/`accusations.py`.
  `accusations.py` additionally carries the #1825 counter-play social verbs:
  `SmearAction` (`smear_accusation`, wraps `secrets.gossip.plant_smear` — the one-move
  L1 smear; telnet `gossip smear`), `RefuteAccusationAction` (`refute_accusation`,
  consentless defense; telnet `accuse/refute`), `DenounceFramerAction`
  (`denounce_framer`, the consent-gated backfire over `justice.denounce`; telnet
  `accuse/denounce`). `investigation.py` gains `StartInvestigationAction`
  (`start_investigation`) — the first player start surface for RESEARCH projects:
  at an active LAB, from a held RESEARCH clue or held frame evidence; telnet
  `search start [<#>]`.
  `movement.py` (#2163) — alongside the existing `GetAction`/`DropAction`/`GiveAction`/
  `TraverseExitAction`/`HomeAction`, the "go there" auto-walk pair: `TravelAction`
  (key `"travel_to"`, `target_type=SINGLE`) computes a route via
  `world.areas.positioning.travel.find_route()` (cross-Area, public-rooms-only,
  hop-capped frontier-batched BFS over the room exit graph — #2223, ADR-0120)
  and paces one hop per `hop_delay_seconds` via
  `evennia.utils.delay()`, reusing `check_exit_traversal`/`traverse_exit` per hop
  so room-state broadcasts match a manual walk; a per-caller
  `.ndb.active_travel_token` makes re-dispatch/cancellation safe — a stale
  scheduled callback no-ops instead of moving the player unexpectedly.
  `StopTravelAction` (`"stop_travel"`, `target_type=SELF`) cancels the pending
  `.ndb.active_travel_task` and clears the token. Shared by telnet `CmdTravel`
  (`travel <name>` / `travel stop`, `src/commands/travel.py`) and the web "Go
  there" buttons on the scene browser + presence panel. **Portal branch (#2222,
  ADR-0121):** `TravelAction.execute()` calls `_try_portal_travel` FIRST — when
  `world.magic.services.portal_travel.portal_route()` finds an eligible
  (known travel-mode Technique, origin anchor, destination anchor) triple, it
  commits instantly via `perform_portal_travel()` (anima debit, broadcasts,
  `move_object`) and returns, skipping `find_route()`/hop-pacing entirely;
  `None` falls through to the walking path unchanged.
  `situations.py` (#1895/#2865, `category="gm"`, both `target_type=SELF`, both gated
  `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` since both mint live `ChallengeInstance`
  rows per ADR-0091): `SetSituationAction` (key `set_situation`) instantiates a whole
  authored `SituationTemplate` at `actor.location` via `instantiate_situation`;
  `PlaceChallengeAction` (key `place_challenge`, #2865) places ONE authored
  `ChallengeTemplate` against a GM-named target object via the pre-existing
  `instantiate_challenge`, minting a standalone `ChallengeInstance`
  (`situation_instance=None`) — the lightweight path #2857's SENIOR gate on
  `InvokeCatalogCheckAction` left missing. Kwargs: `challenge_template_id`,
  `target_object_name`, and mutually exclusive `edge_reason`/`setback_reason`, which
  persist as `ChallengeInstance.severity_adjustment`/`adjustment_reason` (DB-constrained
  to exactly one `DIFFICULTY_BAND_STEP` either way, reason required). The whole placement
  runs in one `transaction.atomic()`. Band-shift resolution + bounds live in
  `actions/definitions/gm_shift.py`, shared with `InvokeCatalogCheckAction` — do NOT
  re-derive them. Telnet for both is `commands/setsituation.py`.
  `portals.py` (#2222, `category="magic"`) — the anchor-lifecycle pair, kept out of
  `movement.py`: `InstallPortalAnchorAction` (key `"portal_anchor_install"`,
  `target_type=SELF`) installs a `PortalAnchor` of a given `kind` in the actor's
  current room (owner/tenant standing + flat `settings.PORTAL_ANCHOR_INSTALL_COST`
  copper debit, wraps `install_portal_anchor`); `DissolvePortalAnchorAction`
  (`"portal_anchor_dissolve"`) soft-deletes one (owner-gated, no refund, wraps
  `dissolve_portal_anchor`) — resolves an explicit `anchor` kwarg (int pk or
  instance) or auto-resolves the room's sole active anchor, failing loud rather
  than guessing when a named id doesn't resolve. Module helper `anchors_in_room()`
  is shared with telnet `CmdPortalAnchor` (`portal/install <kind>=<name>` /
  `portal/dissolve [<kind>]`, `src/commands/portals.py`).
  `social.py` (#2183, ADR-0113) — `EntranceAction` (key `"entrance"`) gains a
  technique-driven path: `execute()` branches on a `technique_id` kwarg to
  `_execute_technique_entrance`, which mirrors `CastTechniqueAction.execute` (scene/
  persona/technique/target resolution, soulfray gating) but routes the outcome through
  a deferral matrix instead of a flat success/failure — a technique cast IS the
  entrance's check (one roll, not two), so flourish/disposition/the Dramatic Moment
  Suggestion (see `world/magic/CLAUDE.md` "Dramatic Moment Suggestion") fire whenever
  the real success level becomes known: immediately (inline resolution), at combat
  round resolution (hostile, `CombatRoundAction.from_entrance`), or at consent-accept
  (`SceneActionRequest.originated_as_entrance`). Reached via telnet `enter
  <technique>[=<target>]` and the web `EntranceTechniqueAttachment` popover, both via
  `action.run()`; `dramatic_moments.py`'s `ConfirmDramaticMomentSuggestionAction` /
  `DismissDramaticMomentSuggestionAction` (account-authorized, mirroring
  `events.py`'s host-lifecycle actions) close the recognition loop a qualifying
  entrance opens.

  **Battle-front composition (#2225):** `_execute_technique_entrance` calls
  `_resolve_battle_context(actor_sheet, scene)` before dispatching. When the
  actor is an active `BattleParticipant` stationed at a `BattlePlace` whose
  battle's scene matches the current scene, the hostile-seeded encounter is
  bound to that `BattlePlace` (via `_maybe_bind_battle_encounter`, called
  inside `_dispatch_entrance_cast` where `cast.encounter` is in scope) and the
  place-encounter-outcome trigger is installed — composing #2183's entrance
  path with #2008's front-stationing gate. When the place already has an open
  encounter, the cast feeds it (via `_feedable_encounter`); no binding needed.
  The stationing check stays in the action layer (ADR-0010); `world.combat`
  never imports from `world.battles`. Non-battle, unstationed, and
  scene-mismatch cases fall through to the normal entrance flow unchanged. The
  benign PENDING path does not get battle binding — the accept-time resolver
  (`resolve_accepted_cast`) has no battle context; a benign intervention seats
  in an existing encounter via `_feedable_encounter` if one exists.

  **Dissolution is a soft-delete**: `perform_dissolution` sets `RoomFeatureInstance.dissolved_at`
  (nullable DateTimeField) rather than deleting the row. The `.active()` queryset manager
  excludes dissolved instances. SANCTUM-anchored threads are soft-retired (`retired_at`) on
  dissolution, never deleted. The `one_personal_per_character_sheet` DB UniqueConstraint on
  `SanctumDetails` was removed (cross-table partial-unique limitation); one-personal-per-founder
  enforcement now lives in the service layer (excluding dissolved rows). Re-sanctifying the
  same room after dissolution is a deferred follow-up.

  `perception.py` — `LookAction` (key `"look"`) and `LookAtItemAction` (key
  `"look_at_item"`) are the shared examine seam for telnet `CmdLook` and the web
  examine-on-click dispatch. After `target_state.return_appearance(...)` (the
  flows-layer base description, post concealment gate, post dreamside swap),
  `LookAction.execute()` makes one call to
  `actions.definitions.examine_extras.gather_examine_extras(actor, target)` —
  the single aggregation seam for every examine-time display extra: the
  EXAMINE_PRE/EXAMINED reactive event pair (cancellable — a cancelled examine
  returns an empty message), reactive-scar sections, ranking displays,
  captivity status, board postings, catering history, crafted provenance, and
  (for a room target) the functionaries line, notice-board hint, and the
  looker's own pursuit-heat line. `LookAtItemAction._render_item()` appends
  the item-scoped provenance/catering subset for drilled worn/container looks.
  See ADR-0213 — this replaced a typeclass-hook path
  (`ObjectParent.at_examined`/`return_appearance` in `typeclasses/mixins.py`,
  and `Room.return_appearance` in `typeclasses/rooms.py`) that had zero live
  callers, since real play always rendered through this action layer instead.

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

### Two built-in gates run BEFORE `get_prerequisites()`

`check_availability()` (`base.py`) consults two central, built-in gates ahead of
any action-specific `Prerequisite` — neither is opted into per-action; every
action gets both automatically:

1. **The dead gate (#2287)** — `Action._dead_gate_reason(actor)`. A dead actor
   is refused on every action key except `DEAD_ALLOWED_ACTION_KEYS`
   (`actions/constants.py` — the ghost-interlude spectator/off-ramp whitelist:
   `look`, `emit`, `pose`, `wake`, `retire`, `death_kudos`, …).
2. **The offscreen-act gate (#3412, ADR-0246)** — `Action._offscreen_gate_reason(actor)`,
   consulted only when the dead gate above did NOT already refuse. Delegates to
   `actions.offscreen_gate.offscreen_act_state(sheet, action_key)`: for the
   narrow set of "2.5 acts" in `OFFSCREEN_ACT_KEYS` (journal entries, character
   goals, persona swaps, proclamations), a character in a degraded lifecycle
   state (CAPTURED, unconscious, DEAD, RETIRED, UNKNOWN) gets ROUTED (refusal
   naming a rescue channel) or BLOCKED instead of ALLOWED. Every other action
   key resolves ALLOWED without a lifecycle read at all — see ADR-0246 for why
   this extends the dead gate's choke point rather than building a second one.

Both gates append to the same `failures` list `check_availability()` builds
before `get_prerequisites()` ever runs, so a refusal from either reads as an
ordinary unmet-prerequisite failure to every caller (web dispatch and telnet
alike) — no separate error path to special-case.

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
- **`BuildWarrantPrerequisite`** (#3477) — staff bypass (same check/message as
  `StaffOnlyPrerequisite`), else requires an `AreaBuildGrant` (`world.gm.models`)
  covering EVERY target the action DECLARES via its `targets` tuple of
  `(kind, kwarg_name)` pairs (fix round 2) — the grant's own area or an
  `AreaClosure` ancestor (subtree descent), `max_level` at or above the level
  checked. Resolution reads ONLY declared kwargs (dispatch passes raw client
  kwargs through `execute(**kwargs)`, which ignores extras — an undeclared
  `area_id` must never be what the warrant checks), all present targets must
  pass (two-place actions like `staff_move_room` check source AND destination),
  and a present-but-unresolvable target refuses. Kinds: `"area"` (act ON the
  area — level is the area's OWN level, maxed with the `level_param` kwarg
  when set, so remove/promote/reclassify respect the ceiling), `"parent"`
  (create-child — level is the incoming child's `level_param` kwarg),
  `"room_container"` (dig into — fixed `AreaLevel.BUILDING`), and the
  row-anchored kinds (`"room"`/`"exit"`/`"place"`/`"line"`/`"emit"`/
  `"variant"`/`"room_clue"`/`"clue_trigger"`/`"anchor"`, all BUILDING) which
  resolve through the row's own FK chain. Nothing declared/resolved ⇒ behaves
  exactly like `StaffOnlyPrerequisite` (keeps root-area creation and
  generic-pool emits staff-only). Actions declare via the
  `_WorldBuilderAction.warrant_targets`/`warrant_level_param` ClassVars; gates
  every `world_builder.py` action except `author_clue`; read side is
  `world.gm.services.has_build_warrant`.
- **`HasCharacterSheetPrerequisite`** — actor has an attached `CharacterSheet`.
- **`HoldsItemPrerequisite`** — actor holds the `item` kwarg.
- **`ItemUsablePrerequisite`** — item template has `on_use_pool` (is usable); consumables
  must have charges remaining. Delegates to `ItemTemplate.is_usable`.
- **`OnUseTargetPrerequisite`** — enforces `ItemTemplate.on_use_target_kind`: null ⇒
  self-use only (external target rejected); set ⇒ requires a target of that kind,
  reachable and visible. Visibility (`_is_visible_to`) now delegates to the real
  perception/concealment seam, `can_perceive` (`world.conditions.services`, #1225) —
  see ADR-0083 for the OOC unseen-observer transparency guarantee it composes with.
- **`CanStealPrerequisite`** (#1909) — reads the `target` kwarg via the
  kwargs-via-context convention, resolves its `ItemInstance`, and delegates to
  `flows.service_functions.inventory.steal_permitted` (visibility = eligibility;
  the `steal` service re-checks the same predicate at execution time).

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

**`objectdb_target_kwargs` does NOT auto-resolve on the REST dispatch path** (#2163,
a real bug that shipped past all per-task tests because they mocked the dispatch
hook). `objectdb_target_kwargs: ClassVar[frozenset[str]]` (declared on e.g.
`TraverseExitAction`, `items.py`'s several actions) is consumed **only** by the
websocket `execute_action` inputfunc's `_resolve_registry_kwargs`
(`server/conf/inputfuncs.py`) — and even there, only for kwargs whose wire key ends
in `_id` (`key.endswith("_id") and key[:-3] in objectdb_targets`), so the kwarg must
be named `<field>_id` (e.g. `target_id`), not the bare field name. The REST dispatch
path (`dispatch_player_action` → `_dispatch_registry`,
`actions/player_interface.py`) does **no** ObjectDB resolution at all — it passes
raw kwargs straight to `action_obj.run()`. If your action takes an ObjectDB-typed
kwarg and is dispatched from the web via `useDispatchPlayerAction`/`postDispatchAction`
(REST, not the websocket), **resolve the id yourself inside `execute()`** — see
`_resolve_room()` in `definitions/locations.py:92-100` for the established pattern
(`ObjectDB.objects.filter(pk=kwargs.get("foo")).first()` when the value is an int,
falling through unchanged when it's already an ObjectDB, so the same `execute()`
works for both a telnet `.run()` call passing a resolved object and a REST dispatch
passing a raw id). Declaring `objectdb_target_kwargs` is harmless but does nothing
for a REST-only action — don't rely on it as your only correctness guarantee, and
write at least one test that calls `.run()` with a plain int in that kwarg (not a
mock, not a pre-resolved object) to prove the REST shape actually works.

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
4. **Emit `EventName.ACTION_INTENT`** (#3418; skipped when `actor is None`) — fires
   BEFORE the prerequisite gate, since intent means "the actor wants to do this,"
   not "the actor can." A trigger that cancels the flow (`stack.was_cancelled()`)
   short-circuits `run()` with a failure `ActionResult` right here, using the
   flow's `cancel_message` or a generic fallback — no prerequisite check, no AP
   charge, no `execute()`. A `MODIFY_PAYLOAD` step on the `target` field writes
   `context.kwargs["target"]` straight from the step's JSON `value` — correct
   only for a pk-shaped kwarg the action itself resolves (the
   `objectdb_target_kwargs` REST-dispatch shape, see above). Redirecting
   `target` to a real `ObjectDB` instance (so a real `execute()` body can call
   `target.location` etc.) goes through the resolving service function
   instead — `redirect_action_target`
   (`flows/service_functions/actions.py`), the action-layer counterpart of
   the movement-redirect pattern's `redirect_move` (ADR-0242/0243).
5. **Enforce prerequisites** — `check_availability()` is called against the
   post-enhancement (and post-redirect) kwargs; if any prerequisite is unmet, `run()`
   returns a failure `ActionResult` immediately (never reaches `execute()`). This is
   a hard gate, not advisory. See "Prerequisites" below for the kwargs-via-context
   convention.
6. Charge declarative AP + fatigue costs (`_charge_costs`) — fails if AP cannot be
   afforded.
7. Call `execute()` with context and kwargs
8. Run post-effects
9. **Emit `EventName.ACTION_RESULT`** (`_emit_result`, #3418; skipped when `actor is
   None`) — fires for every concluded attempt that reached this point, success or
   failure alike (a prerequisite-gate or AP-cost failure still emits; only the
   intent-cancel path in step 4 returns before any result event). `message` is
   coerced to `""` so authored comparison filters (e.g. `contains`) never receive
   `None`. Gathered at the actor's location **after** `execute()` and post-effects
   run — a successful `traverse` fires `ACTION_RESULT` in the destination room,
   not the room the actor departed from.

Generic per-action event declarations (`intent_event`/`result_event` fields on
`Action`) were removed in #3418 — every `Action` now goes through this same
`ACTION_INTENT`/`ACTION_RESULT` pair; author triggers filtered on `action_key`
(see `flows/events/payloads.py`'s `ActionIntentPayload`/`ActionResultPayload`)
instead of a per-action event name.

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

### CharacterCapabilities Facade
Unified query interface for checking character capabilities. Used by
prerequisites to evaluate "can this character do X right now?" The offscreen-act
gate (#3412, ADR-0246) is a deliberate seed of this future facade, not the
facade itself — building the full generalized interface now was rejected as
premature generalization for a slice that only needed the lifecycle-state
question.

### On-Demand Action Availability
WebSocket endpoint for the frontend to request available actions for a
specific actor/target pair. Evaluates prerequisites on demand rather than
pre-computing for every entity.

# Commands — Telnet Compatibility Layer

Thin command layer that parses telnet text input and delegates to Actions.
Commands contain no business logic — all game behavior lives in actions
and service functions.

## Architecture

Commands exist for telnet compatibility only. The web frontend bypasses
commands entirely and calls `dispatch_player_action()`.

```
Telnet (ArxCommand):      text → command.parse() → command.func() → action.run()
Telnet (DispatchCommand): text → command.parse() → command.func() → dispatch_player_action()
Web:                      frontend → websocket → action dispatcher → dispatch_player_action()
```

`dispatch_player_action()` routes by backend: REGISTRY → `action.run()`,
CHALLENGE → `resolve_challenge()`, COMBAT → `declare_action()`/`resolve_round()`,
SCENE_ADAPTIVE → immediate or declaration-deferred depending on round context.
Use `DispatchCommand` whenever the command must reach a CHALLENGE, COMBAT, or
SCENE_ADAPTIVE backend.

## Key Files

### `command.py`
- **`ArxCommand`**: Base command class for REGISTRY actions
  - `action`: The Action instance this command delegates to
  - `resolve_action_args()`: Override to parse telnet text into action kwargs
  - `func()`: Calls `resolve_action_args()` → `action.run()` → sends result to caller
- **`DispatchCommand(ArxCommand)`**: Base class for commands that ride the player-action dispatcher
  - `resolve_action_ref()`: Override to return an `ActionRef` (backend + params)
  - `resolve_action_args()`: Override to return extra kwargs passed alongside the ref
  - `func()`: Calls `dispatch_player_action(caller, ref, kwargs)` — the same seam the web uses
  - `_report_dispatch_result()`: Sends the caller a deferred-round confirmation or inline result

### When to subclass `DispatchCommand` vs `ArxCommand`

| Use | Base class |
|---|---|
| REGISTRY action (most look/say/move/item commands) | `ArxCommand` |
| CHALLENGE backend (dungeon puzzle challenges — requires `challenge_instance_id`) | `DispatchCommand` |
| SCENE_ADAPTIVE action (technique cast, works in and out of combat) | `DispatchCommand` |
| COMBAT backend (technique declaration into the current round) | `DispatchCommand` |

Both bases stay thin: no business logic in commands — all behavior lives in
actions, backends, and service functions.

### Command Files
- **`evennia_overrides/perception.py`**: `CmdLook`, `CmdInventory`
- **`evennia_overrides/communication.py`**: `CmdSay`, `CmdWhisper`, `CmdPose`, `CmdPage`,
  `CmdPemit` (`pemit <name>[,<name>...]=<text>`, `cmd:all()`, #906/#2117 — private GM narration to
  specific characters via `PemitAction`, gated on `MinimumGMLevelPrerequisite(GMLevel.STARTING)`,
  staff bypass preserved)
- **`evennia_overrides/movement.py`**: `CmdGet`, `CmdDrop`, `CmdGive` (#1909: swaps to
  `GiveCoinsAction` when the item-name text parses as money via `parse_coppers`),
  `CmdHome` (bare `home` recalls; `home/set` delegates to `SetPrimaryHomeAction` (#2036) —
  the same seam `room/home` and the web "Set as Home" button use, replacing a hand-rolled
  owner/tenant check that never accepted org-derived standing or wrote
  `CharacterSheet.current_residence`)
- **`evennia_overrides/items.py`**: `CmdWear`, `CmdUndress`, `CmdRemove`, `CmdPut`,
  `CmdWithdraw` (`withdraw <item> from <container>`; also the `withdraw coins <amount>`
  loose-cash branch, #1909 — the `withdraw` command key was already spoken for by
  `TakeOutAction`, so the coin path rides a `coins` prefix on the same command rather
  than a colliding new one), `CmdUse`
- **`currency.py`**: `CmdDeposit` (`deposit <item>`), `CmdSteal` (`steal <item>` /
  `steal <item> from <container>`, mirrors `CmdGet`'s two grammars but always
  dispatches `StealAction` — no plain-take fallback), `CmdSecure`
  (`secure <container>=<open|friends|owner_only>`) — the #1909 physical-currency
  interplay commands.
- **`evennia_overrides/exit_command.py`**: `CmdExit` (dynamic exit traversal)
- **`crafting.py`**: `CmdCraft` (`craft`, #1866) — the telnet face of facet/style
  crafting. One `ArxCommand` parses `craft facet <name> item=<id>`,
  `craft removefacet <item_facet id>`, `craft style <name> item=<id>`,
  `craft quote facet=<name>|style=<name> item=<id>` and calls `AttachFacetAction`/
  `DetachFacetAction`/`AttachStyleAction` directly (`actions/definitions/crafting.py`)
  — the same seam `ItemFacetViewSet`/`ItemStyleCraftViewSet` now dispatch through.
  No business logic in the command.
- **`investigation.py`**: `CmdSearch` (`search`, alias `investigate`, #1866) — a bare
  telnet delegate to the pre-existing `SearchAction` (`actions/definitions/
  investigation.py`), which had zero telnet command before. Mirrors `CmdRest`'s
  (`fatigue.py`) thin-shell shape.
- **`outfit.py`**: `CmdOutfit` (`outfit`, #1866) — the outfit CRUD + wear/present
  namespace. One `ArxCommand` routes a leading subverb (`save`/`rename`/`delete`/
  `addslot`/`removeslot`/`wear`/`undress`/`present`) to `SaveOutfitAction`/
  `RenameOutfitAction`/`DeleteOutfitAction`/`AddOutfitSlotAction`/
  `RemoveOutfitSlotAction` (`actions/definitions/outfits.py`) plus the pre-existing
  `ApplyOutfitAction`/`UndressAction`/`PresentOutfitAction` — the same Actions
  `OutfitViewSet`/`OutfitSlotViewSet` now dispatch through. Bare `outfit`/
  `outfit list` shows a status hub.
- **`places.py`**: `CmdPlaces` (`places`, #1866) — join/leave a Place (named
  sub-location) in the caller's current room. Bare `places` lists active Places
  there; `places join <name>` resolves a Place by name scoped to the caller's room
  (telnet has no pk to reference); `places leave` leaves whichever Place the
  caller's active persona currently occupies. Calls `JoinPlaceAction`/
  `LeavePlaceAction` (`actions/definitions/places.py`) directly.
- **`positions.py`**: `CmdPosition` (`position`, #2005) — the telnet face of the tactical
  position graph, mirroring `CmdPlaces`' shape. Bare `position` lists the caller's current
  room's staged positions with kind, occupants, and ADJACENT-reach adjacency (or
  `"This room has no positions staged."`); `position <name>` resolves a `Position` by name
  scoped to the caller's room (case-insensitive exact, then unique-prefix) and dispatches
  `TakePositionAction` when the caller is unplaced, else `MoveToPositionAction`
  (`actions/definitions/positioning.py`) — the same seam the web position panel uses.
  Ineligible/gated/non-adjacent failures surface the action's own error text verbatim.
- **`door.py`**: `CmdLock`/`CmdUnlock` (`lock`/`unlock`, #1866) — real
  implementation (replacing the former stubs) dispatching to `LockAction`/
  `UnlockAction` (`actions/definitions/doors.py`). Room-owner/tenant gated via the
  Actions' prerequisite, not in the command; no key-item system — lock state is a
  plain `db.locked` Evennia attribute on the Exit, checked by
  `ExitState.can_traverse`.
- **`offer_registry.py`**: `OfferHandler` protocol, `_REGISTRY`, `register_offer_handler`,
  `get_all_pending`, `find_handler` — pure-Python in-process registry; no DB model.
- **`offer_response.py`**: `CmdDecline` (`decline`) — registry-offer decline; see also
  extended `CmdAccept` in `consent.py`.
- **`scene.py`**: `CmdScene` (`scene`) — the scene-lifecycle namespace, thin over the Actions in
  `actions/definitions/scenes.py`: `scene start [name]` (`StartSceneAction`, also enrolls any
  present table-owning GM via `enroll_present_table_gms`, #2113), `scene finish`
  (`FinishSceneAction`), `scene gm <name>` (`GrantSceneGMAction`, #2113 — the fallback GM grant
  for cases auto-enrollment can't reach: gated on `actor_can_administer_scene` + the target
  holding a `GMProfile`), `scene round [...]` (`SetRoundModeAction`, `actions/definitions/
  rounds.py`), `scene succor <ally>` / `scene interpose <ally>` (`SuccorSceneAction`/
  `InterposeSceneAction`, #1744/#1316), bare `scene`/`scene status` (read-only round status, no
  action). Web reaches `StartSceneAction`/`FinishSceneAction`/`GrantSceneGMAction` through the
  same generic available-actions dispatcher. See "Scene Administration" in
  `docs/systems/scenes.md`. No business logic in the command.
- **`encounter.py`**: `CmdEncounter` (`encounter`, #1494) — the GM combat-encounter lifecycle
  namespace, thin over the eight Actions in `actions/definitions/gm_combat.py` (`begin`/
  `resolve`/`add`/`default`/`addpc`/`removepc`/`pause`/`end`). Every subverb is gated by
  `_actor_may_gm_encounter` (staff or `encounter.scene.is_gm(account)`) in the Action layer —
  reads the same `SceneParticipation.is_gm` flag `enroll_present_table_gms`/
  `GrantSceneGMAction`/`_enroll_lead_gm_on_scene` write (#2113). No business logic in the command.
- **`consent.py`**: `ConsentRequestCommand` (base), `CmdIntimidate`, `CmdPersuade`, `CmdDeceive`, `CmdFlirt`, `CmdPerform`, `CmdEntrance`, `CmdRestoreSense` — telnet shells for social consent-flow actions (#1337/#1338); `CmdAccept` (extended to check offer registry first; consent
  fall-through unchanged), `CmdDeny` — target responses. All call `create_action_request` / `respond_to_action_request` — the same service the web viewset calls.
- **`social/grievance.py`**: `CmdGrievance` (`+grievance`, #1429) — the telnet face of the secret-victim grievance prompt; thin over `world.secrets.services.register_secret_grievance` (the same service the web `/api/secrets/grievance/` endpoint calls). A wronged character picks a `GrievanceOption` for a secret they've learned; it applies a one-sided relationship swing toward the perpetrator.
- **`ritual.py`**: `CmdRitual` (alias `perform`) — telnet face of
  `PerformRitualAction` and multi-participant session lifecycle:
  - `ritual <name> [k=v ...]` — single-actor ritual performance (SERVICE rituals execute
    immediately; CEREMONY rituals create a `PendingRitualEffect` for finisher commands)
  - `ritual sessions` — list pending sessions
  - `ritual draft <name> invite=<char>[,<char>] [<extra k=v ...>]`
    — draft a session; extra kwargs are adapter-specific (see `ritual_adapters.py`):
    - soul-tether BILATERAL: `role=sinner|sineater resonance=<name> [writeup=...]`
    - covenant induction: `covenant=<name>` (the covenant to induct into)
    - banner-call rise: `covenant=<name>` (the dormant STANDING covenant to rise)
    - organization induction: `organization=<name>` (the non-Covenant organization to induct into)
  - `ritual join <id> [<extra k=v ...>]` — accept your invitation; adapter-specific join
    kwargs:
    - soul-tether: `role=sinner|sineater`
    - covenant induction: `role=<covenant role name>` (inductee picks their role)
    - banner-call: no extra tokens (members simply accept)
    - Durance: `testament=<oration>` (inductee's oration) + `path=<name>` (optional
      Potential path for the level-3 semi-crossing). For site-convened sessions
      (where `DuranceAdapter.should_auto_fire` returns `True`) the session fires
      automatically on `ritual join` — no `ritual fire` is needed.
  - `ritual decline <id>` — decline your invitation
  - `ritual fire <id>` — fire the session (initiator only)
  - `ritual cancel <id>` — cancel a pending session (initiator only)

  `_handle_draft` / `_handle_join` are generic — they call `get_adapter(ritual)` from
  `ritual_adapters.py` to translate flat `key=value` tokens into the typed structures the
  session services expect. Session subcommands call `draft_session` / `accept_session` /
  `decline_session` / `fire_session` / `cancel_session` directly.
- **`ritual_adapters.py`**: per-ritual draft/join adapter registry, keyed on
  `ritual.service_function_path`. Adapters translate the flat `key=value` tokens that
  `CmdRitual._handle_draft`/`_handle_join` parse into `DraftParse`/`JoinParse` dataclasses
  the session services accept. Five concrete adapters:
  - `SoulTetherAdapter` — `role=` / `resonance=` / `writeup=` for the soul-tether BILATERAL
    session.
  - `CovenantInductionAdapter` — `covenant=<name>` on draft (emits a session-level COVENANT
    reference); `role=<covenant role name>` on join (emits a COVENANT_ROLE reference the
    induction service reads).
  - `BannerCallAdapter` — `covenant=<name>` on draft; no join tokens (members simply accept
    the rise).
  - `OrganizationInductionAdapter` — `organization=<name>` on draft (emits a
    session-level ORGANIZATION reference for the generic, non-Covenant org-induction
    ritual, #1868); no join tokens (members simply accept — unlike Covenant Induction,
    there is no rank to choose since `join_organization` assigns the base rank
    automatically).
  - `DuranceAdapter` — Ritual of the Durance (class-level advancement). `parse_join`:
    `testament=<oration>` → `participant_kwargs["testament"]`; `path=<name>` → path pk via
    `resolve_advanced_path_by_name` (for the level-3 POTENTIAL semi-crossing). `should_auto_fire`:
    True when `session.session_kwargs["site_convened"] == "1"` — a marker stamped by
    `convene_durance_at_site` at draft time; False for any session drafted via plain `ritual draft`
    (the officiant fires manually with `ritual fire <id>`). The check is on the session-level marker
    only — NOT on whether the initiator is a `DuranceTrainingSite` trainer-of-record anywhere; that
    older check over-triggered a live witnessed ceremony if the officiant also held a trainer role at
    any site. `parse_draft`: no-op (officiant supplies nothing extra at draft time).
  Unregistered rituals use the base `RitualDraftAdapter` (no-op empty parses — the behavior
  before adapters were introduced). `get_adapter(ritual)` is the public entry point.
- **`weave.py`**: `CmdWeaveThread` (`weave`) — telnet face of `WeaveThreadAction`; parses
  `weave resonance=<name> <anchor>=<value> [name=<...>]`, one anchor kwarg per call (#2033
  extends the original TRAIT-only reference grammar to mirror `ThreadSerializer
  ._resolve_target`'s `TargetKind` coverage): `trait=<name or id>`,
  `track=<partner>/<track name>` (the caller's OWN developed `RelationshipTrackProgress`
  toward the named partner — partner name resolves via `search_or_raise`, the same
  found/not-found/numbered-disambiguation convention every other command uses),
  `capstone=<id or title>` (one of the caller's OWN recorded `RelationshipCapstone` rows),
  `facet=<name or id>`, `technique=<name or id>` (signature thread; caller must know it),
  `role=<name or id>` (covenant role), `mantle=<name or id>`. SANCTUM (own slot grammar,
  `commands/sanctum.py`) and GIFT (CG/latent-provision only) are not reachable from this
  generic grammar. `weave_thread` (`world/magic/services/threads.py`) asserts ownership on
  the RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE anchors (`relationship.source ==
  character_sheet`, raising `RelationshipBondNotOwned`) — protects the web path too, since
  both routes converge on the same service call. Proves the direct-viewset→Action telnet
  pattern (#1337)
- **`alterations.py`**: `CmdMageScar` (`magescar`) — telnet face of `ResolveAlterationAction` (#1490); lists and resolves pending Mage Scars by library template or scratch-authored fields. Uses namespaced `magescar list` / `magescar resolve <id> ...` subcommands.
- **`imbue.py`**: `CmdImbue` (`imbue`) — finisher for the Rite of Imbuing CEREMONY;
  parses `imbue thread=<name|id> amount=<n>`. Requires an active `PendingRitualEffect`
  for Rite of Imbuing; calls `spend_resonance_for_imbuing` to advance thread level.
- **`threads.py`**: `CmdThreads` (`threads`, #1993) — the thread management hub. Bare
  `threads`/`threads list` shows all the caller's active threads (anchor, resonance,
  display level) via `_anchor_label_for` (`world/magic/crossing/handlers.py`, the same
  helper the crossing ceremony uses). `threads crossing list` shows pending crossing
  offers + available `CrossingOption` rows; `threads crossing choose <id>` resolves a
  pending offer via `ResolveCrossingOfferAction` (the same action the web
  `CrossingRespondView` uses). Replaces the former standalone `crossing` command.
  No business logic in the command.
- **`resonance.py`**: `CmdResonance` (`resonance`, #2032) — read-only spendable-resonance
  visibility. Bare `resonance` lists claimed resonances (balance + lifetime earned) via
  `_build_magic_resonances` (`world/character_sheets/serializers.py`, the same builder
  `sheet/magic` reads — no parallel query pipeline); `resonance history [<name>]` shows the
  caller's last 10 `ResonanceGrant` rows (newest first, source label), optionally narrowed to
  one resonance, via `resonance_grant_history_for_sheet`
  (`world/magic/services/gain.py`) — mirrors `ResonanceGrantViewSet`'s ordering. No business
  logic in the command.
- **`combat.py`**: Two commands sharing a `_CombatCommandMixin` (provides
  `_combat_participant_or_none` and `_find_technique_id`). Both subclass `DispatchCommand`
  — business logic lives entirely in the dispatcher and service layer, never in the command.
  - `CmdDeclareTechnique` (`cast`, alias `declare`) — unified scene-adaptive
    technique cast (#1351/#1330); thin `DispatchCommand` that parses
    `cast <technique> [at <name>] [effort=<level>] [secondary]
    [pull=<thread>[,…] resonance=<name> [tier=<1-3>] [beseech=N]] [fury=<tier> anchor=<name>]`
    and emits a SCENE_ADAPTIVE `ActionRef` keyed to `"cast_technique"`. Outside combat:
    runs `CastTechniqueAction.execute()` immediately (non-combat cast via
    `request_technique_cast`). In a DECLARING round: calls
    `CastTechniqueAction.round_declaration()` which builds a `CombatRoundAction`
    declaration row.

    **Thread-pull params** (`pull=` / `resonance=` / `tier=` / `beseech=`) are parsed by
    the shared `_CombatCommandMixin` pull parser. The pull rides the `cast` or `clash`
    declaration — there is no standalone `pull` verb. In combat, one pull is allowed per
    round (a second attempt surfaces `PULL_ALREADY_COMMITTED`). `pull=` lists comma-separated
    thread names or ids; `resonance=` names the resonance to spend from; `tier=` is 1, 2, or 3
    (default 1). Effects that don't apply to the current context are silently applied as
    far as they fit; the declaration is refused without charge only if none apply
    (inert-effect rule).

    **`beseech=N` (#1718)** — an optional emergency thread-bond draw riding the same
    `pull=`/`resonance=` declaration. When the pulled thread is a COURT-covenant
    COVENANT_ROLE thread, `N` is requested as a temporary bonus to that thread's
    effective level for THIS pull's resolution only (never persisted to `Thread.level`).
    Rolls the shared Court-grant petition check (`world.combat.pull_helpers
    ._resolve_emergency_draw`); on success the bonus is clamped so it may exceed the
    servant's current `court_grant_ceiling` by at most `CourtGrantConfig
    .emergency_draw_max_bonus`, and any amount past the ceiling incurs debt via
    `incur_npc_debt`; on failure the pull still commits with no bonus. Works whether or
    not the Court master is present — it draws on the servant's own bond, not a live
    negotiation. Every attempt records `record_petition_outcome`. **Combat or
    non-combat**: both entry points call the identical combat-agnostic
    `_resolve_emergency_draw(sheet, cast_pull)` helper (it takes no
    `CombatEncounter`/`CombatParticipant`) — the in-combat commit
    (`commit_combat_pull`) and the non-combat charge
    (`world.magic.services.techniques._charge_cast_pull`, reached via
    `request_technique_cast`) each call it directly before
    `spend_resonance_for_pull`, so a standalone `cast <technique>
    pull=<thread> resonance=<name> beseech=N` outside any encounter rolls the
    same petition check and gets the same bonus/debt treatment.

    **Fury params** (`fury=<tier>` / `anchor=<name>`, #1454) — single-token values: `fury=`
    names a `FuryTier` by name or depth; `anchor=` names the bonded character whose harm the
    rage answers to (resolved to a `CharacterSheet` by character key). They inject
    `fury_commitment_id` / `fury_anchor_id` into the dispatch kwargs, which `round_declaration`
    forwards onto the `CombatRoundAction`; `resolve_combat_technique` consumes them (control
    penalty + intensity bonus, Berserk on lost control). A soulfray-risky cast is asked at
    declaration via the `accept soulfray` / `decline soulfray` offer flow (decline = free
    re-declare); no special cast syntax triggers it.

    **Target resolution** (`at <name>`) branches on context and on the technique's authored
    `derive_target_relationship`:
    - Combat context + `ENEMY` relationship → `CombatOpponent` pk → `focused_opponent_target_id`
    - Combat context + `ALLY`/`SELF` relationship → `CombatParticipant` pk → `focused_ally_target_id`
    - Non-combat context → `Persona` pk → `target_persona_id`

    **`secondary` keyword** — adds a standalone `secondary` token to the command args:
    `cast <technique> … secondary`. The technique's `action_category` derives the passive
    slot (PHYSICAL → `passive-physical`, SOCIAL → `passive-social`, MENTAL → `passive-mental`),
    which is passed as `action_slot` in both the `ActionRef` and the dispatch kwargs so
    `round_declaration` writes to the correct passive slot rather than the focused slot.
  - `CmdClashCommit` (`clash`) — commit a technique + optional strain + optional pull
    to an active Clash during a DECLARING round (#1451/#1455); parses
    `clash <opponent> with <technique> [strain=<n>]
    [pull=<thread>[,…] resonance=<name> [tier=<1-3>] [beseech=N]]`,
    resolves the `Clash` by NPC opponent name
    (`Clash.objects.filter(npc_opponent__name__iexact=...)`),
    and emits a COMBAT `ActionRef` with `clash_id=clash.pk` +
    `clash_action_slot=FOCUSED`. The dispatcher routes to `_dispatch_clash_contribution`
    which calls `declare_clash_contribution` (writes a `ClashContributionDeclaration`
    consumed by `_resolve_clashes` in the round post-pass). `strain=<n>` commits
    extra anima beyond the technique's base cost (default 0). Pull params are parsed by
    the shared `_CombatCommandMixin` pull parser (same semantics as `cast`).
- **`combat_maneuvers.py`**: `CmdCombat` (`combat`, #1453/#1452, Succor #1744, USE_ITEM #2120)
  — the shared-verb namespace. One command routes a leading subverb (`combat flee` /
  `cover <ally>` / `interpose [ally]` / `succor <ally>` / `use <item> [on <target>]` / `join` /
  `leave` / `ready` / `combo <name>` / `revert` /
  `yield`) to a REGISTRY `ActionRef` and dispatches through `dispatch_player_action` — the same
  seam the web `CombatEncounterViewSet` uses. `use <item> [on <target>]` (#2120) mirrors
  `CmdUse`'s ` on ` grammar; the item name resolves against the caller's held items inside
  `UseItemManeuverAction` (key `combat_use`), and the target clause resolves an active ally
  first, then an active opponent (`_resolve_use_item_target`). `ready` (#2120) additionally
  early-resolves the round in `PaceMode.READY` encounters once every ACTIVE participant is
  ready (`maybe_resolve_on_ready`). Bare `combat` prints a status hub — anima +
  soulfray stage (+ fury/Berserk when in an active round) alongside the declared action —
  mirroring the resource/risk visibility the web combat panel will show (#1543). Verbs are
  namespaced — not bare top-level keys — to avoid exit/channel/alias collisions (mirrors
  `CmdRitual`'s `ritual <subverb>` routing). Each verb wraps an existing
  combat service via its Action in `actions/definitions/combat_maneuvers.py`; `yield` reuses
  the existing `YieldAction`. `succor <ally>` always names a specific ally to shelter from
  environmental hazards this round (resolved at round-tick DoT application, not declaration).
- **`battle.py`**: `CmdBattle` (`battle`, #1592/#1710/#1712/#1713/#1715/#2010) — the
  large-scale-battle namespace. One `ArxCommand` routes a leading subverb (`battle declare
  strike/support/rescue/rout/rally/repel/hold/breach/fortify/set_environment ... with
  <technique>` / `battle duel <front> vs <boss name>` / `round` / `resolve` / `conclude`) to
  the four round-lifecycle REGISTRY actions in `actions/definitions/battles.py`, all via
  `Action().run()` directly. GM staging subverbs (#2010 — turn a catalog pick into a live
  Battle): `battle create <name> [risk=<level>] [map=<blueprint>]` → `CreateBattleAction`;
  `battle stage <blueprint> [replace]` → `StageBattleMapAction`; `battle spawn <template>
  [count=N] [at <front>] [side=<role>]` → `SpawnBattleUnitsAction`; `battle enlist
  <character> = <side>[, <front>]` → `EnlistBattleParticipantAction`; `battle maps [<term>]`
  / `battle units [<term>]` → `BrowseBattleCatalogAction`, pre-filtered to blueprints/
  templates only. See `docs/systems/battles.md#staging-2010` for the full contract. Bare
  `battle` prints a status hub (battle name, side VP, front, current round).
  All 10 `declare` kinds share one dispatch (a `dict[str, Callable]` lookup, not an if/elif
  chain): `strike`/`rout` resolve a named unit on either side (ACTIVE only) or accept
  `side`/`place <name>` for command-tier-gated SIDE/PLACE-scope fan-out (#1710); `rally`
  mirrors that against the declarant's own side only, also matching ROUTED units (the point
  of rallying); `support`/`rescue` name an ally; `repel`/`hold` are PLACE-scope only
  (`place <name>` required); `breach`/`fortify` target a specific `Fortification` by
  `place <name> fortification <wall|gate|battlement>` (#1713 — the extra kind token
  disambiguates since a front may hold multiple structures and `Fortification` has no
  name of its own); `set_environment` casts battlefield weather (#1715) — the technique
  carries `target_weather_type`, so no weather argument is parsed; omitting a target casts
  at BATTLE scope (SUPREME command_tier gated), or `place <name>` narrows it to a
  PLACE-scope local exception. Subverbs are namespaced — not bare top-level keys — to avoid
  exit/channel/alias collisions (mirrors `CmdCombat`/`CmdDuel`). No business logic in the
  command.
- **`duels.py`**: `CmdDuel` (`duel`, #1492) — the PC-vs-PC duel-lifecycle namespace. One command
  routes a leading subverb (`duel challenge <name>` / `accept [id]` / `decline [id]` /
  `withdraw [id]` / `risk`) to a REGISTRY `ActionRef` and dispatches through `dispatch_player_action` —
  the same seam the web uses — reaching the already-built duel Actions in
  `actions/definitions/duels.py` (`challenge`/`accept`/`decline`/`withdraw`/`acknowledge_risk`). Bare
  `duel` prints a status hub (pending incoming/outgoing challenges + active-duel state). Namespaced —
  not bare keys — because `accept`/`decline` collide with `CmdAccept`/`CmdDeny`; mirrors `CmdCombat`'s
  subverb routing. `yield` (concede an active duel) stays on `combat yield` (#1453); the hub points to
  it. The optional `[id]` selects a specific pending challenge (the #1180 threaded-inbox path); without
  it the action falls back to the actor's single pending challenge. No business logic in the command.
- **`consent_preferences.py`**: `CmdConsent` (`consent`, #1487) — the social-consent preference
  namespace. Routes a leading subverb (`consent on|off`, `consent category <key>=<mode>`,
  `consent whitelist add <name> to <category>`, `consent whitelist remove <name> from <category>`,
  `consent whitelist list [category]`) to REGISTRY `ActionRef`s and dispatches through
  `dispatch_player_action` — the same seam the web uses — reaching the already-built consent
  Actions in `actions/definitions/consent_preferences.py`
  (`set_social_consent_preference` / `set_social_consent_category_rule` /
  `add_social_consent_whitelist` / `remove_social_consent_whitelist`). Bare `consent` and
  `consent whitelist list [category]` render the caller's social-consent summary.
- **`endorse.py`**: `CmdPoses` (`poses`) and `CmdEndorse` (`endorse`) — telnet faces of
  `PoseEndorseAction`, `SceneEntryEndorseAction`, `StylePresentationEndorseAction`.
  `poses <char>` lists endorseable poses in the current scene.
  `endorse pose/entry/style <char> resonance=<name> [confirm]` dispatches to the
  appropriate action. Both derive the active scene from the caller's room via
  `get_active_scene` (#1340).
- **`fashion.py`**: `CmdJudgePresentation` (`judge`) — telnet face of
  `JudgePresentationAction`; parses `judge <presentation_id>` (#1340).
- **`missions.py`**: `CmdMission` (`mission`, #1349) — the mission play namespace. Thin over the
  mission play services in `world.missions.services.play` (+ `services.journal`) — the *same*
  functions the web `MissionJournalViewSet` calls; no separate Action (mirrors `CmdRitual`'s
  service-direct session subcommands). Bare `mission`/`mission list` shows the caller's journal
  (+ pending invites addressed to the caller's persona, #887);
  `mission beat <id>` renders the current beat's numbered options (routing single-vs-group on
  `node.conflict_mode` + participant count); `mission resolve <id> <n>` / `mission abandon <id>`
  drive the single-player path; `mission pick <id> <n>` then `mission vote <id> <n>` drive the
  two-stage group decision. `mission invite <id> <name>` invites a co-located character to join
  (#887); `mission accept <invite-id>` / `mission decline <invite-id>` respond to a pending
  invitation (the invitee is not yet a participant — thin over `world.missions.services.run`'s
  `invite_to_mission` / `respond_to_mission_invite`). `mission report <id> <style>` closes out a RESOLVED run at a
  co-located report-to **Functionary** (#1766), choosing a payout *style*
  (`humble`/`accurate`/`embellished`, #1753) — thin over `world.missions.services.report`.
  Options are chosen by the small ordinal shown in `mission beat`
  (the presented list already fans out per `ChallengeApproach`, so the ordinal carries the
  approach — no `approach=` token). Instances are participant-scoped (a non-participant gets the
  same "not part of that mission" message whether or not the id exists). Namespaced subverbs to
  avoid bare-key collisions. No business logic in the command.
- **`react.py`**: `CmdReact` (`react`, #1341) — the reaction/favorite namespace. One command routes
  a leading subverb: `react favorite <char> #N` → `ToggleFavoriteAction`;
  `react emoji <char> #N <emoji>` → `ToggleReactionAction`; `react <kind> <char> #N [<choice>]`
  (the subverb IS the kind: `react kudos <char> #1`, `react entrance <char> #1 <resonance>`) →
  `ReactToWindowAction`; bare `react` lists open reactable events in the current scene. Pose
  targeting reuses `get_endorseable_poses_in_scene` (`<char> #N`, the same scheme as `endorse`);
  the active scene derives from the caller's room via `get_active_scene`. The entrance resonance
  name is resolved to `str(pk)` here (mirrors `CmdEndorse._resolve_resonance`) — the Action stays a
  thin slug-taking wrapper. Shared by telnet + the web viewsets; no business logic in the command.
- **`gemit.py`**: `CmdGemit` (`gemit`, staff-only `perm(Admin)`, #1450) — the *push* face of the
  public-reaction center. Thin over `world.narrative.services.broadcast_gemit` (the same service the
  web gemit endpoint calls). Broadcasts a **hand-authored, verbatim** message (colour codes and all)
  to a *reach*: `gemit <msg>` (game-wide), `gemit/society <a>,<b> = <msg>`, or `gemit/org <a>,<b> =
  <msg>` (members of those societies/orgs, by active persona). No body is ever generated. Player/
  covenant-targeted story emits are a separate, non-public tool — not this command.
- **`gm_ops.py`**: `CmdGMDashboard` (`gm`, alias `gmdashboard`) — `gm dashboard` (#2004, the
  GM's queue/tables/evidence read-out) plus the GM adjudication toolkit subverbs (#2118),
  thin `parse_kv_and_flags` parsing + `action.run()` over the three Actions in
  `actions/definitions/gm_adjudication.py`: `gm check [find <term>]` / `gm check <character>
  <check-type>=<band> [edge=<reason>|setback=<reason>]` (`InvokeCatalogCheckAction` — a
  multi-word check-type name must be referenced by pk, since the check-type name IS the
  key token and can't be pre-registered as a multiword key), `gm award <character>
  xp=<amount>|dev=<trait> amount=<n> [reason=<text>]` (`GMAwardAction`), `gm condition
  <character> condition=<name> [severity=<n>] [duration=<n>] [note=<text>]`
  (`GMApplyConditionAction`). `gm suggest <kind>=<text>` (#2127 — `kind` one of
  `new_situation`/`check_fit`/`difficulty_guide`/`pool_guide`/`other`) dispatches
  `SubmitCatalogSuggestionAction` (`actions/definitions/gm_catalog.py`), gated
  `MinimumGMLevelPrerequisite(GMLevel.STARTING)` plus a `proposal_kind` tier check
  against the caller's `GMLevel` (`PROPOSAL_KIND_MIN_LEVEL`) — refuses a below-tier
  kind with a level-appropriate message; creates a `CatalogSuggestion` routed to the
  same staff inbox `GMApplication` uses. `CmdGMIdle` (`gmidle`, staff-only
  `perm(Admin)`) — idle GM tables. No business logic in the command; permission
  gating (`IsSceneGMPrerequisite` + `MinimumGMLevelPrerequisite` where applicable)
  lives entirely in the Actions.
- **`gm_tables.py`**: `CmdGMTable` (`gmtable`, #1505) — basic telnet parity for GM-table admin
  (the React `frontend/src/tables/` module is the primary surface). Thin over `world.gm.services`,
  subverb-dispatched: `gmtable [list]`, `gmtable create <name>[=<desc>]`, `gmtable members <id>`,
  `gmtable invite <id>=<persona>`, `gmtable kick <membership-id>`, `gmtable archive <id>`,
  `gmtable transfer <id>=<account>`. **Authorization mirrors the web exactly** so telnet can't
  escalate: create/list/members/invite/kick are table-owner (GM) ops gated on
  `account.gm_profile == table.gm`; `archive` + `transfer` are staff-only (the web gates both behind
  `IsAdminUser`). No business logic in the command.
- **`gmtrust.py`**: `CmdGMTrust` (`gmtrust`, #2000) — the GM trust-ladder namespace. Subverb-dispatched:
  `gmtrust show [account]` (self-service; naming another account is staff-only), `gmtrust evidence
  <account>` (staff-only aggregate track record), `gmtrust promote <account>=<level> reason=<why>`
  (staff-only level change — `reason` is required and may not be blank, mirroring the web
  `PromoteGMInputSerializer`; the level text may be a multi-word label like `Junior GM`, matched
  case-insensitively against both `GMLevel` values and labels). Thin over `world.gm.services`
  (`promote_gm` / `gm_evidence_summary`) — the same functions `GMProfileViewSet.promote` /
  `GMProfileViewSet.evidence` call. No business logic in the command.
- **`locations.py`**: `CmdRoom` (`room`, aliases `build` + legacy `manageroom`; #1470 editor +
  #670 Room Builder) — the room family. Switch-routed, one small verb per switch (the ratified
  incremental rhythm): `room/name|desc|public` → `RoomEditAction`; `room/dig <dir>=<name>
  [like=<room>] [size=<tier>]` → `DigRoomAction`; `room/size <tier>` → `ResizeRoomAction`;
  `room/drop confirm` → `RemoveRoomAction`; `room/addexit <room>=<there>,<back>` /
  `room/removeexit <exit>` / `room/renameexit <exit>=<name>` → the exit actions;
  `room/home` → `SetPrimaryHomeAction` (owner-or-tenant standing, #2036 —
  `IsRoomTenantPrerequisite` widened to `is_owner OR is_tenant`); `room/aura <resonance>` /
  `room/aura clear <resonance>` → `TagRoomResonanceAction`/`UntagRoomResonanceAction` (#2036,
  same owner-or-tenant gate; tagging additionally requires the caller has claimed that
  resonance); `room/tenant <char>` /
  `room/evict <char>` → tenancy actions; `room/extend <units>` → `StartExtensionAction`;
  `room/decorate <template> [here]` → `CommissionDecorationAction`; `room/style <name>` →
  `SetBuildingStyleAction` (#1469, knowledge-gated throwback tier); `room/fixture <kind>` /
  `room/removefixture <kind>` → the #1514 comfort-fixture actions; `room/map [floor]` —
  read-only ASCII floor map (`world.buildings.map_render`); the #1930 condition family
  `room/settle [confirm]` / `room/refurbish [confirm]` / `room/prepare [confirm]` →
  `SettleBuildingArrearsAction`/`RefurbishBuildingAction`/`PrepareBuildingAction` (bare =
  owner-only status + cost quote; `confirm` pays — for prepare it commissions the
  BUILDING_PREPARATION cleanup project, then `project/donate` / `project/check` carry it)
  and `room/ultraupkeep` → `ToggleUltraUpkeepAction`. Permissions by relationship
  (owner structural / tenant redescribe+home), gated in actions + services. No business
  logic in the command.
- **`projects.py`**: `CmdProject` (`project`, alias `+project`, #1574) — project status +
  contribution surface. `+project <id>` shows a project's status (progress/target, remaining
  coin to fund); `project/donate <id>=<amount>` dispatches `DonateToProjectAction` (key
  `project_donate`), debiting the caller's `CharacterPurse` and recording a MONEY
  `Contribution` via `world.projects.services.donate_to_project`. `project/check
  <id>=<method>` dispatches `CheckContributeAction` (key `project_check`) → rolls an authored
  `ContributionMethod`'s check (spending `ap_cost` AP), advancing progress on success
  (`contribute_check_to_project`); methods are keyed by `ProjectKind` (none for RANSOM →
  no check path). `project/story <id>=<text>` (`StoryContributeAction`, key `project_story`)
  records the narrative on the caller's latest contribution. The ransom flow reuses
  `donate` — a Ransom is a money-threshold Project (#1500).
- **`captivity.py`**: `CmdDemandRansom` (`demandransom`, staff-only `perm(Admin)`, #1500) — the
  GM demand surface for the crowdfundable ransom. `demandransom <captive>` (default amount) or
  `demandransom <captive> = <coppers>` finds the captive's held `Captivity` and calls
  `world.captivity.ransom_project.demand_ransom_project`, raising a RANSOM `Project` in the cell
  that anyone may `project/donate` toward (freed the instant it's funded). The same service backs
  the web `DemandRansomView` (`POST /api/gm/demand-ransom/`). Thin over the service — no business
  logic in the command (mirrors `gemit`).
- **`grant_item.py`**: `CmdGrantItem` (`grant_item`, `cmd:all()`, #707/#2117) — the ad-hoc
  narrative item grant surface. `grant_item <character>=<item template name>` parses the raw text
  into `target_name`/`template_name` kwargs and delegates to `GrantItemAction` (key `grant_item`,
  REGISTRY backend, `actions/definitions/items.py`) via `action.run()` — the same seam every other
  `ArxCommand` uses. The Action resolves the target by name
  (`actor.search(..., global_search=True)`) and calls
  `world.items.services.narrative_grants.grant_touchstone_item_to_character` to create one
  `ItemInstance` of the named `ItemTemplate`, held by the target's `CharacterSheet`. No shop/
  merchant system exists in this codebase — this command IS the acquisition channel for
  story-earned touchstones/reagents (a GM hand-awarding a specific item after a story beat).
  Gated on `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` (staff bypass preserved) — requires
  JUNIOR-tier GM trust or higher, not a staff flag. No business logic in the command.
- **`grant_distinction.py`**: `CmdGrantDistinction` (`grant_distinction`, `cmd:all()`, #2037) —
  the post-CG distinction award surface. `grant_distinction <character>=<distinction slug>[,rank]`
  parses the raw text into `target_name`/`distinction_slug`/optional `rank` kwargs and delegates
  to `GMAwardDistinctionAction` (key `gm_award_distinction`, REGISTRY backend,
  `actions/definitions/distinctions.py`) via `action.run()`. The Action resolves the target by
  name (`actor.search(..., global_search=True)`), looks up the catalog `Distinction` by slug
  (case-insensitive, active only — never freehand), validates an explicit rank against
  `max_rank` (reject, not clamp), and calls `world.distinctions.services.grant_distinction`
  (origin `GM_AWARD`) — the shared acquisition seam; re-awarding a held distinction ranks it up.
  Gated on `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` (staff bypass preserved). Mirrors
  `grant_item.py` exactly. No business logic in the command.
- **`setstage.py`**: `CmdSetStage` (`setstage`, `cmd:all()`, #1498/#2117) — telnet face of
  `SetTheStageAction` (key `set_the_stage`, REGISTRY backend). A STARTING-tier-or-higher GM (or
  staff) caller instantiates a `PositionBlueprint` into their current room: `setstage` shows this
  room's positions + default blueprint, `setstage list` lists all blueprints by pk, `setstage
  <name|id>` instantiates one, `setstage <name|id> replace` replaces the room's existing position
  grid. Thin `ArxCommand` over `action.run()` (same seam as the web quick-action
  `_set_the_stage_actions`); gated by `MinimumGMLevelPrerequisite(GMLevel.STARTING)` (staff bypass
  preserved). No business logic in the command.
- **`setsituation.py`**: `CmdSetSituation` (`setsituation`, `cmd:all()`, #1895/#2117/#2127) — telnet
  face of `SetSituationAction` (key `set_situation`, REGISTRY backend). A JUNIOR-tier-or-higher GM
  (or staff) caller instantiates an authored `SituationTemplate` into their current room via
  `action.run()`. Gated by `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` (staff bypass preserved) —
  mints live `Challenge`/`ChallengeInstance` rows, one tier above bare approval. `setsituation find
  <term>` (#2127) extends the same command with a STARTING-tier-or-higher browse mode, mirroring
  `gm check find`'s shape: dispatches `FindSituationAction` (`actions/definitions/gm_catalog.py`)
  instead, searching `SituationTemplate` by name/description and any matching `SituationKind`
  (breadth-filtered on `minimum_gm_level`) — read-only, never instantiates anything. No business
  logic in the command.
- **`persona.py`**: `CmdPersona` (`persona`, alias `wear-face`, #1347) — list, create, or switch
  faces. Bare `persona`/`persona list` renders all the caller's personas (marking the active one
  `◄ active`). `persona <name>`/`wear-face <name>` resolves the name among the caller's own faces
  and dispatches `SetActivePersonaAction` (key `"set_active_persona"`, REGISTRY backend) through
  `dispatch_player_action` — the same seam the web `PersonaViewSet.set_active` uses. `persona create
  <name>` (durable ESTABLISHED) and `persona mask <name>` (TEMPORARY anonymous mask, worn on
  creation) call the validated `scenes.services.create_persona`/`create_mask` directly (#1127) — the
  same services the web `create-established`/`create-mask` actions use; staff bypass the
  ESTABLISHED cap. `persona profile <name> [concept=… quote=… personality=… background=…]` (#1270)
  views or authors a non-primary persona's **Guise Sheet** (its own fabricated bio) via
  `scenes.services.set_persona_profile` (sole mutator; PRIMARY rejected); values run free to the
  next key. Pose/sdesc reflection of the presented persona is #1109's scope, not this command.
- **`form.py`**: `CmdForm` (`form`, #1111 slice 4) — list, shift into, or revert
  your alternate selves. Bare `form`/`form list` renders the active alt-self
  (`true self` if none) and the available list. `form shift <name|id>` resolves the
  owned `AlternateSelf` and dispatches `ShiftFormAction` (key `"shift_form"`, REGISTRY
  backend). `form revert` dispatches `RevertFormAction` (key `"revert_form"`). Both
  route through `dispatch_player_action` — the same seam the web form dispatcher uses.
  Namespaced subverbs (`shift`/`revert`) avoid top-level key collisions with exits/channels/
  aliases. No business logic in the command.
- **`where.py`**: `CmdWhere` (`where`, #1463) — the public presence/navigation surface.
  Thin read over `world.areas.services.where_listing`: characters in **public** rooms,
  each with their coloured area-hierarchy path (`colored_area_path` walks `AreaClosure`,
  colouring each segment by `Area.color` with cascade-down inheritance). Private rooms /
  private RP never appear (the #1287 invariant). Colours are author-set flavour (PLACEHOLDER).
- **`who.py`**: `CmdWho` (`who`, #1463) — the online roster. Thin read over
  `world.scenes.presence.who_listing`: online characters by **active** persona with a **coarse**
  idle marker (active / idle / away — never exact, so identical idle times can't out an account's
  alts). The web game-view "Who" tab + the `/api/areas/presence/` endpoint share the same service.
- **`comfort.py`**: `CmdComfort` (`comfort`, #1514/#1522) — read-only personal-comfort glance. Leads
  with *your* comfort band + the biting reasons (`world.locations.character_comfort.character_comfort_summary`
  — room exposure minus your worn-clothing mitigation, plus injury), then the room's own comfort
  level. Clothing (esp. resonance-imbued) is what counteracts it. No action.
- **`weather.py`**: `CmdTime` (`time`, alias `weather`, #1522) — IC time + local-weather glance.
  Thin over `world.weather.services.current_conditions(room)`: shows the IC clock
  (time/phase/season) and the room's effective weather + one season/phase-appropriate emit line
  (the same data the periodic WEATHER-category echo pushes and the React widget renders).
  `weather squelch` / `weather unsquelch` toggle the player's `narrative.UserCategoryMute` on the
  WEATHER category (silences the live echo, still readable in its tab). No action.
- **`presence.py`**: `CmdAfk` (`afk`) + `CmdHide` (`hide`/`unhide`, #1463) — self-presence
  privacy toggles. `afk` is a transient away marker (puppet ndb → `who` shows `away`); `hide`
  toggles persistent quiet mode (`TenureDisplaySettings.appear_offline` via
  `world.roster.services.display.set_appear_offline`): off where/who + unpageable except the
  caller's `PlayerAllowList`. Viewer-scoping lives in the presence services + `CmdPage`'s gate.
  The **web equivalent** is `GET`/`PATCH /api/roster/visibility-settings/`
  (`roster.views.settings_views.VisibilitySettingsView`, #1484) — same `set_appear_offline` write,
  scoped to the player's active character; the toggle lives on the frontend `SettingsPage`.
- **`fatigue.py`**: `CmdRest` (`rest`, #1491) — telnet face of `RestAction`. Spend AP to become
  Well-Rested; thin REGISTRY command that delegates directly to `actions.definitions.fatigue.RestAction`.
- **`sanctum.py`**: `CmdSanctum` (`sanctum`, #1497) — the sanctum-management namespace. One
  `DispatchCommand` routes a leading subverb to a REGISTRY `ActionRef` and dispatches through
  `dispatch_player_action` — the same seam the web `SanctumViewSet` uses — reaching the 7
  Actions in `actions/definitions/sanctum.py`. Bare `sanctum`/`sanctum status` = status hub
  (current sanctum in room, weaving wells). Grammar:
  `sanctum install resonance=<name> owner=<personal|covenant>`,
  `sanctum weave slot=<personal|covenant|helper>`,
  `sanctum homecoming amount=<n> [narrative=<text>]`,
  `sanctum purging resonance=<name> amount=<n>`,
  `sanctum dissolve`, `sanctum absorb`, `sanctum sever <thread name|id>`.
  Namespaced subverbs avoid exit/channel/alias collisions (mirrors `CmdCombat`). No
  business logic in the command.
- **`motif.py`**: `CmdMotif` (`motif`, #2030) — the player-facing Motif style-binding
  namespace. One `DispatchCommand` routes a leading subverb to a REGISTRY `ActionRef`
  and dispatches through `dispatch_player_action` — the same seam the web
  `MotifStyleViewSet` uses — reaching the 3 Actions in
  `actions/definitions/motif_style.py`. Bare `motif`/`motif list` lists the caller's
  current style bindings. Grammar: `motif bindstyle <style>=<resonance>`,
  `motif unbindstyle <style>`. Style/resonance lookup is exact-name matching
  (case-insensitive), since Evennia's partial/fuzzy search is broken on PostgreSQL.
  Namespaced subverbs avoid exit/channel/alias collisions (mirrors
  `CmdSignature`/`CmdSanctum`). No business logic in the command.
- **`companion.py`**: `CmdCompanion` (`companion`, #1918) — the companion lifecycle namespace. One
  `DispatchCommand` routes a leading subverb (`bind` / `fight` / `deploy` / `release`) through
  `dispatch_player_action` — the same seam the web `CompanionViewSet` uses — reaching the Actions in
  `actions/definitions/companions.py`. Bare `companion`/`companion status`/`companion list` = status hub
  (active companions + remaining capacity). Grammar:
  `companion bind archetype=<name|id> gift=<name|id> name=<text>`,
  `companion release <name|id>`, `companion fight <name|id>`, `companion deploy <name|id>`.
  Namespaced subverbs avoid exit/channel/alias collisions (mirrors `CmdSanctum`/`CmdCombat`).
  No business logic in the command.
- **`crafting_station.py`**: `CmdLabStation` (`station`, #1234) — the Lab
  crafting-station namespace. One `DispatchCommand` routes a leading subverb
  (`station install [level=<n>]` / `station upgrade level=<n>` / `station repair
  points=<n>`) to a REGISTRY `ActionRef` and dispatches through
  `dispatch_player_action` — the same seam the web `LabStationViewSet` uses —
  reaching `StartRoomFeatureProjectAction` / `RepairLabStationAction` in
  `actions/definitions/room_features.py`. Bare `station` shows a status hub (level,
  durability, broken flag) for the Lab station in the caller's current room, if any.
  Mirrors `CmdSanctum`'s subverb-routing shape. No business logic in the command.
- **`hire.py`**: `CmdHire` (`hire`, #1493) — telnet face of the three NPC-service lifecycle
  Actions (`npc_start`, `npc_resolve`, `npc_end`). Parses `hire <role> [as <persona>]`,
  `hire offer <id>`, `hire end`, and bare `hire` status hub. Stores the ephemeral
  `InteractionSession` on `caller.session.ndb` between operations; delegates to the same registry
  Actions as the web `InteractionViewSet`. `hire <name>` prefers a co-located **Functionary**
  (#1766) standing in the caller's room, falling back to a global role lookup.
- **`functionary.py`**: `CmdFunctionary` (`functionary`, #1766) — list/place/remove the class-1
  Functionaries standing in the caller's current room. Bare `functionary`/`functionary list`
  lists them (open); `functionary place <role>[=<name>]` and `functionary remove <role>` are
  staff-only (`check_permstring("Builder")`). Thin over `world.npc_services.functionaries`
  (`place_functionary`/`remove_functionary`/`functionaries_in_room`); the room the caller stands
  in is resolved via `areas.services.get_room_profile`. Functionaries also surface on `look`
  (`Room.return_appearance` appends them, since they are object-less and never in `contents`).
- **`story.py`**: `CmdStory` (`story`, #1495/#1853) — GM lifecycle actions + player self-service
  under one namespace (mirrors `CmdGMTable`'s precedent of mixed permission tiers in one command).
  GM subverbs (`complete <story-id>` / `resolve <episode-id> ...` / `promote <episode-id> ...` /
  `mark <beat-id> ...`) delegate to `Action().run()` and are gated by the story's Lead GM or staff
  status in the backing action layer — unchanged from #1495. Player subverbs are self-scoped, no
  GM/staff gate: bare `story` / `story list` shows the caller's active stories
  (`world.stories.services.dashboards.active_stories_for_account` — the same service
  `MyActiveStoriesView` calls); `story beats <episode-id>` lists one of the caller's own active
  episode's beats, flagging any staked-without-signoff treasured subject inline
  (`player_pending_treasured_signoffs`); `story signoff <beat-id> <subject> [withdraw]`
  grants/withdraws via `grant_treasured_signoff`/`withdraw_treasured_signoff` — the same service
  functions `TreasuredSignoffViewSet` calls. No business logic in the command.
  `story protect`/`story clearance` (#2001 Task 7) are the telnet face of GM-authorable
  custody protection — thin ORM + service calls over `world.stories.services.custody_clearance`
  (there is no dedicated Action here; Task 6 built plain permission functions, not a
  permission-class-gated Action, so authorization is replicated inline to match the API's
  permission classes exactly, never looser): `story protect <story-id> add <kind>=<subject-ref>
  [beat=<id>] [notes=<text>]` (`kind` one of `npc_fate`/`personal_jeopardy` — character by name,
  global search — `item` — id — `faction` — Organization name, falling back to Society name (a
  name matching both raises a disambiguation error asking for `org=<name>` or `society=<name>`,
  the two accepted alias kind-keys — mirrors `gemit.py`'s explicit-switch spirit) —
  `location`/`custom` — freeform label) creates a `StoryProtectedSubject`; `story protect
  <story-id> remove <protected-id>` soft-deactivates (`is_active=False`, never a hard delete —
  its `CustodyClearance` decision trail CASCADEs from it); `story protect <story-id> list` shows
  every protection (active and inactive) for the story. All three are gated on the story's Lead
  GM or staff (`world.stories.permissions.user_owns_or_leads_story`, mirroring
  `IsProtectedSubjectStoryOwnerOrStaff`). `story clearance request <kind>=<subject-ref>
  scope=<appear|harm|remove> [story=<id>] [message=<text>]` is the identity-based path (fans out
  to every active protection sharing that identity across stories, Task 6 review Fix 4 —
  `matching_active_protected_subjects`, skipping any already-live request and reporting it back);
  `story clearance request protected=<id> scope=... [story=<id>] [message=<text>]` is the raw-pk
  variant for a custodian-relayed id (a duplicate there is a hard error, not a skip). `story
  clearance grant|deny <id> [note=<text>]` — custodian Lead GM only, no staff bypass (staff act
  only through escalate→resolve); `story clearance escalate <id>` — requester-only; `story
  clearance resolve <id> grant|deny [note=<text>]` — staff-only; `story clearance revoke <id>` —
  custodian or staff; `story clearance list [pending]` — the caller's own requests plus requests
  against stories they own/lead, staff sees all (mirrors `CustodyClearanceViewSet.get_queryset`).
  Disclosure in every line of output follows the same rule as the API (custodian GM username,
  subject label via the shared `subject_display_label` helper, and scope only — never another
  story's title/notes). `story crossover invite <event-id> story=<id> [episode=<id>] [message=<text>]`
  (inviting GM), `story crossover accept|decline <invite-id> [episode=<id>] [note=<text>]` (invited
  story's Lead GM), `withdraw <invite-id>` (inviter), `list [pending]` (#2002) — thin over
  `world.stories.services.crossover` (the same service the web `CrossoverInviteViewSet` calls);
  authorization replicated inline (sender-only withdraw, recipient-only accept/decline) so telnet
  cannot escalate.
- **`durance.py`**: `CmdDurance` (`durance`, Progression, #1700) — the Ritual of the Durance
  readiness hub + site-convene surface. Bare `durance`/`durance status` shows level, unlock
  gate, eligible paths, declared intent, and training-site presence. `durance intent <path>`
  declares path intent (reuses `SetPathIntentAction`); `durance intent clear` clears it
  (reuses `ClearPathIntentAction`). `durance convene` calls `convene_durance_at_site` and
  echoes the session pk for the inductee to issue `ritual join <id> testament=... path=...`.
  This is setup + status only — the rite runs through `ritual` session verbs, never bypassed.
- **`progression.py`**: `CmdTraining` (`training`) + `CmdProgressionUnlock` (`progression`) —
  telnet faces of `ManageTrainingAction` and `PurchaseUnlockAction`. `training [list]` shows
  weekly AP budget and allocations; `training add skill=<id>|spec=<id> ap=<n> [mentor=<id>]`,
  `training update id=<id> [ap=<n>] [mentor=<id>]`, and `training remove id=<id>` dispatch through
  `dispatch_player_action` to the REGISTRY `manage_training` action. `progression unlocks` lists
  class-level and thread XP-lock unlocks from the same read services the web unlock shop uses;
  `progression unlock class=<id>` and `progression unlock thread=<id> level=<n>` dispatch to the
  REGISTRY `purchase_unlock` action. Both commands are namespaced subverb commands to avoid bare
  one-word key collisions. **Note (#2116):** `progression unlock class=<id>` is now a real
  precondition of the Durance advance — `advance_class_level_via_session`/
  `convene_durance_at_site` additionally require the purchased `CharacterUnlock` receipt
  alongside `check_requirements_for_unlock`; see `world/progression/CLAUDE.md`'s multi-gate rule.
  **#2122:** `progression unlocks` also prepends the caller's XP balance
  (`ExperiencePointsData.current_available`) + last-5 `XPTransaction` rows, mirroring
  `CmdKudos._show_balance`'s account-scoped lookup pattern — previously the balance only
  leaked into failed-purchase error text. Not duplicated onto `sheet`.
- **`gift_learning.py`**: `CmdLearn` (`learn`, #2116) — the gift/technique/thread-weaving
  acquisition namespace. One `DispatchCommand` routes a leading subverb (`gift <id>` /
  `technique <id>` / `thread <id>`) through `dispatch_player_action` — the same seam the web
  endpoints use — reaching the three Actions in `actions/definitions/gift_acquisition.py`.
  Bare `learn`/`learn status` shows a hub: open `GiftUnlock` rows (XP cost + purchased/missing)
  and open teaching offers (pitch/cost/teacher) for both techniques and thread-weaving. Wires
  the previously-unreachable `spend_xp_on_gift_unlock`/`accept_technique_offer` services
  (`world.magic.services.gift_acquisition`) to a player-facing surface, and gives
  `accept_thread_weaving_unlock` telnet parity with its pre-existing web endpoint. No business
  logic in the command.
- **`journals.py`**: `CmdJournal` (`journal`, #1350) — the journal authoring namespace. One
  `ArxCommand` routes a leading subverb (`journal write title=<text> body=<text> [public]
  [tags=a,b,c]` / `respond <id|#> type=praise|retort ...` / `edit <id|#> ...`) to the same
  registry Actions the web `JournalEntryViewSet` uses: `CreateJournalEntryAction`,
  `RespondToJournalAction`, `EditJournalEntryAction`. Bare `journal` / `journal list` lists the
  caller's recent top-level entries. `title`/`body` are free text (values run to the next `key=`
  token); `public` is a bare flag; `tags` is comma-separated. Namespaced to avoid top-level key
  collisions.
- **`goals.py`**: `CmdGoal` (`goal`, #1350) — the goal authoring namespace. One `ArxCommand`
  routes a leading subverb (`goal add domain=<id|name> points=<n> [notes=<text>]` (shares the
  same weekly revision limit as `set`) / `set domain=<id>:points=<n>[,...]` / `log
  [domain=<id|name>] title=<text> content=<text> [public]`) to the same registry Actions the
  web `CharacterGoalViewSet` / `GoalJournalViewSet` use: `SetCharacterGoalsAction` and
  `LogGoalProgressAction`. Bare `goal` / `goal list` shows current point allocations and points
  remaining. Domains resolve by id or name (iexact); `title`/`content`/`notes` are free text
  (values run to the next `key=` or the bare `public` flag); `public` is a bare flag. Namespaced
  to avoid top-level key collisions.
- **`progression_rewards.py`**: `CmdKudos` (`kudos`) / `CmdVote` (`vote`) / `CmdRandomScene`
  (`randomscene`, alias `rscene`) / `CmdPathIntent` (`pathintent`) (#1348) — telnet faces of the
  7 progression-reward Actions. `kudos [claim <category_id> <amount>]` dispatches
  `ClaimKudosAction`. `vote [remove] <interaction|participation|journal> <id>` dispatches
  `CastVoteAction` / `RemoveVoteAction`. `randomscene [claim|reroll] <id>` dispatches
  `ClaimRandomSceneAction` / `RerollRandomSceneAction`. `pathintent [<path_id>|clear]` dispatches
  `SetPathIntentAction` / `ClearPathIntentAction`. All are thin REGISTRY `ArxCommand` subclasses;
  no business logic — behavior lives in `actions/definitions/progression_rewards.py` and
  `world/progression/services/`.
- **`relationships.py`**: `CmdRelationship` (`relationship`, #1485) — the relationship-building
  namespace. One `ArxCommand` routes a leading subverb (`relationship impression <name> ...` /
  `develop <name> ...` / `capstone <name> ...` / `redistribute <name> ...`) and runs the matching
  relationship Action via `action.run()` directly — the same seam the web
  `RelationshipUpdateViewSet` uses (not the dispatcher; these are plain REGISTRY actions). Bare
  `relationship` / `relationship list` renders the caller's relationships; `relationship show
  <name|#>` renders one in detail (telnet-only — the web gets list/detail implicitly from
  `CharacterRelationshipViewSet`). Tracks resolve by name (iexact) or id; `title=`/`writeup=` are
  free text (values run to the next `key=`); an active scene in the caller's current room is
  linked automatically when the target is co-located. No consent gate (ADR-0024) — these describe
  regard, they don't compel behavior; kudos/complaint feedback is a follow-up.
- **`covenant.py`**: `CmdCovenant` (`covenant`, #1346) — covenant membership lifecycle namespace.
  One `ArxCommand` routes a leading subverb to the matching covenant Action via `action.run()` —
  the same seam the web covenant viewsets use (both converge on `world.covenants.services`).
  Subverbs: `covenant [list]` (membership hub), `covenant engage [<covenant>]`,
  `covenant disengage [<covenant>]`, `covenant leave [<covenant>]`,
  `covenant kick <char> [in <covenant>]`, `covenant rank <char> <rank> [in <covenant>]`,
  `covenant transfer <char> [in <covenant>]`, `covenant standdown [<covenant>]`.
  Supply the covenant name when the character belongs to more than one. Namespaced — not bare
  top-level keys — to avoid exit/channel/alias collisions; mirrors `CmdCombat`/`CmdDuel`.
  No business logic in the command. Covenant induction and banner-call rise are session-driven via
  `CmdRitual` + `CovenantInductionAdapter`/`BannerCallAdapter` (see `ritual_adapters.py`).
- **`events.py`**: `CmdEvent` (`event`, alias `events`, #1499) — the event lifecycle + invitee RSVP
  namespace. One `ArxCommand` routes a leading subverb and runs the matching event Action via
  `action.run()` directly — the same seam the web `EventViewSet` / `EventInvitationViewSet` use.
  `event create name=<text> room=<name|id> when=<datetime> [desc=…] [public=…] [phase=…]` →
  `CreateEventAction` (acts as the caller's active persona); `event schedule/start/complete/cancel
  <id>` → the host-lifecycle Actions (account-authorized — staff and scene GMs can manage an event
  with no character, so they pass `actor=None, account=<caller.account>`); `event invite <id>
  persona=|org=|society=<name|id> [by=<persona>]` → `InviteToEventAction`; `event rsvp <id>
  accept|decline` → `RespondInvitationAction` (the invitee acts as their own active persona; only a
  persona-targeted invitation addressed to them may be RSVP'd). Bare `event` / `event list` shows the
  caller's visible events; `event show <id>` renders one in detail (telnet-only — the web gets
  list/detail implicitly from `EventViewSet`). `when=` accepts ISO 8601 or `YYYY-MM-DD HH:MM`
  (room/when/name/desc values may contain spaces — they run to the next `key=`). No consent gate
  (ADR-0024 — events are calendaring; an invitation does not compel behavior).
- **`evennia_overrides/builder.py`**: `CmdDig`, `CmdOpen`, `CmdLink`, `CmdUnlink` (Evennia overrides)

### Account Commands (`account/`)
- **`account_info.py`**: `CmdAccount` (`@account`/`account`) — bare shows account information
  display; `account email <address>` (#2122) sets/updates the account's primary allauth
  `EmailAddress` and (re)sends the confirmation email — the telnet path to satisfy
  `can_apply_for_characters()`'s verified-email gate for `create <user> <pass>`-registered
  accounts, which collect no email otherwise. Operates on `self.account` only (no
  target-account argument — can't touch another account's email). Calls
  `EmailAddress.set_as_primary()` + `EmailAddress.send_confirmation(request=None,
  signup=False)` directly rather than the higher-level `EmailAddress.objects.add_email()` /
  `send_verification_email_to_address()` helper — that helper additionally calls
  `django.contrib.messages.add_message(request, ...)`, which requires a real `HttpRequest`
  with message-storage middleware and raises `TypeError` on `request=None` outside an HTTP
  request/response cycle (this project has `django.contrib.messages` installed via Evennia's
  default settings). `send_confirmation(request=None, ...)` is itself a documented allauth
  call shape (confirmations sent outside a request context) and is safe here because
  `settings.FRONTEND_URL` / `HEADLESS_FRONTEND_URLS` is always an absolute URL, so allauth's
  `render_url` never dereferences `request.build_absolute_uri`. `can_apply_for_characters()`
  (`evennia_extensions/models.py`) is unchanged — this command only gives telnet-only accounts
  a path to satisfy it. Also home to `CmdRoster` (`roster`/`roster status`, #2122) — read-only
  status of the caller's own pending `RosterApplication` rows via `PlayerData
  .get_pending_applications()`; roster browsing stays web-only (by design), scoped to the
  caller's own `PlayerData` (no id-based lookup exists, so it can't leak another account's
  applications).
- **`character_switching.py`**: `CmdIC`, `CmdCharacters` — character switching
- **`sheet.py`**: `CmdSheet` — the character sheet **hub**. Bare `sheet` shows the overview;
  `sheet/<section>` dispatches to a section (mirroring the web sheet tabs). The sheet is the
  baseline for a character and sections (secrets, and — as built — renown, relationships, society
  standings, covenant, magic) hang off it. Add a section: write a renderer in `sheet_sections.py`
  and register it in `SHEET_SECTIONS` — **don't** add a standalone `+command`.
- **`sheet_sections.py`**: the `sheet/<section>` renderers + `SHEET_SECTIONS` registry. Sections:
  `secret` (`sheet/secret [character]`, #1334 — your own secrets, or the ones you know about a
  character; locked layers "Unknown"); `renown` (`sheet/renown`, #676 — your prestige / fame tier /
  society standing, via `build_renown_payload`, mirroring the web `RenownPanel`); `relationship`
  (`sheet/relationship`, — your regard toward others, a qualitative warm/cold/neutral read of
  `CharacterRelationship.affection`, mirroring the web `RelationshipsSection`); `standing`
  (`sheet/standing` — your **organizational** positions: org memberships with rank titles + org
  reputations, scoped to active persona; distinct from `renown`, which holds fame / prestige /
  *society* reputation); `covenant` (`sheet/covenant` — your covenant membership(s), role, rank,
  and which you're *engaged* in, from `CharacterCovenantRole`; read-only); `title`
  (`sheet/titles`, #1522 — the earned, displayable titles your active character holds, from
  `achievements.CharacterTitle`; cosmetic, mirrors the web Titles tab); `distinction`
  (`sheet/distinction`, #1446 — your distinctions, secret-badged, over the shared
  `_build_distinctions` builder, mirroring the web Distinctions tab); `magic` (`sheet/magic`,
  #1446 — gifts/techniques/motif/aura/**resonance balances** (#2032) over the shared
  `_build_magic` builder, mirroring the web Magic tab; describe-only — casting/weaving/rituals
  stay in-scene, per "the sheet describes; the scene does" in `design-tenets.md`; resonance
  *history* is a separate read surface, `resonance history` (`commands/resonance.py`));
  `status` (`sheet/status`, #1446 — condition, fatigue, and
  anima as qualitative words (wound band, fatigue zones, `anima_band_for`), plus coin
  (`format_coppers`) and weekly AP (current/effective-maximum/banked); self-only, read-only,
  mirroring the web Status tab). Each is thin over its app's data. Add a section: a renderer
  + a registry entry (+ `SECTION_NAMES`). Standing and covenant now also have web homes: standing
  lives in the consolidated **Reputation** tab (society + org standing + covenant associations);
  covenant core identity surfaces in the sheet header, with full detail in the Reputation tab's
  covenant subsection (#1446). Status and Inventory now also have web homes: the game-rail
  **Status** and **Inventory** tabs (`frontend/src/status/`,
  `frontend/src/inventory/components/InventorySidebarPanel.tsx` — the latter reuses
  `useInventory`/`useEquippedItems`/`ItemCard` with Worn badges + a `/wardrobe` link).

### Social Commands (`social/`)
- **`blocking.py`**: `CmdBlock`/`CmdUnblock`/`CmdShareBlock`/`CmdMute`/`CmdUnmute`/`CmdBlockList`
  (#1278) — telnet face of the persona block/mute menu; thin over `world.scenes.block_services`.
- **`tidings.py`**: `CmdTidings` (`tidings`, #1450) — the pull/browse face of the public-reaction
  tidings feed; thin over `world.tidings.services.public_feed_for` (the same service the web
  `/api/tidings/feed/` endpoint calls). Lists recent deeds + scandals the active character's
  societies are aware of, newest first. (`gossip`/`news` are intentionally *not* used — `gossip`
  is reserved for level-1-secret access at hubs, `news` for OOC game news; criers are NPCs.)
- **`gossip.py`**: `CmdGossip` (`gossip`, #1572) — work the rumor mill at a **social hub**. Thin over
  `world.secrets.gossip`: `gossip` (list your gossipable Level-1 secrets + their heat here), `gossip
  seek` (roll to overhear a hot secret you don't know), `gossip plant <#>` (spread it — raises
  regional heat), `gossip suppress <#>` (lower heat). Gated on Gossip ≥ 1 + standing in an
  `is_social_hub` room (the services enforce both; the command surfaces the skill gate). The reserved
  `gossip` verb the tidings note above set aside.

### Frontend Integration
- **`frontend.py`**: `FrontendMetadataMixin` — for non-action commands (builder, page)
- **`utils.py`**: `serialize_cmdset()` — serializes cmdset for frontend
- **`serializers.py`**: `CommandSerializer` — DRF serializer for command payloads

### Other
- **`default_cmdsets.py`**: Command set registration
- **`exceptions.py`**: `CommandError` — raised for invalid input
- **`payloads.py`**: Look/examine payload builders
- **`descriptors.py`**: Serializable command/dispatcher descriptors

## Adding a New Command

1. Create the Action first (see `src/actions/CLAUDE.md`)
2. Create a command class inheriting from `ArxCommand`
3. Set `key`, `aliases`, `locks`, and `action`
4. Override `resolve_action_args()` to parse telnet text into action kwargs
5. Add to the appropriate cmdset in `default_cmdsets.py`

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
- **`evennia_overrides/communication.py`**: `CmdSay`, `CmdWhisper`, `CmdPose`, `CmdPage`
- **`evennia_overrides/movement.py`**: `CmdGet`, `CmdDrop`, `CmdGive`, `CmdHome`
- **`evennia_overrides/exit_command.py`**: `CmdExit` (dynamic exit traversal)
- **`door.py`**: `CmdLock`, `CmdUnlock` (stubs pending LockAction/UnlockAction)
- **`offer_registry.py`**: `OfferHandler` protocol, `_REGISTRY`, `register_offer_handler`,
  `get_all_pending`, `find_handler` — pure-Python in-process registry; no DB model.
- **`offer_response.py`**: `CmdDecline` (`decline`) — registry-offer decline; see also
  extended `CmdAccept` in `consent.py`.
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
  the session services accept. Three concrete adapters:
  - `SoulTetherAdapter` — `role=` / `resonance=` / `writeup=` for the soul-tether BILATERAL
    session.
  - `CovenantInductionAdapter` — `covenant=<name>` on draft (emits a session-level COVENANT
    reference); `role=<covenant role name>` on join (emits a COVENANT_ROLE reference the
    induction service reads).
  - `BannerCallAdapter` — `covenant=<name>` on draft; no join tokens (members simply accept
    the rise).
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
- **`weave.py`**: `CmdWeaveThread` (`weave`) — telnet face of `WeaveThreadAction`;
  parses `weave resonance=<name> trait=<name or id> [name=<...>]` (TRAIT anchor only — the
  reference grammar; other anchor kinds are extended by the thread-weaving journey
  issue). Proves the direct-viewset→Action telnet pattern (#1337)
- **`alterations.py`**: `CmdMageScar` (`magescar`) — telnet face of `ResolveAlterationAction` (#1490); lists and resolves pending Mage Scars by library template or scratch-authored fields. Uses namespaced `magescar list` / `magescar resolve <id> ...` subcommands.
- **`imbue.py`**: `CmdImbue` (`imbue`) — finisher for the Rite of Imbuing CEREMONY;
  parses `imbue thread=<name|id> amount=<n>`. Requires an active `PendingRitualEffect`
  for Rite of Imbuing; calls `spend_resonance_for_imbuing` to advance thread level.
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
- **`combat_maneuvers.py`**: `CmdCombat` (`combat`, #1453/#1452, Succor #1744) — the shared-verb
  namespace. One command routes a leading subverb (`combat flee` / `cover <ally>` /
  `interpose [ally]` / `succor <ally>` / `join` / `leave` / `ready` / `combo <name>` / `revert` /
  `yield`) to a REGISTRY `ActionRef` and dispatches through `dispatch_player_action` — the same
  seam the web `CombatEncounterViewSet` uses. Bare `combat` prints a status hub — anima +
  soulfray stage (+ fury/Berserk when in an active round) alongside the declared action —
  mirroring the resource/risk visibility the web combat panel will show (#1543). Verbs are
  namespaced — not bare top-level keys — to avoid exit/channel/alias collisions (mirrors
  `CmdRitual`'s `ritual <subverb>` routing). Each verb wraps an existing
  combat service via its Action in `actions/definitions/combat_maneuvers.py`; `yield` reuses
  the existing `YieldAction`. `succor <ally>` always names a specific ally to shelter from
  environmental hazards this round (resolved at round-tick DoT application, not declaration).
- **`battle.py`**: `CmdBattle` (`battle`, #1592/#1710/#1712/#1713/#1715) — the large-scale-battle
  namespace. One `ArxCommand` routes a leading subverb (`battle declare
  strike/support/rescue/rout/rally/repel/hold/breach/fortify/set_environment ... with
  <technique>` / `battle duel <front> vs <boss name>` / `round` / `resolve` / `conclude`) to
  the four REGISTRY actions in `actions/definitions/battles.py`, all via `Action().run()`
  directly. Bare `battle` prints a status hub (battle name, side VP, front, current round).
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
  service-direct session subcommands). Bare `mission`/`mission list` shows the caller's journal;
  `mission beat <id>` renders the current beat's numbered options (routing single-vs-group on
  `node.conflict_mode` + participant count); `mission resolve <id> <n>` / `mission abandon <id>`
  drive the single-player path; `mission pick <id> <n>` then `mission vote <id> <n>` drive the
  two-stage group decision. `mission report <id> <style>` closes out a RESOLVED run at a
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
- **`gm_tables.py`**: `CmdGMTable` (`gmtable`, #1505) — basic telnet parity for GM-table admin
  (the React `frontend/src/tables/` module is the primary surface). Thin over `world.gm.services`,
  subverb-dispatched: `gmtable [list]`, `gmtable create <name>[=<desc>]`, `gmtable members <id>`,
  `gmtable invite <id>=<persona>`, `gmtable kick <membership-id>`, `gmtable archive <id>`,
  `gmtable transfer <id>=<account>`. **Authorization mirrors the web exactly** so telnet can't
  escalate: create/list/members/invite/kick are table-owner (GM) ops gated on
  `account.gm_profile == table.gm`; `archive` + `transfer` are staff-only (the web gates both behind
  `IsAdminUser`). No business logic in the command.
- **`locations.py`**: `CmdRoom` (`room`, aliases `build` + legacy `manageroom`; #1470 editor +
  #670 Room Builder) — the room family. Switch-routed, one small verb per switch (the ratified
  incremental rhythm): `room/name|desc|public` → `RoomEditAction`; `room/dig <dir>=<name>
  [like=<room>] [size=<tier>]` → `DigRoomAction`; `room/size <tier>` → `ResizeRoomAction`;
  `room/drop confirm` → `RemoveRoomAction`; `room/addexit <room>=<there>,<back>` /
  `room/removeexit <exit>` / `room/renameexit <exit>=<name>` → the exit actions;
  `room/home` → `SetPrimaryHomeAction` (tenant-gated); `room/tenant <char>` /
  `room/evict <char>` → tenancy actions; `room/extend <units>` → `StartExtensionAction`;
  `room/decorate <template> [here]` → `CommissionDecorationAction`; `room/style <name>` →
  `SetBuildingStyleAction` (#1469, knowledge-gated throwback tier); `room/fixture <kind>` /
  `room/removefixture <kind>` → the #1514 comfort-fixture actions; `room/map [floor]` —
  read-only ASCII floor map (`world.buildings.map_render`). Permissions by relationship
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
- **`setstage.py`**: `CmdSetStage` (`setstage`, staff `perm(Admin)`, #1498) — telnet face of
  `SetTheStageAction` (key `set_the_stage`, REGISTRY backend). A staff caller instantiates a
  `PositionBlueprint` into their current room: `setstage` shows this room's positions + default
  blueprint, `setstage list` lists all blueprints by pk, `setstage <name|id>` instantiates one,
  `setstage <name|id> replace` replaces the room's existing position grid. Thin `ArxCommand` over
  `action.run()` (same seam as the web quick-action `_set_the_stage_actions`); staff-gated by
  `StaffOnlyPrerequisite`. No business logic in the command.
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
  one-word key collisions.
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
- **`account_info.py`**: `CmdAccount` — account information display
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
  `achievements.CharacterTitle`; cosmetic, mirrors the web Titles tab). Each is thin over its
  app's data. Add a section: a renderer + a registry entry (+ `SECTION_NAMES`). *Web tabs for
  standing/covenant are a follow-up — the "which contextual center owns this" call is open (#1446).*

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

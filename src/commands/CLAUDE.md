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
  - `ritual draft <name> invite=<char>[,<char>]` — draft a session
  - `ritual join <id>` — accept your invitation
  - `ritual decline <id>` — decline your invitation
  - `ritual fire <id>` — fire the session (initiator only)

  Session subcommands call `draft_session` / `accept_session` / `decline_session` / `fire_session` directly.
- **`weave.py`**: `CmdWeaveThread` (`weave`) — telnet face of `WeaveThreadAction`;
  parses `weave resonance=<name> trait=<name or id> [name=<...>]` (TRAIT anchor only — the
  reference grammar; other anchor kinds are extended by the thread-weaving journey
  issue). Proves the direct-viewset→Action telnet pattern (#1337)
- **`imbue.py`**: `CmdImbue` (`imbue`) — finisher for the Rite of Imbuing CEREMONY;
  parses `imbue thread=<name|id> amount=<n>`. Requires an active `PendingRitualEffect`
  for Rite of Imbuing; calls `spend_resonance_for_imbuing` to advance thread level.
- **`combat.py`**: Two commands sharing a `_CombatCommandMixin` (provides
  `_combat_participant_or_none` and `_find_technique_id`). Both subclass `DispatchCommand`
  — business logic lives entirely in the dispatcher and service layer, never in the command.
  - `CmdDeclareTechnique` (`cast`, alias `declare`) — unified scene-adaptive
    technique cast (#1351/#1330); thin `DispatchCommand` that parses
    `cast <technique> [at <name>] [effort=<level>] [secondary]
    [pull=<thread>[,…] resonance=<name> [tier=<1-3>]]`
    and emits a SCENE_ADAPTIVE `ActionRef` keyed to `"cast_technique"`. Outside combat:
    runs `CastTechniqueAction.execute()` immediately (non-combat cast via
    `request_technique_cast`). In a DECLARING round: calls
    `CastTechniqueAction.round_declaration()` which builds a `CombatRoundAction`
    declaration row.

    **Thread-pull params** (`pull=` / `resonance=` / `tier=`) are parsed by the shared
    `_CombatCommandMixin` pull parser. The pull rides the `cast` or `clash` declaration —
    there is no standalone `pull` verb. In combat, one pull is allowed per round (a second
    attempt surfaces `PULL_ALREADY_COMMITTED`). `pull=` lists comma-separated thread names
    or ids; `resonance=` names the resonance to spend from; `tier=` is 1, 2, or 3
    (default 1). Effects that don't apply to the current context are silently applied as
    far as they fit; the declaration is refused without charge only if none apply
    (inert-effect rule).

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
    [pull=<thread>[,…] resonance=<name> [tier=<1-3>]]`,
    resolves the `Clash` by NPC opponent name
    (`Clash.objects.filter(npc_opponent__name__iexact=...)`),
    and emits a COMBAT `ActionRef` with `clash_id=clash.pk` +
    `clash_action_slot=FOCUSED`. The dispatcher routes to `_dispatch_clash_contribution`
    which calls `declare_clash_contribution` (writes a `ClashContributionDeclaration`
    consumed by `_resolve_clashes` in the round post-pass). `strain=<n>` commits
    extra anima beyond the technique's base cost (default 0). Pull params are parsed by
    the shared `_CombatCommandMixin` pull parser (same semantics as `cast`).
- **`combat_maneuvers.py`**: `CmdCombat` (`combat`, #1453/#1452) — the shared-verb
  namespace. One command routes a leading subverb (`combat flee` / `cover <ally>` /
  `interpose [ally]` / `join` / `leave` / `ready` / `combo <name>` / `revert` / `yield`)
  to a REGISTRY `ActionRef` and dispatches through `dispatch_player_action` — the same
  seam the web `CombatEncounterViewSet` uses. Bare `combat` prints a status hub (mirrors
  `CmdSheet`). Verbs are namespaced — not bare top-level keys — to avoid exit/channel/alias
  collisions (mirrors `CmdRitual`'s `ritual <subverb>` routing). Each verb wraps an existing
  combat service via its Action in `actions/definitions/combat_maneuvers.py`; `yield` reuses
  the existing `YieldAction`.
- **`endorse.py`**: `CmdPoses` (`poses`) and `CmdEndorse` (`endorse`) — telnet faces of
  `PoseEndorseAction`, `SceneEntryEndorseAction`, `StylePresentationEndorseAction`.
  `poses <char>` lists endorseable poses in the current scene.
  `endorse pose/entry/style <char> resonance=<name> [confirm]` dispatches to the
  appropriate action. Both derive the active scene from the caller's room via
  `_get_active_scene` (#1340).
- **`fashion.py`**: `CmdJudgePresentation` (`judge`) — telnet face of
  `JudgePresentationAction`; parses `judge <presentation_id>` (#1340).
- **`gemit.py`**: `CmdGemit` (`gemit`, staff-only `perm(Admin)`, #1450) — the *push* face of the
  public-reaction center. Thin over `world.narrative.services.broadcast_gemit` (the same service the
  web gemit endpoint calls). Broadcasts a **hand-authored, verbatim** message (colour codes and all)
  to a *reach*: `gemit <msg>` (game-wide), `gemit/society <a>,<b> = <msg>`, or `gemit/org <a>,<b> =
  <msg>` (members of those societies/orgs, by active persona). No body is ever generated. Player/
  covenant-targeted story emits are a separate, non-public tool — not this command.
- **`locations.py`**: `CmdManageRoom` (`manageroom`, #1470) — owner-gated room editor.
  Thin over `RoomEditAction` (key `edit_room`): `manageroom/name <name>`,
  `manageroom/desc <text>`, `manageroom/public <yes|no>`. Edits the room the caller
  is standing in; ownership is gated by `IsRoomOwnerPrerequisite`, writes live in
  `world.locations.services.set_room_display_data`. No business logic in the command.
- **`where.py`**: `CmdWhere` (`where`, #1463) — the public presence/navigation surface.
  Thin read over `world.areas.services.where_listing`: characters in **public** rooms,
  each with their coloured area-hierarchy path (`colored_area_path` walks `AreaClosure`,
  colouring each segment by `Area.color` with cascade-down inheritance). Private rooms /
  private RP never appear (the #1287 invariant). Colours are author-set flavour (PLACEHOLDER).
- **`who.py`**: `CmdWho` (`who`, #1463) — the online roster. Thin read over
  `world.scenes.presence.who_listing`: online characters by **active** persona with a **coarse**
  idle marker (active / idle / away — never exact, so identical idle times can't out an account's
  alts). The web game-view "Who" tab + the `/api/areas/presence/` endpoint share the same service.
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
  and which you're *engaged* in, from `CharacterCovenantRole`; read-only). Each is thin over its
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

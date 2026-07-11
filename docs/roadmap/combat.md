# Combat — Status

**Status:** core party and duel combat ship end-to-end; the frontier is the authored effect palette,
embodied combat (companions, mounts, war), and *proving* the WIRED-UNPROVEN paths — not the round engine.

This is the combat **status map**. Per-capability tiers, the MVP bar, and sequencing live in the
[`player-capability-ledger.md`](player-capability-ledger.md) (the spine — read it first). The
scope-by-scope build record is archived in [`combat-build-history.md`](combat-build-history.md). When
this doc, the ledger, and the code disagree, the **code wins**, then the ledger.

## MVP bar (the no-improv tenet)

Anything a player should plausibly do in a fight — or any event that can happen (a war) — must have a
real system; never a GM winging it. A combat capability is "done" only when an **E2E asserts the
outcome** (a closed issue or a "SHIPPED" line is not proof). See the ledger's governing tenets.

## What's PROVEN (trust these)

- Damage technique cast at an NPC drops its health (telnet → resolve_round).
- DEFEND halves / INTERPOSE zeroes incoming damage.
- SUCCOR shelters a named ally from a round-ticked environmental hazard, in both combat and
  non-combat scene rounds (#1744, ADR-0069) — the environmental-DoT sibling of INTERPOSE.
- Escalation → Audere offer → accept → real power change.
- Dramatic surge (ally mortal peril / hated foe / high stakes) → provable intensity spike →
  stronger next cast; visible in the web combat panel and telnet room log (#2013).
- Multi-PC group combos (effect-type × resonance).
- **On-use items as a round action (#2023/#2120).** `combat use <item> [on <target>]`
  (telnet) and `POST /api/combat/{pk}/use_item/` (web) both declare a USE_ITEM
  `CombatRoundAction` through the shared `combat_use` REGISTRY action; round resolution
  dispatches the real `UseItemAction` with the declared target threaded through (a healing
  potion declared on an ally provably lands on the ally, not the user — the #2120
  target-forwarding fix) and decrements the item charge (journey tests in
  `world/combat/tests/test_combat_maneuvers_e2e.py` + `test_use_item_maneuver.py`).
- **Ready-mode early resolution (#2120).** In `PaceMode.READY`, the round resolves the
  moment every ACTIVE participant is ready (`maybe_resolve_on_ready`, wired into
  `combat ready` / the web `ready` endpoint via `ReadyAction`); a lone ready participant
  provably does not trigger it (`world/combat/tests/test_pace_mode_ready.py`). TIMED keeps
  the game-clock sweep; MANUAL keeps GM-only resolution.
- **Tactical placement, end-to-end (#2005).** Voluntary `take_position` (entry onto the
  position graph), GM `gm_place_in_position` (unchecked staging teleport), and positioned
  opponent spawn (`add_opponent(..., position=...)`) close the last placement gaps —
  ADJACENT-reach technique gating now binds against a real, populated position graph rather
  than defaulting everyone to the same spot (journey test in `world/combat/tests/
  test_declare_reach_gate.py`). Full telnet parity: `position` / `position <name>`
  (`CmdPosition`) lists/takes/moves the same way the web position panel does.

## WIRED-UNPROVEN (treat as not-done — write the journey test, fix what it exposes)

- Enemy-NPC condition application · thread-pull final outcome. (Combo full journey proven in #2017.)

## The combat gaps that define MVP (see the ledger's DO pillar)

- **Effect palette** — summon, reflect, incorporeal, sink, telekinesis, teleport, obstacle, force-field.
- **Charm / switch-sides** an enemy NPC; **negotiate / parley** an NPC down (built in this PR,
  #1590/#1591, ADR-0058); **dispel** a condition.
- **Companions / pets / summons** with breath weapons & ordered abilities.
- **Roles grant techniques** via the one specialization engine (ADR-0055; reverses bonuses-only).
- **War / battle system** — spine landed (#1592): `Battle` (1:1 Scene extension),
  abstract unit attrition + VP accumulation, `BattleRoundContext` seam, GM + player REGISTRY
  actions, `CmdBattle` telnet namespace, E2E `test_battle_telnet_e2e.py`. Peril/rescue +
  AFK override shipped (#1733). Resources/units/terrain/tactics + type-matchups shipped
  (#1711). Command hierarchy + the Champion shipped (#1710). Campaign-stakes propagation
  + win-gated Legend shipped (#1785). Battle-flow actions (rout/rally/repel/hold, second
  BattleUnit.morale resource, BattlePlace.controlled_by objective) shipped (#1712). Siege
  warfare: Fortification objectives + BREACH/FORTIFY + persistent
  Building.fortification_level investment (#1713). Naval-ship vertical slice shipped
  (#1714): `BattleVehicle` (unit+place pair), REPOSITION declaration gated on vehicle
  commander, overlap-gated cross-vehicle targeting (`places_overlap` — the boarding
  gate), hull-breach/living-mount-defeat ejection + drowning/falling hazard. The
  persistent half shipped (#1832, ADR-0086): `ShipDetails` (a per-kind `Building`
  extension — hull IS `fortification_level`) with commission/upgrade/repair Projects
  and ship-as-sanctum bonuses, `materialize_ship_as_battle_vehicle` snapshotting into
  #1714's `BattleVehicle` for one `Battle`, and a battle-conclusion hook
  (`apply_ship_battle_outcome`) writing `needs_repair` back onto the persistent ship
  when its hull is breached — see [ships.md](../systems/ships.md). Airship/
  dragon/kraken remain data variants (`VehicleKind`) pending their own end-to-end
  pass — no dedicated content or persistent-ship equivalent yet. REPOSITION's
  movement resolution and telnet subcommand both shipped with #2007 (the
  resolution logic had actually been built since #1714 — only the
  Action-layer/telnet wiring was missing).
  Live strategic battle map shipped (#2009): read-only REST aggregate
  (`GET /api/battles/`, `GET /api/battles/<pk>/`, scene-visibility-gated) + a
  slim `BATTLE_STATE` WS ping (`{battle_id, round_number}`, sent post-commit
  on round transitions/conclusion) driving a React Flow map page at
  `/scenes/:id/battle` — see [battles.md](../systems/battles.md#web-surface-2009).
  Deferred: a post-conclusion battle writeup page (#1735), which should reuse
  `BattleDetailSerializer`'s aggregate shape rather than authoring a second one.
  GM battle staging shipped (#2010, ADR-0111): the setup layer had **no** mutation
  path at all before this (a Battle could only exist via admin/tests/factories). A
  JUNIOR-trust GM now stands one up from an admin-authored catalog —
  `BattleMapBlueprint`/`BlueprintBattlePlace`/`BlueprintFortification` and
  `BattleUnitTemplate`/`BattleUnitTemplateCapability` — via `create_battle` /
  `stage_battle_map` / `spawn_battle_units` / `enlist_battle_participant` /
  `browse_battle_catalog` (`world.battles.staging`), the `battle create/stage/spawn/
  enlist/maps/units` telnet subverbs, a read-only catalog REST API
  (`world.gm.permissions.HasGMTrust`, new JUNIOR-tier DRF permission class), and a
  minimal `StagingPanel` on the `/scenes/:id/battle` map page. A starter catalog (2
  blueprints, 3 unit templates) ships via the "battles" seed cluster — see
  [battles.md](../systems/battles.md#staging-2010).
  Battle movement shipped (#2007): `BattleActionKind.MOVE` — self-move,
  commander-ordered unit move (reuses #1710's command-tier gate), and withdrawal —
  moves a `BattleParticipant`/`BattleUnit` between existing fronts via multi-round,
  MOVEMENT-capability-bounded transit; `BattlePlace.movement_cost` consumed for the
  first time as check-difficulty. `WITHDRAWN` (`BattleParticipantStatus`) wired for
  the first time. Web click-to-move on the #2009 strategic map deferred — not yet
  scoped.
- Mounts / charging / flying (P2, no-improv-flagged). Ranged / archery enforcement shipped (#2011): REACH_N multi-hop reach, offensive-only elevation bonus, attack-cover via PositionShelter.applies_to_attacks.

## Reserved term: "clash"

"Clash" is reserved for the shipped opposed-magic contest (two combatants pouring anima to overpower
each other). Do **not** reuse the word for any other concept (models, vars, docs). For
opposing-affinity / environmental rejection use "backfire" / "rejection" / "dissonance".

## Design principles (condensed; ADRs hold the why)

- Players vs. the Bad Guys — **no PvP killing** (ADR-0023); asymmetrical PvE, NPCs have no sheets (ADR-0038).
- One round framework, three modes (ADR-0002); one focused + up to two secondary actions (ADR-0003);
  tempo is action-driven, AFK-safe (ADR-0004).
- **Enforced** impossible to solo — combos and covenant roles are fundamental; built for heroic team-up
  arcs that climax in Audere Majora. Enforced by the boss break bar (#2016, ADR-0102): a secondary
  health pool damaged only by team play (combos + distinct-PC distinct-effect-type hits).
  The combo invariant (#2051, ADR-0107) hard-blocks <2-slot combos at save time and runtime;
  BOSS-tier opponents with legend-paying aftermath require an authored `wall_breaker_combo` FK.
  **Vows as combat roles** (#2022, ADR-0108): a character's engaged `CovenantRole` drives three
  pillars of combat power — (1) **stat power** scaling with the COVENANT_ROLE thread level
  (`VowStatScaling`), (2) **equipment effectiveness** scaling (`VowGearScaling`), and (3)
  **specialized techniques** granted by the role that resolve variants by the vow's depth
  (`CharacterTechnique.role_source`). When the vow dims (#2051), all three pillars collapse —
  which is why soloing legend content is lethal.
- Magic is predominant; relationship bonuses matter; **difficulty scales on party size + average level
  only** (ADR-0037); combat merits Legend, never XP (ADR-0036).

## Deeper detail & history

- Capability tiers + MVP slate: [`player-capability-ledger.md`](player-capability-ledger.md)
- Build history (the old combat.md): [`combat-build-history.md`](combat-build-history.md)
- Decisions: [`../adr/README.md`](../adr/README.md) (esp. 0002–0004, 0023, 0036–0040, 0046, 0055, 0057)

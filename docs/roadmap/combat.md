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
  pass — no dedicated content, telnet reposition subcommand, reposition-movement
  resolution, or persistent-ship equivalent yet.
  Live strategic battle map shipped (#2009): read-only REST aggregate
  (`GET /api/battles/`, `GET /api/battles/<pk>/`, scene-visibility-gated) + a
  slim `BATTLE_STATE` WS ping (`{battle_id, round_number}`, sent post-commit
  on round transitions/conclusion) driving a React Flow map page at
  `/scenes/:id/battle` — see [battles.md](../systems/battles.md#web-surface-2009).
  Deferred: a post-conclusion battle writeup page (#1735), which should reuse
  `BattleDetailSerializer`'s aggregate shape rather than authoring a second one.
- Mounts / charging / flying (P2, no-improv-flagged); ranged / archery enforcement.

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

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
- Multi-PC group combos (effect-type × resonance).

## WIRED-UNPROVEN (treat as not-done — write the journey test, fix what it exposes)

- Enemy-NPC condition application · combo full journey · thread-pull final outcome.

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
  Building.fortification_level investment (#1713).
  Deferred: naval/aerial (#1714), battle writeup page (#1735).
- Mounts / charging / flying (P2, no-improv-flagged); ranged / archery enforcement.

## Reserved term: "clash"

"Clash" is reserved for the shipped opposed-magic contest (two combatants pouring anima to overpower
each other). Do **not** reuse the word for any other concept (models, vars, docs). For
opposing-affinity / environmental rejection use "backfire" / "rejection" / "dissonance".

## Design principles (condensed; ADRs hold the why)

- Players vs. the Bad Guys — **no PvP killing** (ADR-0023); asymmetrical PvE, NPCs have no sheets (ADR-0038).
- One round framework, three modes (ADR-0002); one focused + up to two secondary actions (ADR-0003);
  tempo is action-driven, AFK-safe (ADR-0004).
- Intentionally impossible to solo — combos and covenant roles are fundamental; built for heroic team-up
  arcs that climax in Audere Majora.
- Magic is predominant; relationship bonuses matter; **difficulty scales on party size + average level
  only** (ADR-0037); combat merits Legend, never XP (ADR-0036).

## Deeper detail & history

- Capability tiers + MVP slate: [`player-capability-ledger.md`](player-capability-ledger.md)
- Build history (the old combat.md): [`combat-build-history.md`](combat-build-history.md)
- Decisions: [`../adr/README.md`](../adr/README.md) (esp. 0002–0004, 0023, 0036–0040, 0046, 0055, 0057)

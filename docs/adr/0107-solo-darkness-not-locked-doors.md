# ADR-0107: Solo darkness, not locked doors

## Status

Accepted — 2026-07-09

## Context

Issue #2051: legend content must be extremely difficult for a solo player by
design — without threads or assistance you almost certainly fail. The question
was how to enforce this: hard party-size gates, difficulty inflation, or
structural darkness.

## Decision

Legend content is **warned-lethal solo**. The system enforces this through
four structural guards and warning surfaces, never by locking the door:

1. **Combos are never solo** — a code invariant. `ComboDefinition` requires
   ≥2 slots (`COMBO_MIN_SLOTS`), each filled by a distinct PC-controlled action.
   Enforced at three layers: admin inline `min_num`, model `clean()`, and a
   runtime belt in `detect_available_combos`. Companions materialize as
   `CombatOpponent` and structurally cannot produce `CombatRoundAction`.

2. **Vow power is continuously co-presence-enforced.** When a covenant-mate
   leaves the room or a scene ends, `revalidate_engagements` re-runs
   `can_engage_membership` and dims the vow (capabilities, thread pulls, soak,
   max health, the covenant level buff). The **Court exception** is intact —
   a servant on the master's business keeps their vow lit anywhere.

3. **Legend payouts require the risk floor.** A `MissionOptionRouteReward`
   with `sink=LEGEND_POINTS` or a `MissionRenownAward` with legend-paying risk
   requires the parent template's `risk_tier ≥ LEGEND_RISK_FLOOR_TIER` (4 = HIGH).
   Hard-blocked at save time; a one-time legacy audit lists existing violations.

4. **Boss encounters require a wall-breaker combo.** A BOSS-tier
   `CombatOpponent` with a legend-paying `aftermath_pool` requires a
   `wall_breaker_combo` FK pointing at a ≥2-slot `ComboDefinition`. HERO_KILLER
   is unbeatable by design and not combo-gated.

5. **Solo warning surfaces.** A solo character accepting a legend-risk mission
   or entering a BOSS/HERO_KILLER encounter is told, in-world and
   unmistakably: "You are alone. Your threads are quiet. This will very likely
   kill you."

## Rejected

- **Hard party-size gates on attempts.** Solo attempts are always possible;
  the system's job is honest lethality, not a locked door.
- **Numeric stat inflation** as the solo deterrent. ADR-0037 already sanctions
  party-size + average-level as the encounter-scaling axes; this mechanism is
  orthogonal — power darkness, not difficulty math.
- **NPC allies as assistance.** Companions never satisfy multi-PC requirements
  or bypass soak. A pet-class solo run against a boss bounces off the soak wall
  exactly as a bare solo run does.

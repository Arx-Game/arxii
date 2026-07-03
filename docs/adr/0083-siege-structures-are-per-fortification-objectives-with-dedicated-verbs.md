# Siege structures are per-Fortification objectives; BREACH/FORTIFY are dedicated verbs

A `BattlePlace` may have multiple `Fortification` rows (#1713) — a front can carry an
outer wall, a gate, and a battlement, each independently breachable via its own
`integrity`/`max_integrity`. This resolves ADR-0082's explicitly flagged
reconsideration point ("if a future issue needs multiple independently-capturable
objectives within one front, that's the point to reconsider") in favor of
per-structure state, driven by the issue's own plural framing ("walls, gates,
battlements" as distinct objectives; "fortify a gate, man the battlements, undermine
a wall" as distinct verbs against distinct targets). Rejected: a single shared
integrity value on `BattlePlace` itself, mirroring `BattleUnit.strength`. That would
have forced every siege front to collapse to one all-or-nothing defensive value,
losing the "grind down the gate before the wall" escalation the feature is built
around.

`BREACH`/`FORTIFY` are new `BattleActionKind` values, not a reuse of STRIKE/REPEL.
Rejected: reusing REPEL as "fortify" — REPEL's `place_defense_bonus` is an explicit
same-round-only defense bonus (cleared every round), not a persistent restore, so it
cannot double as a structure-repair verb without changing REPEL's existing, already-
shipped (#1712) semantics. Also rejected: widening STRIKE's `target_unit` to accept a
`Fortification`, which would touch STRIKE's own-side-exclusion and modifier-stack code
paths #1712 had only just finished, coupling two independently-evolving verbs. A
dedicated pair mirrors the established precedent of ROUT/RALLY (morale axis) and
REPEL/HOLD (front-control axis) each getting their own pair for a new resource axis.

> Status: accepted · Source: #1713 Decisions 1-2 · Related: ADR-0081 (BattlePlace as
> the existing home for battle-scale front/terrain data), ADR-0082 (the flagged
> reconsideration point this ADR resolves)

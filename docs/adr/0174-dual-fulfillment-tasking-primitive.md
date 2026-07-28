# ADR-0174: Dual-fulfillment tasking — NPC jobs are one abstract check, never a walked mission graph

## Status

Accepted (issue #2820, phase 1)

## Context

Spy networks (#2820) need org-issued jobs an NPC agent performs offscreen — and the
same "an NPC does it OR a player does it" shape recurs for tax collection, crime
jobs, military actions, and magical research. Two candidate architectures: give
agents an offscreen walker over the existing `MissionTemplate` graph (one content
pipeline, but NPCs simulating node-by-node traversal), or a separate simple
primitive per system (no simulation, but a parallel authoring system per domain —
the Arx 1 sustainability sin).

## Decision

One shared `world/tasking` primitive; **missions stay PC-only**. NPC fulfillment is
a single abstract check with outcome-tier routes: the handler's dispatch check at
assignment banks a margin (`DISPATCH_MARGIN_STEP` per success level), the agent's
own `perform_check` at deadline resolves the job (promoted `NPCAsset`s have real
sheets — ADR-0091 — so no new resolution machinery). PC fulfillment (phase 5) runs
the template's nullable `mission_template` and grades its outcome tier into the
**same** `TaskOutcomeRoute` table — one authored payout surface, two execution
engines. Asset risk flows only through the template's consequence pool (ADR-0092),
scoped to the dispatched agent via `ResolutionContext.npc_asset`. Standing posts
(listeners, guards) are `NPCAssignment` rows, never tasks: tasks always end.

## Rejected

- **Offscreen mission-graph walker** — project owner ruling: "I really don't want
  us to simulate an NPC walking down the entire mission graph… they are
  abstracted." Simulationist NPC traversal adds authoring burden (default routes
  per branch) for no player-visible payoff.
- **Per-system operation primitives** (spy ops, tax ops, war ops as separate
  models) — forks the content pipeline per domain; the recurring dual-fulfillment
  need is exactly one primitive.
- **Extending `Projects`** — Projects are collective progress-bars with PC
  contributors; assignment + tiered-outcome semantics would muddy both.

# Tasking glossary

Domain-local vocabulary for `world/tasking`. Cross-cutting terms live in the
root `AGENT_GLOSSARY_MAP.md`.

- **Task (org task)** — a discrete, deadline-bearing job an organization issues
  against an authored template. Always terminal (COMPLETED/FAILED/EXPIRED).
  _Avoid_: "mission" (a PC-run branching graph in `world/missions`), "job",
  "operation", "assignment" (see Posting). NOT a game-clock cron task — those
  are `CronDefinition`s in `game_clock`.
- **Task template** — the authored definition a task instantiates: check,
  difficulty, duration, target shape, payout routes, risk pool.
- **Dispatch check** — the handler's roll at assignment time; models briefing
  quality. Its success level becomes the **handler margin**
  (`DISPATCH_MARGIN_STEP` points per level) applied to the resolution check.
- **Resolution check** — the agent's own offscreen roll at deadline; the
  tradecraft. Its outcome tier selects the payout route and grades the risk
  pool.
- **Handler** — the persona running the job: rolls dispatch, physically
  collects, receives payouts. May differ from the task's issuer (cutout play).
- **Agent** — the dispatched `assets.NPCAsset`. Only promoted assets are
  dispatchable (they have real sheets); raw functionaries are not.
  _Avoid_: "asset" alone when the dispatched-on-a-task sense is meant.
- **Outcome route** — a per-outcome-tier payout row on a template. No route for
  a tier = nothing happens (fail closed).
- **Risk pool** — the template's `actions.ConsequencePool`; the ONLY path by
  which tasking compromises or loses an agent (ADR-0092), scoped to the
  dispatched asset via `ResolutionContext.npc_asset`.
- **Posting** — a standing "stay here until recalled" placement; an
  `npc_services.NPCAssignment`, deliberately NOT a task. Tasks end; postings
  persist.
- **Report** — the prose the handler reads once a task resolves; authored per
  route via `report_template` format kwargs `{task}`/`{target}`/`{agent}`.

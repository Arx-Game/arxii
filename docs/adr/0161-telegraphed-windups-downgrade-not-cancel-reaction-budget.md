# Telegraphed wind-ups downgrade, never mid-round-interrupt; a 1-reaction budget plus a 2-answer absorption cap

#2637 (telegraphed enemy wind-ups) and #2639 (reaction economy) are specced and built
together — one PR, two related mechanics that share a fire seam. This is the batch-3
lore-transcript sizing (rulings F-6c/e, F-9a, F-10b/c) landing in code, extending
ADR-0118's declared-reaction shape into a multi-round, telegraphed enemy attack and
capping how many reactions can answer one moment.

## Decision

**Wind-ups are pre-armed, not mid-round interrupts.** A `ThreatPoolEntry.windup_rounds
> 0` entry commits to a `PendingOpponentAttack` at declaration — the SAME pre-armed-
policy shape ADR-0118 established for guardian reactions (a `CombatRoundAction` armed
during DECLARING, fired during RESOLVING) — rather than a new mid-round check inserted
into the resolution loop. It matures `windup_rounds` rounds later through the ordinary
`CombatOpponentAction` pipeline, synthesized fresh at maturation so `resolve_npc_attack`
and the flat-damage path need no new branch, only a `damage_scale` multiplier.

**Wreck downgrades; only the perfect chain cancels.** A landing PC hit on a winding-up
opponent adds `+1` downgrade (`+2` if the wind-up was called out — called-out beats
blind, F-6c). `downgrades >= 3` fully cancels the attack; anything below that scales its
damage down (`x(1 - 0.25*downgrades)`, floored at `x0.25`). A single lucky hit never
robs the wind-up of its threat outright — the payoff for "we saw it coming and hit it"
is proportional, and full cancellation is earned by a coordinated multi-hit chain, not a
single roll.

**The reaction budget and the absorption cap are two distinct numbers, sharing one fire
seam (F-10c).** `REACTIONS_PER_ROUND = 1` — how many reactions ONE participant may
spend this round (`CombatParticipant.reactions_used`, reset every
`begin_declaration_phase`). `ABSORPTION_CAP_PER_MOMENT = 2` — how many interceptors may
answer ONE landing hit (`DamagePreApplyPayload.answers_consumed`), regardless of who
fired them. Both gate + increment at `_dispatch_interpose_action`, the shared tail both
`_try_interpose` (PC ward) and `_try_interpose_for_opponent` (ALLY-summon ward) call —
one seam, two counters, so a future third reaction type inherits both budgets for free.
A declined reaction returns the SAME "did not fire" no-op shape an unaffordable or
failed reaction already uses — no new UI state, no new error path.

**Standing defenses stay outside both budgets.** Absorb/reflect/blink are conditions
with their own `reactive_anima_cost` (ADR-0060) — they are not gated by
`REACTIONS_PER_ROUND` or counted against `ABSORPTION_CAP_PER_MOMENT`. Folding them in
would require threading the cap into flow-triggered `CALL_SERVICE_FUNCTION` handlers in
a different module (`world.magic.services.effect_handlers`) for a mechanic (`declare
_interpose`'s round-scoped budget) that standing conditions don't share the lifecycle
of. Flagged judgment call — worth revisiting if a future situation lets a standing
condition and a declared reaction meaningfully compete for the same hit.

**No new dive/brace verb.** The existing defense check on maturation (whatever
`ThreatPoolEntry.defense_check_type` the entry authors, or flat damage if none) IS the
universal blind floor — a PC with no interposer and no downgrades still rolls to defend
exactly as they do against any other NPC attack today. Riding rule: no new buttons.

**The `select_npc_actions` wiring gap.** Investigated in-PR: it had zero production
callers outside the simulation harness (`world/combat/simulation.py`) — no Action,
command, or task called it before `resolve_round` in live play, so NPCs genuinely never
acted in production combat. `resolve_round` now auto-selects (while status is still
DECLARING) when the round has no NPC selection of either shape yet (no
`CombatOpponentAction` AND no `PendingOpponentAttack` declared this round) — a
conservative, idempotent fallback that leaves any explicit prior selection (staff,
simulation, tests) alone.

## Rejected alternatives

- **A new mid-round "wind-up resolves now" interrupt inserted into `_resolve_actions`**
  — rejected: ADR-0118 already established the pre-armed-declaration shape for
  reactions; a wind-up is symmetric (an NPC's own pre-armed commitment) and reuses the
  identical `resolve_round` orchestration seam (`_mature_pending_opponent_attacks` runs
  once, before the round's normal `CombatOpponentAction` query) instead of a parallel
  interrupt mechanism.
- **Full cancellation on any successful hit** — rejected (F-6c): would make wind-ups
  trivially neutralizable by a single lucky PC and remove the "commit resources to
  actually break this" tension the downgrade ladder is built for.
- **One shared reaction/absorption counter** — rejected: conflates "how much can ONE
  guardian do" with "how much can THIS moment absorb," which are different questions —
  a single counter would either let one guardian answer every hit of the round (if
  scoped per-participant only) or block a second guardian from ever helping on a
  different hit (if scoped per-round only).
- **Folding standing defenses into the absorption cap** — rejected for v1 scope: those
  conditions already self-limit via their own anima cost and are architecturally
  distant (flow-triggered, different module); folding them in is a larger, separable
  change flagged for a future pass rather than smuggled into this PR.
- **A dedicated dive/brace verb for the blind floor** — rejected: the existing defense
  check already IS that floor; a new verb would be a second button doing the same job
  the round's normal defense roll already does.

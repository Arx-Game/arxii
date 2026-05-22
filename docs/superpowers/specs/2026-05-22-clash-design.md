# Clash — Design Spec

**Date:** 2026-05-22
**Status:** Draft — pending spec review and user approval
**Branch:** `clash-design`
**Owner:** core combat + magic substrate (shared — Tehom)

## Overview

A **Clash** is a multi-round contested struggle inside a combat encounter: one or
more PCs pour effort into overpowering — or enduring — a magical or physical force,
round after round, while the opposition pushes back. It is the "beam-struggle"
trope generalised: locked blades, a wave of force against a wave of force, holding
a monster pinned while it thrashes, shielding the party from a sustained barrage,
grinding through a fortress-wall of magic.

"Clash" is the reserved term for exactly this mechanic (see
`docs/roadmap/combat.md` → "Reserved terminology: 'clash'"). This spec is the
design pass that entry has been waiting for.

### How this spec came about

It emerged from a 2026-05-21/22 brainstorm on "what's left to make magic real."
Three families of missing magic-in-combat capability surfaced — Clash, per-character
state effects, and Challenges-in-combat — plus a foundational positioning/zones
concern. Clash was chosen as the first spec because it is the highest-confidence
"we want this" feature and it is **positioning-independent** (it can ship before the
zones model is settled). The positioning work is captured separately in
`docs/plans/2026-05-21-positioning-zones-design-notes.md`.

### Design pillars

- **PvE-asymmetric.** Combat is PCs vs. autonomous NPCs. There is no double opt-in:
  the system surfaces a clash opportunity, PCs choose to commit, and the NPC side is
  driven entirely by authored threat patterns. GMs do not pilot NPCs.
- **Strain is the lever; effort is the fantasy.** A clash is won by pouring in
  anima past the safety margin — gritting your teeth and pushing. The escalation
  cost is Soulfray and, ultimately, the Audere offer. This is the heroic-tragic arc
  the magic system is built around.
- **Rides existing machinery.** Every per-round clash contribution is a real
  technique cast through `use_technique`. Anima cost, overburn → Soulfray, mishap
  riders, reactive events, corruption — all fire for free. The clash layer adds
  only the progress meter, multi-PC aggregation, and threshold resolution.
- **Authored, data-driven outcomes.** Clash outcomes resolve through consequence
  pools, like everything else in magic. No per-clash service functions; the
  triggering authored content carries the pools.

## Scope

**In scope:**

- The `Clash` primitive and per-round contribution flow
- All five flavors (the archetypal Clash + Suppress, Break Free, Ward, Break) —
  they share the meter primitive; design once
- The generalised **Strain** mechanism (anima-denominated "try harder"), designed
  general, built with Clash as its sole consumer
- Multi-PC commit via focused + passive action slots
- Per-flavor opportunity-surfacing rules
- Anima commit → check → `CheckOutcome` tier → progress delta, with overburn /
  Soulfray / Audere riding the existing `use_technique` pipeline
- Affinity-matrix integration (the RPS cycle as a contest tilt)
- Resolution consequence pools per flavor, plus the per-round incremental pool
- NPC threat-pattern integration (the NPC side of each flavor)
- `use_technique` clash-commit mode and `resolve_round` orchestration
- Combo integration — clash state as an authored combo prerequisite

**Out of scope (deferred):**

- Frontend / web UI for clash declaration and round-by-round visibility — backend
  first; UI is a follow-up
- Authored content for specific clash-capable techniques, sustained attacks,
  barriers, etc. — authoring work, not architecture
- Positioning / zones / spatial concerns —
  `docs/plans/2026-05-21-positioning-zones-design-notes.md`
- The reactive-layer `TECHNIQUE_PRE_CAST` block/modify capability — **not a Clash
  dependency** (see §10). It remains a separate deferred item.
- **Fury** — the deliberate control-lowering / rage lever (see §11)

## The five flavors

| Flavor | What it is | Side |
|---|---|---|
| **Clash** (archetype) | Two attacks/forces meet head-on, each straining to overpower the other | offensive ↔ offensive |
| **Suppress** | PCs hold a lock condition on the NPC while it tries to break free | PC sustaining |
| **Break Free** | PCs push out of a lock the NPC has placed on them | PC escaping |
| **Ward** | PCs endure a sustained NPC attack across its duration | PC defending |
| **Break** | PCs grind through a magical barrier around the NPC | PC offensive vs. defense |

"Clash" names both the family (the model, the mechanic) and its purest form (two
forces head-on). The other four are named variations of it. This is not a
terminology collision — the family and its archetype are the same concept.

Suppress and Break Free are the **same meter mechanic** viewed from opposite sides
— whichever party placed the lock determines which threshold is the PCs' goal.

## §1 — Core primitive

### The `Clash` model (`world/combat`)

A clash only exists inside a `CombatEncounter`; the model lives in `world/combat`.
Magic supplies the cast machinery via `use_technique`.

Four meter shapes, one model, `flavor` as discriminator:

| `flavor` | Meter semantics | PC win | NPC win |
|---|---|---|---|
| `CLASH` | 0-centered, signed | reaches `+pc_win_threshold` | reaches `−npc_win_threshold` |
| `LOCK` | `0` (dissolved) → `MAX` (locked-in) | per `lock_pc_role` | per `lock_pc_role` |
| `WARD` | ward integrity, bidirectional | endures the duration | meter hits `0` (ward collapses) |
| `BREAK` | one-way accumulation toward barrier strength | reaches threshold | n/a — barrier persists if abandoned |

`LOCK` carries `lock_pc_role` (`SUSTAINING` = Suppress, `ESCAPING` = Break Free) —
the same meter, the field naming which threshold the PCs are driving toward.

**Key fields:** `encounter` FK, `flavor`, `lock_pc_role` (nullable — non-null iff
`flavor == LOCK`), `progress`, `pc_win_threshold`, `npc_win_threshold` (nullable),
`status` (`ACTIVE` / `RESOLVED`), `started_round`, `resolved_round` (nullable),
`resolution` (nullable enum — see §9), `resolution_consequence_pool` FK,
`per_round_consequence_pool` FK (nullable), `npc_opponent` FK to `CombatOpponent`
(the NPC side — contribution computed live from threat pattern + boss phase, never
snapshotted), `initiator` FK to `CharacterSheet` (nullable — narrative / audit).
`WARD` additionally tracks the sustained attack's end round.

Discriminator integrity is enforced with `clean()` + DB `CheckConstraint`s, in line
with the project's other discriminator models (`Thread`, `MagicalAlterationTemplate`).

### Model hierarchy

```
Clash
  └── ClashRound        (one per round: pc_progress_delta, npc_progress_delta, progress_after)
        └── ClashContribution   (one per PC per round)
```

`ClashContribution` fields: `clash_round` FK, `character` FK (`CharacterSheet`),
`action_slot` (`FOCUSED` / `PASSIVE`), `anima_committed`, `technique` FK (nullable),
`check_outcome` (the `CheckOutcome` tier), `progress_delta` (signed),
`was_overburn`, `was_audere`, `soulfray_severity_accrued`. A
`UniqueConstraint(clash_round, character)` enforces one contribution per PC per
round. This mirrors the `CombatPull` / `CombatPullResolvedEffect` audit pattern.

### Per-round flow (inside `resolve_round`)

1. **Declaration** — PCs declare clash contributions: a focused action ("commit to
   clash X with N anima") or a passive ("lend strength to clash X").
2. **Resolution** (in initiative order — see §10):
   - Each PC contribution runs through `use_technique` — anima deduction, overburn
     → Soulfray, mishap rider, reactive events, corruption all fire normally.
   - Each commit's check resolves to a `CheckOutcome` tier → a progress delta via
     the tier→delta table.
   - Sum PC deltas; compute the NPC delta from the threat pattern; apply the
     affinity tilt (§8).
   - Write `ClashRound` + `ClashContribution` rows; update `clash.progress`.
   - Fire `per_round_consequence_pool` if set (visible incremental feedback).
   - Threshold check → if crossed, resolve (fire `resolution_consequence_pool`, set
     `RESOLVED`).
3. Unresolved → the clash persists `ACTIVE` into the next round.

## §2 — Strain (generalised "pour in more anima to try harder")

**Strain** is the anima-denominated lever for exerting extra effort on a magical
action. Any magical action *can* carry a strain commitment; Clash is its first and,
for this spec, only consumer.

- Total anima drawn = the technique's computed `effective_cost` + the
  strain commitment. The computed cost becomes a *floor*; the caller chooses how
  much more to pour in.
- Excess over the character's pool → overburn → Soulfray severity, via the existing
  `calculate_soulfray_severity` path. No new risk machinery.
- The strain commitment converts to amplification — a **check modifier**. The
  conversion is governed by an authored `StrainConfig` singleton (sibling to
  `SoulfrayConfig` / `CorruptionConfig`), so the curve is staff-tunable. The design
  intent is **diminishing returns**: early anima converts efficiently, deep strain
  converts poorly, so "dump everything" is a real decision against the Soulfray
  risk rather than a foregone optimum.

Strain is the anima-denominated sibling of thread pulls (Spec A): thread pulls
spend *resonance* for authored thematic payoff and risk only opportunity cost;
strain spends *anima* — stability, then life force — for direct mechanical
amplification and risks Soulfray, mishap, and the Audere offer. Thread pulls draw
on *who you are*; strain is *raw effort and sacrifice*.

**Build scope:** Strain is designed as a general mechanism but built and tested
with Clash as the sole consumer — a clash's `ClashContribution` row *is* a strain
record (`anima_committed`, `was_overburn`, `soulfray_severity_accrued`). Wiring
strain into ordinary (non-clash) technique casts is a deferred follow-up; it needs
the regular-cast action UI and a non-clash strain audit record, which is broader
than Clash.

## §3 — Per-flavor specifics

### `CLASH` — offensive ↔ offensive

- **Meter:** 0-centered. PCs push toward `+pc_win_threshold`, NPC toward
  `−npc_win_threshold`.
- **NPC side:** the NPC is also pouring a big attack in; per-round contribution
  derives from the threat-pool entry's attack power + boss-phase modifiers, with a
  small variance roll. Automatic — no GM input.
- **Thresholds:** *derived* from the two attacks' relative power.
- **Resolution outcomes:** `PC_DECISIVE` (PC attack overwhelms; full damage lands,
  NPC attack canceled) · `PC_MARGINAL` (PC wins; NPC attack partially lands) ·
  `MUTUAL` (both detonate; both take damage) · `NPC_MARGINAL` · `NPC_DECISIVE` (NPC
  attack overwhelms; PC eats their own backlash *and* the NPC's full attack).

### `LOCK` — Suppress / Break Free

- **Meter:** `0` (dissolved) → `MAX` (locked-in). `lock_pc_role` names the PCs' goal:
  - `SUSTAINING` (Suppress): PCs applied the lock on the NPC; PCs push *up*, NPC
    pushes *down*.
  - `ESCAPING` (Break Free): NPC locked the PC(s); PCs push *down*, NPC pushes *up*.
- **NPC side:** Suppress — the NPC rolls an authored "break-free force" each round.
  Break Free — the NPC's lock has an authored "maintenance force" pushing the meter.
- **Thresholds:** *explicitly authored* — "lock strength `MAX`" has no natural
  pre-existing source. The one flavor needing a new authoring field.
- **Resolution:** lock secured vs. lock dissolved. Decisive vs. marginal — a
  decisive secure upgrades the lock to a nastier condition; a decisive dissolve
  shatters it cleanly (NPC staggered).
- A secured lock holds for its authored condition duration **without** further
  clashing — that secured-lock window is the striker's combo opportunity.

### `WARD` — enduring a sustained attack

- **Meter:** ward integrity, moving *both ways* each round (closer to `LOCK` than to
  a one-way accumulation).
- **NPC side:** does *not* contest the meter — it is channeling a sustained attack
  that lasts D rounds, applying pressure each round.
- **Thresholds:** *derived* from the attack's per-round pressure. "Winning" =
  surviving the duration with the ward intact.
- **Ends:** when the attack's duration expires (PCs endured) or the meter collapses
  to `0` early (ward breaks; the remaining barrage pours through unwarded).
- **Resolution:** final meter state → a consequence pool keyed by endurance band
  (endured cleanly / barely held / collapsed partway / overwhelmed).

### `BREAK` — grinding through a barrier

- **Meter:** one-way accumulation toward the barrier's authored strength.
- **NPC side:** contributes *nothing* to the meter; the boss keeps acting normally
  while the PCs work the breach.
- **Thresholds:** *derived* from the barrier's own authored strength — a field on
  the boss / threat pattern for v1 (extensible to barrier-Challenges when the
  Challenges-in-combat spec lands). Not the soak stat.
- **Resolution:** reaching the threshold breaches the barrier (decisive = a bigger /
  longer combo opening). PCs abandoning it / the encounter ending leaves the barrier
  intact (`ABANDONED`). There is no "NPC wins" — a barrier simply persists.
- `BREAK` does **not** touch the existing soak/probing counter. It is a separate,
  parallel mechanic.

## §4 — Opportunity surfacing

Clash opportunities are **surfaced by authored events** — the system detects them
from authored content, then PCs opt in. The NPC side is automatic.

| Flavor | Opportunity arises when… | Detected from |
|---|---|---|
| `CLASH` | a clash-capable PC attack and a clash-capable NPC attack resolve *opposed* | technique `clash_capable` flag + threat-pool entry `clash_capable` flag |
| Suppress | a lock-applying PC technique lands on the boss | technique authored as lock-applying |
| Break Free | a lock-applying NPC action lands on PC(s) | threat-pool entry authored as lock-applying |
| `WARD` | the boss begins a sustained-attack threat-pool entry | threat-pool entry authored as sustained (carries a duration) |
| `BREAK` | the boss has an active barrier | boss / threat-pattern authored barrier |

**`CLASH` emerges; the other four are foreseeable.** A clash of two big attacks
cannot be known until both resolve opposed — so round 1, the PC's already-declared
attack *is* their opening commitment, the clash forms retroactively, and rounds 2+
are deliberate commit decisions. Suppress / Break Free / `WARD` / `BREAK` are all
visible at declaration time (the lock landed, the barrage is channeling, the
barrier is up), so PCs declare *into* them from the first round.

**Surfacing to players:** an active `Clash` makes clash-contribution actions appear
in `get_player_actions` — riding the Phase 7 unified action interface. A clash
contribution is a `COMBAT`-backend `PlayerAction`: "Commit to [clash]" (focused) and
"Lend strength to [clash]" (passive). Every round the clash is `ACTIVE`, the join
action is available — new PCs can enter an in-progress clash.

**Lifetime & declining:** the opportunity *becomes* the `Clash` model — `ACTIVE`
until `RESOLVED`. Not committing is a valid (bad) choice: a `WARD` nobody wards
resolves NPC-favored as the barrage lands; a `CLASH` the PC stops feeding loses
ground each round to the NPC's continued push.

**POV note:** per the character-POV principle (a system never surfaces options the
character would not consider), clash opportunities should only surface to PCs who
could perceive them. v1 has no positioning, so every PC in the encounter sees every
opportunity — but opportunity visibility routes through the same POV-filtered
`get_player_actions` seam, so "you can't see the clash from behind the wall" works
without re-architecture once positioning lands.

## §5 — Multi-PC commit

Each round a PC contributes through one of two action slots:

- **Focused contribution** — the clash *is* the PC's main action. Full strain
  available; the contribution runs as a technique cast through `use_technique`, the
  check type being whatever the contributing technique uses, strain commitment
  riding as `extra_modifiers`. Largest per-round contribution.
- **Passive contribution** — "Lend strength to the clash" slotted into one of the
  PC's two passive categories (Physical / Social / Mental). The PC's focused action
  that round is something else. Lower stakes: a capped, lower anima commitment, a
  smaller modifier, a smaller delta.

**Aggregation:** every contributor rolls their own check independently; committed
anima → strain modifier → check → `CheckOutcome` tier → that contributor's progress
delta. The round's PC progress delta = the **sum** of all contributors' deltas.
This is the "X successes of varying levels, failures/botches subtract" model — each
PC's contribution is one success-level, and they sum; a botch genuinely drags the
round down even as others succeed.

**Constraints / v1 simplifications:**

- One clash contribution per PC per round (focused *or* passive), even when multiple
  clashes are running. Keeps the round's combinatorics bounded.
- The clash records its `initiator` for narrative framing and audit; mechanically
  all focused contributors are equal. No "lead bonus" in v1.
- Covenant-role synergies (a Crown archetype coordinating a clash, etc.) are a
  natural future authored layer — flagged, not built.

The cooperative mechanic is the summation; the pressure is attrition — every
contributor spends their *own* anima and risks their *own* Soulfray, so a clash
that drags grinds the whole party's pools down.

## §6 — Affinity-matrix integration

The clash reuses the existing `AffinityInteraction` matrix (the shipped
resonance-environment work) rather than authoring a parallel opposition table.

- The clash reads the same nine `AffinityInteraction` rows as directed
  `(PC-side affinity, NPC-side affinity)` pairs — the caster-vs-caster analogue of
  the shipped caster-vs-place interaction. No new rows.
- The matrix row yields a **tilt**, not an outcome. Per the RPS cycle
  (Primal > Celestial > Abyssal > Primal): the side whose affinity dominates gets a
  check-modifier *bonus* on its contributions, the dominated side a symmetric
  *penalty*. Magnitude derives from the row's authored `severity_multiplier` × a
  clash-tuning coefficient (location — `ResonanceEnvironmentConfig` vs. a new
  `ClashConfig` — is a plan-phase detail).
- Same-affinity matchups (the `ALIGNED` diagonal) → **no tilt**. The diagonal's
  `AMPLIFY` semantics are a caster-vs-place boon and do not transfer to
  caster-vs-caster; two same-affinity forces are a pure strain contest.
- The tilt is **per-contributor**: each PC contributor's *contributing-technique*
  affinity vs. the NPC clash-attack's affinity sets *that contributor's* tilt.
  Consistent with per-contributor checks, and it makes affinity matchup a real
  tactical choice (send the contributors whose affinity dominates the boss's).
- Affinity-less attacks → no matrix lookup → no tilt → pure strain contest.
- Affinity is the tilt; strain is the core. A disfavored side that strains harder
  still wins — affinity just means digging deeper to do it.

## §7 — Resolution & consequence pools

### Resolution triggers

| Flavor | Resolves when… | Also resolves if… |
|---|---|---|
| `CLASH` | meter crosses `±threshold` | max-round cap → `MUTUAL`; a side exhausts → other side wins |
| `LOCK` | meter reaches `MAX` (secured) or `0` (dissolved) | PCs stop sustaining a Suppress → meter decays on the NPC's contributions alone |
| `WARD` | the sustained attack's duration expires | meter collapses to `0` early → `overwhelmed` |
| `BREAK` | meter reaches the barrier threshold | PCs abandon it / encounter ends → barrier holds (`ABANDONED`) |

**Decisive vs. marginal = overshoot at the crossing.** Crossing by a hair →
marginal; blowing well past the threshold in the winning round → decisive.

### Consequence pools

Resolution fires the flavor's authored `resolution_consequence_pool` with the
resolution tier as the selector — the same consequence-pool machinery the rest of
magic uses (tier-keyed `Consequence` entries; selected `ConsequenceEffect`s apply
damage, conditions, window-states, backlash). The pool FK on the `Clash` is
**populated at clash-creation from the triggering authored content**: a
clash-capable technique authors its `CLASH` pool, a sustained-attack threat entry
its `WARD` pool, a lock-applying technique its `LOCK` pool, a barrier its `BREAK`
pool. Data-driven; no per-clash service functions.

**Window-states are consequence effects.** A won Suppress fires an effect securing
the "boss held" `ConditionInstance` (persists for its authored duration without
further clashing); a won `BREAK` fires the "barrier down" `ConditionInstance`.
Combo eligibility reads those conditions (§9). No new plumbing — they are
`ConsequenceEffect` rows in the resolution pool.

**The per-round incremental pool** (`per_round_consequence_pool`, nullable) fires
each round, keyed on the current meter band. It is **load-bearing for `WARD`** — it
*is* the per-round damage mitigation: the sustained attack deals its pressure each
round and the meter band selects how much the ward absorbs vs. how much gets
through. For `CLASH` it is lighter — narrative tension plus perhaps minor stress.

**Soulfray / Audere / mishaps fire during the rounds, not at resolution** — every
per-round contribution runs through `use_technique`, so the overburn ladder happens
live. Resolution only fires the outcome pool; outcome-pool effects that deal damage
(an `NPC_DECISIVE` backlash) flow through the existing survivability handlers.

**The `resolution` enum** — the five-tier `CLASH` set
(`PC_DECISIVE` / `PC_MARGINAL` / `MUTUAL` / `NPC_MARGINAL` / `NPC_DECISIVE`) is the
superset; `LOCK` uses the four win/loss tiers, `WARD` maps its endurance bands onto
them, `BREAK` uses `BROKEN` (decisive/marginal) + `ABANDONED`. Exact enum membership
is a plan-phase decision.

## §8 — Cast-pipeline & round-resolver integration

Clash needs two contained integrations. It does **not** need the reactive-layer
`TECHNIQUE_PRE_CAST` block/modify capability (see §10).

### Clash-commit mode on the cast pipeline

`use_technique` already separates *resolving the cast* (anima cost, the check, the
Soulfray ladder, reactive events, corruption) from *applying effects to targets*
(damage profiles, applied conditions). A clash contribution invokes the first half
and substitutes the second:

- The caller specifies a `strain_commitment` — anima poured in beyond the computed
  `effective_cost`, which becomes a floor. This is the one real change inside the
  cost path.
- The cast runs the full pipeline — overburn → Soulfray, mishap rider, reactive
  events, corruption all fire live, per round.
- Instead of `apply_damage_to_opponent` / applying conditions, the cast's
  `CheckOutcome` is captured and handed back to the clash orchestrator, which
  converts it to a progress delta and writes the `ClashContribution`.

Whether this is a parameter on `use_technique`, a thin `commit_to_clash` wrapper, or
a decomposition of `use_technique` into reusable halves is a plan-phase decision.
The design point: reuse the cast-resolution half, replace the effect-application
half with meter contribution.

### `resolve_round` orchestration

Round resolution gains a clash phase:

1. **Opportunity detection** — alongside the existing combo detection: opposed
   clash-capable attacks → form `CLASH`; lock-applying landings → `LOCK`;
   sustained-attack threat entries → `WARD`; barrier present → `BREAK` available.
2. **Contribution gathering** — collect declared focused + passive contributions per
   active `Clash`.
3. **Per-round resolution** (in initiative order, following the Phase 7
   `RoundChallengeDeclaration` post-pass precedent) — run each PC contribution
   through clash-commit; compute the NPC contribution; apply the affinity tilt;
   aggregate; write `ClashRound` + `ClashContribution`; update `progress`; fire
   `per_round_consequence_pool`.
4. **Threshold check** — crossed / duration expired / exhaustion → compute the
   resolution tier, fire `resolution_consequence_pool`, set `RESOLVED`.

## §9 — Combo integration

Clash state is a **general authored prerequisite surface on `ComboDefinition`** — a
combo definition can require either an *active* clash of a given flavor on the boss
or a *resolved* clash's window-state (the "boss held" / "barrier down"
`ConditionInstance` rows).

- A won Suppress maintains a "boss held" state; a won `BREAK` produces a
  "barrier down" state. Both are `ConditionInstance` rows on the boss.
- `ComboDefinition` gains a clash-prerequisite field; combo eligibility checks it.
- Suppress and `BREAK` are the typical combo-enablers, but the surface is general so
  authors can build others.

This makes Suppress and `BREAK` feel purposeful — not merely "win the clash" but
"win the clash *so that* the striker can land the finisher." It runs parallel to —
not as a replacement for — the incremental soak/probing counter.

## §10 — Why `TECHNIQUE_PRE_CAST` block/modify is *not* a dependency

An earlier draft of this spec's scope listed the reactive-layer
`TECHNIQUE_PRE_CAST` block/modify intercept as a co-built dependency. Working the
design through showed that to be wrong:

- Every clash flavor's "interception" of casts is **core combat orchestration** —
  `resolve_round` detecting opportunities and the clash-commit mode on
  `use_technique`. None of it is an authored reactive-trigger reaction.
- Per the project rule (flows/triggers are *only* for unique per-entity exceptions;
  universal effects are core gated services), clash formation **must** be core
  logic, not a `TriggerDefinition` reacting to `TECHNIQUE_PRE_CAST`.

So the reactive-layer block/modify capability is **not in Clash's scope**. It
remains a real, separate deferred item (resonance-environment recommended-next-steps
#5, Tehom/core); Clash is simply not its forcing function. `TECHNIQUE_PRE_CAST` /
`CAST` / `AFFECTED` events still *fire* during clash contributions — a clash-commit
is a real cast — so authored reactive triggers keyed on them work normally.

## §11 — Related but out of scope: Fury

**Fury** is a second narrative lever the magic system wants but this spec does not
build: deliberately *lowering control* — getting angry, abandoning precision,
letting intensity surge.

Fury is distinct from Strain. They are different axes:

- **Strain** spends anima directly — *how much you give*. Risk: exhaustion →
  Soulfray.
- **Fury** lowers control, widening the intensity/control delta. Because control
  reduces anima cost (anima is *stability*), widening that delta **drives anima cost
  up** — Fury makes every working cost more and shred you faster. Risk: accelerated
  burn plus unpredictability. *How recklessly you channel it.*

Both roads can culminate in **Audere** — pushing past your limits and enduring as
your soul is torn apart. Strain and Fury are two roads; Audere is the destination.

Clash v1 uses Strain as its lever. Fury is recorded here, distinguished from Strain,
and deferred — it gets its own design when prioritised. Audere already gives clashes
a recklessness *beat* in the meantime (the Audere offer fires mid-clash when a
straining contributor crosses the threshold).

## §12 — Testing strategy

Layered tests ending in full-pipeline integration coverage, following every magic
scope's pattern.

**Model unit tests** (`world/combat/tests/`) — `Clash` discriminator integrity
(`lock_pc_role` non-null iff `flavor == LOCK`, threshold fields, `status`
transitions, the `resolution` enum); `ClashRound` / `ClashContribution`
relationships and the one-contribution-per-PC-per-round `UniqueConstraint`;
factories (`ClashFactory` + per-flavor variants, `ClashRoundFactory`,
`ClashContributionFactory`).

**Service tests** — strain conversion (the `StrainConfig` diminishing-returns curve;
overburn when commitment exceeds the pool); clash-commit (a contribution runs the
cast pipeline, produces a `CheckOutcome`, converts to a delta, writes the
`ClashContribution`); aggregation (multi-PC deltas sum; focused-vs-passive magnitude
gap; a botch subtracting); NPC-side contribution per flavor; affinity tilt
(per-contributor, RPS cycle, same-affinity and affinity-less → no tilt); resolution
(threshold crossing, decisive-vs-marginal by overshoot, exhaustion, `WARD` duration
expiry, `BREAK` abandonment; resolution pool fires with the tier as selector;
window-state `ConditionInstance` production).

**Round-orchestration tests** — `resolve_round` clash phase (opportunity detection
per flavor, contribution gathering, per-round resolution in initiative order,
threshold check); clash interleaving with normal combat in one round; multi-round
persistence; a PC joining an in-progress clash.

**End-to-end integration tests** (`world/combat/tests/integration/test_clash_flow.py`)
— one full-pipeline scenario per flavor:

- `CLASH`: declare big attack → opposed NPC big attack → clash forms → multi-round
  contributions → threshold → resolution pool → damage outcome
- Suppress: lock technique lands → clash opens → sustain to `MAX` → "boss held"
  condition → a combo with that prerequisite becomes eligible
- Break Free: NPC lock lands on PCs → push the meter to `0` → escape
- `WARD`: NPC sustained attack → endure across the duration → per-round mitigation
  via `per_round_consequence_pool` → final endurance outcome
- `BREAK`: boss barrier → sustain the breach → threshold → "barrier down" condition
  → combo eligibility
- **Cross-cutting:** a contributor overburns → Soulfray accrues across rounds →
  Audere offer fires mid-clash → accepts → wins the clash at the cost of a Mage Scar

**Seed content** — a `ClashContent` factory orchestrator (sibling to the magic
`MagicContent` pattern): a clash-capable technique, a sustained-attack threat entry,
a lock-applying technique, a barrier, per-flavor consequence pools, and a combo
carrying a clash-state prerequisite.

**Regression scope** — all plausibly-affected suites: `world/combat`, `world/magic`
(the `use_technique` strain extension is additive — existing technique-use tests
must still pass), `world/mechanics`, `world/conditions`, `world/checks`. One run
without `--keepdb` before pushing (integration tests create encounters →
`CombatNPC` typeclasses, so the fresh-DB caution applies).

## Open items for the plan phase

- Exact `Clash` schema — field types, nullability, the precise discriminator
  `CheckConstraint`s
- Whether clash-commit is a `use_technique` parameter, a wrapper, or a decomposition
- Location of the affinity-tilt coefficient (`ResonanceEnvironmentConfig` vs. a new
  `ClashConfig`) and of the tier→delta table and per-tier default thresholds
- Final `resolution` enum membership across the flavors
- The archetype `flavor` enum value (`CLASH` literal vs. a descriptive value)
- The `ComboDefinition` clash-prerequisite field shape (active-clash vs.
  window-state condition — likely both)
- New authored fields: `Technique.clash_capable`, lock-applying / sustained /
  barrier markers on `ThreatPoolEntry`, lock-strength `MAX`, barrier strength
- **`CLASH` threshold formula** — "derived from the two attacks' relative power"
  needs a concrete formula. `Clash` creation happens at opportunity-detection time
  and must write concrete `pc_win_threshold` / `npc_win_threshold` values.
- **`WARD` NPC per-round pressure source** — whether the sustained attack's
  per-round pressure is a fixed authored value or follows the same threat-pool /
  boss-phase modifier path as `CLASH`/`LOCK` NPC contributions. The round resolver
  needs a defined way to compute the `WARD` NPC delta.
- **`WARD` endurance bands** — the count of bands and the meter ranges that map to
  them. Load-bearing because `per_round_consequence_pool` *is* the per-round `WARD`
  mitigation; the band definition drives how much damage is absorbed per round.
- **Passive-contribution cap** — the formula and location of the cap on a passive
  contribution's anima commitment (authored per-technique, a `ClashConfig` field, or
  a fixed fraction of the focused cap). Surfaces immediately in `ClashContribution`
  validation.

## Related work

- `docs/roadmap/combat.md` — combat overview; the "Clash of Wills" entry; reserved
  terminology
- `docs/roadmap/magic.md` — Scopes 1–7, the `use_technique` pipeline, Audere,
  Soulfray, corruption
- `docs/plans/2026-05-21-positioning-zones-design-notes.md` — the positioning work
  Clash is deliberately independent of
- `docs/superpowers/specs/2026-05-16-resonance-environment-universal-path-design.md`
  — the `AffinityInteraction` matrix Clash reuses
- `docs/superpowers/specs/2026-05-17-unified-player-action-interface-design.md` —
  the `get_player_actions` / `PlayerAction` seam clash contributions surface through

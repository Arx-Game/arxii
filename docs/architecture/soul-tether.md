# Resonance Pivot — Spec B: Soul Tether (+ Accepting-a-Soul-Tether Ritual Capstone)

**Status:** Design
**Date:** 2026-05-03
**Depends on:**
- Resonance Pivot Spec A (DONE) — Thread model, `RELATIONSHIP_CAPSTONE` anchor kind, `is_soul_tether` storage fields, `ThreadPullEffect` / `Ritual` / `RitualComponentRequirement` machinery, soft-retire (`retired_at`), per-character handlers (`character.threads`, `character.resonances`).
- Scope #5 Magical Alteration Resolution (DONE) — `PendingAlteration` lifecycle, constrained-authoring pattern.
- Scope #5.5 Reactive Foundations (DONE) — `emit_event`, `cancel_event`, `MODIFY_PAYLOAD`, `PROMPT_PLAYER` flow steps and `@reply` resolution.
- Scope #6 Soulfray Recovery & Decay (DONE) — generalized `passive_decay_per_day` on `ConditionTemplate`, stage-entry conditions, `decay_condition_severity`, scheduler tick patterns, Treatment.
- Scope #7 Corruption (DONE) — `accrue_corruption` with `redirect_origin` parameter, `reduce_corruption` primitive, `CORRUPTION_ACCRUING` and `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` reactive events, `is_protagonism_locked` aggregator, Atonement Rite as service-dispatched Ritual reference, severity-driven stage advancement with HOLD_OVERFLOW + resist check.

**Blocks:** None — Spec B's other planned pieces (Ritual of Devotion, Ritual of Betrayal, Relational Resilience) remain post-MVP and are explicitly out of scope here.

**Related:** Spec A §2.2 (soul-tether storage fields migrated), §5 (`RELATIONSHIP_CAPSTONE` anchor kind), §3.8 (pull-duration model). Scope 7 §3.2 (`accrue_corruption` interception hook), §3.5 (`CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`), §1.4 (Soul Tether narrative arc).

---

## 1. Context & Design Intent

### 1.1 What this spec builds

This spec ships **Soul Tether** plus the **Accepting-a-Soul-Tether Ritual Capstone** — two of the three pieces originally scoped under Resonance Pivot Spec B. The remaining pieces (Relational Resilience, Ritual of Devotion, Ritual of Betrayal) are deferred to follow-up specs.

Soul Tether is a **bond mechanic** between two PCs that mediates the Corruption risk a Sinner accrues from non-Celestial casting. The bond is composed of three things:

1. A `CharacterRelationship.is_soul_tether=True` flag plus `soul_tether_role` on each side (storage shipped by Spec A; we activate it here).
2. The Sinner's `RELATIONSHIP_CAPSTONE` Thread carrying **the Hollow** — a draining capacity buffer that absorbs incoming corruption from `CORRUPTION_ACCRUING` events on the Sinner's behalf.
3. The optional Sineater-side `RELATIONSHIP_CAPSTONE` Thread carrying **personal benefits** — a tier-0 passive `CORRUPTION_RESISTANCE` derived from the Sineater's per-resonance `lifetime_helped` counter.

The bond is filled and emptied through **Sineating** — a Sinner-initiated, Sineater-accepted action that costs the Sineater anima/fatigue and refills the Hollow. At dramatic moments (Sinner stage-advance resist checks, stage-3+ rescue rituals) the Sineater can opt to commit reservoir capacity and/or take Strain severity to bonus a roll or pull the Sinner back.

### 1.2 Three design goals (recorded explicitly)

1. **Balance** — Abyssal magic is the fastest-advancing, highest-yield magical path, but it accrues Corruption faster than any other path. Soul Tether is the canonical narrative-flavored mitigation channel that lets Abyssal users keep playing without becoming Subsumed. Every aspect of the bond's tuning serves this balance role.

2. **Narrative** — Themes of identity loss, loss of humanity, and rescue from the brink are most potent when expressed through Abyssal corruption. Soul Tether gives players the *mechanical hooks* to tell those stories to each other directly: a Sineater eating their partner's sins, the partner sliding toward the abyss, the climactic stage-3+ rescue ritual. **No GM intervention required for any beat in this arc**, including stage-5 Subsumption recovery.

3. **Social** — The bond mechanically rewards deep relationship RP between PCs. Soul Tether requires *active maintenance* through scenes between the two characters. Critically: **being a Sineater should not feel punishing**. The role carries personal benefits (resistance to absorbed corruption, optional Thread pulls), and routine Sineating costs only token recoverable anima/fatigue. Cost only intensifies during dramatic moments, where the Sineater opts in.

### 1.3 Hard design principles (recorded as spec invariants)

These three principles bind every implementation decision in this spec.

#### 1.3.1 Anti-resentment

**No mechanic in this system may create a gameplay reason to resent an inactive player.** The only consequence of a partner's inactivity should be the loss of their RP.

Consequences:
- No background ticks. Dormant tethers cost both characters zero anima/fatigue/Resonance.
- No dormancy detection or auto-penalty. A bond simply sits idle.
- No "broken oath" condition on dissolution.
- No reservoir decay over time. The Hollow's contents persist between sessions until Sineating empties it or corruption drains it.

#### 1.3.2 XP-anti-pattern (what you spend on must benefit you)

**No character should be required to spend XP/Resonance for "no benefit."** Every purchasable investment in this system must produce a direct benefit for the spender.

Consequences:
- The **Sinner's** `RELATIONSHIP_CAPSTONE` Thread is required for the redirect to function. The Sinner pays for it because the Sinner directly benefits (the Hollow protects them).
- The **Sineater's** `RELATIONSHIP_CAPSTONE` Thread is *optional*. Without it, Sineating still works — the Sineater simply doesn't manifest the resistance benefit (their `lifetime_helped` counter accumulates regardless). They invest only when they want personal benefits.
- All positive mechanical effects in this system gate on Thread presence/level. Trackers, costs, and audit rows happen regardless. **Only benefits gate on Threads.**

#### 1.3.3 No staff bottleneck

**Stage-5 Subsumption is rescuable by PCs without GM intervention.** The cost simply scales high enough at stage 5 to feel climactic, without being literally impossible. The "rescued from the brink" beat is a player-driven narrative arc.

### 1.4 Glossary

| Term | Meaning |
|------|---------|
| **Sinner** | The character on the Abyssal-or-Primal side of a Soul Tether bond — the one who accrues Corruption from non-Celestial casting and is protected by the bond. `CharacterRelationship.soul_tether_role = ABYSSAL`. |
| **Sineater** | The character on the Celestial-or-Primal side — the one who eats sins out of the Hollow on the Sinner's behalf. `CharacterRelationship.soul_tether_role = SINEATER`. |
| **The Hollow** | The buffer on the Sinner's `RELATIONSHIP_CAPSTONE` Thread that absorbs incoming corruption. *Filled with sins* by the Sinner's casting (mechanically: capacity drains as it absorbs). *Emptied of sins* by the Sineater eating them out (mechanically: capacity refills). |
| **Sineating** | The action of the Sineater eating sins out of the Hollow. Sinner-initiated request; Sineater accepts via `PROMPT_PLAYER` `@reply` with chosen amount. Active-voice verb form refers to what the Sineater does (*"the Sineater is Sineating"*). |
| **Hollowed** | Passive-voice verb form, refers to what the Sinner experiences when sins are eaten out of their Hollow (*"the Sinner asks to be Hollowed"*, *"once Hollowed, capacity returns"*). Same underlying event as Sineating, named from the other side. Player-facing prose templates and prompt copy should use whichever form fits the sentence's subject. |
| **Tether Strain** | A per-resonance condition that accrues on the Sineater only at dramatic moments — opt-in stage-advance bonus, rescue rituals, reservoir overflow opt-ins. Not from routine Sineating. |
| **Lifetime Helped** | Per-resonance monotonic counter on the Sineater's `CharacterResonance` rows. Increments on every accepted Sineating unit and every rescue ritual. Drives the resistance benefit when the Sineater has a Thread in that resonance. |

---

## 2. Architecture Overview

The bond's loop, end to end:

```
(routine maintenance — fills the Hollow with capacity to absorb)
   Sinner →    request_sineating(scene, resonance, units_offered)
                    │
                    ▼
   Sineater ←  PROMPT_PLAYER (offer payload: units, costs, current Hollow, current Strain)
   Sineater →  @reply <units_accepted>     (0 = decline; 1..max = accept partial)
                    │
                    ▼
                resolve_sineating(): deduct anima/fatigue per unit,
                                    increment hollow_current,
                                    increment lifetime_helped,
                                    write Sineating audit row,
                                    fire stat increments

(redirect — drains the Hollow on Sinner's casts)
   Sinner casts non-Celestial technique
                    │
                    ▼
                accrue_corruption() emits CORRUPTION_ACCRUING (Scope 7)
                    │
                    ▼
   Spec B subscriber:  iterate Sinner's active tethers (priority order),
                       drain hollow_current by accrued amount,
                       cancel_event() for fully-absorbed amount,
                       overflow falls through to normal Sinner accrual

(stage-advance dramatic prompt — Sineater opt-in)
   Sinner approaching Corruption stage advance
                    │
                    ▼
                emit CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (Scope 7)
                    │
                    ▼
   Spec B subscriber:  if Sinner has active tether and Sineater is in same scene,
                       fire PROMPT_PLAYER to Sineater with bonus offer
   Sineater →  @reply <commitment>   (0 = decline; 1..max = spend Hollow + take Strain)
                    │
                    ▼
                MODIFY_PAYLOAD on resist-check bonus, deduct from Hollow,
                add Strain severity to (sineater, resonance) instance

(rescue ritual — climactic recovery, stages 3+)
   Sineater initiates soul_tether_rescue ritual in scene with Sinner present
                    │
                    ▼
                perform_soul_tether_rescue():
                    check + budget
                    deduct Resonance, components, Strain severity
                    call reduce_corruption() (Scope 7 primitive)
                    write SoulTetherRescue audit row
                    increment lifetime_helped
```

---

## 3. Affinity Gates and Multiplicity

### 3.1 Sineater eligibility

**Sineater must be Celestial-primary or Primal-primary affinity.** Mirrors the Atonement Rite gate (Scope 7 §4): non-Abyssal-primary characters can lead the role. Abyssal-primary characters cannot Sineater — their own corrupted nature is the wrong shape to anchor against.

### 3.2 Sinner eligibility

**Sinner must be non-Celestial-primary** — i.e., Abyssal-primary or Primal-primary. Celestial-primary characters cannot be Sinners because they don't accrue Corruption (Scope 7 §3.1: Celestial coefficient is 0).

The canonical case is Abyssal-primary Sinners. Primal-primary characters accrue Corruption much slower (Scope 7: Primal coefficient is 0.2, Abyssal is 1.0) and at low levels are fully cleared by passive decay (see §11). At higher tiers, where their casting outpaces decay, a Primal Sinner becomes mechanically meaningful.

### 3.3 Multiplicity: many-to-many

Either side can hold multiple tethers simultaneously. There are no hard caps.

The natural disincentive is **relationship-strength scaling**. Each bond's mechanical capacity caps on the relationship's developed-absolute-value (see §4.3). Spreading yourself across many shallow relationships produces many weak tethers; deep engagement with one partner produces a single strong tether. The economic shape encourages focus without forbidding breadth.

This decision is deliberate against the player-attrition reality. If a Sineater goes inactive, their Sinner partners cannot be left stuck; if a Sinner goes inactive, their Sineater shouldn't be locked into a one-and-only bond. Many-to-many handles attrition cleanly.

---

## 4. Bond Strength Architecture

### 4.1 Sinner's Thread (required for redirect)

For the redirect mechanic to function, the Sinner must have an active `RELATIONSHIP_CAPSTONE` Thread on the bond. This is the magical anchor on which the Hollow lives.

- Field: `Thread.hollow_current` (PositiveIntegerField, default 0). Only meaningful for `RELATIONSHIP_CAPSTONE` Sinner-side Threads. Other Threads ignore it.
- `hollow_max` (computed at runtime, not stored): a function of `Thread.level` capped by the relationship's `developed_absolute_value`. Exact formula in §10.1.
- Without the Sinner's Thread: no Hollow, no redirect; the Sinner's `CORRUPTION_ACCRUING` events pass through normally to their own corruption pool.

The Sinner pays for the `ThreadWeavingUnlock` and the Resonance investment because the Sinner directly benefits — the Hollow protects *them*. Spec compliance with §1.3.2.

### 4.2 Sineater's Thread (optional, gates personal benefits)

The Sineater may optionally weave their own `RELATIONSHIP_CAPSTONE` Thread on the bond. This Thread is **not required** for Sineating to function or for the redirect to work — both function with only the Sinner's Thread present.

The Sineater Thread's purpose is to gate personal benefits:
- Tier-0 passive `CORRUPTION_RESISTANCE` effect (see §8) — derives runtime value from the Sineater's `lifetime_helped[Thread.resonance]`.
- Higher-tier pull effects (vital bonuses, social bonuses, etc.) authored later as concrete content.

Without a Sineater Thread, the Sineater still *accumulates* `lifetime_helped` — the counter is never gated on Thread presence — but the value is dormant. They cannot manifest the resistance benefit without investing in the Thread directly.

This satisfies §1.3.2: the Sineater's investment produces personal benefits proportional to their commitment.

### 4.3 Relationship cap on Thread level

Each Thread's maximum level is capped by the relationship's `developed_absolute_value` (sum of permanent points across all tracks). Concretely: `Thread.level <= floor(developed_absolute_value / N)` for tunable N (specific value settled at implementation).

This keeps relationship-RP and Resonance investment growing together. A player cannot grind Resonance into a paper-thin bond and weaponize it; the relationship must actually deepen for the Thread (and therefore the bond) to grow.

---

## 5. The Hollow and the Redirect Mechanic

### 5.1 Narrative framing (player-facing)

The Hollow is the **bond's sacred absence** — a space carved out by love that catches darkness before it reaches the Sinner. Every non-Celestial cast the Sinner makes deposits sins into the Hollow. When the Hollow fills with sins, no more can be absorbed; further casting accrues corruption to the Sinner directly. The Sineater eats the sins out of the Hollow, opening it back up.

Mechanically: `hollow_current` is *available capacity remaining*. It decrements as sins fill it (corruption absorbed) and increments when the Sineater eats sins out (Sineating accepted). Player-facing copy and prose templates describe this in the Sin-eating framing — the field name is mechanical; the IC language is *sins held* / *sins eaten*.

### 5.2 Subscriber on `CORRUPTION_ACCRUING`

Spec B installs a subscriber on the `CORRUPTION_ACCRUING` reactive event (Scope 7 §3.2 emits this pre-mutation; payload includes `character_sheet`, `resonance`, `amount`, `source`, mutable). Pseudocode for the handler:

```python
def on_corruption_accruing(payload):
    sinner_sheet = payload.character_sheet
    accruing_amount = payload.amount
    resonance = payload.resonance

    # Skip if no active tether or not a Sinner role
    tethers = active_soul_tethers_for(sinner_sheet)  # is_soul_tether=True, role=ABYSSAL
    if not tethers:
        return

    # Collect the Sinner-side Threads anchored to active tether bonds.
    # Per Spec A's RELATIONSHIP_CAPSTONE unique constraint, the Sinner has at
    # most one Thread per (resonance, capstone) combination. Different bonds
    # (different capstones) can each have their own Thread in the same
    # resonance — multiple Threads in the cast's resonance is normal for a
    # Sinner with multiple tethers. We further filter to Threads whose
    # resonance matches the corruption being accrued, since only matching-
    # resonance Threads are eligible to absorb.
    sinner_threads = sinner_threads_for_tethers(tethers, resonance=resonance)

    # Drain across them in priority order (highest Thread.level first)
    remaining = accruing_amount
    for thread in sorted(sinner_threads, key=lambda t: -t.level):
        if remaining <= 0:
            break
        absorbed = min(thread.hollow_current, remaining)
        thread.hollow_current -= absorbed
        thread.save(update_fields=["hollow_current"])
        remaining -= absorbed

    if remaining < accruing_amount:
        # Some or all absorbed — replace the original event
        cancel_event(payload)
        if remaining > 0:
            # Overflow falls through to Sinner normally
            accrue_corruption(
                character_sheet=sinner_sheet,
                resonance=resonance,
                amount=remaining,
                source=payload.source,
                redirect_origin=None,  # this leg isn't a Sineater redirect
            )
        # if remaining == 0, fully absorbed; no further accrual
```

Key properties:
- **No Sineater-side cost during routine redirect.** The Sineater paid anima/fatigue at refill time, not severity. Routine corruption flow drains the Hollow only.
- **Overflow is faithful.** If the Hollow can absorb 8 of a 12-unit accrual, the remaining 4 hit the Sinner normally. No magical "eat all or nothing" semantics.
- **Priority across multiple tethers** is by Thread strength (highest level first). Drains spread across the strongest bonds.

### 5.3 Spec 7 contract divergence

Scope 7 §3.2 anticipated that the redirect would issue a "small trace amount of `accrue_corruption` to the Sineater" — i.e., the Sineater would accumulate actual Corruption from absorption directly during routine redirects. **Spec B deliberately diverges here.** Routine Sineating produces no Sineater-side Corruption and no Tether Strain. Strain only accrues at *dramatic* moments — opt-in stage-advance bonuses and rescue rituals. The Sineater's "loss of identity" cost is reserved for dramatic moments where the player has explicit agency, not as a constant background tax.

**Why this divergence is the better design:**

- **Sineater-corruption stories still happen** — they emerge from Strain stage 4-5 stage-entry effects (§6.4), which themselves only accrue when the Sineater took Strain at a *dramatic* moment (stage-advance bonus or rescue ritual). The "I started to taste the darkness" arc is therefore always tied to a specific scene of high stakes, not to a quiet aggregate drift. Better narrative payoff per unit of corruption accrued.
- **Tension in non-dramatic moments comes from negotiation, not from mechanical drift.** The pressure between Sinner and Sineater in routine play is the Sinner asking to be Hollowed and the Sineater choosing how much to eat — that *is* the routine dramatic beat, played out at the bond's normal cadence. There's no need for a hidden background tax to make routine play feel weighty; the Sineating negotiation itself is the weight.
- **Compatible with §1.3 invariants.** Anti-resentment (§1.3.1) is preserved because the Sineater never accrues corruption from a partner who's just casting a lot off-screen — corruption only reaches the Sineater when both characters are in scene together AND the Sineater opts into a dramatic moment. The XP-anti-pattern (§1.3.2) is preserved because the Sineater's only corruption risk comes from their own explicit choices.

The `redirect_origin` parameter on `accrue_corruption` (which Scope 7 added for the original redirect-to-Sineater idea) is therefore unused by Spec B's redirect overflow path (overflow is straight Sinner accrual, not a Sineater leg). It remains available for the Strain-stage-4-5 corruption-accrual aftermath in §6.4 — that authored content sets `redirect_origin=sinner_sheet` for audit lineage, since the Sineater's corruption there is genealogically traceable to a specific Sinner's bond and a specific dramatic scene.

---

## 6. Tether Strain Condition (Sineater Side)

### 6.1 Per-resonance lazy ConditionInstance

`TetherStrainTemplate` is a single authored `ConditionTemplate` row (5 stages, severity-driven, `passive_decay_per_day` enabled). `ConditionInstance` rows are lazy-created per `(sineater_sheet, resonance)` — same lazy-creation pattern as Corruption (Scope 7 §3.2).

A Sineater feeding two Sinners — one Abyssal, one Primal — has two independent Strain conditions, each tracking severity in its specific resonance. Each has its own decay tick, its own stage-entry effects, and its own contribution to dramatic-moment costs.

### 6.2 When Strain accrues

Strain severity rises **only at dramatic moments**:

1. **Stage-advance prompt opt-in** (§7.2). When the Sineater accepts a bonus offer to help their Sinner pass a stage-advance resist check, the accepted commitment includes Strain severity.
2. **Rescue rituals** (§8). The Sineater takes Strain severity scaled to the Sinner's current stage when they perform the ritual.
3. **Hollow overflow opt-in** (deferred — not in MVP). A future iteration may allow the Sineater to opt in to absorbing past Hollow capacity, taking Strain in exchange. MVP just lets overflow hit the Sinner.

**Routine Sineating produces no Strain.** This is the design promise: §1.2 social goal (Sineater doesn't feel punished) requires that the routine cost be only token anima/fatigue at refill time.

### 6.3 Stage effects

Stage authoring (specific values settled at implementation, but shape recorded):

| Stage | Tier name (placeholder) | Effects |
|-------|------------------------|---------|
| 1 | Bone-Tired | Minor fatigue: -1 to social and concentration checks. |
| 2 | Soul-Worn | Reduced anima regen daily tick. |
| 3 | Heart-Cracked | Anima regen blocked entirely while at this stage. |
| 4 | Shadow-Touched | Mishap chance on own non-Celestial casts (additive). Stage entry MAY grant authored small-corruption-accrual aftermath conditions ("Tinged with Shadow," etc.) — see §6.4. |
| 5 | Half-Lost | Action point reduction; severe penalties to non-rescue-related actions. Stage entry MAY grant a more pronounced corruption-accrual aftermath. |

All stages decay through `passive_decay_per_day` over weeks; the Sineater eventually returns to baseline without intervention. Decay doesn't require Sineating scenes — it's the natural healing of having stopped taking Strain.

### 6.4 "Make him worse" — flavor corruption accrual at high stages

At Strain stages 4-5, stage-entry effects MAY include authored small-corruption-accrual aftermath in the matching resonance. Mechanically: the stage's `on_entry_conditions` M2M can include an authored `MagicalAlterationTemplate` (Scope 5) with `kind=CORRUPTION_TWIST` that calls `accrue_corruption` with a capped low amount. The Sineater starts to taste the darkness they've been eating.

Strict bounds:
- Capped low enough that a fully-maxed Strain (stage 5 in every resonance) cannot, by itself, push the Sineater toward Subsumption.
- Authored content only — no automatic Strain-to-Corruption conversion. Specific alterations like "Tinged with Shadow," "Hungry Eyes," "Echoes of the Pit" are out of MVP scope (separate authoring spec).
- The `redirect_origin` parameter on the resulting `accrue_corruption` call is set to the Sinner's CharacterSheet for audit trail.

---

## 7. The Sineating Action

### 7.1 Sinner-initiated, Sineater-accepted

The Sineating action expresses both characters' agency:
- The **Sinner** initiates by asking ("please take some of this from me"). Their request is the moment of admitting need.
- The **Sineater** receives a `PROMPT_PLAYER` (Spec 5.5 mechanism) carrying the offer payload and chooses an amount via `@reply`. They may decline cleanly (`@reply 0`).

This produces several narrative wins:
- The decline is itself a meaningful IC moment — a Sineater who refuses or limits how much they'll take is telling a real story. The audit row preserves declines so achievements like "asked their Sineater 50 times and was refused 30 times" are queryable.
- "Persuaded to take more" is built into the structure — the Sinner's request and the Sineater's chosen amount are the negotiation.
- Both sides express commitment per scene. There is no automatic refill; nothing happens unless the Sinner asks AND the Sineater accepts.

### 7.2 Service flow

```
sinner →  request_sineating(sineater_sheet, resonance, max_units_requested, scene)
              │
              │  validates: active tether between them, both in scene,
              │             resonance is one Sinner accrues, Sineater no active engagement
              ▼
          fire PROMPT_PLAYER to Sineater. Payload:
          {
            "kind": "SINEATING_OFFER",
            "sinner_sheet_id": ...,
            "resonance_id": ...,
            "max_units_offered": N,
            "anima_cost_per_unit": X,
            "fatigue_cost_per_unit": Y,
            "current_hollow": current,
            "hollow_max": max,
            "sineater_current_strain_stage": stage_in_resonance,
          }
              │
              ▼
sineater → @reply <units_accepted>      (0..max_units_offered)
              │
              ▼
          resolve_sineating(prompt_id, units_accepted):
            atomic:
              units = clamp(units_accepted, 0, max_units_offered)
              if units > 0:
                deduct units * anima_cost_per_unit from Sineater's anima
                deduct units * fatigue_cost_per_unit from Sineater's fatigue
                increment Sinner's Thread.hollow_current by units
                  (clamped to hollow_max)
                increment Sineater's CharacterResonance.lifetime_helped[resonance] by units
              write Sineating audit row (units_offered, units_accepted, costs)
              fire stat increments: sineating.units_accepted+=units,
                                   sineating.units_declined+=(0 if units>0 else 1)
              if Sineater.character.account: send notification
              if Sinner.character.account: send notification
```

### 7.3 Per-scene cap on units

Per-scene unit cap = a function of the relationship's `developed_absolute_value` and the Sinner's Thread level (specific formula at implementation). The Sinner can re-request multiple times within a scene as long as cumulative accepted units remain under the cap. This permits a particularly demanding stretch of RP to include multiple Sineatings without grinding.

### 7.4 Cost recovery profile

The token anima/fatigue cost recovers fast. Implementation should choose values that recover within hours (anima: standard daily regen tick; fatigue: existing fatigue mechanics or a similar fast-decay path). The Sineater should not feel ongoing depletion from refill scenes — only the immediate "this scene cost me a small piece" moment, which heals before the next scene.

---

## 8. Stage-Advance Dramatic Prompt

### 8.1 Subscriber on `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`

Scope 7 §3.5 emits `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` pre-mutation when a HOLD_OVERFLOW Corruption stage is about to test for advancement. Payload includes `character_sheet`, `condition_instance`, `resist_check_type`, `resist_difficulty`, `current_bonus` (mutable). Spec B subscribes with priority below other modifiers (if any later add).

```python
def on_stage_advance_check_about_to_fire(payload):
    sinner_sheet = payload.character_sheet
    condition = payload.condition_instance

    # Only intercept Corruption conditions (others not ours)
    if condition.template.corruption_resonance is None:
        return

    tethers = active_soul_tethers_for(sinner_sheet)
    if not tethers:
        return

    # Find a Sineater partner in the same scene as the Sinner
    sineater_in_scene = find_sineater_in_scene(sinner_sheet, tethers)
    if sineater_in_scene is None:
        return  # No prompt fires; resist check proceeds normally

    # Fire PROMPT_PLAYER to the Sineater
    prompt_payload = {
        "kind": "STAGE_ADVANCE_BONUS_OFFER",
        "sinner_sheet_id": sinner_sheet.id,
        "resonance_id": condition.template.corruption_resonance_id,
        "current_stage": current_stage_of(condition),
        "advancing_to_stage": next_stage_of(condition),
        "max_hollow_to_spend": hollow_total_across_tethers(tethers),
        "max_strain_offer": <by formula>,
        "bonus_per_unit_committed": <by formula>,
    }
    fire_prompt_player(sineater_in_scene, prompt_payload)
    # PROMPT_PLAYER suspends the resist check via Twisted Deferred (Spec 5.5)
```

When the Sineater `@reply`s with their commitment, the bonus is added to the resist check via `MODIFY_PAYLOAD` on `current_bonus`, the appropriate amount drains from the Hollow, and Strain severity is added to the Sineater's `(sineater, resonance)` ConditionInstance. The resist check then resumes.

### 8.2 Decline path

If the Sineater declines (`@reply 0`) or isn't reachable, the resist check proceeds unchanged. The Sinner's stage advance fires per Scope 7's normal logic. This is by design — the dramatic prompt is opt-in, and a decline produces a real narrative consequence (the Sinner advances). Both choices have IC weight.

---

## 9. Rescue Ritual

### 9.1 Single scaling ritual

The rescue ritual is a single `Ritual` row authored under Spec A's machinery (`dispatch_kind=SERVICE`, components, prose templates). Service function: `perform_soul_tether_rescue`.

### 9.2 Gates and preconditions

- Sinner has at least one Corruption ConditionInstance at stage 3+.
- Sineater is the Sinner's tethered partner on at least one bond (`is_soul_tether=True`, `soul_tether_role=SINEATER`).
- Both are in the same scene.
- Neither in active `CharacterEngagement`.
- One ritual per `(sineater, sinner)` pair per scene.

### 9.3 Cost

Paid before effect resolution:
- **Strain severity** in the matching resonance — scaled to Sinner's current stage. Stage 3 is a moderate hit; stage 5 is severe. Specific values authored at implementation.
- **Resonance** from the Sineater's `CharacterResonance.balance` for the matching resonance.
- **Ritual components** consumed per Spec A's `RitualComponentRequirement`.

### 9.4 Effect

Mirrors `perform_anima_ritual` (Scope 6): a check-outcome-tiered budget.

```python
def perform_soul_tether_rescue(sineater_sheet, sinner_sheet, resonance, components):
    # validate gates ...
    # consume components ...
    # deduct Resonance from Sineater balance ...
    # roll Magical Endurance check at appropriate difficulty
    check_outcome = perform_check(sineater_sheet, ...)
    budget = compute_rescue_budget(check_outcome, sineater_thread_level_on_bond)

    sinner_stage_at_start = current_stage(sinner_sheet, resonance)

    # Apply Strain to Sineater
    sineater_strain_taken = compute_strain_cost(sinner_stage_at_start)
    advance_condition_severity(
        ConditionInstance for (sineater_sheet, resonance) on TetherStrainTemplate,
        amount=sineater_strain_taken,
    )

    # Reduce Sinner's corruption
    severity_reduced = reduce_corruption(
        sheet=sinner_sheet,
        resonance=resonance,
        amount=budget,
        source=RescueSource.SOUL_TETHER,
    )

    sinner_stage_at_end = current_stage(sinner_sheet, resonance)

    # Increment lifetime_helped
    sineater_resonance = sineater_sheet.resonances.get_or_create(resonance)
    sineater_resonance.lifetime_helped += budget
    sineater_resonance.save()

    # Audit
    write_rescue_audit_row(
        sinner_sheet, sineater_sheet, scene, resonance,
        sinner_stage_at_start, sinner_stage_at_end,
        severity_reduced, sineater_strain_taken, check_outcome,
    )

    # Achievement stat increments
    increment_stat("rescue.performed", sineater_sheet, by=1)
    if sinner_stage_at_start == 5:
        increment_stat("rescue.stage5_save", sineater_sheet, by=1)

    return RescueOutcome(...)
```

`reduce_corruption` (Scope 7 primitive) handles the field decrement, condition stage retreat, decay-driven aftermath cleanup, and `is_protagonism_locked` lift when crossing back below stage 5.

### 9.5 Stage-5 design note

A single rescue ritual is unlikely to drop a Sinner from stage 5 to stage 1 — typical outcomes drop them to stage 4 or 3, leaving more rescues needed. The "rescued from the brink" beat is genuinely earned through repeated effort and ongoing relationship investment. Stage 5 is rescuable per principle §1.3.3, but the cost is high enough that the rescue arc itself is multi-scene.

---

## 10. Resistance Benefit (Threads Gate, lifetime_helped Drives)

### 10.1 The lifetime_helped counter

`CharacterResonance.lifetime_helped` (PositiveIntegerField, default 0, monotonic). New field on the existing per-`(character_sheet, resonance)` model. Same shape as Spec A's `lifetime_earned`.

Increments:
- On every accepted Sineating unit (§7.2 service flow).
- By `severity_reduced` on every rescue ritual (§9.4 service flow).

Permanence: never decreases. Survives bond dissolution. Survives partner death. The Sineater carries what they earned forever.

### 10.2 Resistance is gated on Sineater Thread

Per principle §1.3.2, the resistance benefit is *only* manifest when the Sineater has woven their own `RELATIONSHIP_CAPSTONE` Thread in the matching resonance. Without a Thread in resonance X, `lifetime_helped[X]` accumulates but is dormant.

Implemented as a tier-0 passive `ThreadPullEffect` on Sineater-side `RELATIONSHIP_CAPSTONE` Threads:
- New `effect_kind` enum value: `CORRUPTION_RESISTANCE`.
- Effect's runtime value derives from `lifetime_helped[Thread.resonance]` of the Sineater. Not a stored amount.
- **Application point and scope:** the resistance applies to the **Sineater's own corruption accrual when *they themselves* cast non-Celestial techniques** — i.e., it reduces what *their own* casting writes to *their own* `CharacterResonance.corruption_current`. It is *not* applied to the Hollow's draining behavior on a Sinner partner's casts (the Hollow drains uniformly per absorbed amount; the Sineater is not "casting" during a redirect). Concretely: when `accrue_corruption` is called for a Sineater character whose source is their own non-Celestial cast, `accrue_corruption` looks up matching active Sineater-side `RELATIONSHIP_CAPSTONE` Threads and applies the strongest matching `CORRUPTION_RESISTANCE` multiplier to the accrual amount before storing.
- Multiplicative reduction: `effective_amount = base_amount * max(0.1, 1 - lifetime_helped[X] / threshold)` for tunable threshold. Caps at 90% reduction (floor multiplier 0.1).
- Per Spec A's `Thread.resonance` schema (one resonance per Thread, plus the unique constraint on `(owner, resonance, target_capstone)`), a Sineater wanting resistance to multiple resonances weaves multiple Threads — either across different bonds (different capstones) or, on a single bond, by weaving one Thread per resonance. Each Thread manifests resistance for its own resonance independently.

### 10.3 Implementation note

The runtime resolver for the `CORRUPTION_RESISTANCE` effect is a small extension to `resolve_pull_effects` (Spec A) — it reads the Sineater's `CharacterResonance.lifetime_helped` for the Thread's resonance and computes the multiplier on demand. No new persistent state.

The application point is `accrue_corruption` (Scope 7): when called for a non-Celestial Sineater cast, look up the Sineater's active Sineater-side `RELATIONSHIP_CAPSTONE` Threads in the cast's resonance, take the strongest matching `CORRUPTION_RESISTANCE` effect, multiply the accrual amount before storing.

---

## 11. Companion Piece: Passive Corruption Decay Tuning

This is **not a Soul Tether feature** — it's a small piece of Corruption tuning that the Soul Tether design assumes. Listed here because the spec hangs together only with this floor in place.

Author `passive_decay_per_day` and `passive_decay_max_severity` values on existing Corruption `ConditionTemplate` rows (Wild Hunt, Web of Spiders) and any future Corruption templates. Tuning numbers (settled at implementation, not in this spec):

- Primal-flavored Corruption: decay rate sufficient to fully clear a low-tier Primal-primary character's accrual over a small number of days. *Primal users below mid-tier do not need a Sineater.*
- Abyssal-flavored Corruption: decay rate slow enough that an Abyssal-primary character past tier 1 cannot rely on decay alone. *Abyssal users post-tier-1 need a Sineater (or rely on Atonement Rite, which is one-shot per scene and only effective at stages 1-2).*

`passive_decay_blocked_in_engagement=False` for Corruption (matches the design — corruption decays during normal life, not just out of combat).

The decay tick is the existing `decay_all_conditions_tick()` from Scope 6 — no new infrastructure.

---

## 12. Formation: Accepting a Soul Tether (Ritual Capstone)

### 12.1 The capstone event

Formation is itself a `RelationshipCapstone` event with ritual-flavor metadata. New fields on `RelationshipCapstone`:
- `is_ritual_capstone` (BooleanField, default False).
- `ritual` (FK to `magic.Ritual`, nullable, only set when `is_ritual_capstone=True`).

The capstone row is the *narrative event* (writeup, scene linkage, both PCs commit IC). The associated `Ritual` is the in-scene magical action (components, performance check, prose templates).

### 12.2 Prerequisites

- Both characters have an active `CharacterRelationship`.
- Both characters consent to the capstone via the existing capstone consent flow.
- Affinity gates met (§3.1, §3.2).
- The Sinner has purchased their `ThreadWeavingUnlock` for `RELATIONSHIP_CAPSTONE` and has Resonance available to weave their first Thread on the bond. (No requirement on Sineater.)

**No relationship-strength prerequisite.** Anyone with an active relationship can attempt formation. The relationship-cap on Thread level (§4.3) keeps early tethers mechanically weak until the relationship deepens.

### 12.3 Ritual mechanics

The ritual has low-DC performance check; failure means the bond doesn't form (no catastrophic outcome). Components are authored — likely shared symbolic items (a strand of hair, a witnessed token, a written name). Specific authoring is implementation, but the IC framing is **witchy** — explicit ritual language, candles-and-circle vibes, sacred-named promises.

### 12.4 Service flow

```python
def accept_soul_tether(initiator_sheet, partner_sheet, sinner_role, resonance):
    # `CharacterRelationship` has `source` and `target` fields (Spec A schema):
    # the bond is represented as TWO rows — initiator→partner AND partner→initiator.
    # Each row carries its own `soul_tether_role` independently. We set both rows
    # in the same atomic block so the bond is symmetric in directionality.

    rel_outgoing = get_or_create_relationship(source=initiator_sheet, target=partner_sheet)
    rel_incoming = get_or_create_relationship(source=partner_sheet, target=initiator_sheet)
    require(rel_outgoing.is_active and rel_incoming.is_active)
    require(both_consent_recorded(rel_outgoing, rel_incoming))
    require(affinity_gates_met(initiator_sheet, partner_sheet, sinner_role))

    # Determine which side is Sinner
    sinner_sheet = initiator_sheet if sinner_role == "ABYSSAL" else partner_sheet
    sineater_sheet = partner_sheet if sinner_role == "ABYSSAL" else initiator_sheet

    require(sinner_sheet.threads.has_unlock(RELATIONSHIP_CAPSTONE))

    with atomic():
        # Create the formation capstone event. RelationshipCapstone FKs to one
        # CharacterRelationship row (per Spec A's Thread schema, which expects a
        # single capstone target FK to `target_capstone`). Convention: anchor on
        # the Sinner→Sineater direction so the Sinner's Thread can FK to it
        # cleanly via target_capstone.
        anchor_relationship = (
            rel_outgoing if rel_outgoing.source_id == sinner_sheet.id else rel_incoming
        )
        capstone = RelationshipCapstone.objects.create(
            relationship=anchor_relationship,
            is_ritual_capstone=True,
            ritual=Ritual.objects.get(name="accept_soul_tether"),
            writeup=...,  # from form
            ...
        )

        # Flip is_soul_tether and set role on BOTH directional rows so the bond
        # is detectable from either direction.
        for rel in (rel_outgoing, rel_incoming):
            rel.is_soul_tether = True
            rel.soul_tether_role = (
                "ABYSSAL" if rel.source_id == sinner_sheet.id else "SINEATER"
            )
            rel.save(update_fields=["is_soul_tether", "soul_tether_role"])

        # Weave Sinner's Thread, anchored to the formation capstone.
        # Per Spec A's RELATIONSHIP_CAPSTONE constraint, exactly one Thread per
        # (owner, resonance, target_capstone) — so the Sinner gets one Thread per
        # resonance they want to invest the bond in, all anchored to this capstone.
        sinner_thread = weave_thread(
            owner=sinner_sheet,
            target_kind=RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            resonance=resonance,
        )
        # sinner_thread.hollow_current starts at 0 — Sineater must Sineat to fill it.

    # Sineater's optional Thread is woven separately (anchors to the same capstone
    # via target_capstone with the Sineater as `owner`). Not part of formation.

    write_capstone_audit_row(...)
    fire_event(SOUL_TETHER_FORMED, ...)
```

The Sineater's optional Thread is woven separately if/when they choose to invest. Not part of the formation flow.

### 12.5 Reformation after dissolution

If a tether dissolves (§13) and one or both characters later wish to reform with the same partner, they perform the same ritual again. Each formation is a fresh `RelationshipCapstone` row. No cooldown. The Sinner weaves a new Thread; the previous (soft-retired) Thread remains for journaling.

---

## 13. Dissolution (MVP Stub)

Dissolution is **out of MVP scope** as a designed surface. The MVP exposes only the primitive: setting `is_soul_tether=False` on the `CharacterRelationship` triggers soft-retire on both sides' active `RELATIONSHIP_CAPSTONE` Threads (`retired_at` set per Spec A) and emits the `SOUL_TETHER_DISSOLVED` event (defined in `flows/constants.py`). API endpoint accepts the flip; either side may call it without the other's consent.

Persistence on dissolution:
- Sineater's `lifetime_helped` counters persist. They earned the resistance; they keep it.
- Sineater's TetherStrain ConditionInstances persist. They decay naturally from there.
- Sinner's accumulated Corruption persists. The bond breaking does not heal them.
- Audit rows (`Sineating`, `SoulTetherRescue`) persist.

What is *not* implemented (deliberately deferred):
- "Broken oath" condition or any Strain-like residual on either party.
- Resonance refund of any kind.
- Cooldown to reform.
- Dormancy detection (no shared scene for X weeks → auto-dormant).

A future spec ("Ritual of Betrayal," "Severing the Tether," etc.) will layer narrative drama on top of this primitive without changing the underlying mechanism.

---

## 14. Achievement-Supporting Data Architecture

### 14.1 Audit rows (per-event, queryable)

#### `Sineating`

Written every time a Sineating action resolves (including declines). Fields:

| Field | Type | Notes |
|-------|------|-------|
| `sinner_sheet` | FK CharacterSheet | |
| `sineater_sheet` | FK CharacterSheet | |
| `relationship` | FK CharacterRelationship | for join queries |
| `scene` | FK Scene, nullable | |
| `resonance` | FK Resonance | |
| `units_offered` | PositiveIntegerField | what the Sinner asked for |
| `units_accepted` | PositiveIntegerField | 0 = declined; 1..N = accepted |
| `anima_cost` | PositiveIntegerField | total cost paid by Sineater |
| `fatigue_cost` | PositiveIntegerField | |
| `created_at` | DateTimeField | |

Indexes on `(sinner_sheet, created_at)`, `(sineater_sheet, created_at)`, `(relationship, created_at)`.

#### `SoulTetherRescue`

Written every time a rescue ritual resolves. Fields:

| Field | Type | Notes |
|-------|------|-------|
| `sinner_sheet` | FK CharacterSheet | |
| `sineater_sheet` | FK CharacterSheet | |
| `relationship` | FK CharacterRelationship | |
| `scene` | FK Scene, nullable | |
| `resonance` | FK Resonance | |
| `sinner_stage_at_start` | PositiveSmallIntegerField | |
| `sinner_stage_at_end` | PositiveSmallIntegerField | |
| `severity_reduced` | PositiveIntegerField | what `reduce_corruption` removed |
| `sineater_strain_taken` | PositiveIntegerField | |
| `check_outcome` | FK CheckOutcome | |
| `created_at` | DateTimeField | |

### 14.2 Persistent state fields (sources of truth)

Two new persistent fields, each the **single source of truth** for the value it represents (not denormalizations of other state):

- `Thread.hollow_current` — the current Hollow capacity on a Sinner-side `RELATIONSHIP_CAPSTONE` Thread (§4.1, §5). Mutated only by the `CORRUPTION_ACCRUING` redirect handler (drain) and `resolve_sineating` (refill). Not derived from anything.
- `CharacterResonance.lifetime_helped` — the per-resonance monotonic counter on the Sineater (§10.1). Incremented only by `resolve_sineating` and `perform_soul_tether_rescue`. Permanent.

Per-relationship and per-Thread aggregates (e.g., "total units this Sineater has accepted on bond X") are *not* stored — they are computed by aggregation over audit rows on demand. No additional fast-path counters in MVP. Audit rows plus the join to `CharacterRelationship` are sufficient for any achievement query, including compound queries by track type.

### 14.3 Stat integration

Each service fires `world.achievements.services.increment_stat()` for a small set:

| Stat | Fired by | Per-event amount |
|------|----------|------------------|
| `sineating.units_accepted` | `resolve_sineating` (units > 0) | `units` |
| `sineating.units_declined` | `resolve_sineating` (units == 0) | 1 |
| `sineating.requests_made` | `request_sineating` | 1 |
| `rescue.performed` | `perform_soul_tether_rescue` | 1 |
| `rescue.stage5_save` | `perform_soul_tether_rescue` (stage_at_start=5) | 1 |
| `rescue.severity_reduced` | `perform_soul_tether_rescue` | `severity_reduced` |
| `tether.formed` | `accept_soul_tether` | 1 |

Future achievements use these stats plus joined audit rows (e.g., "I can fix her" = `rescue.performed >= N` AND join to Romance-tier-3+ relationship). Stat names follow `world.achievements` conventions.

### 14.4 Compound achievements (illustrative, not in scope)

Future authoring can target these without touching this spec's code:

- **"I can fix her"** — `rescue.performed >= N` AND queried through Romance-tier-3+ on the rescued relationship.
- **"I will not lose you"** — Sineater performs a stage-5 rescue (`rescue.stage5_save >= 1`) on their Romance partner.
- **"Patron Saint"** — Sineating events with N distinct Sinners.
- **"I can make him worse"** — needs a separate trigger event (e.g., Sineater's own corruption rises to stage 2+, OR Sinner pushes partner past some threshold). Not implemented in this spec, but the audit row + `lifetime_helped` infrastructure plus the "make him worse" flavor accrual at Strain stages 4-5 (§6.4) make this achievable forward.

---

## 15. Models

### 15.1 New models

#### `magic.Sineating`
Audit row per §14.1.

#### `magic.SoulTetherRescue`
Audit row per §14.1.

#### `magic.TetherStrainTemplate`
Not a new model class — an authored `ConditionTemplate` row. Migration creates it; admin/seeds may extend stage-entry effects later.

#### `magic.SoulTetherConfig` (singleton tuning surface)

SharedMemoryModel singleton (pk=1). All Soul Tether tuning knobs — rescue and sineating
costs, caps, and budget formulas — are read from this row rather than from module
constants, so staff can adjust them via the admin without a code change. Lazy-created via
`get_soul_tether_config()` in `world/magic/services/soul_tether.py`.

Fields:

| Field | Default | Meaning |
|-------|---------|---------|
| `anima_cost_per_unit` | 2 | Sineater anima cost per Sineating unit |
| `fatigue_cost_per_unit` | 1 | Sineater fatigue cost per unit |
| `per_scene_cap_hard_max` | 20 | Absolute ceiling on units accepted per scene |
| `per_scene_cap_level_mult` | 2 | Per-Thread-level multiplier for per-scene cap |
| `per_scene_cap_base` | 5 | Base per-scene cap before level scaling |
| `hollow_max_level_mult` | 10 | Multiplier on Thread level for max Hollow capacity |
| `rescue_strain_stage3/4/5` | 5/10/18 | Strain thresholds for rescue at each Sinner stage |
| `rescue_resonance_stage3/4/5` | 10/20/35 | Resonance cost for rescue at each Sinner stage |
| `rescue_budget_base_stage3/4/5` | 60/120/250 | Base severity-reduction budget per stage |
| `rescue_budget_base_mult_tenths` | 10 (→ 1.0) | Base multiplier in tenths |
| `rescue_budget_success_mult_tenths` | 5 (→ 0.5) | Success-level multiplier in tenths |
| `rescue_budget_thread_mult_hundredths` | 5 (→ 0.05) | Thread-level multiplier in hundredths |

### 15.2 Modifications to existing models

#### `magic.Thread`
Add `hollow_current` (PositiveIntegerField, default 0). Documented as "Only meaningful for `RELATIONSHIP_CAPSTONE` Sinner-side Threads. Other Threads ignore."

#### `magic.CharacterResonance`
Add `lifetime_helped` (PositiveIntegerField, default 0, monotonic). Mirrors `lifetime_earned`'s semantics.

#### `relationships.RelationshipCapstone`
Add `is_ritual_capstone` (BooleanField, default False) and `ritual` (FK `magic.Ritual`, nullable).

#### `relationships.CharacterRelationship`
No model change — `is_soul_tether` and `soul_tether_role` already shipped (Spec A §2.2).

### 15.3 New `ThreadPullEffect.effect_kind` enum value

`CORRUPTION_RESISTANCE` — tier-0 passive, derives runtime value from Sineater's `lifetime_helped[Thread.resonance]`. Implementation in `resolve_pull_effects` reads the Sineater's `CharacterResonance` row and computes the reduction multiplier.

### 15.4 Authored content (data, not migration code)

- `Ritual` rows: `accept_soul_tether`, `soul_tether_rescue`. Both `dispatch_kind=SERVICE`.
- `RitualComponentRequirement` rows for both rituals.
- `ImbuingProseTemplate` or equivalent prose for the Hollow / Sineating / rescue events.
- Authored `ConditionTemplate` for `TetherStrainTemplate` with 5 stages, each with severity_threshold and stage-entry effects per §6.3.
- `passive_decay_per_day` values on existing Corruption `ConditionTemplate` rows (Wild Hunt, Web of Spiders) per §11.

---

## 16. Service Functions

All in `world/magic/services/soul_tether.py` unless noted.

| Function | Purpose |
|----------|---------|
| `accept_soul_tether(initiator_sheet, partner_sheet, sinner_role, ritual_components)` | Formation. §12.4. |
| `dissolve_soul_tether(relationship, initiator_sheet)` | Stub. §13. |
| `request_sineating(sinner_sheet, sineater_sheet, resonance, max_units, scene)` | Sinner asks. §7.2. |
| `resolve_sineating(prompt_id, units_accepted)` | Sineater @reply resolution. §7.2. |
| `perform_soul_tether_rescue(sineater_sheet, sinner_sheet, resonance, components)` | Rescue ritual. §9.4. |
| `compute_hollow_max(thread)` | Derived from Thread level + relationship cap. §4.3. |
| `active_soul_tethers_for(sheet)` | Helper: returns the character's active tethers (either side). |
| `find_sineater_in_scene(sinner_sheet, tethers, scene)` | Helper used by stage-advance subscriber. |
| `get_soul_tether_config() -> SoulTetherConfig` | Lazy-create the singleton (pk=1). All rescue and sineating cost calculations read from this rather than module constants. |

---

## 17. Reactive Subscribers

In `world/magic/triggers/soul_tether.py`:

| Subscriber | Event | Handler |
|------------|-------|---------|
| `on_corruption_accruing` | `CORRUPTION_ACCRUING` | Drain Hollow on Sinner's tethered Threads, cancel event, replace overflow. §5.2. |
| `on_stage_advance_check_about_to_fire` | `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` | Fire `PROMPT_PLAYER` for Sineater bonus offer. §8.1. |

Both registered with priority below the foundation events themselves so they intercept before any further consumers.

---

## 18. API Surface

DRF viewsets in `world/magic/views/soul_tether.py`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/magic/soul-tether/accept/` | POST | Formation; validates consent and gates. Calls `accept_soul_tether`. |
| `/api/magic/soul-tether/dissolve/` | POST | Stub dissolution. Calls `dissolve_soul_tether`. |
| `/api/magic/soul-tether/sineating/request/` | POST | Sinner initiates; returns prompt ID. Calls `request_sineating`. |
| `/api/magic/soul-tether/sineating/respond/{prompt_id}/` | POST | Sineater accepts/declines (alternative to `@reply` for web UI). Calls `resolve_sineating`. |
| `/api/magic/soul-tether/rescue/` | POST | Sineater performs rescue. Calls `perform_soul_tether_rescue`. |
| `/api/magic/soul-tether/{relationship_id}/` | GET | View tether state: Hollow current/max, Thread levels, lifetime stats. |

All endpoints use serializer-level validation per project pattern; views are thin delegations to services.

---

## 19. Testing Strategy

### 19.1 Unit tests

Per service function, in `world/magic/tests/test_soul_tether_services.py`:
- `accept_soul_tether`: validates consent flow, affinity gates, atomic creation.
- `request_sineating`: validates active tether, scene presence, prompt firing.
- `resolve_sineating`: atomic deduction, audit row, stat increments, decline path.
- `perform_soul_tether_rescue`: gates, costs, `reduce_corruption` invocation, lifetime_helped increment.

### 19.2 Integration tests

In `src/world/magic/tests/integration/test_soul_tether_flow.py`:

1. **Formation pipeline.** Capstone consent → service call → `is_soul_tether=True` → roles set → Sinner Thread woven.
2. **Full Sineating loop.** Sinner casts Abyssal → `CORRUPTION_ACCRUING` → tether with full Hollow → fully absorbed, no Sinner accrual. Sinner casts after empty Hollow → falls through normally. Sineating refills Hollow.
3. **Stage-advance dramatic prompt.** Sinner approaches stage advance → resist check fires → Sineater in scene → prompt → accept bonus → Sinner's resist passes; decline → Sinner advances.
4. **Rescue at stages 3, 4, 5.** Each: Sineater performs ritual, Strain accrues, `reduce_corruption` called, severity drops, audit row. Stage 5 path: protagonism unlocks on retreat below threshold.
5. **Resistance benefit gate.** Sineater accumulates `lifetime_helped` without weaving Thread → resistance does not manifest. Weave Thread → resistance manifests at value derived from counter. Two Threads in different resonances → independent resistance per resonance.
6. **Anti-resentment invariant.** Set up tether; both characters dormant for simulated 12 weeks (advance world clock) — neither character pays anima/fatigue/Resonance during dormancy. Passive corruption decay applies to Sinner regardless.
7. **Dissolution.** `dissolve_soul_tether` → `is_soul_tether=False` → both Threads soft-retired → `lifetime_helped` persists → Strain decays naturally from existing severity.
8. **Many-to-many.** Sineater forms tethers with two Sinners (one Abyssal, one Primal). Two independent Strain ConditionInstances. Two independent Threads' Hollows drain on each Sinner's casts. Resistance benefits manifest independently per resonance once Sineater Threads woven.
9. **Multi-bond redirect priority.** Sinner has two Sineater partners. Corruption accrual drains highest-Thread-level Hollow first; overflow drains next; final overflow accrues to Sinner.
10. **Decline-recorded audit.** Sinner makes 5 Sineating requests; Sineater declines 3, accepts 2. Audit rows count 5 events with units_accepted = [0, 0, X, 0, Y]. Stat increments fire correctly.

### 19.3 Test seed factories

- `SoulTetherFactory(initiator_sheet, partner_sheet, sinner_role)` — creates relationship + capstone + ritual + thread + role flags.
- `SineatingFactory` — creates audit rows for backfill testing.
- `SoulTetherRescueFactory` — same.
- `TetherStrainTemplateFactory` + `wire_soul_tether_content()` orchestrator for the integration-test game-content factory layer. `wire_soul_tether_content()` is also called from `seed_magic_dev()` (#2027) so the Rituals/ConditionTemplates/TriggerDefinitions exist in a real deploy, not only under test setup; `seed_relationship_track_thread_unlock()` seeds the paired RELATIONSHIP_TRACK `ThreadWeavingUnlock` (+ canonical "Devotion" `RelationshipTrack`) that `accept_soul_tether` gates on.

---

## 20. Out of MVP Scope (explicit)

- **Ritual of Devotion** and **Ritual of Betrayal** — separate Spec B follow-ups.
- **Relational Resilience** — the broader Spec B aggregate-relationship-bonus mechanic. Separate spec.
- **Specific Strain stage 4-5 corruption-accrual aftermath content** ("Tinged with Shadow," "Hungry Eyes," etc.) — authored separately.
- **Tuning numbers** (Hollow capacity formulas, refill caps, Strain decay rates, resistance thresholds, ritual difficulties, anima/fatigue per unit) — settled at implementation, staff-tunable via admin where appropriate.
- **Public-facing Soul Tether leaderboard / visibility controls** — `lifetime_helped` is private; dashboard exposure is a future concern.
- **Multi-tier rescue ritual variants.** Single scaling ritual covers all stages.
- **Dissolution narrative variants** — only the primitive flip + soft-retire are MVP.
- **Hollow overflow opt-in for the Sineater.** Routine overflow always falls through to the Sinner; Sineater cannot mid-cast opt to absorb more. Future enhancement if play surfaces the need.
- **Cross-Sineater coordination** — multiple Sineaters performing a joint rescue. Single-Sineater ritual only.
- **"I can make him worse" achievement infrastructure** — flagged as forward-compatible (audit rows + `lifetime_helped` + Strain stage-entry corruption-accrual at §6.4 are sufficient hooks), but no specific achievement authored.

---

## 21. Open Questions / Deferred Decisions

These are decisions the spec deliberately leaves for implementation, where data informs the choice better than upfront design:

1. **Hollow capacity formula** — `f(thread_level, developed_absolute_value)`. Pre-alpha placeholder; staff-tunable.
2. **Per-scene Sineating cap** — `g(developed_absolute_value, sinner_thread_level)`. Same.
3. **Anima/fatigue cost per unit** — small enough to recover within hours.
4. **Strain decay rate** — `passive_decay_per_day` value on `TetherStrainTemplate`. Tuned so a maxed Strain naturally returns to baseline within weeks.
5. **Resistance threshold** — `lifetime_helped` value at which 90% reduction caps.
6. **Rescue ritual cost scaling** — Strain, Resonance, components scaled to Sinner's stage at start.
7. **Stage-advance bonus per unit committed** — how much resist-roll bonus per Hollow unit + Strain severity.
8. **Strain stage authoring** — exact tier names, exact effects per stage, exact corruption-accrual amounts on stages 4-5.
9. **Passive corruption decay rates per affinity** (§11) — Primal, Abyssal, future affinity-flavored Corruption templates.
10. **Reformation cooldown** — currently zero per §12.5. May revisit if play surfaces grinding patterns.

---

## 22. Cross-Spec Dependencies and Hooks Consumed

| Hook | From | Consumed by |
|------|------|-------------|
| `CORRUPTION_ACCRUING` | Scope 7 §3.2 | Spec B §5.2 redirect handler |
| `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` | Scope 7 §3.5 | Spec B §8.1 stage-advance prompt handler |
| `accrue_corruption(redirect_origin=...)` | Scope 7 §3.2 | Spec B §6.4 (Strain stage-entry accrual) |
| `reduce_corruption()` | Scope 7 §3.3 | Spec B §9.4 rescue ritual |
| `is_protagonism_locked` aggregator | Scope 7 §3.6 | Naturally handled by `reduce_corruption` cleanup |
| `cancel_event()` | Scope 5.5 | Spec B §5.2 |
| `PROMPT_PLAYER` flow step + `@reply` | Scope 5.5 | Spec B §7.2, §8.1 |
| `MODIFY_PAYLOAD` flow step | Scope 5.5 | Spec B §8.1 (resist-check bonus) |
| `Thread`, `ThreadPullEffect`, `Ritual`, `RitualComponentRequirement` | Spec A | Spec B §4, §10, §12, §9 |
| `RELATIONSHIP_CAPSTONE` `target_kind` and `is_soul_tether` storage | Spec A §5, §2.2 | Spec B §4 |
| `ThreadWeavingUnlock` for `RELATIONSHIP_CAPSTONE` | Spec A | Spec B §4.1, §12.2 |
| `passive_decay_per_day` on `ConditionTemplate` | Scope 6 | Spec B §6, §11 |
| `decay_condition_severity`, `decay_all_conditions_tick` | Scope 6 | Spec B §6.3 (Strain decay), §11 (Corruption decay) |
| `perform_check`, `CheckOutcome` | World mechanics | Spec B §9.4 |
| `world.achievements.services.increment_stat` | Achievements app | Spec B §14.3 |
| Capstone consent flow, `RelationshipCapstone` | Relationships app | Spec B §12.1 |

This is a richly-woven feature — almost every infrastructure piece this game has built feeds into Soul Tether, which is exactly why it's a strong test of the systems.

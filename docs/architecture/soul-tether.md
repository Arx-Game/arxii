# Resonance Pivot — Spec B: Soul Tether (+ Accepting-a-Soul-Tether Ritual Capstone)

**Status:** Design
**Date:** 2026-05-03
**Depends on:**
- Resonance Pivot Spec A (DONE) — Thread model, `RELATIONSHIP_CAPSTONE` anchor kind, `is_soul_tether` storage fields, `ThreadPullEffect` / `Ritual` / `RitualComponentRequirement` machinery, soft-retire (`retired_at`), per-character handlers (`character.threads`, `character.resonances`).
- Scope #5 Magical Alteration Resolution (DONE) — `PendingAlteration` lifecycle, constrained-authoring pattern.
- Scope #5.5 Reactive Foundations (DONE) — `emit_event`, `cancel_event`, `MODIFY_PAYLOAD`, `PROMPT_PLAYER` flow steps and `@reply` resolution.
- Scope #6 Soulfray Recovery & Decay (DONE) — generalized `passive_decay_per_day` on `ConditionTemplate`, stage-entry conditions, `decay_condition_severity`, scheduler tick patterns, Treatment.
- Scope #7 Corruption (DONE) — `accrue_corruption` with `redirect_origin` parameter, `reduce_corruption` primitive, `CORRUPTION_ACCRUING` and `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` reactive events, `is_protagonism_locked` aggregator, (the Atonement Rite once listed here was removed in #4751), severity-driven stage advancement with HOLD_OVERFLOW + resist check.

**Blocks:** None — Spec B's other planned pieces (Ritual of Devotion, Ritual of Betrayal, Relational Resilience) remain post-MVP and are explicitly out of scope here.

**Related:** Spec A §2.2 (soul-tether storage fields migrated), §5 (`RELATIONSHIP_CAPSTONE` anchor kind), §3.8 (pull-duration model). Scope 7 §3.2 (`accrue_corruption` interception hook), §3.5 (`CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`), §1.4 (Soul Tether narrative arc).


> **Superseded in part by #3957 (ties, redrawn — ADR-0308), 2026-09-21.** Every reference
> below to `RelationshipTrack`, `RelationshipTrackProgress`, track points,
> `developed_absolute_value` or per-track tiers describes a shape that no longer exists. A
> relationship is now two directed sides (`CharacterRelationship`) that pool one depth
> (`pair_depth()`), each holding `RelationshipLabel` rows and claiming its own tier on one
> shared ladder. `Thread.target_relationship` anchors to the SIDE row (was
> `target_relationship_track`), `ThreadWeavingUnlock.unlock_type` names a `RelationshipType`
> (was `unlock_track`), and weaving a RELATIONSHIP_TRACK thread is gated on the weaver's
> claimed tier reaching `RelationshipGrowthConfig.thread_min_tier`. For the current shape
> read `src/world/relationships/CLAUDE.md` and `docs/systems/magic.md`; this document stays
> as the record of the design as approved.

> **Superseded in part by #5123 (ADR-5123-A, ADR-5123-B), 2026-11-14.** A thread holds several
> resonances (one thread per anchor, `Thread.resonance` the leading one), so a Sineater no longer
> weaves one thread per resonance on a bond; the uniqueness constraints below are `(owner,
> target)`. The part of #5123 that made the Mire a share of the Sineater's aura (recorded in
> `CharacterResonance.mire_lifetime` and held to `DriftConfig.mire_allowance_percent`) was
> replaced by #5177, below.

> **Superseded in part by #5177 (ADR-5177), 2026-11-17.** Sineating is a ritual with a roll,
> framed by two poses in a shared scene, and it moves corruption the Sinner already carries onto
> the Sineater. The Sineater's thread is woven when the tether forms, so it is no longer
> optional. The Mire is the corruption a Sineater carries for their Sinners, held per Sinner in
> `MireHolding` and settled through the settling rite. Anything below that describes the
> request-and-accept Sineating, its anima and fatigue costs, `resolve_sineating`, the
> `PROMPT_PLAYER` offer for Sineating, an optional Sineater thread, or a resistance that only
> counts in the thread's own resonance describes a shape that no longer exists. Sections 1.4,
> 4.2, 5.3, 7, 10, 14, 15, 16, 18 and 19 are rewritten to what the code does now, and section 7.5
> describes the Mire. The rescue and the stage-advance prompt are unchanged except for three
> things: presence is by character, a fallen Sineater is refused, and the Sineater's thread
> level now reaches the rescue budget.

---

## 1. Context & Design Intent

### 1.1 What this spec builds

This spec ships **Soul Tether** plus the **Accepting-a-Soul-Tether Ritual Capstone** — two of the three pieces originally scoped under Resonance Pivot Spec B. The remaining pieces (Relational Resilience, Ritual of Devotion, Ritual of Betrayal) are deferred to follow-up specs.

Soul Tether is a **bond mechanic** between two PCs that mediates the Corruption risk a Sinner accrues from non-Celestial casting. The bond is composed of three things:

1. A `CharacterRelationship.is_soul_tether=True` flag plus `soul_tether_role` on each side (storage shipped by Spec A; we activate it here).
2. The Sinner's `RELATIONSHIP_CAPSTONE` Thread carrying **the Hollow** — a draining capacity buffer that absorbs incoming corruption from `CORRUPTION_ACCRUING` events on the Sinner's behalf.
3. The Sineater-side `RELATIONSHIP_CAPSTONE` Thread, woven when the tether forms (#5177), on a ritual capstone of the Sineater's own side of the bond. It carries the resonance the Sineater earns from Sineating, and its presence turns on the Sineater's `CORRUPTION_RESISTANCE`, which is sized by the Sineater's per-resonance `lifetime_helped` counter.

The bond is worked through **Sineating**, a ritual with a configured check, asked for by the Sinner's pose and performed by the Sineater's pose. It moves corruption the Sinner already carries onto the Sineater, refills the Hollow, and pays both of them resonance in their own half of the bond. It costs the Sineater no anima and no fatigue; the burden is the cost. What the Sineater takes on is the **Mire**, which they settle later through the settling rite. At dramatic moments (Sinner stage-advance resist checks, stage-3+ rescue rituals) the Sineater can opt to commit reservoir capacity and/or take Strain severity to bonus a roll or pull the Sinner back.

### 1.2 Three design goals (recorded explicitly)

1. **Balance** — Abyssal magic is the fastest-advancing, highest-yield magical path, but it accrues Corruption faster than any other path. Soul Tether is the canonical narrative-flavored mitigation channel that lets Abyssal users keep playing without becoming Subsumed. Every aspect of the bond's tuning serves this balance role.

2. **Narrative**: Themes of identity loss, loss of humanity, and rescue from the brink are most potent when expressed through Abyssal corruption. Soul Tether gives players the *mechanical hooks* to tell those stories to each other directly: a Sineater taking on their partner's sins and carrying them, the partner sliding toward the abyss, the climactic stage-3+ rescue ritual. **No GM intervention required for any beat in this arc**, including stage-5 Subsumption recovery.

3. **Social**: The bond mechanically rewards deep relationship RP between PCs. Soul Tether requires *active maintenance* through scenes between the two characters. Critically: **being a Sineater should not feel punishing**. The role carries personal benefits (resistance to the corruption they take on, resonance earned from every Sineating, a reward for settling the Mire), and Sineating itself costs no anima and no fatigue (#5177). The cost is the burden the Sineater chooses to carry, which they settle on their own timing. Strain only accrues during dramatic moments, where the Sineater opts in.

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
- The **Sineater's** `RELATIONSHIP_CAPSTONE` Thread costs them nothing: formation weaves it for them (#5177), so every Sineater with a tether and a resonance to channel has the resistance benefit and earns resonance from Sineating. This replaces the earlier rule that the Sineater bought it themselves; the Sineater spends nothing, so the principle holds.
- All positive mechanical effects in this system gate on Thread presence/level. Trackers and audit rows happen regardless. **Only benefits gate on Threads.**

#### 1.3.3 No staff bottleneck

**Stage-5 Subsumption is rescuable by PCs without GM intervention.** The cost simply scales high enough at stage 5 to feel climactic, without being literally impossible. The "rescued from the brink" beat is a player-driven narrative arc.

### 1.4 Glossary

| Term | Meaning |
|------|---------|
| **Sinner** | The character on the Abyssal-or-Primal side of a Soul Tether bond, the one who accrues Corruption from non-Celestial casting and is protected by the bond. `CharacterRelationship.soul_tether_role = SINNER`. |
| **Sineater** | The character on the Celestial-or-Primal side, the one who takes on carried corruption on the Sinner's behalf. `CharacterRelationship.soul_tether_role = SINEATER`. A Sineater may be an NPC a GM runs. A Sineater whose aura is predominantly Abyssal has **fallen** and serves no one until it is predominantly something else. |
| **The Hollow** | The buffer on the Sinner's `RELATIONSHIP_CAPSTONE` Thread that absorbs incoming corruption. *Filled with sins* by the Sinner's casting (mechanically: capacity drains as it absorbs). *Emptied of sins* by Sineating (mechanically: capacity refills). The Hollow guards corruption the Sinner is about to accrue; it does not hold corruption the Sinner already carries. |
| **Sineating** | A ritual with a roll, framed by poses in a shared scene (#5177). The Sinner's pose asks for it, the Sineater's pose performs it, chooses how many of the offered units to take on, and rolls the configured check. It moves carried corruption from the Sinner to the Sineater, refills the Hollow, and pays each of them resonance in their own half of the bond. Active-voice verb form refers to what the Sineater does (*"the Sineater is Sineating"*). |
| **Hollowed** | Passive-voice verb form, refers to what the Sinner experiences when a Sineater performs Sineating for them (*"the Sinner asks to be Hollowed"*, *"once Hollowed, capacity returns"*). Same underlying event as Sineating, named from the other side. |
| **The Mire** | The corruption a Sineater carries for their Sinners, and only that. It lives on the Sineater's own corruption in a resonance, and `MireHolding` records how much of it came from which Sinner. The Sineater settles it through the settling rite by Absolve, Condemn or Succumb (§7.5). |
| **Tether Strain** | A per-resonance condition that accrues on the Sineater only at dramatic moments, opt-in stage-advance bonus and rescue rituals. Not from Sineating. The telnet command that pledges against a stage advance is `sineater brace`. |
| **Lifetime Helped** | Per-resonance monotonic counter on the Sineater's `CharacterResonance` rows. Increments on every performed Sineating unit and every rescue ritual. Sizes the resistance benefit (§10). |

---

## 2. Architecture Overview

The bond's loop, end to end:

```
(Sineating, a ritual in a shared scene, moves carried corruption and refills the Hollow)
   Sinner →    pose/entreat or the pose composer's Sineating row  (EntreatSineatingAction)
                    │   writes SineatingPendingOffer (one per pair), tells the Sineater
                    ▼
   Sineater →  pose/sineat or the composer's row, units chosen   (PerformSineatingAction)
                    │
                    ▼
                perform_sineating(): refuse if fallen / not set up / pair already performed
                                      in this scene / Mire at its stage cap,
                                    weave the Sineater's thread if the tether has none,
                                    roll sineating_check_type,
                                    take_on_corruption(): Sinner sheds through reduce_corruption
                                      (SINEATING), Sineater takes on through accrue_corruption
                                      (SINEATING_CARRIED, after resistance), MireHolding grows,
                                    refill the Hollow, count lifetime_helped,
                                    pay each party units x resonance_per_unit x earned_share
                                      (SineatingOutcomeAward for the rolled tier),
                                    write the Sineating audit row, delete the plea

(redirect — drains the Hollow on Sinner's casts)
   Sinner casts non-Celestial technique
                    │
                    ▼
                accrue_corruption() emits CORRUPTION_ACCRUING (Scope 7)
                    │
                    ▼
   Spec B subscriber:  iterate Sinner's active tethers (highest thread level first),
                       drain hollow_current by accrued amount,
                       lower payload.amount by what was absorbed,
                       overflow past the Hollow accrues to the Sinner as normal;
                       nothing passes on to the Sineater

(stage-advance dramatic prompt — Sineater opt-in)
   Sinner approaching Corruption stage advance
                    │
                    ▼
                emit CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (Scope 7)
                    │
                    ▼
   Spec B subscriber:  if Sinner has active tether and Sineater is in the same room,
                       fire PROMPT_PLAYER to Sineater with bonus offer
   Sineater →  `sineater brace` / web response  (0 = decline; 1..max = spend Hollow + take Strain)
                    │
                    ▼
                MODIFY_PAYLOAD on resist-check bonus, deduct from Hollow,
                add Strain severity to (sineater, resonance) instance

(rescue ritual — climactic recovery, stages 3+)
   Sineater initiates soul_tether_rescue ritual in the active scene with Sinner present
                    │
                    ▼
                perform_soul_tether_rescue():
                    refuse a fallen Sineater, find the scene from where both stand,
                    check + budget (the Sineater's thread level feeds the budget)
                    deduct Resonance, components, Strain severity
                    call reduce_corruption() (Scope 7 primitive)
                    write SoulTetherRescue audit row
                    increment lifetime_helped

(settling the Mire, the Sineater, later, on their own timing)
   Sineater reflects on "the Mire you carry for <Sinner>"  (a burden reflection, §7.5)
   chooses Absolve, Condemn or Succumb, then performs the settling rite
                    │
                    ▼
                mire_settling: Absolve/Condemn clear and reward, Succumb turns the Mire into
                the Sinner's resonance in the Sineater's aura and pays the Sinner,
                the fall pays every Sinner when the aura turns predominantly Abyssal
```

---

## 3. Affinity Gates and Multiplicity

### 3.1 Sineater eligibility

**Sineater must be Celestial-primary or Primal-primary affinity.** Non-Abyssal-primary characters can lead the role. (This once mirrored the Rite of Atonement's gate; that rite was removed in #4751.) Abyssal-primary characters cannot Sineater — their own corrupted nature is the wrong shape to anchor against.

The gate at formation reads the Sineater's primary affinity. Since #5177 it is also checked on every Sineating and every rescue, against the Sineater's aura as it is now: a Sineater whose `dominant_affinity` is Abyssal (`sineater_has_fallen`) is refused with `SineaterFallenError` ("<Name> has fallen too far into the Abyss to carry anyone's sins."). A Sineater falls by succumbing to the Mire until their aura is predominantly Abyssal (§7.5), and serves again once they have disowned enough to be predominantly something else. A sheet with no aura, or an aura with no shares, has not fallen.

### 3.2 Sinner eligibility

**Sinner must be non-Celestial-primary** — i.e., Abyssal-primary or Primal-primary. Celestial-primary characters cannot be Sinners because they don't accrue Corruption (Scope 7 §3.1: Celestial coefficient is 0).

The canonical case is Abyssal-primary Sinners. Since #4751 the canonical Primal coefficient is 0 (only Abyssal casts corrupt; Abyssal is 1.0), so a Primal-primary character accrues Corruption only from other sources, such as a redirect, and what they carry is cleared by passive decay (see §11). A Primal Sinner is mechanically meaningful only where a redirect or an authored non-zero Primal coefficient puts Corruption on them.

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

### 4.2 Sineater's Thread (woven at formation, gates personal benefits)

Forming a tether weaves a `RELATIONSHIP_CAPSTONE` Thread for the Sineater too (#5177). It sits on a ritual capstone of the Sineater's own side of the bond (the capstone the Sinner's thread sits on belongs to the Sinner's side, and a weave may only anchor to the weaver's own relationship side), through `weave_tether_bond_thread`, which skips the `ThreadWeavingUnlock` gate the Sineater never paid. The Sineater names the thread's resonance when the tether forms (`accept_soul_tether(sineater_resonance=...)`); with none named it is `default_sineater_resonance`: their strongest resonance of their main affinity, else the strongest they hold of any affinity. A resonance is never invented, so a Sineater who holds none has no thread yet. A sheet with no aura (a minted story NPC) gets an empty `CharacterAura` first (`ensure_aura`) so the affinity gates can run.

A tether formed before #5177 has no Sineater thread. `ensure_sineater_thread` weaves it the first time the Sineater performs Sineating or settles a burden, at the resonance they name or the default.

The Sineater's thread does three things:
- Its resonance is the one the Sineater earns from Sineating and from settling the Mire (§7), so each half of the bond earns in its own resonance.
- Its presence turns on the Sineater's `CORRUPTION_RESISTANCE` (§10). Resistance applies to a Sineater with any live thread on a tether, in any resonance.
- Its level feeds the rescue budget (`_get_sineater_thread_level`, §9.4). The lookup is for the Sineater's thread on this bond, whatever resonance it channels.

Higher-tier pull effects (vital bonuses, social bonuses, etc.) are authored later as concrete content.

### 4.3 Relationship cap on Thread level

Each Thread's maximum level is capped by the relationship's `developed_absolute_value` (sum of permanent points across all tracks). Concretely: `Thread.level <= floor(developed_absolute_value / N)` for tunable N (specific value settled at implementation).

This keeps relationship-RP and Resonance investment growing together. A player cannot grind Resonance into a paper-thin bond and weaponize it; the relationship must actually deepen for the Thread (and therefore the bond) to grow.

---

## 5. The Hollow and the Redirect Mechanic

### 5.1 Narrative framing (player-facing)

The Hollow is the **bond's sacred absence**, a space carved out by love that catches darkness before it reaches the Sinner. Every non-Celestial cast the Sinner makes deposits sins into the Hollow. When the Hollow fills with sins, no more can be absorbed; further casting accrues corruption to the Sinner directly. Sineating takes the sins out of the Hollow, opening it back up.

Mechanically: `hollow_current` is *available capacity remaining*. It decrements as sins fill it (corruption absorbed) and increments when a Sineating is performed. Player-facing copy and prose templates describe this in the Sineating framing, the field name is mechanical; the IC language is *sins held* / *sins taken on*.

### 5.2 Subscriber on `CORRUPTION_ACCRUING`

Spec B installs a subscriber on the `CORRUPTION_ACCRUING` reactive event (Scope 7 §3.2 emits this pre-mutation; payload includes `character_sheet`, `resonance`, `amount`, `source`, `redirect_origin`, mutable). The handler is `soul_tether_redirect_handler` in `world/magic/services/soul_tether.py`:

```python
def soul_tether_redirect_handler(*, payload):
    # An overflow re-call carries redirect_origin: skip it.
    if payload.redirect_origin is not None:
        return
    # Corruption a Sineater carries for a Sinner, and corruption a character adds by giving
    # in to a Compulsion, arrives whole: the carrier's own Hollow absorbs neither.
    if payload.source in (SINEATING_CARRIED, INDULGED):
        return

    # The Sinner-side threads on active tethers, in the accruing resonance.
    sinner_threads = _get_sinner_tether_threads_for_resonance(payload.character_sheet,
                                                              payload.resonance)
    remaining = payload.amount
    for thread in sorted(sinner_threads, key=lambda t: -t.level):   # strongest bond first
        absorbed = min(thread.hollow_current, remaining)             # locked re-fetch
        thread.hollow_current -= absorbed
        remaining -= absorbed

    payload.amount = remaining   # accrue_corruption short-circuits when this reaches 0
```

Key properties:
- **No Sineater-side effect during the redirect.** The handler only drains the Hollow. Corruption reaches the Sineater only through Sineating (§7), when the Sineater chooses to take it on.
- **Overflow is faithful, and it accrues to the Sinner.** If the Hollow can absorb 8 of a 12-unit accrual, the remaining 4 hit the Sinner normally, as the same accrual with a lower amount. Nothing passes on to the Sineater, and there is no second `accrue_corruption` call.
- **Priority across multiple tethers** is by Thread strength (highest level first). Drains spread across the strongest bonds.

### 5.3 Spec 7 contract divergence

Scope 7 §3.2 anticipated that the redirect would issue a "small trace amount of `accrue_corruption`" to the Sineater, so that the Sineater would accumulate Corruption from every absorption. **Spec B deliberately diverged**, and it still does: the redirect never writes to the Sineater, the Hollow's overflow accrues to the Sinner, and Strain only accrues at dramatic moments.

The Sineater's corruption now comes from one place instead: Sineating (§7). When a Sineater performs the ritual they choose how many units to take on, and that much of the Sinner's carried corruption moves onto them as the Mire, softened by their resistance (§10). The choice is theirs every time, so the "loss of identity" cost is something the player decides on, scene by scene, not a background tax. Anti-resentment (§1.3.1) holds: nothing reaches the Sineater from a partner's off-screen casting, and a Sineater who never performs Sineating carries nothing.

The `redirect_origin` parameter on `accrue_corruption` and `CorruptionSource.SPEC_B_REDIRECT` remain in the code. They were made for passing a Sinner's overflow on to a Sineater, which Sineating now does by choice through `take_on_corruption`; the handler above reads `redirect_origin` only as a recursion guard. Whether to remove them is a decision left to the maintainer (#5177).

---

## 6. Tether Strain Condition (Sineater Side)

### 6.1 One lazy ConditionInstance per Sineater

`TetherStrainTemplate` is a single authored `ConditionTemplate` row ("Tether Strain": 5 stages, severity-driven, `passive_decay_per_day` enabled). The `ConditionInstance` is lazy-created per Sineater, not per resonance (`_get_or_create_tether_strain_instance(sineater_sheet)`), the first time they take Strain at a dramatic moment: the template is not per-resonance at the database level, and a Sineater feeding two Sinners has one Strain condition whose severity both bonds add to. It has its own decay tick, stage-entry effects, and contribution to dramatic-moment costs.

### 6.2 When Strain accrues

Strain severity rises **only at dramatic moments**:

1. **Stage-advance prompt opt-in** (§7.2). When the Sineater accepts a bonus offer to help their Sinner pass a stage-advance resist check, the accepted commitment includes Strain severity.
2. **Rescue rituals** (§8). The Sineater takes Strain severity scaled to the Sinner's current stage when they perform the ritual.
3. **Hollow overflow opt-in** (deferred — not in MVP). A future iteration may allow the Sineater to opt in to absorbing past Hollow capacity, taking Strain in exchange. MVP just lets overflow hit the Sinner.

**Sineating produces no Strain.** The corruption a Sineater takes on is the Mire, not Strain, and Sineating costs no anima or fatigue (§7). The burden is what the Sineater chose to carry; Strain is a separate condition for the dramatic moments.

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

At Strain stages 4-5, stage-entry effects MAY include authored small-corruption-accrual aftermath in the matching resonance. Mechanically: the stage's `on_entry_conditions` M2M can include an authored `MagicalAlterationTemplate` (Scope 5) with `kind=CORRUPTION_TWIST` that calls `accrue_corruption` with a capped low amount. The Sineater starts to taste the darkness they have been carrying.

Strict bounds:
- Capped low enough that a fully-maxed Strain (stage 5 in every resonance) cannot, by itself, push the Sineater toward Subsumption.
- Authored content only — no automatic Strain-to-Corruption conversion. Specific alterations like "Tinged with Shadow," "Hungry Eyes," "Echoes of the Pit" are out of MVP scope (separate authoring spec).
- The `redirect_origin` parameter on the resulting `accrue_corruption` call is set to the Sinner's CharacterSheet for audit trail.

---

## 7. The Sineating Action

Sineating is a ritual with a roll, framed by poses in a shared scene (#5177). Telnet and the web both reach it through actions (`world/magic/services/sineating.py` holds the rules; `actions/definitions/sineating.py` the actions).

### 7.1 Sinner asks by pose, Sineater performs by pose

- The **Sinner** writes a pose and attaches a plea to it, naming the Sineater and how many units to offer. The others present see only the pose. The plea is `EntreatSineatingAction`, writing a `SineatingPendingOffer` (one per Sinner and Sineater pair, replaced by a repeat plea), and the Sineater is told privately that a plea waits.
- The **Sineater** writes a pose and attaches the ritual to it, choosing how many of the offered units to take on (`PerformSineatingAction`). The game rolls the configured check. The Sinner is told privately what happened; the Sineater reads their own result line. The room sees only the pose.
- The Sineater may instead decline (`DeclineSineatingAction`): the plea is removed, a `Sineating` audit row with `units_accepted = 0` is kept so achievements like "asked fifty times and was refused thirty" stay queryable, and `sineating.units_declined` rises.

The pose carries the act the way it carries a reflection (#5124). The pose action and the pose endpoint read `sineating_role` (`entreat` or `perform`), `sineating_partner_id` (the other character's sheet id) and `sineating_units`. `pending_sineating_from` checks every refusal before the pose is posted, and `record_pending_sineating` carries the act out after it is posted. A pose carries a reflection or a Sineating, not both. If the act is refused after the pose posted (a race), the pose stands and the writer is told why nothing happened.

Telnet: `pose/entreat <sineater>=<units> <text>` and `pose/sineat <sinner>=<units> <text>`; `sineater decline <sinner>`; `sineater pleas` lists the pleas waiting and what the Sineater carries per Sinner. Web: a Sineating row in the pose composer, built like `ReflectingOnRow`, listing the options from `GET /api/magic/sineating-options/`.

### 7.2 Service flow

```
request_sineating(sinner, sineater, units)          [written when the entreating pose posts]
    refuses: no active tether, Sineater has fallen, the pair do not share an active scene,
             the pair already performed Sineating in this scene, no Sinner thread,
             the Sinner does not accrue the tether's resonance, no capacity left
    units clamped to 1..per-scene cap (§7.3)
    update_or_create SineatingPendingOffer (resonance = the Sinner's tether thread's)
    stat sineating.requests_made += 1

perform_sineating(sinner, sineater, units)          [run when the performing pose posts]
    refuses (writing nothing): no plea waits; they no longer share the plea's active scene
             (the stale plea is deleted); Sineater has fallen; pair already performed in this
             scene (counted from Sineating rows with units_accepted > 0); Sineating not set up;
             the Sineater carries too much to take on any (the Mire stage cap, §7.4)
    atomic:
      ensure_sineater_thread()            the thread comes first: resistance acts on it
      roll cfg.sineating_check_type at cfg.sineating_difficulty_level, with the activity
        skill terms of MagicActivity.SINEATING
      look up SineatingOutcomeAward for the rolled tier (missing: refuse, nothing written)
      take_on_corruption(units x cfg.corruption_per_unit)   whatever the roll (§7.3, §7.5)
      refill the Hollow by units, capped at its maximum
      lifetime_helped += units on the Sineater's row in the tether's resonance
      each party earns floor(units x cfg.resonance_per_unit x earned_share), as
        GainSource.SINEATING: the Sinner in their thread's resonance, the Sineater in
        their own thread's resonance (nothing, with a line saying so, when they hold none)
      write the Sineating audit row (corruption_moved, corruption_taken, outcome, both
        earnings); delete the plea
    stat sineating.units_accepted += units
    sineating_lines(result) is what each party reads; telnet and the web say the same thing
```

The roll scales how much resonance both earn and nothing else. The units the Sineater chose move the corruption whatever the roll. `SineatingOutcomeAward` (an `OutcomeTierAward` with `earned_share`, one row per outcome tier) holds the share: 1.00 is a full share, 0.00 earns nothing, a share above 1.00 rewards a critical, and a better outcome never earns less than a worse one. What the check is, is a row in `SoulTetherConfig.sineating_check_type`; the code does not know or care which skill or stat it names. Until a check type is set and every outcome tier has an award row, the ritual refuses with "Sineating has not been set up yet." and the Required content page lists what is missing (`sineating_is_ready`).

### 7.3 What moves, and what is free

- Each unit refills the Hollow by 1 and moves `SoulTetherConfig.corruption_per_unit` (default 60) of the Sinner's corruption in the tether's resonance, never more than the Sinner carries. One number the Sineater chooses drives both.
- The Sinner's side goes down through `reduce_corruption` with `CorruptionRecoverySource.SINEATING` and without the resonance cleansing normally grants back, because the roll decides the earnings. The Sineater's side goes up through `accrue_corruption` with `CorruptionSource.SINEATING_CARRIED`, after the resistance of §10, and `MireHolding.amount` rises by what arrived. The Hollow's redirect handler skips this source, so the Sineater's own Hollow, if they are a Sinner on another tether, absorbs none of it.
- Sineating costs the Sineater no anima and no fatigue. `SoulTetherConfig.anima_cost_per_unit` and `fatigue_cost_per_unit`, the cost columns on `Sineating` and `SineatingPendingOffer`, and the old Sineater grant that was recorded in `mire_lifetime` are gone.
- Sineating is its own act, separate from the Anima ritual. Distinct social acts can be paired in one scene and each pays in full.

### 7.4 Per-scene cap and the Mire's stage cap

- **Per plea:** the units offered are clamped to a cap computed from the Sinner's thread: `min(per_scene_cap_hard_max, SOUL_TETHER_SCENE_CAP-lane baseline at the Sinner's thread rung + per_scene_cap_base)`. The cap bounds a single plea; it is not a running total across a scene. A pair performs Sineating once per scene, so the cap and the once-per-scene rule together bound what one pair moves in a scene. The once-per-scene rule is read from the `Sineating` audit rows.
- **Mire cap:** the Sineater's corruption in the resonance never reaches the threshold of the stage after `CorruptionConfig.sineater_max_stage` (the Compulsion stage in seeded content). `corruption_that_can_move` reports how much of the chosen amount fits, working backward through the Sineater's resistance. The ritual takes on only what fits and says so ("You could take on only part of it; settle some of the Mire to carry more."); when none fits it refuses with "You carry too much of the Mire to take on more. Settle some of it first." The Sinner sheds only what the Sineater takes on.

### 7.5 The Mire and settling it

The Mire is the corruption a Sineater carries for their Sinners, and the word means only that. It is held as corruption, so it climbs the same stages as a Sinner's, softened by the Sineater's resistance, and it stops at the Compulsion stage (§7.4). `MireHolding` (per Sineater-side `CharacterRelationship` and resonance: `amount`, `purified_since_payout`, `succumbed_since_fall`) records how much of the Sineater's corruption in a resonance came from which Sinner, so the holdings in a resonance never sum to more than that corruption. `services/mire.py` owns the writers: `take_on_corruption` and `release_mire` change `amount`, and `reduce_corruption` shrinks holdings in proportion when corruption falls for any other reason (decay, rescue, staff, and unheld corruption comes off first). `mire_carried_by` reads what a Sineater carries per Sinner, with the stage each resonance has reached; the web shows it to the Sineater only (`SoulTetherDetailSerializer.mire`, `SoulTetherStatusPanel`) and `sineater pleas` lists it on telnet.

The Sineater settles the Mire whenever they like, in whatever amounts they like; one large settling and several small ones give the same total. They write a reflection whose subject is the burden taken from one Sinner (`Reflection.tether`, `ReflectionTargetKind.BURDEN`), as a pose in a scene or a journal entry, and choose one of three things. Then they perform the settling rite, which carries each burden out at the rite's share `s`, after the disowned deeds and before the embraced ones (`services/mire_settling.py`). For each resonance held from that Sinner:

| Choice | What the rite does at share `s` |
|--------|----------------------------------|
| Absolve | `floor(held x s)` leaves the Mire, with no resonance granted back. `purified_since_payout` rises by it. The Sineater earns `purify_reward_percent` of it in their own thread's resonance (`GainSource.MIRE_PURIFIED`), and their side of the tie moves toward affection by `absolve_affection` scaled by `s` (`move_gauges`). |
| Condemn | The same, and the tie moves toward conflict by `condemn_conflict`. |
| Succumb | `floor(held x s)` leaves the Mire and becomes that much of the Sinner's resonance in the Sineater's own aura (`GainSource.SUCCUMBED`), which can make them Unsettled. `succumbed_since_fall` rises by it. The Sinner earns `succumb_bonus_percent` of the amount succumbed plus `jackpot_percent` of everything the Sineater purified for them since the last payout, in their thread's resonance (`GainSource.SUCCUMB_BONUS`), and the jackpot resets to 0. Both tie gauges move (`succumb_affection`, `succumb_conflict`). The Sinner's `sineater.succumbed` and `sineater.succumbed_amount` stats rise. |

The jackpot is the tether's, however many resonances it is held in: it builds while the Sineater resists, pays out on a Succumb and resets. Succumbing is always the player's choice; absolving or condemning gives a respectable reward, and succumbing gives the Sinner the most.

Atoning: the `SUCCUMBED` grant is a deed that carries the burden reflection that caused it, so the Sineater can later reflect on the succumbing itself (the reflection control names it by the pose or journal entry where they did it) and Embrace or Disown it like any deed, one reflection per grant. Atoning repairs their aura and does not restore the jackpot. A Sineater can also disown the unsettling resonance as a whole, as anyone Unsettled can.

**The fall.** After a Succumb, if the Sineater's `dominant_affinity` is Abyssal, each Sinner with `succumbed_since_fall` above 0 is paid `fall_payout_percent` of it in their thread's resonance (`GainSource.SINEATER_FALL`), the Sinner of the most recent succumbing is paid `fall_breaker_bonus_percent` more on top, every counter resets (the reset is what stops a second payout for the same fall), and the Sinner's `sineater.broken` stat rises. From then on the Sineater is refused for Sineating and rescue (§3.1) until their aura is predominantly something else.

An NPC a GM runs can be a Sineater and does all of this the same way: presence is by character (`shared_active_scene`: both characters stand in the same room and it has a live scene), not by pairing the players' accounts, and the NPC's GM writes the poses, chooses the amounts, reflects and settles as the NPC. Stats and gains key on the sheet, so an NPC Sineater counts.

What the Mire does to the Sineater: the corruption stage conditions, the early-stage display as Intrusive Thoughts and Compulsion, and the Compulsion's penalty and lifting are described in `docs/architecture/corruption.md`; the same code serves a Sinner and a Sineater because it reads corruption, not the tether. Settling below the Compulsion stage clears the Compulsion.

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

    # Find a Sineater partner standing in the same room as the Sinner
    sineater_in_scene = _find_sineater_in_location(tethers, sinner_location)
    if sineater_in_scene is None:
        return  # No prompt fires; resist check proceeds normally

    # Fire PROMPT_PLAYER to the Sineater (a PendingStageAdvanceOffer row is written when
    # shared_active_scene finds the pair's active scene)
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

When the Sineater `@reply`s with their commitment, the bonus is added to the resist check via `MODIFY_PAYLOAD` on `current_bonus`, the appropriate amount drains from the Hollow, and Strain severity is added to the Sineater's Tether Strain ConditionInstance (§6.1). The resist check then resumes.

### 8.2 Decline path

If the Sineater declines (`@reply 0`) or isn't reachable, the resist check proceeds unchanged. The Sinner's stage advance fires per Scope 7's normal logic. This is by design — the dramatic prompt is opt-in, and a decline produces a real narrative consequence (the Sinner advances). Both choices have IC weight.

---

## 9. Rescue Ritual

### 9.1 Single scaling ritual

The rescue ritual is a single `Ritual` row authored under Spec A's machinery (`dispatch_kind=SERVICE`, components, prose templates). Service function: `perform_soul_tether_rescue`.

### 9.2 Gates and preconditions

- Sinner has at least one Corruption ConditionInstance at stage 3+.
- Sineater is the Sinner's tethered partner on at least one bond (`is_soul_tether=True`, `soul_tether_role=SINEATER`).
- The Sineater has not fallen (`SineaterFallenError`, §3.1).
- Both are in the same active scene. The scene is found from where the two characters stand (`shared_active_scene`, by character, not by pairing player accounts), so an NPC Sineater a GM runs can perform the rescue; a scene passed in must be that one.
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
    # the Sineater's thread on this bond in this resonance (woven at formation, §4.2)
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
- By the units chosen on every performed Sineating, in the tether's resonance (§7.2).
- By `severity_reduced` on every rescue ritual (§9.4 service flow).

Permanence: never decreases. Survives bond dissolution. Survives partner death. The Sineater carries what they earned forever.

### 10.2 Resistance applies to a Sineater with any live thread on a tether

Per principle §1.3.2, the resistance benefit manifests only for a Sineater who has a Sineater-side `RELATIONSHIP_CAPSTONE` Thread. Since #5177 formation weaves that thread, so every Sineater with a tether and a resonance to channel has one (§4.2); a tether formed earlier gets it the first time its Sineater performs Sineating.

`_apply_sineater_corruption_resistance` in `world/magic/services/corruption.py` applies the resistance inside `accrue_corruption`:

- It applies when the character owns any live Sineater-side thread (`_get_sineater_threads_for(sheet)`, which looks for a live `RELATIONSHIP_CAPSTONE` thread on a ritual capstone of a tether where the sheet is the Sineater, in any resonance), and `CharacterResonance.lifetime_helped > 0` for the resonance being accrued.
- The thread's own resonance does not need to match the accruing resonance. The Sineater's thread channels the resonance they earn, which is not the resonance of the corruption they carry. The size of the resistance comes from `lifetime_helped` in the resonance being accrued.
- `effective_amount = ceil(amount x max(0.1, 1 - lifetime_helped / SoulTetherConfig.resistance_full_at))`. At `resistance_full_at` units of lifetime Sineating in that resonance (default 1000) resistance reaches its 90% cap; before that it is proportional, so half that much resists 50%.
- It softens corruption the Sineater takes on through Sineating (`SINEATING_CARRIED`) and corruption their own casting writes. It does not apply to corruption they choose to indulge by giving in to a Compulsion (`INDULGED`): the resistance a Sineater earns softens what they take on and cast, not what they choose to add to themselves.
- A recursion guard skips it when `redirect_origin` is set (an overflow re-call).

Before #5177 the formula divided by a hard-coded 1000 in `corruption.py` and applied only to a Sineater who had bought a thread of their own in the very resonance being accrued, which no flow prompted them to do. The divisor is now `SoulTetherConfig.resistance_full_at` and the thread exists. The Sineating ritual weaves the thread before it takes the corruption on, and `corruption_that_can_move` reads the resistance too, so the stage cap (§7.4) is worked out against what would arrive.

### 10.3 Implementation note

This is an inline step in `accrue_corruption`, not a `ThreadPullEffect` resolved through `resolve_pull_effects`; the `CORRUPTION_RESISTANCE` effect-kind of §15.3 names the benefit, and the multiplier is computed on demand from `lifetime_helped` with no stored amount.

---

## 11. Companion Piece: Passive Corruption Decay Tuning

This is **not a Soul Tether feature** — it's a small piece of Corruption tuning that the Soul Tether design assumes. Listed here because the spec hangs together only with this floor in place.

Author `passive_decay_per_day` and `passive_decay_max_severity` values on the existing reference Corruption `ConditionTemplate` rows (one per the first authored Primal and Abyssal Resonance, seeded by `author_reference_corruption_content()`; the named "Wild Hunt"/"Web of Spiders" rows were removed in #2967) and any future Corruption templates. Tuning numbers (settled at implementation, not in this spec):

- Primal-flavored Corruption: decay rate sufficient to fully clear a low-tier Primal-primary character's accrual over a small number of days. *Primal users below mid-tier do not need a Sineater.*
- Abyssal-flavored Corruption: decay rate slow enough that an Abyssal-primary character past tier 1 cannot rely on decay alone. *Abyssal users post-tier-1 need a Sineater; corruption falls only through a Sineater's Sineating or rescue, or daily decay (the Rite of Atonement was removed in #4751).* Decay comes off a Sineater's own corruption that is not held for anyone first, then off what they hold for their Sinners in proportion (`reduce_corruption` shrinks the `MireHolding` rows to stay within the corruption).

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
- The Sinner has purchased their `ThreadWeavingUnlock` for `RELATIONSHIP_CAPSTONE` and has Resonance available to weave their first Thread on the bond. (No requirement on Sineater: formation grants their thread.)

**No relationship-strength prerequisite.** Anyone with an active relationship can attempt formation. The relationship-cap on Thread level (§4.3) keeps early tethers mechanically weak until the relationship deepens.

### 12.3 Ritual mechanics

The ritual has low-DC performance check; failure means the bond doesn't form (no catastrophic outcome). Components are authored — likely shared symbolic items (a strand of hair, a witnessed token, a written name). Specific authoring is implementation, but the IC framing is **witchy** — explicit ritual language, candles-and-circle vibes, sacred-named promises.

### 12.4 Service flow

```python
def accept_soul_tether(initiator_sheet, partner_sheet, sinner_role, resonance,
                       ritual_components, sineater_resonance=None):
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
    sinner_sheet = initiator_sheet if sinner_role == "SINNER" else partner_sheet
    sineater_sheet = partner_sheet if sinner_role == "SINNER" else initiator_sheet
    ensure_aura(sinner_sheet); ensure_aura(sineater_sheet)   # a minted NPC has no aura (#5177)

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
                "SINNER" if rel.source_id == sinner_sheet.id else "SINEATER"
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
        # sinner_thread.hollow_current starts at 0, a Sineating refills it.

        # #5177: the Sineater's own thread, on a ritual capstone of the Sineater's own side
        # (the capstone above belongs to the Sinner's side, and a weave may only anchor to the
        # weaver's own side). weave_tether_bond_thread skips the unlock gate.
        weave_tether_bond_thread(
            sineater_sheet, sineater_side_capstone,
            sineater_resonance or default_sineater_resonance(sineater_sheet),
        )

    write_capstone_audit_row(...)
    fire_event(SOUL_TETHER_FORMED, ...)
```

The Sineater's Thread is part of formation (#5177, §4.2); only a Sineater who holds no resonance at all is left without one until they do. Formation also gives a sheet with no aura an empty `CharacterAura` (`ensure_aura`) before the affinity gates run, so a minted story NPC can join a tether.

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

Written every time a Sineating is performed or declined. Fields:

| Field | Type | Notes |
|-------|------|-------|
| `sinner_sheet` | FK CharacterSheet | |
| `sineater_sheet` | FK CharacterSheet | |
| `relationship` | FK CharacterRelationship | for join queries |
| `scene` | FK Scene, nullable | |
| `resonance` | FK Resonance | the tether's resonance |
| `units_offered` | PositiveIntegerField | what the Sinner asked for |
| `units_accepted` | PositiveIntegerField | 0 = declined; 1..N = performed with that many units |
| `corruption_moved` | PositiveIntegerField | corruption that left the Sinner |
| `corruption_taken` | PositiveIntegerField | corruption that arrived on the Sineater, after their resistance |
| `outcome` | FK CheckOutcome, nullable | the outcome of the Sineater's roll; empty for a declined plea |
| `sinner_resonance_earned` | PositiveIntegerField | resonance the Sinner earned in their thread's resonance |
| `sineater_resonance_earned` | PositiveIntegerField | resonance the Sineater earned in their thread's resonance |
| `created_at` | DateTimeField | |

Indexes on `(sinner_sheet, -created_at)`, `(sineater_sheet, -created_at)`, `(relationship, -created_at)`. The `anima_cost` and `fatigue_cost` columns of the first design were removed in #5177. The once-per-pair-per-scene rule reads these rows (`units_accepted > 0`).

#### `SineatingPendingOffer`

The Sinner's plea, one row per `(sinner_sheet, sineater_sheet)` pair. Written by `request_sineating`, consumed (then deleted) by `perform_sineating` or `decline_sineating`, and read by `GET /api/magic/soul-tether/sineating/pending/`. A plea the pair has left the scene of is stale and deleted when the ritual is performed.

#### `MireHolding`

How much corruption a Sineater carries for one Sinner in one resonance, and the two running totals the settling rite pays from. Unique on `(relationship, resonance)`, where `relationship` is the Sineater's own `CharacterRelationship` side toward the Sinner (unique per pair, and it outlives a tether being dissolved and formed again).

| Field | Type | Notes |
|-------|------|-------|
| `amount` | PositiveIntegerField | corruption held from this Sinner in this resonance; partitions the Sineater's `corruption_current`, not a copy of it |
| `purified_since_payout` | PositiveIntegerField | the jackpot's base: what the Sineater has absolved or condemned for this Sinner since the last Succumb payout |
| `succumbed_since_fall` | PositiveIntegerField | what the Sineater has succumbed to for this Sinner since their last fall; sizes this Sinner's share of the fall's payout |

The holdings in a resonance never sum to more than the Sineater's `corruption_current` in it. `take_on_corruption` and `release_mire` write `amount`; `reduce_corruption` shrinks it when corruption falls for any other reason.

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

Two persistent fields from the first design, each the **single source of truth** for the value it represents (not denormalizations of other state):

- `Thread.hollow_current`, the current Hollow capacity on a Sinner-side `RELATIONSHIP_CAPSTONE` Thread (§4.1, §5). Mutated only by the `CORRUPTION_ACCRUING` redirect handler (drain), `perform_sineating` (refill) and the stage-advance commitment (spend). Not derived from anything.
- `CharacterResonance.lifetime_helped`, the per-resonance monotonic counter on the Sineater (§10.1). Incremented only by `perform_sineating` and `perform_soul_tether_rescue`. Permanent.

Per-relationship and per-Thread aggregates (e.g., "total units this Sineater has accepted on bond X") are *not* stored — they are computed by aggregation over audit rows on demand. No additional fast-path counters in MVP. Audit rows plus the join to `CharacterRelationship` are sufficient for any achievement query, including compound queries by track type.

### 14.3 Stat integration

Each service fires `world.achievements.services.increment_stat()` for a small set:

| Stat | Fired by | Per-event amount |
|------|----------|------------------|
| `sineating.units_accepted` | `perform_sineating`, on the Sineater | units chosen |
| `sineating.units_declined` | `decline_sineating`, on the Sineater | 1 |
| `sineating.requests_made` | `request_sineating`, on the Sinner | 1 |
| `sineater.succumbed` | a Succumb at the settling rite, on the Sinner | 1 |
| `sineater.succumbed_amount` | a Succumb at the settling rite, on the Sinner | the Mire succumbed |
| `sineater.broken` | the fall's payout, on each Sinner paid | 1 |
| `rescue.performed` | `perform_soul_tether_rescue` | 1 |
| `rescue.stage5_save` | `perform_soul_tether_rescue` (stage_at_start=5) | 1 |
| `rescue.severity_reduced` | `perform_soul_tether_rescue` | `severity_reduced` |
| `tether.formed` | `accept_soul_tether`, on the Sinner | 1 |

Stats key on the sheet, so an NPC Sineater and the Sinners of an NPC Sineater count the same as player characters'.

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

#### `magic.Sineating`, `magic.SineatingPendingOffer`, `magic.MireHolding`
Per §14.1.

#### `magic.SoulTetherRescue`
Audit row per §14.1.

#### `magic.SineatingOutcomeAward`
One row per `CheckOutcome` tier: `earned_share`, the fraction of full resonance each party earns from a Sineating whose roll landed on that tier (§7.2). Staff author it; `sineating_is_ready` and the Required content page ask for a row on every tier.

#### `magic.TetherStrainTemplate`
Not a new model class — an authored `ConditionTemplate` row. Migration creates it; admin/seeds may extend stage-entry effects later.

#### `magic.SoulTetherConfig` (singleton tuning surface)

SharedMemoryModel singleton (pk=1). All Soul Tether tuning knobs, Sineating, settling the Mire, resistance, and the rescue's costs, caps and budget formulas, are read from this row rather than from module constants, so staff can adjust them via the admin without a code change. Lazy-created via `get_soul_tether_config()` in `world/magic/services/soul_tether.py`. The sizes are listed for staff in #5179.

Fields:

| Field | Default | Meaning |
|-------|---------|---------|
| `sineating_check_type` | unset | The check the Sineater rolls to perform Sineating. Unset: the ritual refuses ("Sineating has not been set up yet.") |
| `sineating_difficulty_level` | 0 | Its difficulty as a level |
| `corruption_per_unit` | 60 | Corruption one unit moves from the Sinner to the Sineater |
| `resonance_per_unit` | 5 | Resonance one unit earns each party at a full share |
| `per_scene_cap_hard_max` | 20 | Absolute ceiling on units offered in one plea |
| `per_scene_cap_base` | 5 | Base cap before level scaling |
| `soul_tether_cap` lane (`ModifierLevelBaseline`) | 2 per rung | Cap added at the Sinner's thread rung (10 thread levels) (#5093) |
| `hollow_max` lane (`ModifierLevelBaseline`) | 10 per rung | Max Hollow capacity at the Sinner's thread rung (#5093) |
| `purify_reward_percent` | 50 | Of the corruption an Absolve or Condemn clears, what the Sineater earns |
| `absolve_affection` / `condemn_conflict` / `succumb_affection` / `succumb_conflict` | 5 each | How far the tie moves at a full share |
| `succumb_bonus_percent` / `jackpot_percent` | 200 / 25 | What the Sinner earns on a Succumb, of the amount succumbed and of what was purified since the last payout |
| `fall_payout_percent` / `fall_breaker_bonus_percent` | 300 / 50 | What each Sinner earns when the Sineater falls, and the extra for the most recent |
| `resistance_full_at` | 1000 | Lifetime Sineating in a resonance at which resistance reaches its 90% cap |
| `rescue_strain_stage3/4/5` | 5/10/18 | Strain thresholds for rescue at each Sinner stage |
| `rescue_resonance_stage3/4/5` | 10/20/35 | Resonance cost for rescue at each Sinner stage |
| `rescue_budget_base_stage3/4/5` | 60/120/250 | Base severity-reduction budget per stage |
| `rescue_budget_base_mult_tenths` | 10 (→ 1.0) | Base multiplier in tenths |
| `rescue_budget_success_mult_tenths` | 5 (→ 0.5) | Success-level multiplier in tenths |
| `RESCUE_BUDGET_THREAD` lane (`ModifierLevelBaseline`) | 50 a rung (→ 0.5) | Thread term in hundredths at the Sineater's thread rung (#5093) |

`anima_cost_per_unit` and `fatigue_cost_per_unit` were removed in #5177.

### 15.2 Modifications to existing models

#### `magic.Thread`
Add `hollow_current` (PositiveIntegerField, default 0). Documented as "Only meaningful for `RELATIONSHIP_CAPSTONE` Sinner-side Threads. Other Threads ignore."

#### `magic.CharacterResonance`
Add `lifetime_helped` (PositiveIntegerField, default 0, monotonic). Mirrors `lifetime_earned`'s semantics. (`mire_lifetime`, added by #5123, was removed in #5177.)

#### `magic.Reflection`
Gains `tether` (nullable FK to the Sineater's `CharacterRelationship` side), `ReflectionTargetKind.BURDEN`, and the choices `ABSOLVE`, `CONDEMN` and `SUCCUMB`, for settling the Mire (§7.5).

#### `relationships.RelationshipCapstone`
Add `is_ritual_capstone` (BooleanField, default False) and `ritual` (FK `magic.Ritual`, nullable).

#### `relationships.CharacterRelationship`
No model change — `is_soul_tether` and `soul_tether_role` already shipped (Spec A §2.2).

### 15.3 New `ThreadPullEffect.effect_kind` enum value

`CORRUPTION_RESISTANCE`, names the Sineater's resistance benefit, whose runtime value derives from the Sineater's `lifetime_helped` in the resonance being accrued (§10). The multiplier is computed inline by `_apply_sineater_corruption_resistance` in `accrue_corruption`, not by `resolve_pull_effects`.

### 15.4 Authored content (data, not migration code)

- `Ritual` rows: `accept_soul_tether`, `soul_tether_rescue`. Both `dispatch_kind=SERVICE`.
- `RitualComponentRequirement` rows for both rituals.
- `ImbuingProseTemplate` or equivalent prose for the Hollow / Sineating / rescue events.
- Authored `ConditionTemplate` for `TetherStrainTemplate` with 5 stages, each with severity_threshold and stage-entry effects per §6.3.
- `passive_decay_per_day` values on the existing reference Corruption `ConditionTemplate` rows per §11.

---

## 16. Service Functions

All in `world/magic/services/soul_tether.py` unless noted.

| Function | Purpose |
|----------|---------|
| `accept_soul_tether(initiator_sheet, partner_sheet, sinner_role, resonance, ritual_components, sineater_resonance=None)` | Formation, including the Sineater's thread. §12.4. |
| `dissolve_soul_tether(relationship, initiator_sheet)` | Stub. §13. |
| `ensure_sineater_thread(sineater_sheet, sinner_sheet, resonance=None)` | The Sineater's live thread on a tether, woven when absent. §4.2. |
| `default_sineater_resonance(sineater_sheet)` | The resonance a Sineater's thread channels when they name none. §4.2. |
| `sineater_has_fallen(sineater_sheet)` | True when the Sineater's aura is predominantly Abyssal. §3.1. |
| `shared_active_scene(first_sheet, second_sheet)` | The active scene two characters are both in, by character, or None. Used by Sineating, the rescue and the stage-advance offer. |
| `perform_soul_tether_rescue(sineater_sheet, sinner_sheet, resonance, components, scene=None)` | Rescue ritual. §9.4. |
| `get_soul_tether_config() -> SoulTetherConfig` | Lazy-create the singleton (pk=1). |

In `world/magic/services/sineating.py`:

| Function | Purpose |
|----------|---------|
| `request_sineating(sinner_sheet, sineater_sheet, units)` | The Sinner's plea; writes the `SineatingPendingOffer`. §7.2. |
| `perform_sineating(sinner_sheet, sineater_sheet, units)` | The ritual: roll, move corruption, refill the Hollow, pay both. §7.2. |
| `decline_sineating(sinner_sheet, sineater_sheet)` | The Sineater turns the plea down; keeps a declined audit row. |
| `sineating_lines(result)` | What each party reads afterward; telnet and the web share it. |
| `sineating_is_ready(config=None)` | Whether a check type is set and every outcome tier has an award. |
| `sineating_options_for(sheet)` | What a character can attach to a pose now; the composer's picker. |
| `pending_sineating_from(sheet, params)` / `record_pending_sineating(pending)` | Check a pose's Sineating before it posts and carry it out after. |

In `world/magic/services/mire.py`:

| Function | Purpose |
|----------|---------|
| `take_on_corruption(*, sineater_sheet, sinner_sheet, resonance, amount, max_stage=None)` | Move corruption from the Sinner to the Sineater and grow the holding. |
| `corruption_that_can_move(...)` | What `take_on_corruption` would move for an amount, without writing. |
| `corruption_ceiling(resonance, max_stage)` | The most corruption a character can hold in a resonance and stay at `max_stage`. |
| `release_mire(*, holding, amount)` | Lower the Sineater's corruption and one holding together. |
| `add_to_largest_holding(sheet, resonance, amount)` | Give corruption added by giving in to a Compulsion to the largest holding. |
| `mire_carried_by(sineater_sheet)` / `mire_for_sinner(...)` | What a Sineater carries, per Sinner and resonance, with its stage. |

Settling the Mire is `world/magic/services/mire_settling.py` (`apply_burden`, `apply_fall`), called by the settling rite in `drift_correction.py`.

---

## 17. Reactive Subscribers

Two `flows.TriggerDefinition` rows (`soul_tether_redirect` and `soul_tether_stage_advance_prompt`), authored as content and seeded by `wire_soul_tether_active_template()`. `_install_soul_tether_triggers` attaches them to the Sinner's object the first time they form a tether; each runs a SERVICE flow step that calls the handler in `world/magic/services/soul_tether.py`.

| Subscriber | Event | Handler |
|------------|-------|---------|
| `soul_tether_redirect_handler` | `CORRUPTION_ACCRUING` | Drain Hollow on Sinner's tethered Threads and lower `payload.amount` to the unabsorbed remainder. §5.2. |
| `soul_tether_stage_advance_prompt` | `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` | Fire `PROMPT_PLAYER` for Sineater bonus offer. §8.1. |

---

## 18. API Surface

DRF views in `world/magic/views.py` and `world/magic/views_sineating.py`, routed under `/api/magic/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `soul-tether/accept/` | POST | Formation; validates consent and gates. Calls `accept_soul_tether`. |
| `soul-tether/dissolve/` | POST | Stub dissolution. Calls `dissolve_soul_tether`. |
| `soul-tether/rescue/` | POST | Sineater performs rescue. Calls `perform_soul_tether_rescue`. |
| `soul-tether/{relationship_id}/` | GET | Tether state: Hollow current/max, Thread levels, lifetime stats, and, to the Sineater only, the Mire they carry for the Sinner (`mire`). Only the two parties of the bond (an NPC a GM runs counts as played) and staff read it; anyone else gets a 404. |
| `sineating-options/?character_sheet=<id>` | GET | What the character can attach to a pose now: a plea to make to each Sineater bonded to them who is here, and a plea to answer for each one waiting. Only a character the requester plays. |
| `soul-tether/sineating/decline/` | POST | The Sineater turns a waiting plea down (`{actor_sheet_id, sinner_sheet_id}`); runs `DeclineSineatingAction`. |
| `soul-tether/sineating/pending/` and `.../{id}/` | GET | The pleas waiting for the requester's characters. |
| `soul-tether/stage-advance/pending/`, `.../{id}/` and `stage-advance/respond/` | GET / POST | The stage-advance bonus offer and its answer. |

The plea and the ritual are not endpoints of their own: they ride a pose (`sineating_role`, `sineating_partner_id`, `sineating_units` on the pose endpoint, §7.1). The earlier `soul-tether/sineating/request/` and `soul-tether/sineating/respond/` routes were removed in #5177.

All endpoints use serializer-level validation per project pattern; views are thin delegations to services and actions.

---

## 19. Testing Strategy

### 19.1 Journeys

The player-facing paths are journeys on the real seams (`integration_tests/test_sineating_journeys.py`, `test_mire_settling_journeys.py`, `test_impulse_journeys.py`): a plea and the ritual by telnet pose and by the web pose endpoint with every refusal, an NPC Sineater a GM runs, Absolve by journal and Condemn by pose, Succumb and atoning for it, the fall, and the impulses at each stage. The curated list is `docs/testing/journeys.md`.

### 19.2 Service and integration tests

- `world/magic/tests/test_sineating.py`: the ritual's arithmetic and each refusal, with the removed costs gone.
- `world/magic/tests/test_mire_settling.py`: Absolve, Condemn, Succumb, the jackpot, the fall.
- `world/magic/tests/test_impulses.py`: the impulses and the Compulsion.
- `world/magic/tests/test_soul_tether_services.py` and `test_soul_tether_resistance.py`: formation (including the Sineater's thread), the rescue's gates and costs, and the resistance.
- `src/world/magic/tests/integration/test_soul_tether_flow.py`: formation pipeline, the Hollow redirect, the stage-advance prompt, the rescue at stages 3, 4 and 5, dissolution, many-to-many independence (one Strain instance shared across a Sineater's bonds, one Hollow per Sinner thread), and the anti-resentment invariant (a dormant tether costs both characters nothing).
- `integration_tests/fuzz/test_unsettled_invariants.py`: the Mire holdings never exceed the corruption.

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
- **Rules for one NPC Sineater shared by several GMs** and **magical scars** that reuse the impulse conditions, separate work (#5177 keeps scars possible).
- **Tuning numbers** (Hollow capacity formulas, refill caps, Strain decay rates, resistance thresholds, ritual difficulties, corruption and resonance per unit, the settling sizes), settled at implementation, staff-tunable via admin where appropriate.
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
2. **Per-plea Sineating cap**: `SOUL_TETHER_SCENE_CAP` lane at the Sinner's thread rung plus `per_scene_cap_base`, capped at `per_scene_cap_hard_max`. Same.
3. **Corruption and resonance per unit, and the outcome shares**: `SoulTetherConfig` and `SineatingOutcomeAward` (#5179).
4. **Strain decay rate** — `passive_decay_per_day` value on `TetherStrainTemplate`. Tuned so a maxed Strain naturally returns to baseline within weeks.
5. **Resistance threshold**: `SoulTetherConfig.resistance_full_at`, the `lifetime_helped` value at which 90% reduction caps.
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
| `accrue_corruption(redirect_origin=...)` | Scope 7 §3.2 | Spec B §5.2 (recursion guard only; the Strain stage-entry accrual of §6.4 is not built) |
| `accrue_corruption` / `reduce_corruption` with `SINEATING_CARRIED`, `SINEATING`, `MIRE_SETTLED` sources | #5177 | §7.3 Sineating, §7.5 settling the Mire |
| `reduce_corruption()` | Scope 7 §3.3 | Spec B §9.4 rescue ritual, §7.3 Sineating |
| `is_protagonism_locked` aggregator | Scope 7 §3.6 | Naturally handled by `reduce_corruption` cleanup |
| `PROMPT_PLAYER` flow step + `@reply` | Scope 5.5 | Spec B §8.1 |
| `MODIFY_PAYLOAD` flow step | Scope 5.5 | Spec B §8.1 (resist-check bonus) |
| `Thread`, `ThreadPullEffect`, `Ritual`, `RitualComponentRequirement` | Spec A | Spec B §4, §10, §12, §9 |
| `RELATIONSHIP_CAPSTONE` `target_kind` and `is_soul_tether` storage | Spec A §5, §2.2 | Spec B §4 |
| `ThreadWeavingUnlock` for `RELATIONSHIP_CAPSTONE` | Spec A | Spec B §4.1, §12.2 |
| `passive_decay_per_day` on `ConditionTemplate` | Scope 6 | Spec B §6, §11 |
| `decay_condition_severity`, `decay_all_conditions_tick` | Scope 6 | Spec B §6.3 (Strain decay), §11 (Corruption decay) |
| `perform_check`, `CheckOutcome` | World mechanics | Spec B §9.4 |
| `perform_check_with_modifiers`, `OutcomeTierAward` | World checks | Spec B §7.2 (the Sineating roll and its outcome table) |
| `move_gauges` | Relationships app | Spec B §7.5 (Absolve, Condemn and Succumb move the tie) |
| The settling rite and `Reflection` | #5124 | Spec B §7.5 (burden reflections) |
| `world.achievements.services.increment_stat` | Achievements app | Spec B §14.3 |
| Capstone consent flow, `RelationshipCapstone` | Relationships app | Spec B §12.1 |

This is a richly-woven feature — almost every infrastructure piece this game has built feeds into Soul Tether, which is exactly why it's a strong test of the systems.

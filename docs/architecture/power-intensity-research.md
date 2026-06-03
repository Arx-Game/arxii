I have enough verified ground truth. Key corrections from my code read: `target_damage_type` and `target_check_type` FKs already exist on `ModifierTarget` (the archaeology claimed damage-type scoping was non-existent), and `EQUIPMENT_RELEVANT_CATEGORIES` currently holds `{stat, magic, affinity, resonance}` (notably NOT `technique_stat`). These shape the candidate directions. Writing the report now.

# Power vs. Intensity in Arxii Magic — Research Landscape Report

*Status: exploratory considerations document. No design is selected. The purpose is to map the option space, anchor it in the actual code, and surface tradeoffs for a later design conversation.*

---

## 1. Executive summary

Arxii's magic system already has a load-bearing axis split baked into every technique: **intensity** (raw power channeled) and **control** (safety/precision). When intensity outruns control at runtime, anima cost spikes, mishap pools escalate, and Soulfray/corruption accrue. This is the engine of the "heroic sacrifice" tension and it works.

The problem the user wants to solve is that this single `intensity` axis is doing **two conceptually different jobs at once**:

- **What the caster CHANNELS** — drives anima cost, control-deficit/mishap selection, resonance/corruption attribution, Soulfray. A ward thrown by a *defender* must never reduce this; reducing it would mean the caster magically paid less for what they poured in.
- **The EFFECTIVE MAGNITUDE the working carries into the world** — drives damage budgets, condition severity/duration, capability grants. This is the lever that *should* be modifiable pre-cast (wards, amps) and via persistent buffs ("+power to fire spells").

Today these two jobs collapse onto the same `technique.intensity` value, read by two parallel functions (`get_runtime_technique_stats` for the magic envelope, `compute_effective_intensity` for combat resolution). There is no place to insert a "power" modifier that changes what lands without also changing what the caster paid. The user's framing — **intensity = channeled (immutable by defenders), power = effective magnitude (modifiable)** — is precisely the separation that mature systems (Ars Magica's Casting Total vs Penetration, GAS's BaseValue vs CurrentValue, PoE's base × modifier pools) institutionalize.

Why now: the magic north-star (cast → pose → log → outcome) needs legible, modifiable outcomes; pre-cast wards/amps and persistent buffs are on the near roadmap; and there is an existing, unwired reactive `TECHNIQUE_PRE_CAST` MODIFY_PAYLOAD hook whose mutations are currently **discarded** (`world/magic/services/techniques.py` reads pre-event `stats.intensity` after emit, never the modified payload). The architecture is at a fork: either reconcile the two intensity computations now, or accrete a third.

---

## 2. Current state of the code

### 2.1 Two intensity computations — parallel implementations, by design but undocumented

There are **two independent functions** producing "effective intensity," at different abstraction levels, with no shared code path:

**`get_runtime_technique_stats(technique, character)`** — `world/magic/services/techniques.py:156-208` (verified). Returns `RuntimeTechniqueStats(intensity, control)`. Combines four streams in sequence:
1. Base `technique.intensity + technique.control` (`:168-170`).
2. **Identity stream** via `CharacterModifier` rows on `technique_stat` ModifierTargets named `"intensity"`/`"control"` (`:181-184`, using `get_modifier_total`).
3. **Process stream** from `CharacterEngagement.intensity_modifier`/`control_modifier`, or `+social_safety` to control when unengaged (`:190-195`).
4. **IntensityTier control penalty**, a threshold lookup keyed on the *final* runtime intensity (`:202-203`).

This is the **only** place `CharacterModifier` intensity/control bonuses and `IntensityTier` penalties are applied. It feeds `calculate_effective_anima_cost` via the control-delta formula (`effective_cost = max(base_cost − (runtime_control − runtime_intensity), 0)`, `:211-238`), mishap-pool selection (`control_deficit = intensity − control`), per-resonance corruption attribution, and the `TECHNIQUE_PRE_CAST`/`TECHNIQUE_CAST` event payloads.

**`compute_effective_intensity(participant, action)`** — `world/combat/services.py:332-358` (verified). Returns `int`. Reads `technique.intensity` as base and adds only `INTENSITY_BUMP` `scaled_value`s from active `CombatPull` rows. **Does not** consult `CharacterModifier`, `IntensityTier`, `CharacterEngagement`, or social safety. Feeds `compute_damage_budget`, `compute_severity`, `compute_duration_rounds` in `CombatTechniqueResolver`.

The combat function's own docstring (`:342-345`) advertises "Future hooks (additive, no signature change required): Condition-derived… Item-derived… Environmental modifiers" — i.e., it is *intended* as the extension point for world-side scaling, but it is narrower than the magic path and silently ignores identity bonuses.

### 2.2 Reconciliation verdict

These are **genuinely parallel implementations of "effective intensity," not one system with two callers.** They overlap on the base term (`technique.intensity`) and diverge on everything else. The divergence is *currently* defensible (combat = pull-only escalation; magic = full envelope) but it is a live parallel-impl risk per the codebase's anti-reinvention rule: any future "+intensity in combat from a distinction" would have to be added to `compute_effective_intensity` even though `get_runtime_technique_stats` already knows how to compute it. The resolver closure does **not** receive `stats.intensity` from `use_technique`; it recomputes independently. So editing `technique.intensity` affects anima/mishap/events through one path and damage through the other — they happen to read the same base field, which masks the duplication.

### 2.3 Do modifiers already touch intensity? Yes — partially

- **Intensity/control ARE ModifierTargets.** `technique_stat` category with names `intensity`/`control` (`world/mechanics/constants.py:14-16`, verified). `CharacterModifier` rows tune them; applied only in `get_runtime_technique_stats`.
- **Scoping FKs already exist on `ModifierTarget`** — and **more than the archaeology claimed**. Verified at `world/mechanics/models.py:120-158`: `target_resonance`, `target_affinity`, `target_capability`, `target_check_type`, **and `target_damage_type`** (OneToOne to `conditions.DamageType`) all exist today. The archaeology's claim that damage-type scoping is "non-existent" on `ModifierTarget` is **stale** — the FK is present (category described as "resistance"). This materially de-risks element/damage-type-scoped power.
- **Equipment relevance is gated.** `EQUIPMENT_RELEVANT_CATEGORIES = {stat, magic, affinity, resonance}` (`constants.py:82-90`, verified). Notably `technique_stat` is **not** in this set — so equipment does not currently feed intensity/control even though distinctions do. A "power" category would need explicit inclusion to be equipment-driven.
- **Stacking is centralized** in `get_modifier_breakdown` (additive sum with amplification and negative-immunity rules) — a power category gets this behavior for free if routed through `CharacterModifier`.

### 2.4 The unwired reactive hook

`TECHNIQUE_PRE_CAST` is emitted with `intensity=stats.intensity` and is MODIFY_PAYLOAD-capable (set/multiply/add/min/max, `flows/models/flows.py:541-554`), **but the modified value is never read back** — downstream resolution uses the pre-event `stats.intensity`. So reactive intensity modulation is currently cosmetic. This is a missing *read step*, not a duplication. (This worktree is literally named `feature-524-precast-modify-path`, suggesting that gap is the active concern.)

---

## 3. The intensity-vs-power distinction

### 3.1 Conceptual model

| | **Intensity (channeled)** | **Power (effective magnitude)** |
|---|---|---|
| Definition | What the caster pours in | What the working carries into the world / target |
| Owner of the value | The caster's commitment + identity | The caster's commitment, *then* modified by amps/wards/buffs/environment |
| Mutable by a defender's ward? | **Never** | **Yes** (a ward subtracts here) |
| Drives | anima cost, control-deficit → mishap pool, Soulfray, per-resonance corruption attribution, resonance signature | damage budget, condition severity/duration, capability magnitude, penetration vs. resistance |
| Risk is priced on | this (you pay full overreach cost for what you channeled) | not this (you can be warded down to zero effect and still pay) |

The single most important invariant the user stated: **a ward reduces power, not intensity.** This mirrors Ars Magica exactly — a spell can be flawlessly cast (full Casting Total spent) yet bounce off Parma Magica (zero penetration). The caster still paid. WFRP makes the same point: risk is priced on dice channeled, reward realized only as effect that lands.

### 3.2 Current consumers, classified

**Caster-side (must read INTENSITY, the channeled value):**
- `calculate_effective_anima_cost` via control-delta (`techniques.py:211-238`)
- `control_deficit → select_mishap_pool` (`:348-350`)
- `ResonanceInvolvement` per-resonance share for corruption (`:112-153`)
- Soulfray severity (already intensity-*independent* — driven by anima deficit/depletion ratio, `soulfray.py:17-42`; included here because it sits in the channel-cost family)
- `TECHNIQUE_PRE_CAST` / `TECHNIQUE_CAST` payloads (audit/reactive signal)

**World-side (should read POWER, the modifiable value):**
- `compute_damage_budget(effective_intensity, success_level)` (`combat/services.py:206`)
- `compute_severity` / `compute_duration_rounds` for applied conditions (`:251-265`)
- `TechniqueCapabilityGrant` value formula (`base + intensity_mult × intensity`)
- clash gating via `compute_effective_intensity` (`clash.py:1176`)

**Intensity-independent today (neither — flagged so a redesign doesn't accidentally wire them):**
- Clash *check roll* (driven by strain_commitment, not intensity, `clash.py:223-229`)
- Social action checks (difficulty-based, `action_services.py:328-339`)
- Resonance-environment backfire (driven by aura × room valence, not intensity, `resonance_environment.py:500-549`)

### 3.3 Where "power" would live

The clean reading of the user's framing: **power = a derived, world-side magnitude = f(channeled intensity, pre-cast amps, persistent buffs, environment), computed at resolution and consumed by the world-side family only.** Intensity stays the caster-side ground truth. The three intensity-scaling formulas (damage, condition severity, capability) should read `effective_power`; the cost/mishap/corruption family keeps reading `intensity`. The open design question is *which mechanism* derives power — that is Section 5.

A note on terminology collision (Section 7 expands): the codebase already uses "power" loosely (`EffectType.base_power`, `IntensityTier`'s "calculated power" help text, `TechniqueDamageProfile.base_damage`). Whatever is chosen must disambiguate "power" (the new modifiable magnitude) from these existing uses, or rename.

---

## 4. Lessons from other systems

Organized by theme; each attributed.

### Scaling / upcasting (effect as a function of a per-cast input)
- **D&D 5e upcasting** is the cleanest "same spell, variable input → spell-defined scaling function." Fireball = 8d6 + 1d6/slot above 3rd. Store *base + per-step delta*, compute effective magnitude from the channeled level rather than authoring variants. ([5thsrd.org/spellcasting](https://5thsrd.org/spellcasting/), [roll20 Fireball](https://roll20.net/compendium/dnd5e/Fireball))
- **D&D 5e cantrips** scale on a *different* axis — character level, not per-cast resource — proving "power as a function of caster development" is a distinct channel. ([5thsrd cantrips](https://5thsrd.org/spellcasting/cantrips/))
- **PoE2 / Tyranny Power Level** is a single scalar that simultaneously lifts magnitude, accuracy, penetration, area — "one intensity number fans out to many facets." Strong precedent for a single derived `effective_power` feeding damage+severity+duration+capability uniformly. ([Power Level](https://pillarsofeternity2.wiki.fextralife.com/Power+Level))

### Magnitude bought from a resource
- **Mage: the Awakening 2e** spends successes to raise *factors* (potency/duration/scale), with one nominated **Primary Factor** scaling at a better rate — i.e., buffs change the *conversion rate*, not raw input. ([rpg.stackexchange](https://rpg.stackexchange.com/questions/107002/))
- **Shadowrun Force** is one dial setting effect, dice cap, *and* drain together. ([Force](https://shadowrun.fandom.com/wiki/Force))
- **GURPS** scales effect by energy poured; high skill *cheapens the conversion* (efficiency as a modifier, not additive power). ([gurpsland](https://gurpsland.byethost33.com/m_ecr.htm)) — directly analogous to Arxii's control-delta lowering anima cost.

### Channeled-vs-effective split (the core ask)
- **Ars Magica** is the canonical model: **Casting Total** (channeled) − **Spell Level** (toll) = surplus → **Penetration** (effective reach), compared to Magic Resistance. A perfect cast can land zero effect on a warded target; the caster still paid. Higher spell level inherently penetrates worse — a built-in scale-vs-reach tradeoff. ([ironboundtome](https://ironboundtome.wordpress.com/2011/11/12/how-does-mr-and-penetration-work-in-ars-magica/), [redcap Ch.9](https://www.redcap.org/page/Ars_Magica_5E_Standard_Edition,_Chapter_Nine:_Spells))
- **GAS BaseValue vs CurrentValue**: CurrentValue = BaseValue + active modifiers, **never stored, always recomputed**. Map intensity → BaseValue, power → CurrentValue; wards/amps are just modifier objects. ([GASDocumentation](https://github.com/tranek/GASDocumentation))

### Overreach cost (Soulfray / corruption family)
- **Mage Awakening Reach**: free up to a margin set by mastery, then each increment adds Paradox dice — *free-threshold-then-escalating-cost*, the exact shape of a Soulfray gate. Cost can both harm the caster *and* degrade the cast. ([rpg.stackexchange](https://rpg.stackexchange.com/questions/107002/))
- **Shadowrun overcasting**: Force > Magic flips drain *type* (Stun → lethal Physical) — cost **type transition**, not just amount. ([Overcasting](https://shadowrun.fandom.com/wiki/Overcasting))
- **WFRP Winds of Magic**: extra power dice scale reward and miscast risk together; risk priced on channel, reward on effect. ([warhammerfantasy wiki](https://warhammerfantasy.fandom.com))
- Cross-cutting lesson: **price overreach on intensity (channeled), realize reward on power (landed)** — a suppression environment becomes legibly scary ("full Soulfray cost, 50% landed power"). This is *already* how Arxii works (Soulfray reads deficit, not power) and must be preserved.

### Buffs / modifiers (the "use the existing modifier system" mandate)
- **PoE two-pool math**: `Final = (Base + flatAdded) × (1 + Σincreased) × Π(1+more_i)`. Additive "increased" all sum into one pool; "more" each multiply. Principled stacking with two behaviors. ([maxroll](https://maxroll.gg/poe/getting-started/poe-damage-calculation))
- **5e Metamagic** = priced, composable, *typed* modifiers each touching a distinct axis (magnitude / contest / targeting / delivery / cost). Template for keeping power adjustments orthogonal and stackable. ([dnd5e.wikidot metamagic](https://www.dnd5e.wikidot.com/sorcerer:metamagic))
- **GAS aggregation**: fixed op order (Add → Multiply → Divide → Override) removes order ambiguity; Override-to-zero models a hard null-field ward. ([GASDocumentation](https://github.com/tranek/GASDocumentation))

### Element-scoped modifiers ("+power to fire spells")
- **PoE tag-matched modifiers**: a fire-spell hit collects "increased fire" + "increased elemental" + "increased spell" + generic, summed by **tag match** — no per-element special fields. "+X to fire spells" is *data*, not a rule. ([poewiki Damage](https://www.poewiki.net/wiki/Damage), [Fire Damage](https://www.poewiki.net/wiki/Fire_Damage)) — maps onto Arxii's existing `target_resonance` / `target_damage_type` scoping FKs.

### Reactive / interrupt (pre-cast wards/amps, counters)
- **MTG Stack + priority + LIFO**: a counter placed in the response window resolves first and injects a modifier into the target's pipeline (reduce *landing*, not *channeling*). ([Stack](https://mtg.fandom.com/wiki/Stack), [Priority](https://mtg.fandom.com/wiki/Priority))
- **MTG layers + dependency**: deterministic ordering of heterogeneous continuous effects; the dependency rule reorders "this buff only exists because that effect changed the element." Future-proofs against ad-hoc modifier-interaction mess. ([Layer](https://mtg.fandom.com/wiki/Layer), [Dependency](https://mtg.fandom.com/wiki/Dependency))
- **Noita per-cast modifier queue** vs persistent cast-state — clean per-cast-vs-persistent lifecycle distinction (pre-cast amp = ephemeral; "+power to fire" = persistent condition). ([Noita modifiers](https://noita.wiki.gg/wiki/Modifier_Spells))

### World/environment modifies power
- **GAS snapshot vs non-snapshot capture**: lock power at cast time, or keep re-deriving from live world/relationship state. The exact knob for "a sustained ward grows as you carry it toward a resonant node." ([GASDocumentation](https://github.com/tranek/GASDocumentation))
- **Ars Magica Aura** as a flat environment Add/Subtract to the total; **Genshin elemental gauge** as decaying world-state power that follow-ups react with. ([genshin gauge theory](https://genshin-impact.fandom.com/wiki/Elemental_Gauge_Theory))

---

## 5. Candidate design directions

Four distinct architectures. **No winner is selected.** Each is evaluated on: mechanism, modifier-system reuse, use-case coverage, pros/cons, parallel-impl risk.

---

### Direction A — "Power" as a new ModifierTarget category computed inside runtime stats

**How it works.** Introduce a `power` `ModifierCategory` and `RuntimeTechniqueStats` grows a third field `power`. `get_runtime_technique_stats` becomes the single source: it computes `intensity`, `control` as today, then derives `power` = `f(intensity)` + power-scoped `CharacterModifier` totals (+ pre-cast amp/ward modifiers injected as transient `CharacterModifier`/payload entries). The three world-side formulas (damage/severity/capability) are changed to read `stats.power`; the cost/mishap/corruption family keeps reading `stats.intensity`. `compute_effective_intensity` is **deleted or reduced to a thin shim** that calls `get_runtime_technique_stats` and returns `.power` + combat-pull bumps.

**Modifier-system reuse.** Maximal. Power becomes another `ModifierTarget`; element scoping reuses the **already-present** `target_resonance` / `target_damage_type` FKs; stacking/amplification/immunity come free from `get_modifier_breakdown`; "+power to fire" is a `CharacterModifier` row on a resonance-scoped power target. Add `power` to `EQUIPMENT_RELEVANT_CATEGORIES` if equipment should drive it.

**Use-case coverage.** Persistent "+power to fire" and amps: native. Pre-cast ward: a transient negative power modifier (must NOT touch intensity — satisfied by construction). Soulfray: untouched (reads intensity). Resonance-environment power shift: a power modifier sourced from room valence.

**Pros.** Single computation; eliminates the parallel impl; uses the mandated modifier system end-to-end; the existing scoping FKs make element-scoping nearly free.
**Cons.** `get_runtime_technique_stats` becomes a god-function. Combat's resolver currently *doesn't* have a `CharacterSheet`-rich call path identical to magic; threading the full magic envelope into combat resolution is real surgery. "Power as f(intensity)" entangles the two axes inside one function — the conceptual separation lives only in field names, not in code structure.
**Parallel-impl risk.** *Resolves* the existing one if `compute_effective_intensity` is truly collapsed; *creates a new one* if combat keeps its own pull-summing path alongside the new power field.

---

### Direction B — A dedicated effect-resolution pipeline with ordered modifier stages (GAS/MTG-inspired)

**How it works.** A new resolution component takes `(channeled_intensity, technique, caster, target, environment, reactive_window)` and runs ordered **channels/stages**: Channel 0 = channeled intensity (BaseValue); Channel 1 = caster identity/resonance; Channel 2 = persistent buffs (incl. element-scoped); Channel 3 = environment; Channel 4 = reactive (pre-cast wards/amps, counters). `effective_power` = output of the final channel, **never stored, always recomputed** (GAS CurrentValue). Each channel boundary is a clamp/gate point and a row in a player-facing "power ledger." Intensity is the immutable input; the pipeline only produces power.

**Modifier-system reuse.** Medium-to-high *if* each stage's modifiers are sourced from `CharacterModifier` rows via `get_modifier_total` (additive pool) plus a small set of multiplicative/override ops the current breakdown doesn't yet express. Risk: GAS-style Multiply/Divide/Override is a **superset** of the current additive-only `get_modifier_breakdown`, so either extend that function (preferred) or the pipeline grows its own math (parallel impl).

**Use-case coverage.** Strongest for reactive (the unwired `TECHNIQUE_PRE_CAST` MODIFY_PAYLOAD becomes Channel 4 read back into resolution — closes the existing gap), environment shifts (Channel 3), and live "power ledger" UI for the cast→pose→log→outcome loop. Snapshot-vs-non-snapshot becomes a per-technique flag (sustained wards re-derive). Element-scoped buffs are tag-matched in Channel 2.

**Pros.** Cleanest conceptual separation (intensity literally a different pipeline stage than power); deterministic ordering kills order-of-ops bugs; the itemized ledger directly serves the north-star outcome legibility; reactive becomes first-class.
**Cons.** Largest new surface — highest reinvention danger if it doesn't strictly delegate stacking to the existing modifier system. Two resolution philosophies (pipeline vs. current direct formula reads) would coexist during migration. Needs the additive-only breakdown extended to multiplicative/override ops, which is its own design.
**Parallel-impl risk.** **High** unless disciplined: a pipeline that recomputes modifier totals instead of calling `get_modifier_total` would be a third intensity/power computation. Must be built *on top of* `get_modifier_breakdown`, not beside it.

---

### Direction C — Extend `compute_effective_intensity` into the unified effective-power computation

**How it works.** Take the combat function at its own word (its docstring already promises additive world-side hooks) and grow it into `compute_effective_power(caster, technique, action, environment)`: base intensity + combat-pull bumps + power-scoped `CharacterModifier` totals + pre-cast amp/ward deltas + environment. Rename to reflect that it returns *power*. The magic envelope's `get_runtime_technique_stats` keeps owning intensity/control (caster-side), and resolution calls the new function for the world-side number. Soulfray/mishap/cost stay on `get_runtime_technique_stats.intensity`.

**Modifier-system reuse.** Medium. The function would call `get_modifier_total` for power-scoped targets and reuse scoping FKs — but it currently lives in `combat/services.py` and is combat-shaped (takes `CombatParticipant`/`CombatRoundAction`). Generalizing it to non-combat casts (social, scene actions, environment-only) means broadening the signature away from combat types.

**Use-case coverage.** Combat intensity ramp: native (it already sums pulls). Damage/severity/capability already call it. Persistent/element buffs and amps: add via modifier totals. Pre-cast ward: a negative term. Spell-tier scaling: a `f(technique.level)` term. The non-combat magic paths would need it wired in (they currently use intensity directly for cost only and don't scale world-side magnitude outside combat).

**Pros.** Smallest conceptual leap; honors an explicit existing extension point; keeps caster-side and world-side computations cleanly in *separate functions* (arguably the truest structural expression of the user's split — intensity in one function, power in another). Lower blast radius than B.
**Cons.** The function is combat-namespaced and combat-typed; generalizing it risks an awkward home (does it move to `magic/services`?). Two functions still exist — but now with a *documented contract* (one = channeled, one = effective) rather than accidental overlap.
**Parallel-impl risk.** **Low-to-medium** — it *converts* the existing parallel pair into a deliberate two-function split (intensity fn + power fn) with a clear boundary. Risk is mostly that the rename/move is half-done and a third path sneaks in for non-combat casts.

---

### Direction D — Ars-Magica-style magnitude/toll layer (power = surplus after a manifestation toll)

**How it works.** Reframe entirely: channeled intensity pays a **toll** (the technique's level/magnitude cost) to manifest; only **surplus** becomes power, which is then contested against target resistance (penetration vs. Magic Resistance). `effective_power = channeled_intensity − manifestation_toll + penetration_buffs`, compared to a target's ward/resistance. Wards raise the *target's resistance* (subtracting from landed effect) without touching channeled intensity. Higher technique tier = bigger toll = less surplus, a built-in scale-vs-reach tradeoff.

**Modifier-system reuse.** The penetration-buff and resistance terms are `CharacterModifier` totals (caster's penetration target; target's resistance target — `target_damage_type`/`target_resonance` scoping already supports element-keyed resistance). Toll is `f(technique.level)`. Stacking via existing breakdown.

**Use-case coverage.** Pre-cast ward weakening incoming power: *the* canonical model — ward = target resistance, subtracts from landed power, never from intensity (invariant satisfied structurally). Persistent +power: penetration buff. Spell-tier scaling: the toll *is* tier scaling, with the elegant inversion that bigger spells penetrate worse. Soulfray: priced on full channeled intensity regardless of penetration (suppression becomes legibly punishing — matches WFRP/Shadowrun lessons). Resonance-environment: an aura Add to channel or a resistance shift.

**Pros.** The most principled, literature-validated channeled-vs-effective separation; ward-doesn't-touch-intensity is enforced by the math, not by discipline; "cast succeeded but bounced off the ward" becomes a first-class, pose-able outcome state (great for cast→pose→log). Introduces a genuine target-resistance contest the system lacks.
**Cons.** Largest *design* change — introduces a resistance/penetration contest that doesn't exist today and would interact with the existing check/clash and damage-budget systems (potential double-counting of "defense"). Risks conflating with the existing `IntensityTier` "calculated power" and damage-budget mechanics. Most likely to require rebalancing every authored technique.
**Parallel-impl risk.** **Medium-high on the resistance side** — Arxii already resolves defense through checks, clash, and damage budgets; a new penetration-vs-resistance layer could become a parallel defense system unless explicitly unified with one of those.

---

## 6. Use-case coverage matrix

How each direction handles the concrete cases. (✓ native / clean; ◐ workable with added plumbing; ✗ awkward or requires rethinking that direction's core.)

| Use case | A — Power as ModifierTarget in runtime stats | B — Ordered pipeline | C — Extend compute_effective_intensity | D — Magnitude/toll + penetration |
|---|---|---|---|---|
| **Pre-cast ward weakens incoming power** (must not touch intensity) | ◐ transient negative power modifier; invariant by convention | ✓ Channel 4 reactive modifier; intensity is an earlier untouched stage | ◐ negative term in power fn; intensity fn untouched | ✓ ward = target resistance; invariant enforced by math |
| **Pre-cast amp** | ✓ transient positive power modifier | ✓ Channel 4 positive modifier (reads the currently-unwired MODIFY_PAYLOAD) | ✓ positive term | ✓ penetration buff or toll reduction |
| **Persistent "+power to fire spells"** | ✓ resonance-scoped `CharacterModifier` (uses existing `target_resonance`) | ✓ tag-matched Channel 2 modifier | ✓ scoped modifier total | ✓ scoped penetration buff |
| **Combat intensity ramp** | ◐ shim must still fold in pull bumps | ✓ a channel; or pull bumps as Channel 0 input | ✓ native (already sums pulls) | ◐ pulls raise channeled intensity → more surplus |
| **Spell-level / tier scaling** | ◐ add `f(level)` term to power derivation | ✓ a channel | ✓ `f(level)` term | ✓ tier *is* the toll (bigger tier → less reach), elegant |
| **Soulfray overreach interaction** | ✓ unchanged (reads intensity) | ✓ priced on Channel 0 intensity | ✓ unchanged (intensity fn) | ✓ priced on full channeled intensity, ignores penetration |
| **Resonance-environment power shift** | ◐ env-sourced power modifier (env currently affects backfire, not magnitude) | ✓ Channel 3 environment stage; supports non-snapshot re-derivation | ◐ env term in power fn | ◐ aura Add or resistance shift |
| **"Bounced off a ward" as a legible outcome** | ✗ not modeled (power floored at 0, no contest state) | ◐ representable as a final-channel clamp event | ✗ not modeled | ✓ first-class (penetration ≤ resistance = manifested, zero landed) |
| **Live "power ledger" UI for pose/log** | ◐ derivable but not structured | ✓ each channel is a ledger row (best fit) | ◐ derivable | ◐ two-line ledger (toll, penetration) |
| **Eliminates current parallel impl** | ✓ if shim truly collapses combat fn | ◐ only if built atop existing breakdown | ✓ converts to a documented two-fn split | ◐ may add a new defense path |

---

## 7. Open questions & decomposition sketch

### 7.1 Key decisions still to make

1. **Is "power" a third field on `RuntimeTechniqueStats`, a return of a (renamed) `compute_effective_*`, or the output of a new pipeline component?** This is the A/B/C/D fork and should be decided first; everything else follows.
2. **Terminology disambiguation.** "Power" is already overloaded (`EffectType.base_power`, `IntensityTier` help text "calculated power," `TechniqueDamageProfile.base_damage`). Either reserve a precise term (e.g., `effective_power` / `landed_magnitude`) or rename existing uses. Decide before writing code so the model field names don't collide.
3. **Should the three intensity-scaling formulas be unified behind one helper?** `TechniqueDamageProfile`, `TechniqueAppliedCondition`, `TechniqueCapabilityGrant` all use `base + mult × effective_intensity` with no shared code (archaeology-flagged triple). Whatever drives them should switch from `effective_intensity` to `effective_power` *in lockstep* — a shared helper would make that a one-line change instead of three.
4. **Element scoping mechanism.** Reuse the **already-present** `target_resonance` / `target_damage_type` FKs (preferred — they exist, verified `models.py:127,151`) vs. a new scope field. The archaeology underestimated what's built here; the cheap path is real.
5. **Is power equipment-driven?** If yes, add a `power` category to `EQUIPMENT_RELEVANT_CATEGORIES` (`constants.py:82`) and wire the equipment walk; if no, keep it distinction/condition-sourced.
6. **Wire the reactive read-back (independent of A–D).** The `TECHNIQUE_PRE_CAST` MODIFY_PAYLOAD result is currently discarded. Reading it back is a prerequisite for *any* reactive pre-cast ward/amp and is the named subject of the current worktree. Decide: re-read `pre_payload`, expand `resolve_fn` signature, or have the resolver introspect the payload.
7. **Does any direction introduce a target-resistance contest (D), and if so how does it avoid double-counting** the defense already expressed through checks/clash/damage-budgets?
8. **Snapshot vs. non-snapshot** (does power lock at cast time or re-derive for sustained effects?) — relevant mainly to B/D; decide whether the live-world re-derivation is in scope for v1 or deferred.
9. **Preserve invariants:** Soulfray stays priced on channeled intensity; clash *check rolls* and social-action checks stay intensity-independent; resonance-environment backfire stays valence-driven. Confirm none of A–D accidentally wires these.

### 7.2 Rough decomposition into a sequence of issues (not a commitment)

A plausible ordering that front-loads de-risking and keeps each step shippable:

- **Issue 0 — Reconciliation spike & contract doc.** Document the `get_runtime_technique_stats` vs `compute_effective_intensity` boundary as it stands; correct the stale `docs/systems` claims about ModifierTarget scoping FKs (per the anti-reinvention "fix the doc at source" rule). Pick the A/B/C/D direction. *No code behavior change.*
- **Issue 1 — Wire the pre-cast MODIFY_PAYLOAD read-back.** Make reactive intensity/power mutation actually affect resolution. Self-contained, unblocks all reactive use-cases, matches the current worktree's intent.
- **Issue 2 — Unify the three intensity-scaling formulas behind one helper** reading a single `effective_*` value. Pure refactor; makes the later intensity→power swap atomic.
- **Issue 3 — Introduce the `power` concept** per the chosen direction (new field / renamed function / pipeline skeleton), reading channeled intensity as input and feeding *only* the world-side family. Caster-side family unchanged. Add tests asserting a ward reduces power but not anima cost / mishap pool / Soulfray.
- **Issue 4 — Route power through the modifier system:** persistent "+power to fire" via resonance/damage-type-scoped `CharacterModifier`; decide equipment relevance. Reuse `get_modifier_breakdown`.
- **Issue 5 — Collapse / formalize the parallel impl:** either reduce `compute_effective_intensity` to a documented shim (A/C) or ensure the pipeline (B) delegates all stacking to the existing breakdown.
- **Issue 6 (optional / direction-dependent) — Environment power shift and/or penetration-vs-resistance contest**, plus the player-facing power ledger for cast→pose→log.

This sequence lets the cheap, high-value wins (read-back wire, formula unification) land regardless of which architecture wins, and defers the heaviest reinvention risk (B's op-math extension, D's resistance contest) until after the direction is ratified.

---

*Relevant code anchors for the design conversation: `src/world/magic/services/techniques.py:156-238` (runtime stats + anima cost), `src/world/combat/services.py:332-358` (compute_effective_intensity), `src/world/mechanics/models.py:120-158` (ModifierTarget scoping FKs — including the present `target_damage_type`), `src/world/mechanics/constants.py:9-16,82-90` (category names + equipment-relevant set), `src/flows/models/flows.py:541-554` (MODIFY_PAYLOAD ops).*

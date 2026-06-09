# Power Derivation Pipeline (#524 → #639 / Direction B)

**Status:** fully built and wired (Issues #524–#639).
**Companion docs:** `docs/architecture/power-intensity-research.md` (landscape + candidate
directions), `docs/architecture/power-intensity-research-critique.md`.

---

## 1. Problem and invariant

`use_technique` emits `TECHNIQUE_PRE_CAST` with a mutable payload. Before #524 a
`MODIFY_PAYLOAD` trigger's edit to `power` had no effect because the code kept using
`stats.intensity` downstream — the modify path was a no-op. #524 closed that gap.

**Load-bearing invariant (never relaxed):** *Power is always a **derived** value, never
stored.* It is recomputed each cast. No persisted `power` column exists; none will be
added. Modifiers *contribute to* power; they are never *stored as* power.

---

## 2. Intensity vs power

- **Intensity** — what the caster *channels*. Drives anima cost, mishap (`control_deficit`),
  resonance attribution, and Soulfray. A ward must never reduce this.
- **Power** — the *effective magnitude the working carries into the world*. Drives damage
  budgets, condition severity/duration, and capability grants. This is the modifiable lever.

The two values are separately carried on `TechniquePreCastPayload` (`intensity`, `power`).
Caster-side calculations always read `stats.intensity`; world-side calculations read `power`
(post-hook, from the resolved ledger).

---

## 3. `_derive_power` — the ledger pipeline

`_derive_power` (`world/magic/services/techniques.py`) returns a transient
**`PowerLedger`** (`world/magic/types/power_ledger.py`). The ledger is an ordered tuple of
**`PowerLedgerEntry`** records, each tagged with a `PowerStage` constant, an `op`
(`LedgerOp`: `ADD / MULTIPLY / SET`), an `amount`, and a running total. `ledger.total`
is the effective power (floored at 0).

### 3.1 Stage ordering (build order inside `_derive_power`)

| # | Stage | Source | How applied |
|---|-------|--------|-------------|
| 1 | **BASE** | `stats.intensity` from `get_runtime_technique_stats` (identity + process modifiers, Audere intensity, tier penalty, social safety) | `SET` to channeled intensity |
| 2 | **MULTIPLIER** | `power_multiplier` `ModifierTarget` via `get_modifier_breakdown` + `get_condition_modifier_breakdown`. Immunity-blocked sources excluded. | Single aggregate `×(1 + Σ%/100)` applied to BASE only — one `multiply` call, never per-source, to avoid repeated rounding drift |
| 3 | **FLAT_MODIFIER** | Per-source additive power modifiers via `get_modifier_breakdown` (immunity-blocked excluded) + per-condition rows via `get_condition_modifier_breakdown` | `ADD` per non-zero source |
| 4 | **TERM** | `get_power_term_providers()` — level, aura, and thread all live (#768) | `ADD` per provider |
| 5 | **ENVIRONMENT** | Cast-time `evaluate_resonance_environment` AMPLIFY magnitude only | `ADD` if `kind == AMPLIFY and magnitude > 0` |

Then, in the combat resolver (`CombatTechniqueResolver.__call__`):

| # | Stage | Source | How applied |
|---|-------|--------|-------------|
| 6 | **COMBAT_PULL** | INTENSITY_BUMP pulls via `_sum_intensity_bump_pulls` | `ADD` |
| 7 | **PENETRATION** | `get_penetration_factor(pen_result.success_level)` from the authored `PenetrationOutcomeFactor` ladder (see §4) | `SET 0` (bounce), `SET total` (clean penetration), or `multiply` by `(factor−1)×100` pct |
| — | **REACTIVE** | A pre-cast `MODIFY_PAYLOAD` edit to `payload.power` (appended after the emit, outside `_derive_power`) | `ADD` delta between hook output and seed ledger total |
| — | **CLAMP** | Floor at 0 | `SET 0` if total < 0 |

### 3.2 Stacking model

Stacking is entirely delegated to `get_modifier_breakdown` and `get_condition_modifier_breakdown`.
`_derive_power` does not contain multiplicative-math or stacking logic of its own: the
MULTIPLIER pool is additive-% aggregated first (Σ%), then applied as a single `×(1+Σ%/100)` to
BASE. FLAT stage sources are additive. No special stacking code was added to the pipeline;
the existing modifier system's immunity handling and source attribution carry through.

### 3.3 ENVIRONMENT stage — evaluate-once, AMPLIFY only, double-count guard

`evaluate_resonance_environment` is called **once per cast**, before `_derive_power`, and the
result is passed in as the `environment` argument. This evaluate-once pattern (#639/#722
guard) prevents the primitive from running twice (once for power, once for backfire).

Only AMPLIFY (ALIGNED diagonal) adds power here. Double-count guards:

- **OPPOSED** (REJECT/REPEL/CORRUPT): no power change. The opposition penalty is already the
  Step 10 backfire (`resonance_environment_for_cast`). Subtracting power here would double-count.
- **ALIGNED persistent presence boon**: applied as a `ConditionInstance` on room entry via
  `refresh_resonance_alignment`. That condition's modifier rows already flow through the
  FLAT/condition stage above. Adding it again here would double-count.

### 3.4 REACTIVE entry

After `TECHNIQUE_PRE_CAST` is emitted, `use_technique` reads `pre_payload.power`. If a trigger
edited it via `MODIFY_PAYLOAD`, the signed delta is appended as a `REACTIVE` entry so the ledger
stays internally consistent (`ledger.total == effective_power`). The ledger's floor (≥0) then
becomes the canonical `effective_power`, ensuring a ward-driven 0 is honoured even if the hook
pushed power negative.

---

## 4. Penetration-vs-resistance contest

When the focused opponent has a `barrier_strength > 0` (a ward), the combat resolver runs a
**penetration check** (`perform_check` against `barrier_strength` as the difficulty) before
damage and condition resolution.

The result's `success_level` is looked up against the authored `PenetrationOutcomeFactor` ladder
via `get_penetration_factor(success_level)` (`world/conditions/services.py`). The ladder is a
queryset of `PenetrationOutcomeFactor` rows ordered by `min_success_level`; the highest
matching row's `factor` is returned (default `Decimal("1.00")` when no row matches — an
unauthored ladder must never accidentally zero out a working).

**Outcomes by factor value:**

| Factor | Ledger entry | Effect |
|--------|-------------|--------|
| `0` | `PENETRATION SET 0` `"ward (bounced)"` | `bounced=True` — damage/conditions short-circuited; the ledger records the bounce for narration |
| `1.00` (exactly) | `PENETRATION SET total` `"ward (penetrated)"` | `bounced=False`, power unchanged. The entry distinguishes a warded-but-cleanly-penetrated cast from an unwarded one (which records no PENETRATION entry at all). |
| `0 < factor < 1` | `PENETRATION multiply (factor−1)×100 pct` (negative) | Partial — power reduced |
| `factor > 1` | `PENETRATION multiply (factor−1)×100 pct` (positive) | Overpenetration — power amplified |

**No double-counting with resistance/soak:** `barrier_strength` is the ward gate only.
Damage-type resistance is soaked once, downstream, in `apply_damage_to_opponent`. The
penetration contest does not touch resistance; resistance does not interfere with the
penetration roll.

---

## 5. Snapshot vs recompute decision: RECOMPUTE

Power is **never stored**. Each call to `use_technique` recomputes it via `_derive_power` from
the current character state. There is no persisted `power` column anywhere. Later issues
may add more input terms to `_derive_power`; the derivation point is centralised so those
additions are one-place changes.

---

## 6. Ledger surfacing — payloads and narration

The ledger rides the event payloads throughout the pipeline:

- `TechniquePreCastPayload` — carries `intensity`, `power` (seed total), and `ledger` (seed
  ledger). Mutable; a `MODIFY_PAYLOAD` trigger may edit `power`.
- `TechniqueCastPayload` — frozen; carries `power` (effective) and `ledger` (effective, with
  REACTIVE entry appended if any hook edited it).
- `TechniqueAffectedPayload` — frozen; carries `power` (effective) and `ledger` (effective).

Combat narration reads the ledger via `_power_outcome_clause(power_ledger)` in
`world/combat/interaction_services.py`, which folds a concise ward/environment outcome clause
into the `render_action_outcome_narration` line:

- Full bounce → `"— the ward turns it aside"`
- Partial penetration → `"— the ward bleeds off much of its force"`
- Clean/over-penetration → `"— it tears through the ward"`
- Environment amplification (no PENETRATION entry, positive ENVIRONMENT ADD) →
  `"— the place's resonance swells the working"`
- Plain unwarded, non-magic, or combo path → no clause (backward compatible)

---

## 7. Key symbols (where to find the code)

| Symbol | Module |
|--------|--------|
| `PowerLedger`, `PowerLedgerEntry`, `PowerLedgerBuilder` | `world/magic/types/power_ledger.py` |
| `PowerStage`, `LedgerOp` | `world/magic/constants.py` |
| `_derive_power` | `world/magic/services/techniques.py` |
| `get_modifier_breakdown` | `world/mechanics/services.py` |
| `get_condition_modifier_breakdown` | `world/conditions/services.py` |
| `get_penetration_factor`, `PenetrationOutcomeFactor` | `world/conditions/services.py`, `world/conditions/models.py` |
| `CombatTechniqueResolver._apply_penetration` | `world/combat/services.py` |
| `_power_outcome_clause`, `render_action_outcome_narration` | `world/combat/interaction_services.py` |
| `evaluate_resonance_environment` | `world/magic/services/resonance_environment.py` |

---

## 8. History

- **#524** — introduced `power` as a derived, never-stored value seeded from `stats.intensity`;
  wired the pre-cast `MODIFY_PAYLOAD` path so trigger edits to `power` reach resolution; closed
  the discard-on-emit gap; split caster-side from world-side effects. `_derive_power` returned
  a scalar at this stage.
- **#634–#638** — added modifier/level/thread/aura/Audere terms to the derivation.
- **#639 (Direction B)** — rewrote `_derive_power` to return a `PowerLedger`; added the
  MULTIPLIER/FLAT/TERM/ENVIRONMENT/REACTIVE stages; introduced the penetration-vs-resistance
  contest and the `PenetrationOutcomeFactor` ladder; wired the ledger through combat resolution
  and narration; evaluate-once environment guard.

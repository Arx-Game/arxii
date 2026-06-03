# Issue 0 — Pre-cast Power Read-back Design (#524)

**Status:** approved design, pre-implementation.
**Companion research:** `docs/architecture/power-intensity-research.md` (landscape + 4 candidate directions) and `...-critique.md`. This spec implements the report's **Issue 0/1** and the leading edge of **Direction C** (unify the two effective-intensity computations into one derived power value).

---

## 1. Problem

`use_technique` (`src/world/magic/services/techniques.py`) emits `TECHNIQUE_PRE_CAST` with a mutable payload, but **discards any edits**: after the emit it keeps using the pre-event `stats.intensity` for resolution. A reactive pre-cast trigger that does `MODIFY_PAYLOAD` (a ward weakening an incoming working, an amp strengthening it) therefore has **no effect on what actually lands**. The cancel path works; the modify path is a no-op. This is the #524 gap.

Fixing it cleanly requires naming the thing being modified correctly. Per the research and the user's framing:

- **Intensity** = what the caster *channels*. Caster-side. Drives anima cost, mishap (`control_deficit`), resonance/corruption attribution, Soulfray. **A defender's ward must never reduce this.**
- **Power** = the *effective magnitude the working carries into the world*. World/target-side. Drives damage budgets, condition severity/duration, capability grants. **This is the modifiable lever** (pre-cast wards/amps now; persistent buffs, Audere spikes, environment shifts later).

**Load-bearing invariant (user):** *Power is always a **derived** value, never stored.* It is recomputed each cast as the sum of the caster's intensity + (later) level, threads, aura/resonance, and applicable modifiers. Modifiers *contribute to* power; they are never *stored as* power. This spec introduces power as a derived value seeded from intensity; later issues add the other input terms. No persisted power column, ever.

---

## 2. Scope

### In scope (PR1)
1. Add a derived `power` to the pre-cast payload, seeded from the caster's channeled intensity.
2. Read the post-hook `power` back in `use_technique` and feed it to resolution + the world-side event payloads.
3. Extend the `resolve_fn` contract to receive `power`; the combat resolver **consumes** it for damage/severity/duration/capability, unifying it with the combat pull bumps. Clash and scenes accept-and-ignore (their resolution is intensity-independent today).
4. Reduce `compute_effective_intensity` to its pull-summing role and route combat scaling through the injected `power + pulls` (the front edge of Direction C).
5. Tests proving the intensity/power split: a ward reduces landed effect but not anima/mishap/Soulfray.

### Out of scope (later issues, tracked separately)
- `power` as a `ModifierTarget` category + persistent buffs ("+power to fire spells").
- Level / thread / aura terms in the power derivation.
- Audere / Audere Majora power spike (a derivation term).
- Environment power shift; penetration-vs-resistance contest; the player-facing "power ledger".
- The full ordered pipeline (Direction B).

These will be filed as follow-on issues during the broader decomposition.

---

## 3. Current code (verified anchors)

- `use_technique` — `src/world/magic/services/techniques.py:241-428`. Step 2 computes anima cost from `stats.intensity` (caster-side, stays). Lines 289-309 emit `TECHNIQUE_PRE_CAST` then check only `was_cancelled()`. Line 315 calls `resolve_fn()` (no args). Lines 348/357/407 reuse `stats.intensity`.
- `TechniquePreCastPayload` — `src/flows/events/payloads.py:188-194`: `caster, technique, targets, intensity`. Non-frozen (mutable). `TechniqueCastPayload` (frozen) and `TechniqueAffectedPayload` carry the world-side result.
- `MODIFY_PAYLOAD` — `src/flows/models/flows.py` `_execute_modify_payload`: ops `set/multiply/add/min/max` via `setattr` on the payload field.
- `resolve_fn` call sites (3 production):
  - `src/world/combat/services.py:485` — passes a `CombatTechniqueResolver` instance (callable). The resolver calls `compute_effective_intensity(self.participant, self.action)` in `_apply_damage` (`:206`) and `_apply_conditions` (`:251`).
  - `src/world/combat/clash.py:233` — passes a local no-arg `resolve_fn` doing a strain-based `perform_check`; intensity-independent.
  - `src/world/scenes/action_services.py:328` — passes `lambda: start_action_resolution(...)`; difficulty-based; intensity-independent.
- `compute_effective_intensity` — `src/world/combat/services.py:332-358`: `technique.intensity + Σ INTENSITY_BUMP pull scaled_values`. Does NOT consult identity modifiers (that lives only in `get_runtime_technique_stats`).
- `get_runtime_technique_stats` — `src/world/magic/services/techniques.py:156-208`: the full caster envelope (base + identity `CharacterModifier` + engagement + tier penalty) → `RuntimeTechniqueStats(intensity, control)`.

---

## 4. Design

### 4.1 Payload: add derived `power`

`TechniquePreCastPayload` (`payloads.py`) gains `power: int`, alongside the retained `intensity: int`:

```python
@dataclass
class TechniquePreCastPayload:
    caster: Character
    technique: Technique
    targets: list[Character | ObjectDB]
    intensity: int   # channeled — immutable; what the caster put in
    power: int       # derived effective magnitude — the editable lever
```

`intensity` stays so triggers can *read* the channeled value (e.g. "ward scales with how hard they pushed") while editing only `power`. `TechniqueCastPayload` and `TechniqueAffectedPayload` each gain a `power: int` field carrying the post-hook value to observers/downstream triggers.

### 4.2 `use_technique`: seed, read back, thread through

In `use_technique`, the seed is the **derived power**. For PR1 the derivation is `power = stats.intensity` (the full caster envelope). A small private helper marks the extension point for later input terms (level/threads/aura/modifiers):

```python
def _derive_power(*, channeled_intensity: int, technique: Technique, character: ObjectDB) -> int:
    """Derive effective power. NEVER stored — recomputed each cast.

    PR1: power == channeled intensity. Later issues add level, threads,
    aura/resonance, and power-scoped modifier terms here (Direction C/B).
    """
    return channeled_intensity
```

Flow changes (all in `use_technique`):
1. Seed `pre_payload.power = _derive_power(channeled_intensity=stats.intensity, technique=technique, character=character)` (and keep `intensity=stats.intensity`).
2. After the emit (non-cancelled), read `effective_power = pre_payload.power` (a trigger may have edited it).
3. Call resolution with it: `resolution_result = resolve_fn(power=effective_power)`.
4. Use `effective_power` in the `TECHNIQUE_CAST` and `TECHNIQUE_AFFECTED` payloads.
5. **Unchanged:** anima cost (Step 2, already computed pre-hook from `stats.intensity`), `control_deficit` mishap (`stats.intensity - stats.control`), resonance involvements (`stats.intensity`), Soulfray (deficit-based). The caster-side family never reads `power`.

### 4.3 `resolve_fn` contract: `(*, power: int)`

All resolvers become keyword-callable with `power`:

- **clash** (`clash.py`): `def resolve_fn(*, power: int) -> object:` — ignores `power` (`# noqa: ARG001` with a comment: clash check is strain-driven, not power-scaled). Body unchanged.
- **scenes** (`action_services.py`): change `resolve_fn=lambda: start_action_resolution(...)` to `resolve_fn=lambda *, power: start_action_resolution(...)` — ignores `power` (difficulty-driven). Body unchanged.
- **combat** (`CombatTechniqueResolver.__call__`): becomes `def __call__(self, *, power: int) -> CombatTechniqueResolution:` and threads `power` into `_apply_damage(check_result, power=power)` and `_apply_conditions(check_result, power=power)`.

### 4.4 Combat: consume injected power (front edge of Direction C)

The combat resolver currently calls `compute_effective_intensity(participant, action)` in two places and uses the result as `effective_intensity=` for damage budget, severity, and duration. Change those to use the **injected power plus the combat pull bumps**:

- Split `compute_effective_intensity` so the pull-summation is reusable:

```python
def sum_intensity_bump_pulls(participant: CombatParticipant) -> int:
    """Σ of active INTENSITY_BUMP pull scaled_values for this participant's encounter."""
    total = 0
    character = participant.character_sheet.character
    for pull in character.combat_pulls.active_for_encounter(participant.encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                total += eff.scaled_value
    return total


def compute_effective_intensity(participant: CombatParticipant, action: CombatRoundAction) -> int:
    """DEPRECATED scaling entry point — retained for the clash intensity floor only.

    Equals technique.intensity + INTENSITY_BUMP pulls. Damage/severity/duration now
    scale on the power injected by use_technique (which already folds in the caster's
    full intensity envelope) plus sum_intensity_bump_pulls. See Direction C.
    """
    technique = action.focused_action
    if technique is None:
        return 0
    return technique.intensity + sum_intensity_bump_pulls(participant)
```

- In `_apply_damage` / `_apply_conditions`, replace `eff_intensity = compute_effective_intensity(...)` with:

```python
eff_power = power + sum_intensity_bump_pulls(self.participant)
```

and pass `effective_intensity=eff_power` into `compute_damage_budget` / `compute_severity` / `compute_duration_rounds` (the profile/condition method parameter name stays `effective_intensity` for PR1 — renaming those formula params to `effective_power` is a follow-on cleanup to avoid churn here).

**Consequence (intended):** combat damage now reflects the caster's identity intensity modifiers (carried by `power`←`stats.intensity`), which `compute_effective_intensity` previously ignored. With no production data and a disposable dev DB, there is no balance to preserve; this is the correct unification. Combat tests that asserted exact damage numbers will be updated to the new derivation.

- The **clash intensity floor** (`clash.py:1176`, `compute_effective_intensity(...) < intensity_floor`) keeps calling `compute_effective_intensity` — it is a gameplay gate on channeled+pull intensity, not a power consumer. Left as-is.

### 4.5 Why this honors the "power is always derived" invariant

`power` exists only as: a transient payload field (seeded by `_derive_power`, editable by triggers) and a `resolve_fn` parameter. It is never written to a model column. Each cast recomputes it. Later issues extend `_derive_power` with more input terms — the derivation point is centralized so those additions are one-place changes.

---

## 5. Testing

All on the SQLite inner loop where possible (`flows`, `magic` is PG-tier — use `just test-parity` for magic/combat).

1. **Magic envelope (magic tier):** pre-cast trigger that does `MODIFY_PAYLOAD {field: power, op: multiply, value: 0.5}` →
   - resolution receives halved power (assert via a resolver spy / the `TECHNIQUE_CAST` payload `power`),
   - anima cost unchanged, mishap pool selection unchanged, Soulfray severity unchanged (assert the caster-side outputs equal a no-trigger control run).
2. **No-edit identity:** with no pre-cast trigger, `power == stats.intensity` and every downstream number equals today's behavior for the magic path.
3. **Combat (combat tier):** pre-cast amp `{field: power, op: add, value: N}` → opponent damage rises by the budget delta; a ward `{op: multiply, value: 0.5}` → damage falls; anima/mishap/Soulfray unchanged. Confirm pull bumps still add on top (`eff_power = power + pulls`).
4. **Contract:** clash and scenes resolvers accept `power=` and behave identically to today (their outputs are power-independent).
5. **Regression:** full `just test-fast flows`; `just test-parity world.magic`; `just test-parity world.combat`; `just test-parity world.scenes`. Update combat damage-number assertions to the unified derivation.

---

## 6. Risks & coordination

- **Combat-instance overlap:** PR1 edits `src/world/combat/services.py` (`compute_effective_intensity`, `CombatTechniqueResolver`) and `clash.py` (signature only) — territory the parallel combat instance has worked in. Coordinate / flag at PR time; rebase before pushing. No `frontend/` or `api.d.ts` involvement.
- **`resolve_fn` signature is a breaking contract change** — all 3 production call sites + every test that builds a `resolve_fn`/resolver are updated in the same PR (the research listed them; `test_magic_story_pipeline`, `test_corruption_per_cast_pipeline`, `test_alteration_pipeline`, `test_use_technique`, etc. use `MagicMock`/`lambda: ...` and must become `lambda *, power: ...` or accept the kwarg).
- **Formula param name:** keeping `effective_intensity=` on `compute_damage_budget`/`compute_severity`/`compute_duration_rounds` in PR1 (passing power into it) is a deliberate small inconsistency to bound scope; renamed in a Direction-C follow-on.

---

## 7. Follow-on issues to file (decomposition)

- Power as a `ModifierTarget` category + `_derive_power` reads power-scoped `CharacterModifier` totals (reuse existing `target_resonance`/`target_damage_type` scoping FKs).
- Persistent "+power to fire spells" buffs (data, via the modifier system).
- Audere / Audere Majora power-spike term in `_derive_power` (gated on Audere state) — ties to #543.
- Level / thread / aura terms in `_derive_power`.
- Rename `effective_intensity=` → `effective_power=` across the three scaling formulas; collapse `compute_effective_intensity` fully.
- Environment power shift; penetration-vs-resistance; player-facing power ledger; the full ordered pipeline (Direction B).

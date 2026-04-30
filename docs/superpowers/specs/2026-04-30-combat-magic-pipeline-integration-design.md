# Combat Magic Pipeline Integration

**Date:** 2026-04-30
**Status:** Spec — pre-implementation
**Owner:** brann

## Purpose

Wire combat technique resolution through the magic system's `use_technique`
orchestrator so a combat-cast technique exercises the same pipeline as a
scene-cast one: anima deduction, soulfray accumulation, mishap rolls,
TECHNIQUE_PRE_CAST / TECHNIQUE_CAST event emission, reactive scar interception,
thread-pull bonuses, and corruption checks.

Today, `_resolve_pc_action` in `src/world/combat/services.py` reads
`technique.effect_type.base_power` directly and calls
`apply_damage_to_opponent`. Combat bypasses the magic system entirely, so
none of the above side effects fire on a combat-cast technique. This spec
fixes that for the **damage path only**. Non-attack effect types
(Defense / Buff / Movement / Debuff) are deferred to a follow-up that adds
a conditions-from-techniques resolver.

## Scope

### In scope

- Damage-path combat techniques route through `use_technique`.
- Anima is deducted on combat cast (including overburn → soulfray).
- TECHNIQUE_PRE_CAST and TECHNIQUE_CAST emit during combat rounds.
- Reactive scars subscribed to TECHNIQUE_PRE_CAST can intercept and cancel
  a combat cast (no damage, no anima deducted).
- Mishap rolls fire when the technique's roll triggers them.
- Active `CombatPull` rows for the caster contribute their **FLAT_BONUS**
  scaled values to the offense check's `extra_modifiers` (per Resonance
  Pivot Spec A §5.8).
- Damage delivered to the opponent matches the magic-pipeline-derived value.

### Out of scope (deferred)

- **Non-attack effect types** (Defense / Buff / Movement / Debuff applying
  conditions in combat). Needs a conditions-from-techniques resolver —
  separate PR after this lands.
- **`PerformRitualAction` player command.** Separate small PR.
- **Other pull effect kinds in combat damage**:
  - `INTENSITY_BUMP` — needs `get_runtime_technique_stats` to accept a combat
    context so pull-driven intensity is reflected in anima cost calc. Defer.
  - `CAPABILITY_GRANT` — tied to non-attack pipeline. Defer.
  - `NARRATIVE_ONLY` — cosmetic; surface in narrative buffer. Defer.
  - `VITAL_BONUS` — already wired through `recompute_max_health_with_threads`
    and `apply_damage_reduction_from_threads`; untouched by this spec.
- **TECHNIQUE_AFFECTED per target.** `CombatOpponent` is not an `ObjectDB`,
  so the `targets` parameter to `use_technique` would be empty. PRE_CAST and
  CAST still fire. AFFECTED-per-target waits until the opponent ↔ ObjectDB
  relationship is decided.
- **Frontend changes.** Server-only PR.
- **Refactor of `apply_damage_to_opponent`.** Only the caller changes.

### PR-size constraint

Aim for ~600 lines diff total including tests. The combat-side delta in
`_resolve_pc_action` is intentionally small (~8 lines deleted, ~4 lines
added) so that any concurrent work on `combat/services.py` from the
combat-iterating developer remains merge-friendly.

## Architecture

### Boundary

```
world/combat/services.py
├── resolve_combat_technique(...)        ← NEW: orchestrates the adapter
└── _resolve_pc_action(...)              ← CHANGED: damage path delegates

world/combat/services.py (or sibling submodule)
└── CombatAttackResolver                 ← NEW: dataclass resolver, __call__'d
                                            by use_technique as resolve_fn

world/combat/types.py
└── CombatTechniqueResolution            ← NEW: returned from resolver to
                                            use_technique; consumed by adapter

world/magic/services/techniques.py
└── use_technique                        ← MICRO-CHANGE: check_result extractor
                                            also accepts resolution_result
                                            .check_result directly (3 lines)
```

The adapter lives **combat-side** because combat is the consumer and knows
about `CombatParticipant`, `CombatPull`, `apply_damage_to_opponent`, and
offense check types. Magic stays generic — `use_technique` keeps its single
contract: "give me a `resolve_fn`, I'll wrap the magic envelope around it."

### `use_technique` micro-change

The current extractor in `use_technique` reads `check_result` from
`resolution_result.main_result.check_result` (the social-action shape from
Scope #4). Combat's `CombatTechniqueResolution` exposes `check_result`
directly without a `main_result` wrapper, so the extractor is generalized
to accept either shape:

```python
# After:
if effective_check_result is None:
    effective_check_result = getattr(resolution_result, "check_result", None)
    if effective_check_result is None and hasattr(resolution_result, "main_result"):
        main = resolution_result.main_result
        if main is not None and hasattr(main, "check_result"):
            effective_check_result = main.check_result
```

Behavior unchanged for existing callers; combat callers pick up the new
direct path.

## Data flow

```
_resolve_pc_action(participant, action, ...)
  │
  ├── if combo_upgrade: existing combo path (unchanged)
  ├── if effect_type.base_power is None: no-op (deferred — non-attack types)
  └── else: damage path
        │
        v
resolve_combat_technique(participant, action, target, fatigue_category, ...)
  │
  ├── pull_flat_bonus = sum FLAT_BONUS scaled_value across active pulls for
  │       this participant in this encounter
  │
  ├── resolver = CombatAttackResolver(participant, action, target,
  │       pull_flat_bonus, fatigue_category, offense_check_type,
  │       offense_check_fn)
  │
  └── use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        targets=[],   # AFFECTED deferred
      )
        │
        ├─ runtime stats → effective anima cost → soulfray warning checkpoint
        ├─ TECHNIQUE_PRE_CAST emit (cancellable)
        │       └── on cancel: return TechniqueUseResult(confirmed=False)
        ├─ deduct_anima
        │
        ├─ resolver()  ─────────────────────────────────────────┐
        │     │                                                 │
        │     ├─ extra_modifiers = effort_mod + pull_flat_bonus │
        │     ├─ check_result = perform_check(...)              │
        │     ├─ scaled = base_power if SL>=2; //2 if SL==1; 0  │
        │     ├─ if scaled > 0: apply_damage_to_opponent(...)   │
        │     └─ return CombatTechniqueResolution(...)          │
        │     ◄─────────────────────────────────────────────────┘
        │
        ├─ soulfray accrual (uses .check_result via extractor)
        ├─ mishap rider     (uses .check_result via extractor)
        ├─ corruption accrual
        └─ TECHNIQUE_CAST emit
        ▼
adapter unpacks TechniqueUseResult:
  ├── if not result.confirmed: return empty damage_results (cancelled)
  └── else: pull damage_results out of result.resolution_result
       │
       ▼
_resolve_pc_action appends damage_results to ActionOutcome,
runs apply_fatigue (unconditional — preserves existing contract)
```

### Two invariants preserved

1. **PRE_CAST cancel = no observable side effects.** Damage application
   and the offense check both live inside the resolver, which
   `use_technique` only invokes after PRE_CAST clears. A cancelling
   reactive scar produces `confirmed=False`, no damage, no anima deducted.

2. **Soulfray and mishap see the real check result.** The resolver runs
   the check inside the envelope, and the (extended) extractor in
   `use_technique` hands the right `CheckResult` to soulfray accumulation
   and mishap selection.

## Component shapes

### `CombatTechniqueResolution` (new — `world/combat/types.py`)

```python
@dataclass(frozen=True)
class CombatTechniqueResolution:
    """Returned from a combat resolver into use_technique.

    Frozen — once the inner resolution is computed it cannot change.
    Read by the adapter to populate the outer ActionOutcome.
    """
    check_result: CheckResult
    damage_results: list[OpponentDamageResult]
    pull_flat_bonus: int
    scaled_damage: int
```

`check_result` is a top-level attribute (not nested under `main_result`)
because combat doesn't have an action-resolution wrapper to nest under.
`use_technique`'s extractor handles both shapes.

### `CombatAttackResolver` (new — `world/combat/services.py`)

```python
@dataclass
class CombatAttackResolver:
    """Resolves the inner damage step of a combat-cast attack technique.

    Built by resolve_combat_technique() and passed to use_technique() as
    resolve_fn. State is inspectable at any point during/after the cast,
    which closures don't allow. Subclassable when non-attack effect types
    arrive (next PR): CombatBuffResolver, CombatDefenseResolver, etc.
    """
    participant: CombatParticipant
    action: CombatRoundAction
    target: CombatOpponent
    pull_flat_bonus: int
    fatigue_category: str
    offense_check_type: CheckType
    offense_check_fn: PerformCheckFn | None

    def __call__(self) -> CombatTechniqueResolution:
        check_result = self._roll_check()
        scaled_damage = self._scale(check_result)
        damage_results = self._apply(scaled_damage)
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=scaled_damage,
        )

    def _roll_check(self) -> CheckResult:
        """Roll the offense check with effort + pull-bonus modifiers."""
        ...

    def _scale(self, check_result: CheckResult) -> int:
        """Scale base_power by success_level: full / half / zero."""
        ...

    def _apply(self, scaled_damage: int) -> list[OpponentDamageResult]:
        """Apply damage to target if alive and damage > 0."""
        ...
```

Each step is its own method so subclasses (next PR's
`CombatBuffResolver` etc.) can override what differs without
re-implementing the orchestration.

### `resolve_combat_technique` (new — `world/combat/services.py`)

```python
def resolve_combat_technique(
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent,
    fatigue_category: str,
    offense_check_type: CheckType,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Route a damage-path combat technique through use_technique."""
    encounter = participant.encounter
    pull_flat_bonus = _sum_active_flat_bonuses(participant, encounter)

    resolver = CombatAttackResolver(
        participant=participant,
        action=action,
        target=target,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=fatigue_category,
        offense_check_type=offense_check_type,
        offense_check_fn=offense_check_fn,
    )

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        targets=[],   # AFFECTED-per-target deferred — see spec
    )

    return _build_combat_result(technique_use_result, resolver)
```

### `_resolve_pc_action` change

```python
def _resolve_pc_action(...):
    outcome = ActionOutcome(...)
    technique = action.focused_action
    if technique is None:
        return outcome

    target = action.focused_target
    fatigue_category = _ACTION_TO_FATIGUE_CATEGORY.get(...)

    if target is not None:
        target.refresh_from_db()
        if target.status != OpponentStatus.DEFEATED:
            if action.combo_upgrade:
                # combo path UNCHANGED
                ...
            elif technique.effect_type.base_power is not None:
                # damage path — route through magic pipeline
                combat_result = resolve_combat_technique(
                    participant=participant,
                    action=action,
                    target=target,
                    fatigue_category=fatigue_category,
                    offense_check_type=offense_check_type,
                    offense_check_fn=offense_check_fn,
                )
                outcome.damage_results.extend(combat_result.damage_results)
            else:
                # non-attack effect type — deferred PR adds the pipeline
                # (Defense / Buff / Movement / Debuff applying conditions)
                pass

    apply_fatigue(...)   # unchanged — applies even on cancel
    return outcome
```

## Cancel and error handling

| Failure mode | Behavior |
|---|---|
| PRE_CAST cancelled by reactive scar | `confirmed=False`, anima not deducted, resolver never called, adapter returns empty `damage_results`. Fatigue still applied (preserves existing contract). |
| Soulfray warning at checkpoint | Round resolution always passes `confirm_soulfray_risk=True` (frontend handles preview). If `False` is somehow passed, treated identically to cancel. |
| Anima overburn | Existing `use_technique` semantics: anima deducts to negative/zero, soulfray severity accrues. No combat-specific handling. |
| Missing `CharacterAnima` for caster | `use_technique` raises `DoesNotExist`. PCs always have `CharacterAnima`; raising on a missing row is the correct data-integrity signal. |
| Resolver raises mid-cast | Anima already deducted; exception propagates. Existing transactional model of `use_technique` — combat inherits it. |
| Target defeated mid-resolution | Preserved inside `CombatAttackResolver._apply`: `target.refresh_from_db()`, skip if `status == DEFEATED`. |
| Non-attack effect type (`base_power is None`) | `_resolve_pc_action` checks before invoking adapter. No-op behavior preserved until next PR. |

## Tests

### Integration tests — `world/combat/tests/test_combat_magic_integration.py`

| Test | Assertion |
|---|---|
| `test_combat_cast_deducts_anima` | `CharacterAnima.current` decreases by `effective_cost` after combat round resolves a technique |
| `test_pre_cast_emitted_in_combat` | `TECHNIQUE_PRE_CAST` payload captured during round resolution |
| `test_cast_emitted_in_combat` | `TECHNIQUE_CAST` payload captured after round resolution |
| `test_reactive_scar_cancels_combat_cast` | `ReactiveCondition` on PRE_CAST with cancel flow → no damage, no anima deducted, no `TECHNIQUE_CAST` emitted |
| `test_mishap_fires_on_combat_control_deficit` | technique with `intensity > control` → mishap conditions present on caster after round |
| `test_active_flat_bonus_pulls_modify_offense_check` | participant has active `CombatPull` with FLAT_BONUS scaled_value=4 → `perform_check` called with `extra_modifiers` including +4 |
| `test_combat_damage_routes_through_pipeline` | full happy path — anima deducted, damage applied, events emitted, `OpponentDamageResult.damage_dealt > 0` |

### Unit tests — `world/combat/tests/test_combat_attack_resolver.py`

| Test | Assertion |
|---|---|
| `test_resolver_rolls_check_with_pull_bonus` | resolver with `pull_flat_bonus=3` → `perform_check` receives `extra_modifiers` containing 3 |
| `test_resolver_full_success_returns_full_damage` | mock `perform_check` returns `success_level=2` → `scaled_damage == base_power` |
| `test_resolver_partial_success_returns_half_damage` | `success_level=1` → `scaled_damage == base_power // 2` |
| `test_resolver_miss_returns_zero_damage` | `success_level=0` → `scaled_damage == 0`, no `apply_damage_to_opponent` call |
| `test_resolver_skips_defeated_target` | target with `status=DEFEATED` → `damage_results=[]` even on hit |

### Test data

All factories already exist: `CombatParticipantFactory`,
`CombatOpponentFactory`, `CombatPullFactory`,
`CombatPullResolvedEffectFactory`, `TechniqueFactory`,
`CharacterAnimaFactory`. No new factories needed.

### Regression coverage

The existing `_scale_damage_by_check` inline body is removed (logic moves
into `CombatAttackResolver._roll_check` + `_scale`). No callers remain
after the swap. Existing combat round-resolution tests assert observable
damage outcomes, which the new path produces equivalently.

## Anti-patterns avoided

- **Inverting dependencies.** Magic does not import combat. The adapter
  lives combat-side; magic only learns about combat through the
  `resolve_fn` callback contract.
- **Closure-captured state.** Resolver is a dataclass with explicit
  attributes, not a closure. Inspectable, testable, subclassable.
- **Speculative pull-effect routing.** Only `FLAT_BONUS` is consumed in
  this PR, per Spec A §5.8. Other kinds are commented at the call site
  with their deferred owners.
- **Combat-specific failure modes for anima.** Overburn is the existing
  `use_technique` semantic; combat inherits it without inventing a
  combat-only rejection path.

## References

- `src/world/magic/services/techniques.py:use_technique`
- `src/world/combat/services.py:_resolve_pc_action`
- `src/world/magic/tests/test_reactive_integration.py` (cancel-path pattern)
- `docs/superpowers/specs/2026-04-02-scope4-scene-magic-enhancement-design.md`
  (the social-action wrapper pattern this spec mirrors for combat)
- `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md`
  §5.8 (FLAT_BONUS routing rule)

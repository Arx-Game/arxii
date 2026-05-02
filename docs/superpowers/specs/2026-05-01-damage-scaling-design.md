# Damage Scaling by Effective Intensity

**Date:** 2026-05-01
**Status:** Spec — pre-implementation
**Owner:** brann
**Predecessors:**
- `docs/superpowers/specs/2026-04-30-combat-magic-pipeline-integration-design.md`
- `docs/superpowers/specs/2026-05-01-combat-magic-non-attack-effects-design.md`

## Purpose

Route `effective_intensity` (the aggregator added by the non-attack effects PR — `technique.intensity` + INTENSITY_BUMP pull contributions + future hooks) into damage calculation, mirroring what was done for condition severity and duration. Today combat damage is `EffectType.base_power × SL_threshold` (full / half / zero) — flat per-type, doesn't reflect caster investment, can't differentiate techniques within the same effect type.

This spec adds:

1. **Per-technique damage authoring** via a new `TechniqueDamageProfile` through-model. Each row is one damage component with the same formula shape used by `TechniqueAppliedCondition` and `TechniqueCapabilityGrant`. A technique can have multiple rows for multi-component damage (e.g., a slashing fire sword: one slashing row + one fire row).
2. **Damage types and resistance lookup.** `TechniqueDamageProfile.damage_type` and `ThreatPoolEntry.damage_type` (FKs to existing `DamageType`). Damage application reads `ConditionResistanceModifier` rows on the target for matching damage types and applies the modifier as flat additional soak (negative modifier = vulnerability). Closes the existing `damage_type=None # TODO` in `_resolve_npc_action`.
3. **Tunable success-level multiplier.** `DamageSuccessLevelMultiplier` lookup table replaces the inline full/half/zero thresholds in the PC offense path. Sane defaults seeded by the planned startup-page mechanism (or factories in tests). Tunable in admin without code changes.
4. **Capability-grant `effective_intensity` extension.** `TechniqueCapabilityGrant.calculate_value()` accepts an `effective_intensity` override so combat-internal Challenge resolution (a future feature) can read pull-bumped Capability values. Out-of-combat callers continue to use `technique.intensity` unchanged.

The pattern is **per-subsystem profile models, one shared formula shape**: Capabilities (existing), Conditions (existing), Damage (new), each with its own subsystem-specific metadata. They unify at the formula level, not the model level.

## Scope

### In scope

- New `TechniqueDamageProfile` through-model (`world/magic/models/techniques.py`).
- New `DamageSuccessLevelMultiplier` lookup model (`world/conditions/models.py`).
- `ThreatPoolEntry.damage_type` FK (`world/combat/models.py`).
- `apply_damage_to_opponent` and `apply_damage_to_participant` accept `damage_type` and apply resistance lookup.
- `_resolve_npc_action` passes `threat_entry.damage_type` (closes pre-existing TODO).
- `CombatTechniqueResolver._apply_damage` rewritten to iterate damage profiles and use the multiplier lookup.
- `TechniqueCapabilityGrant.calculate_value()` keyword-only `effective_intensity` override.
- `get_resistance_modifier_for_target(target, damage_type)` and `get_damage_multiplier(success_level)` helpers in `world/conditions/services.py`.
- `TechniqueFactory.post_generation` seeds a damage profile from `EffectType.base_power` so existing tests don't need per-test setup.
- Tests across `world/magic`, `world/combat`, `world/conditions`.

### Out of scope (deferred)

- **Frontend** — server-only PR.
- **`ConditionDamageInteraction` wiring** (Frozen+Force = +50% damage and removes Frozen). Different mechanic from flat resistance; needs its own resolution flow that can apply/remove conditions mid-damage. Wire after observing flat resistance behavior in play.
- **Defense-side multiplier lookup table** — `DEFENSE_FULL_MULTIPLIER` etc. stay as constants. Pulling them out symmetrically is a follow-up PR.
- **Multi-component NPC damage** — `ThreatPoolEntry` gets `damage_type` FK only. Multi-component would need a parallel `ThreatPoolEntryDamageProfile` model; defer until authoring need appears.
- **Condition stack-count effect on resistance** — `ConditionResistanceModifier` reads `modifier_value` flat. A future `scales_with_severity` flag could match `ConditionCheckModifier`'s shape; not needed now.
- **Combat-internal Challenge resolution callers for `TechniqueCapabilityGrant.calculate_value`** — the `effective_intensity` keyword is added but no combat caller uses it yet. Lands when mid-combat Challenge resolution becomes a feature.
- **`EffectType.base_power` retirement** — stays as an authoring-time default seed. Remove when content tooling matures and the field has nothing live depending on it.
- **Auto-seed of `DamageSuccessLevelMultiplier` rows** — startup-page mechanism (planned) handles first-game-launch defaults. Tests use the factory.

## Architecture

### Boundaries

- **Combat does not import magic models.** Reads `technique.damage_profiles` via the existing reverse-FK relation it already uses for `technique.condition_applications`.
- **Magic does not import combat.** `compute_effective_intensity` lives combat-side; magic stays generic.
- **Conditions does not import combat.** `get_resistance_modifier_for_target` and `get_damage_multiplier` operate on `ObjectDB` targets and accept `DamageType` instances; combat consumes them but conditions doesn't know about encounters.
- **No data migrations.** Schema-only. `DamageSuccessLevelMultiplier` defaults seeded via factories (tests) or the startup-page mechanism (production).

### Module map

```
world/magic/
├── models/techniques.py
│   ├── Technique                   ← unchanged (no new fields)
│   ├── TechniqueCapabilityGrant    ← .calculate_value() accepts effective_intensity override
│   └── TechniqueDamageProfile      ← NEW
├── factories.py
│   ├── TechniqueFactory            ← post_generation seeds a damage profile from EffectType.base_power
│   └── TechniqueDamageProfileFactory ← NEW
└── tests/
    └── test_technique_damage_profile.py ← NEW

world/combat/
├── models.py
│   └── ThreatPoolEntry             ← add damage_type FK (nullable)
├── services.py
│   ├── CombatTechniqueResolver._apply_damage      ← iterates damage_profiles, applies each component
│   ├── apply_damage_to_opponent                   ← accept damage_type kwarg; subtract resistance
│   ├── apply_damage_to_participant                ← migrate damage_type from str to FK; resistance lookup
│   ├── _resolve_npc_action                        ← passes threat_entry.damage_type (closes TODO)
│   └── compute_effective_intensity                ← unchanged
└── tests/
    ├── test_damage_scaling_pipeline.py            ← NEW
    └── test_npc_damage_types.py                   ← NEW

world/conditions/
├── models.py
│   ├── ConditionResistanceModifier ← unchanged (model exists; gains a consumer)
│   └── DamageSuccessLevelMultiplier ← NEW lookup table
├── services.py
│   ├── get_resistance_modifier_for_target(target, damage_type) ← NEW
│   └── get_damage_multiplier(success_level)                    ← NEW
├── factories.py
│   └── DamageSuccessLevelMultiplierFactory ← NEW
└── tests/
    ├── test_damage_multiplier.py    ← NEW
    └── test_resistance_lookup.py    ← NEW
```

## Data flow

### PC technique cast in combat

```
_resolve_pc_action(participant, action)
  │
  ├─ if combo_upgrade: existing combo path (unchanged — combos own bypass_soak)
  │
  └─ else: resolve_combat_technique(...)
        ▼
  CombatTechniqueResolver.__call__()
        │
        ├─ check_result = _roll_check()
        ├─ damage_results = _apply_damage(check_result)
        │     │
        │     ├─ target = action.focused_opponent_target  (None → return [])
        │     ├─ target.refresh_from_db(); skip if DEFEATED
        │     ├─ profiles = list(technique.damage_profiles.select_related("damage_type"))
        │     │       (no profiles → return [])
        │     ├─ eff_intensity = compute_effective_intensity(participant, action)
        │     ├─ multiplier = get_damage_multiplier(check_result.success_level)
        │     │       (≤ 0 → return [])
        │     │
        │     └─ for each profile:
        │           skip if SL < profile.minimum_success_level
        │           budget = profile.compute_damage_budget(eff_intensity, SL)
        │           scaled = int(budget * multiplier)
        │           skip if scaled ≤ 0
        │           ▼
        │     apply_damage_to_opponent(target, scaled, damage_type=profile.damage_type)
        │           │
        │           ├─ effective_soak = target.soak_value
        │           ├─ resistance = get_resistance_modifier_for_target(
        │           │       target.objectdb, profile.damage_type)
        │           │       (0 if damage_type is None; negative = vulnerability)
        │           ├─ damage_through = max(0, raw_damage − soak − resistance)
        │           ├─ probing_increment = raw_damage  (probing reads pre-soak/resistance)
        │           ├─ apply to health, save status, return OpponentDamageResult
        │
        └─ applied_conditions = _apply_conditions(check_result)  (existing, unchanged)
```

Each damage component fires its own `apply_damage_to_opponent` call → its own `OpponentDamageResult`. Multiple `DAMAGE_PRE_APPLY` and `DAMAGE_APPLIED` events emit per cast (one per component). Reactive subscribers see each independently.

### NPC attack against a PC

```
_resolve_npc_action(opponent, npc_action)
  │
  └─ resolve_npc_attack(opponent_action, participant, ...)
        │
        ├─ check_result = perform_check(character, defense_check_type)  (defense roll)
        ├─ multiplier = _damage_multiplier_for_success(check_result.success_level)
        │     (existing DEFENSE_* constants — out of scope)
        ├─ final_damage = floor(threat_entry.base_damage × multiplier)
        │
        └─ apply_damage_to_participant(
              participant, final_damage,
              damage_type=opponent_action.threat_entry.damage_type,  # NEW (was None)
              source=opponent_action.opponent,
            )
              │
              ├─ DAMAGE_PRE_APPLY emit (cancellable)
              ├─ effective_damage from payload
              ├─ effective_damage = apply_damage_reduction_from_threads(...)  (existing)
              ├─ resistance = get_resistance_modifier_for_target(character, damage_type)  # NEW
              ├─ effective_damage = max(0, effective_damage − resistance)
              ├─ vitals.health -= effective_damage
              └─ DAMAGE_APPLIED emit, incapacitation/death gates (existing)
```

### `get_resistance_modifier_for_target` flow

```python
def get_resistance_modifier_for_target(
    target: ObjectDB,
    damage_type: DamageType | None,
) -> int:
    """Sum ConditionResistanceModifier values across active conditions
    on the target whose damage_type matches (specific or null = all-types).
    Negative return = vulnerability; positive = resistance."""
    if damage_type is None:
        return 0
    instances = target.condition_instances.filter(
        is_suppressed=False, resolved_at__isnull=True,
    ).select_related("condition", "current_stage")
    total = 0
    for instance in instances:
        # Template-level (applies at all stages)
        for mod in ConditionResistanceModifier.objects.filter(
            condition=instance.condition,
            damage_type__in=[damage_type, None],
        ):
            total += mod.modifier_value
        # Stage-level (only when at that stage)
        if instance.current_stage:
            for mod in ConditionResistanceModifier.objects.filter(
                stage=instance.current_stage,
                damage_type__in=[damage_type, None],
            ):
                total += mod.modifier_value
    return total
```

A condition like "Wet" might author:
- `damage_type=Fire, modifier_value=10` → +10 fire resistance
- `damage_type=Lightning, modifier_value=-15` → −15 lightning resistance (vulnerability)

These coexist as separate `ConditionResistanceModifier` rows on one `ConditionTemplate`. The lookup picks up only rows matching the incoming `damage_type` (or null = all-types).

### Multi-component damage worked example

A "slashing fire sword" technique with two damage profiles:
- Row 1: `damage_type=Slashing, base_damage=10, intensity_mult=Decimal("0.5")`
- Row 2: `damage_type=Fire, base_damage=4, intensity_mult=Decimal("0.3")`

At intensity=8, SL=2 (full success), multiplier=1.0:
- Row 1 budget: `10 + ⌊0.5 × 8⌋ = 14` → scaled `14 × 1.0 = 14`
- Row 2 budget: `4 + ⌊0.3 × 8⌋ = 6` → scaled `6 × 1.0 = 6`

Each is applied as a separate `apply_damage_to_opponent` call. Two `DAMAGE_PRE_APPLY` and two `DAMAGE_APPLIED` events fire. Soak (say 5) and resistance per type apply independently:

- Opponent has Wet condition: +10 Fire resistance, no Slashing modifier
- Slashing component: `max(0, 14 − 5 − 0) = 9` damage
- Fire component: `max(0, 6 − 5 − 10) = 0` damage (Wet absorbs the fire)
- Total: 9 damage, two distinct `OpponentDamageResult` entries
- `probing_current` increases by `14 + 6 = 20` (raw, pre-soak, per-component)

## Component shapes

### `TechniqueDamageProfile` (`world/magic/models/techniques.py`)

```python
class TechniqueDamageProfile(SharedMemoryModel):
    """One damage component a technique deals when used in combat."""

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="technique_damage_profiles",
        help_text="Damage type for resistance lookup. Null = untyped damage.",
    )
    minimum_success_level = models.PositiveIntegerField(default=1)

    base_damage = models.PositiveIntegerField(default=0)
    damage_intensity_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
    )
    damage_per_extra_sl = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "damage_type"],
                name="unique_damage_profile_per_technique_per_type",
            ),
        ]

    def __str__(self) -> str:
        type_str = self.damage_type.name if self.damage_type else "untyped"
        return f"{self.technique.name} → {self.base_damage} {type_str}"

    def compute_damage_budget(
        self, *, effective_intensity: int, success_level: int,
    ) -> int:
        intensity_contribution = int(
            self.damage_intensity_multiplier * effective_intensity,
        )
        sl_above = max(0, success_level - self.minimum_success_level)
        sl_contribution = self.damage_per_extra_sl * sl_above
        return self.base_damage + intensity_contribution + sl_contribution
```

Unique-together on `(technique, damage_type)` means at most one row per damage type per technique. A "slashing+fire sword" has one slashing row and one fire row — two distinct types.

`bypass_soak` is intentionally not a field — combos own that knob; solo casts always pass through soak. (See follow-up: if a future spec wants conditional soak-bypass, route through combos or Challenge resolution.)

### `DamageSuccessLevelMultiplier` (`world/conditions/models.py`)

```python
class DamageSuccessLevelMultiplier(NaturalKeyMixin, SharedMemoryModel):
    """Tunable lookup: success_level → damage multiplier.

    Resolver picks the highest-threshold row whose min_success_level is
    ≤ the actual SL. Below the lowest threshold yields zero damage.
    """
    min_success_level = models.IntegerField(unique=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2)
    label = models.CharField(max_length=64, blank=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["min_success_level"]

    class Meta:
        ordering = ["-min_success_level"]

    def __str__(self) -> str:
        suffix = f" — {self.label}" if self.label else ""
        return f"SL ≥ {self.min_success_level}: ×{self.multiplier}{suffix}"
```

Defaults seeded by the startup-page (production) or factory (tests):
- `(min_success_level=2, multiplier=Decimal("1.00"), label="Full")`
- `(min_success_level=1, multiplier=Decimal("0.50"), label="Partial")`

### `ThreatPoolEntry` change

```python
damage_type = models.ForeignKey(
    "conditions.DamageType",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="threat_pool_entries",
    help_text="Damage type for resistance lookup. Null = untyped attack.",
)
```

### Helpers in `world/conditions/services.py`

```python
def get_resistance_modifier_for_target(
    target: ObjectDB,
    damage_type: DamageType | None,
) -> int:
    """Sum ConditionResistanceModifier values across active conditions on
    the target whose damage_type matches (or is null = all-types).
    Returns 0 for null damage_type or no relevant conditions.
    Negative return values mean vulnerability."""
    if damage_type is None:
        return 0
    instances = target.condition_instances.filter(
        is_suppressed=False,
        resolved_at__isnull=True,
    ).select_related("condition", "current_stage")
    total = 0
    for instance in instances:
        for mod in ConditionResistanceModifier.objects.filter(
            condition=instance.condition,
            damage_type__in=[damage_type, None],
        ):
            total += mod.modifier_value
        if instance.current_stage:
            for mod in ConditionResistanceModifier.objects.filter(
                stage=instance.current_stage,
                damage_type__in=[damage_type, None],
            ):
                total += mod.modifier_value
    return total


def get_damage_multiplier(success_level: int) -> Decimal:
    """Highest matching threshold wins. SL below the lowest yields 0."""
    rows = DamageSuccessLevelMultiplier.objects.filter(
        min_success_level__lte=success_level,
    ).order_by("-min_success_level")
    first = rows.first()
    return first.multiplier if first else Decimal("0")
```

### `CombatTechniqueResolver._apply_damage`

```python
def _apply_damage(
    self, check_result: CheckResult,
) -> list[OpponentDamageResult]:
    target = self.action.focused_opponent_target
    if target is None:
        return []
    target.refresh_from_db()
    if target.status == OpponentStatus.DEFEATED:
        return []

    technique = self.action.focused_action
    profiles = list(
        technique.damage_profiles.select_related("damage_type").all(),
    )
    if not profiles:
        return []

    sl = check_result.success_level
    eff_intensity = compute_effective_intensity(self.participant, self.action)
    multiplier = get_damage_multiplier(sl)
    if multiplier <= 0:
        return []

    results: list[OpponentDamageResult] = []
    for profile in profiles:
        if sl < profile.minimum_success_level:
            continue
        budget = profile.compute_damage_budget(
            effective_intensity=eff_intensity, success_level=sl,
        )
        scaled = int(budget * multiplier)
        if scaled <= 0:
            continue
        target.refresh_from_db()
        if target.status == OpponentStatus.DEFEATED:
            break  # don't keep hammering a defeated target
        result = apply_damage_to_opponent(
            target,
            scaled,
            damage_type=profile.damage_type,
        )
        results.append(result)
    return results
```

### `apply_damage_to_opponent` change

Add `damage_type` kwarg; subtract resistance before health change:

```python
def apply_damage_to_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
    damage_type: DamageType | None = None,
) -> OpponentDamageResult:
    effective_soak = 0 if bypass_soak else opponent.soak_value

    resistance = 0
    if damage_type is not None and opponent.objectdb is not None:
        resistance = get_resistance_modifier_for_target(
            opponent.objectdb, damage_type,
        )

    damage_through = max(0, raw_damage - effective_soak - resistance)
    probing_increment = 0 if bypass_soak else max(0, raw_damage)

    opponent.health -= damage_through
    opponent.probing_current += probing_increment

    defeated = opponent.health <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED

    opponent.save(update_fields=["health", "probing_current", "status"])

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
    )
```

`apply_damage_to_participant` gets the same treatment — current `damage_type: str` parameter migrates to `damage_type: DamageType | None` (FK). Caller migration is small (current callers in the combat module only).

### `TechniqueCapabilityGrant.calculate_value` extension

```python
def calculate_value(
    self, *, effective_intensity: int | None = None,
) -> int:
    """effective_intensity: when provided (e.g., from combat where pull
    bumps may apply), uses that aggregate. When None (out-of-combat
    challenges), falls back to self.technique.intensity."""
    intensity = (
        effective_intensity
        if effective_intensity is not None
        else self.technique.intensity
    )
    return int(self.base_value + (self.intensity_multiplier * Decimal(intensity)))
```

Existing callers pass nothing → behavior unchanged. No combat-side caller is added in this PR; the keyword is reserved for future Challenge-in-combat work.

### Factory updates

```python
class TechniqueDamageProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TechniqueDamageProfile
    technique = factory.SubFactory("world.magic.factories.TechniqueFactory")
    damage_type = None
    minimum_success_level = 1
    base_damage = 5
    damage_intensity_multiplier = Decimal("0")
    damage_per_extra_sl = 0


class TechniqueFactory(factory.django.DjangoModelFactory):
    # ... existing fields ...

    @factory.post_generation
    def damage_profile(self, create, extracted, **kwargs):
        """Auto-seed a damage profile from EffectType.base_power when present.
        Pass damage_profile=False to skip; pass an explicit profile dict to override.
        """
        if not create or extracted is False:
            return
        if extracted is not None:
            return  # caller provided their own; assume already attached
        if self.effect_type.base_power:
            TechniqueDamageProfileFactory(
                technique=self,
                base_damage=self.effect_type.base_power,
            )


class DamageSuccessLevelMultiplierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DamageSuccessLevelMultiplier
        django_get_or_create = ("min_success_level",)
    min_success_level = 2
    multiplier = Decimal("1.00")
    label = "Full"
```

Tests that exercise damage resolution call `DamageSuccessLevelMultiplierFactory(min_success_level=2, multiplier=Decimal("1.00"))` and `DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("0.50"))` in `setUpTestData`.

## Cancel and error handling

| Failure mode | Behavior |
|---|---|
| Technique has no damage profiles | `_apply_damage` returns `[]` immediately. Conditions still apply if condition profiles exist. Pure narrative-only techniques unaffected. |
| `damage_type=None` (untyped) | Resistance lookup short-circuits to 0. Soak still applies. |
| Target has no `objectdb` (post-cleanup edge) | Resistance lookup short-circuits to 0; damage proceeds with soak only. |
| `DamageSuccessLevelMultiplier` table empty (unseeded) | `get_damage_multiplier` returns 0 → no damage applied. Tests catch this via factory setup; production is seeded by the startup page. |
| `DAMAGE_PRE_APPLY` cancelled by reactive | One component cancelled; other components in the same cast still fire (separate events per component). |
| Multiple components on a target defeated mid-cast | Loop breaks on the first `target.status == DEFEATED` check after a damage application. Subsequent components don't fire. No posthumous damage events. |
| Resistance modifier sums to large negative (heavy vulnerability) | Damage amplified; clamped at end by `max(0, …)`. If play exposes pathological amplification, a clamp on resistance itself can be added in a one-line follow-up. |

## Tests

### Magic — `TechniqueDamageProfile` (`world/magic/tests/test_technique_damage_profile.py`)

- `test_compute_damage_budget_baseline` — base only, regardless of intensity/SL.
- `test_compute_damage_budget_intensity_scaling` — `intensity_mult × eff_intensity` term.
- `test_compute_damage_budget_sl_kicker` — `per_extra_sl × (SL − min_sl)` term.
- `test_compute_damage_budget_below_min_sl_unaffected_by_kicker`.
- `test_unique_constraint_per_technique_per_damage_type` — duplicate raises.
- `test_null_damage_type_allowed_once` — one untyped row per technique.

### Conditions — `DamageSuccessLevelMultiplier` (`world/conditions/tests/test_damage_multiplier.py`)

- `test_get_damage_multiplier_returns_zero_when_table_empty`.
- `test_get_damage_multiplier_returns_full_at_threshold`.
- `test_get_damage_multiplier_returns_partial_below_full`.
- `test_get_damage_multiplier_returns_zero_below_lowest`.
- `test_highest_threshold_wins`.

### Conditions — resistance lookup (`world/conditions/tests/test_resistance_lookup.py`)

- `test_returns_zero_for_no_active_conditions`.
- `test_returns_zero_for_null_damage_type`.
- `test_template_level_modifier_for_matching_type`.
- `test_template_level_modifier_for_all_types_damage_type_null`.
- `test_stage_level_modifier_when_at_that_stage`.
- `test_negative_modifier_means_vulnerability`.
- `test_aggregates_across_multiple_conditions`.
- `test_skips_suppressed_instances`.
- `test_skips_resolved_instances`.

### Combat — damage pipeline integration (`world/combat/tests/test_damage_scaling_pipeline.py`)

- `test_resolver_skips_when_no_damage_profiles` — conditions only technique still casts; no damage fires.
- `test_single_component_damage_full_success` — happy path.
- `test_single_component_damage_partial_success` — half damage on partial.
- `test_intensity_scales_damage` — INTENSITY_BUMP pull → boosted damage.
- `test_multi_component_damage_each_applied_separately` — two events, two results.
- `test_resistance_modifier_reduces_damage_for_matching_type`.
- `test_resistance_modifier_does_not_apply_to_other_types`.
- `test_negative_resistance_amplifies_damage`.
- `test_threshold_lookup_below_min_sl_yields_no_damage`.
- `test_subsequent_components_skip_after_target_defeated`.
- `test_solo_cast_never_passes_bypass_soak` — explicit assertion that the resolver path never sets `bypass_soak=True`.

### NPC side (`world/combat/tests/test_npc_damage_types.py`)

- `test_npc_attack_passes_damage_type_through` — DAMAGE_PRE_APPLY payload carries the threat entry's damage type.
- `test_npc_attack_resistance_lookup_applies` — PC has resistant condition → damage reduced.

### Magic — capability-grant override

- `test_calculate_value_uses_effective_intensity_override`.
- `test_calculate_value_default_uses_technique_intensity`.

### Factory & regression

- `test_technique_factory_seeds_damage_profile_from_effect_type`.
- `test_technique_factory_skip_damage_profile_when_explicitly_disabled`.
- `test_existing_combat_damage_tests_still_pass` — existing assertions hold under the new pipeline.

### Test discipline

- All test data via FactoryBoy. No fixtures.
- `setUpTestData` for shared content per class.
- Per-app development: `arx test world.magic`, `arx test world.combat`, `arx test world.conditions`.
- **No-keepdb sweep before declaring done**: `echo "yes" | uv run arx test`. Per the lesson from #413, do not skip this.
- Frontend untouched (server-only PR).

## Migration plan

Schema-only. No data migrations.

### Migration order

1. `magic` — `TechniqueDamageProfile` model and unique constraint.
2. `combat` — `ThreatPoolEntry.damage_type` FK (nullable).
3. `conditions` — `DamageSuccessLevelMultiplier` model.

Each is independent of the others.

### Code update sequencing

Single branch. Commits in this order so reviewers can step through:

1. Conditions schema + factory + `get_damage_multiplier` helper.
2. Magic schema + factory + `compute_damage_budget`.
3. `TechniqueFactory.post_generation` seeds a damage profile from `EffectType.base_power`.
4. `TechniqueCapabilityGrant.calculate_value()` `effective_intensity` override.
5. Combat schema + `ThreatPoolEntry.damage_type` factory updates.
6. `get_resistance_modifier_for_target` helper.
7. `apply_damage_to_opponent` and `apply_damage_to_participant` accept `damage_type`; resistance lookup wired.
8. `_resolve_npc_action` passes `threat_entry.damage_type` (closes TODO).
9. `CombatTechniqueResolver._apply_damage` rewritten.
10. Tests added per step (not bulk-at-the-end).

## Anti-patterns avoided

- **Coupling Technique to a specific subsystem.** No `damage_*` fields on `Technique`. Damage authoring lives in `TechniqueDamageProfile`, parallel to `TechniqueAppliedCondition` and `TechniqueCapabilityGrant`. Future subsystems (summons, etc.) get their own profile models.
- **One-mega-effect-model unification.** Each subsystem has its own metadata; collapsing them under a single "scaled effect" model would force every subsystem's quirks into one schema. The unification is at the formula level, not the model level.
- **Per-technique soak bypass.** `bypass_soak` stays combo-only. Solo casts can never bypass soak. Architectural rule, not author discipline.
- **Hardcoded SL multipliers.** Replaced with a tunable lookup table so combat damage feel can be retuned without code changes.
- **Cross-app imports between magic and combat.** Combat reads `technique.damage_profiles` via reverse-FK; no model-import dependency.
- **Inline narration of removed fields.** No comments noting what was removed or omitted; the schema speaks for itself.

## References

- `docs/superpowers/specs/2026-04-30-combat-magic-pipeline-integration-design.md` — predecessor (damage path through use_technique).
- `docs/superpowers/specs/2026-05-01-combat-magic-non-attack-effects-design.md` — predecessor (TechniqueAppliedCondition, compute_effective_intensity, CombatOpponent → ObjectDB).
- `src/world/magic/models/techniques.py` — Technique, TechniqueCapabilityGrant, TechniqueAppliedCondition.
- `src/world/conditions/models.py` — DamageType, ConditionResistanceModifier, ConditionInstance.
- `src/world/combat/services.py` — CombatTechniqueResolver, apply_damage_to_opponent, _resolve_npc_action.

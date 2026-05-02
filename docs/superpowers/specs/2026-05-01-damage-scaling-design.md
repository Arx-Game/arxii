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
├── handlers.py                      ← NEW: CharacterConditionHandler (mirrors CharacterCombatPullHandler)
├── services.py
│   └── get_damage_multiplier(success_level) ← NEW (single query per cast — table is tiny)
├── factories.py
│   └── DamageSuccessLevelMultiplierFactory ← NEW
└── tests/
    ├── test_damage_multiplier.py            ← NEW
    └── test_character_condition_handler.py  ← NEW

typeclasses/characters.py            ← wire `character.conditions = CharacterConditionHandler(self)`
                                       (mirrors how `character.combat_pulls` is wired)
```

**Why a handler, not a service function.** A
`get_resistance_modifier_for_target(target, damage_type)` service function
that queries `target.condition_instances.filter(...)` re-hits the database
on every call — defeating SharedMemoryModel's identity-map cache and
forcing the same prefetch work per damage component. The right pattern is
a per-character handler that loads active ConditionInstances + their
resistance modifiers once, exposes a `resistance_modifier(damage_type)`
method that walks the cached list in Python, and is invalidated by
mutation services. See `world/combat/handlers.py:CharacterCombatPullHandler`
for the reference.

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
        │           ├─ resistance = target.objectdb.conditions.resistance_modifier(
        │           │       profile.damage_type)
        │           │       (handler reads the cached active-condition list once
        │           │        per cast; 0 if damage_type is None;
        │           │        negative = vulnerability)
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
              ├─ resistance = character.conditions.resistance_modifier(damage_type)  # NEW
              ├─ effective_damage = max(0, effective_damage − resistance)
              ├─ vitals.health -= effective_damage
              └─ DAMAGE_APPLIED emit, incapacitation/death gates (existing)
```

### `CharacterConditionHandler` (`world/conditions/handlers.py`)

Mirrors `CharacterCombatPullHandler`. Loads active condition instances
with their resistance modifiers prefetched on first read; subsequent
reads walk the cached list in Python. Wired onto the Character
typeclass as `character.conditions`.

```python
class CharacterConditionHandler:
    """Per-character handler over active ConditionInstance rows."""

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _active(self) -> list[ConditionInstance]:
        return list(
            ConditionInstance.objects.filter(
                target=self.character,
                is_suppressed=False,
                resolved_at__isnull=True,
            )
            .select_related("condition", "current_stage")
            .prefetch_related(
                Prefetch(
                    "condition__conditionresistancemodifier_set",
                    to_attr="resistance_modifiers_cached",
                ),
                Prefetch(
                    "current_stage__conditionresistancemodifier_set",
                    to_attr="resistance_modifiers_cached",
                ),
            )
        )

    def active(self) -> list[ConditionInstance]:
        return self._active

    def resistance_modifier(self, damage_type: DamageType | None) -> int:
        """Sum ConditionResistanceModifier values across active instances
        whose damage_type matches (specific) or is null (all-types).

        Walks the cached active list — no DB query past the first access.
        Negative return = vulnerability; positive = resistance.
        """
        if damage_type is None:
            return 0
        total = 0
        for instance in self._active:
            for mod in instance.condition.resistance_modifiers_cached:
                if mod.damage_type_id in (damage_type.pk, None):
                    total += mod.modifier_value
            if instance.current_stage_id:
                for mod in instance.current_stage.resistance_modifiers_cached:
                    if mod.damage_type_id in (damage_type.pk, None):
                        total += mod.modifier_value
        return total

    def invalidate(self) -> None:
        """Clear the cached active list. Called by condition mutation services
        (apply_condition / bulk_apply_conditions / process_round_end / etc.)."""
        self.__dict__.pop("_active", None)
```

**Wiring on Character.** The Character typeclass installs the handler
the same way `combat_pulls` is installed (via a property or `at_init`).
Implementation detail for the plan; the spec just says "available as
`character.conditions`."

**Invalidation responsibilities.** Existing condition-mutation services
(`apply_condition`, `bulk_apply_conditions`, `process_round_start`,
`process_round_end`, treatment / decay / suppression services) must call
`character.conditions.invalidate()` after writing to keep the cache in
sync. The plan should grep for ConditionInstance writes (.save(), .create(),
.update(), .delete()) and ensure each site follows the mutation with
the invalidate call. Mirror of how combat_pulls invalidation works in
`expire_pulls_for_round`.

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
            # Non-null pairs: one row per (technique, damage_type)
            models.UniqueConstraint(
                fields=["technique", "damage_type"],
                condition=Q(damage_type__isnull=False),
                name="unique_damage_profile_per_technique_per_type",
            ),
            # Null pairs: at most one untyped row per technique. PostgreSQL
            # treats multiple NULLs as distinct under a standard
            # UniqueConstraint, so the null case needs its own partial.
            models.UniqueConstraint(
                fields=["technique"],
                condition=Q(damage_type__isnull=True),
                name="unique_untyped_damage_profile_per_technique",
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

`ThreatPoolEntry` already has `attack_category` (a `CharField` with
`ActionCategory.choices` — PHYSICAL/SOCIAL/MENTAL). That field drives
**which check type and fatigue pool** the attack uses; it is not a damage
type. Today it is misused as a damage type because
`apply_damage_to_participant` accepts `damage_type: str` and the NPC code
passes `attack_category` through.

This PR adds `damage_type` as a **separate concept** — a true FK to
`DamageType` for resistance lookup. Both fields coexist:

| Field | Purpose | Type |
|---|---|---|
| `attack_category` (existing) | Check / fatigue category. Selects which defense check type + fatigue pool. Values: physical / social / mental. | `CharField(choices=ActionCategory.choices)` |
| `damage_type` (NEW) | Resistance-lookup type. Identifies the elemental / damage-class identity for `ConditionResistanceModifier` matching. Values: Fire, Cold, Slashing, Holy, etc. | `ForeignKey("conditions.DamageType", null=True, on_delete=PROTECT)` |

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

`attack_category` is unchanged.

### Helpers in `world/conditions/services.py`

Resistance lookup is on the handler (`character.conditions.resistance_modifier(damage_type)`),
not a service function. The only damage-related service helper is the
multiplier lookup, which queries the (tiny) `DamageSuccessLevelMultiplier`
table once per cast:

```python
def get_damage_multiplier(success_level: int) -> Decimal:
    """Highest matching threshold wins. SL below the lowest yields 0."""
    rows = DamageSuccessLevelMultiplier.objects.filter(
        min_success_level__lte=success_level,
    ).order_by("-min_success_level")
    first = rows.first()
    return first.multiplier if first else Decimal("0")
```

This is called once per cast (outside the per-component damage loop) so a
single query per cast is acceptable. The table is typically 2–3 rows
total; SharedMemoryModel caches them in-memory for subsequent runs in
the same process.

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
        resistance = opponent.objectdb.conditions.resistance_modifier(damage_type)

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

### `apply_damage_to_participant` migration

The current signature is `damage_type: str = "physical"`. The string is
accepted today because callers conflate `ThreatPoolEntry.attack_category`
with damage type (see ThreatPoolEntry section above). Migrate to FK:

```python
def apply_damage_to_participant(
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
    damage_type: DamageType | None = None,   # was: str = "physical"
    source: object | None = None,
) -> ParticipantDamageResult:
    ...
```

Caller updates inside `world/combat/services.py`:

- `_resolve_npc_action` (the direct path, currently passing
  `damage_type=npc_action.threat_entry.attack_category`) → pass
  `damage_type=npc_action.threat_entry.damage_type` instead. The
  `attack_category` is no longer plumbed through this argument; it
  already drives check type / fatigue selection elsewhere and doesn't
  belong on this parameter.
- `resolve_npc_attack` (the defense-check path, currently passing
  `damage_type=opponent_action.threat_entry.attack_category`) → same
  change to `threat_entry.damage_type`.
- `process_damage_consequences` call site at the existing
  `damage_type=None # TODO` line — no change required (already None);
  remove the TODO comment since the gap is resolved structurally.

### `DamagePreApplyPayload` and `DamageAppliedPayload` migration

Both payloads currently declare `damage_type: str`. Migrate to
`damage_type: DamageType | None`:

```python
@dataclass
class DamagePreApplyPayload:
    target: Character
    amount: int
    damage_type: DamageType | None   # was: str
    source: DamageSource


@dataclass(frozen=True)
class DamageAppliedPayload:
    target: Character
    amount_dealt: int
    damage_type: DamageType | None   # was: str
    source: DamageSource
    hp_after: int
```

`apply_damage_to_participant` constructs the payloads with the FK
directly. Reactive subscribers reading `payload.damage_type` need their
expectations updated from string comparison to FK identity (or `.name`
attribute access). The implementation must grep for `payload.damage_type`
and `damage_type ==` patterns specifically, not only for assertion
migrations: scar logic that branches on damage type via string
comparison will silently fail to match after the migration (no
exception, just a missed branch). The current grep shows no
flow-trigger consumers reading the field — only test assertions, which
migrate alongside — but treat this as a verification step at
implementation time, not a foregone conclusion.

### `TechniqueCapabilityGrant.calculate_value` extension

The current signature is `calculate_value(self, intensity: int | None = None)`
— one positional parameter named `intensity`. Migrate to keyword-only and
rename for clarity:

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

**Breaking-call-site changes** (search at implementation time, the
current grep shows these specifically):

- `src/world/magic/tests/test_capability_grants.py:51` —
  `grant.calculate_value(intensity=20)` → `grant.calculate_value(effective_intensity=20)`
- All other callers (`grant.calculate_value()` with no args, lines 41
  and 61 of the same test plus `mechanics/services.py:488`) are unaffected.

No combat-side caller for this keyword is added in this PR; the kwarg
is reserved for future Challenge-in-combat work.

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
- `test_unique_constraint_per_technique_per_typed_pair` — second row with same `(technique, damage_type)` where damage_type is non-null raises IntegrityError.
- `test_null_damage_type_unique_per_technique` — second untyped (`damage_type=None`) row for the same technique raises IntegrityError. Verifies the partial unique constraint on the NULL case (PostgreSQL would otherwise allow multiple NULLs under a plain UniqueConstraint).

### Conditions — `DamageSuccessLevelMultiplier` (`world/conditions/tests/test_damage_multiplier.py`)

- `test_get_damage_multiplier_returns_zero_when_table_empty`.
- `test_get_damage_multiplier_returns_full_at_threshold`.
- `test_get_damage_multiplier_returns_partial_below_full`.
- `test_get_damage_multiplier_returns_zero_below_lowest`.
- `test_highest_threshold_wins`.

### Conditions — `CharacterConditionHandler` (`world/conditions/tests/test_character_condition_handler.py`)

- `test_returns_zero_for_no_active_conditions`.
- `test_returns_zero_for_null_damage_type`.
- `test_template_level_modifier_for_matching_type`.
- `test_template_level_modifier_for_all_types_damage_type_null`.
- `test_stage_level_modifier_when_at_that_stage`.
- `test_negative_modifier_means_vulnerability`.
- `test_aggregates_across_multiple_conditions`.
- `test_skips_suppressed_instances`.
- `test_skips_resolved_instances`.
- `test_handler_caches_active_list_on_first_read` — assert the list is
  loaded once: a second `resistance_modifier()` call within the same
  handler instance does not issue further DB queries (use
  `assertNumQueries`).
- `test_invalidate_drops_cache` — call `.invalidate()`, then
  `resistance_modifier()` again; assert the cached property is recomputed.
- `test_apply_condition_invalidates_handler` — after
  `apply_condition(target=character, ...)`, calling
  `character.conditions.resistance_modifier(damage_type)` reflects the
  newly-applied condition.
- `test_bulk_apply_conditions_invalidates_handler`.
- `test_process_round_end_invalidates_handler` — when a condition expires
  via tick, the handler reflects its absence.

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

1. Conditions schema (`DamageSuccessLevelMultiplier`) + factory + `get_damage_multiplier` helper.
2. `CharacterConditionHandler` in `world/conditions/handlers.py`; wire `character.conditions` on the typeclass.
3. Invalidation calls added to existing condition-mutation services
   (`apply_condition`, `bulk_apply_conditions`, `process_round_start`,
   `process_round_end`, treatment / suppression services). Each mutation
   ends with `target_character.conditions.invalidate()`.
4. Magic schema (`TechniqueDamageProfile`) + factory + `compute_damage_budget`.
5. `TechniqueFactory.post_generation` seeds a damage profile from `EffectType.base_power`.
6. `TechniqueCapabilityGrant.calculate_value()` `effective_intensity` override.
7. Combat schema (`ThreatPoolEntry.damage_type`) + factory updates.
8. Payload migration (`DamagePreApplyPayload.damage_type`, `DamageAppliedPayload.damage_type`) from `str` to `DamageType | None`. Grep for `payload.damage_type` consumers; update.
9. `apply_damage_to_opponent` and `apply_damage_to_participant` accept `damage_type`; resistance lookup wired via `target.conditions.resistance_modifier(...)`.
10. `_resolve_npc_action` and `resolve_npc_attack` pass `threat_entry.damage_type` (closes TODO).
11. `CombatTechniqueResolver._apply_damage` rewritten.
12. Tests added per step (not bulk-at-the-end).

## Anti-patterns avoided

- **Coupling Technique to a specific subsystem.** No `damage_*` fields on `Technique`. Damage authoring lives in `TechniqueDamageProfile`, parallel to `TechniqueAppliedCondition` and `TechniqueCapabilityGrant`. Future subsystems (summons, etc.) get their own profile models.
- **One-mega-effect-model unification.** Each subsystem has its own metadata; collapsing them under a single "scaled effect" model would force every subsystem's quirks into one schema. The unification is at the formula level, not the model level.
- **Per-technique soak bypass.** `bypass_soak` stays combo-only. Solo casts can never bypass soak. Architectural rule, not author discipline.
- **Hardcoded SL multipliers.** Replaced with a tunable lookup table so combat damage feel can be retuned without code changes.
- **Cross-app imports between magic and combat.** Combat reads `technique.damage_profiles` via reverse-FK; no model-import dependency.
- **Inline narration of removed fields.** No comments noting what was removed or omitted; the schema speaks for itself.
- **`filter()` on SharedMemoryModel related managers in service functions.** Resistance lookup is on a per-character handler (`CharacterConditionHandler`) that caches the active condition list, mirroring `CharacterCombatPullHandler`. Service functions never call `target.condition_instances.filter(...)` directly; that defeats the identity-map cache.

## References

- `docs/superpowers/specs/2026-04-30-combat-magic-pipeline-integration-design.md` — predecessor (damage path through use_technique).
- `docs/superpowers/specs/2026-05-01-combat-magic-non-attack-effects-design.md` — predecessor (TechniqueAppliedCondition, compute_effective_intensity, CombatOpponent → ObjectDB).
- `src/world/magic/models/techniques.py` — Technique, TechniqueCapabilityGrant, TechniqueAppliedCondition.
- `src/world/conditions/models.py` — DamageType, ConditionResistanceModifier, ConditionInstance.
- `src/world/combat/services.py` — CombatTechniqueResolver, apply_damage_to_opponent, _resolve_npc_action.

# Combat Magic Non-Attack Effects

**Date:** 2026-05-01
**Status:** Spec — pre-implementation
**Owner:** brann
**Predecessor:** `docs/superpowers/specs/2026-04-30-combat-magic-pipeline-integration-design.md`

## Purpose

Route non-attack effect types (Buff / Defense / Movement / Debuff) through the
combat→`use_technique` pipeline established by the predecessor PR, and let
attack techniques apply conditions on top of damage. Today, combat-cast
techniques without `EffectType.base_power` are silent no-ops in
`_resolve_pc_action` — `if technique.effect_type.base_power is not None`
gates the entire damage path, so support archetypes (shield, buff, hinder,
reposition) can declare actions that produce no observable effect. That
collapses cooperative play built around non-damage contributions.

This spec adds:

1. **Ally / self targeting** on `CombatRoundAction` so techniques can land on
   PCs (the caster, an ally) instead of only opponents.
2. **`TechniqueAppliedCondition` through model** — per-technique authoring of
   conditions to apply, with formula-based severity and duration scaling.
3. **`compute_effective_intensity` helper** that aggregates the caster's
   effective scaling input — `technique.intensity` plus active `INTENSITY_BUMP`
   pull contributions plus future hooks. Applies to condition formulas; opens
   the door to thread-pull-driven buffing.
4. **`CombatOpponent` → `ObjectDB` linkage** with multi-layered safeguards
   so PCs and persistent NPCs are never destroyed by combat cleanup. Closes
   the polymorphic-FK escape hatch the predecessor spec hinted at and lets
   `TECHNIQUE_AFFECTED` fire uniformly on every target including mooks.
5. **Round-tick wiring** so conditions actually decay — `process_round_start`
   and `process_round_end` are called from combat lifecycle. Pre-existing
   gap (NPC threat entries already applied conditions that never ticked); fixed
   here because non-attack conditions make the gap user-visible.

## Scope

### In scope

- Combat-cast techniques with `effect_type.base_power is None` route through
  `use_technique` and apply authored conditions.
- Combat-cast techniques with `effect_type.base_power is not None` (attack
  types) **also** apply authored conditions, in addition to damage.
- Ally / self targeting on `CombatRoundAction`. Self-cast = ally target = caster's
  participant.
- `TechniqueAppliedCondition` through model with per-technique condition
  authoring: severity formula (base + intensity_mult × effective_intensity +
  per_extra_sl × max(0, SL − min_sl)) and the equivalent for duration.
- `CombatOpponent.objectdb` OneToOne FK with `objectdb_is_ephemeral` flag,
  multi-layer guard against marking persistent characters ephemeral, cleanup
  function that deletes only ephemeral ObjectDBs at encounter completion.
- `CombatNPC` typeclass for ephemeral combat-only ObjectDBs.
- `TECHNIQUE_AFFECTED` per-target events fire uniformly on all targets
  (ally, self, persona-bearing enemy, ephemeral mook).
- Round-tick (`process_round_start` / `process_round_end`) called from
  combat lifecycle for active participants and active opponents.

### Out of scope (deferred)

- **Frontend** — server-only PR.
- **Damage scaling by `effective_intensity`** — damage stays on
  `EffectType.base_power × SL-threshold` (full / half / zero). Hooking damage
  into intensity-driven scaling is a larger combat-tuning conversation.
- **`PerformRitualAction` player command** — carried over from predecessor
  PR's deferred list.
- **Other CombatPull effect kinds** (`CAPABILITY_GRANT`, `NARRATIVE_ONLY`)
  — not consumed by combat yet. `INTENSITY_BUMP` is wired in this PR via
  `compute_effective_intensity`; the others wait for authoring need.
- **NPC-side condition application using formula scaling** —
  `ThreatPoolEntry.conditions_applied` stays a flat M2M without
  severity/duration formulas. Refactoring it to mirror
  `TechniqueAppliedCondition` would double scope.
- **Combat-scoped vs persistent condition lifecycle policy** — no
  "clear on encounter end" flag added by this PR. Persistent-target
  conditions decay via natural duration semantics.
- **`CombatOpponent` row deletion at encounter end** — rows preserved for
  historical record. Only the ephemeral ObjectDB is destroyed.
- **Authoring UI for `TechniqueAppliedCondition` rows** — admin-only for now.

### PR-size constraint

Estimated ~1500-1700 lines including tests, larger than the predecessor
PR's ~600-line target. The user has explicitly accepted the larger scope
to keep design context coherent (rather than splitting the CombatOpponent
identity refactor into a prerequisite PR).

## Architecture

### Boundaries

- **Magic does not import combat.** `compute_effective_intensity` lives
  combat-side; magic still only sees the resolver as a `resolve_fn` callback.
  The `targets=[...]` parameter to `use_technique` is the only data combat
  passes "out" to magic and was already part of the contract.
- **Conditions does not import combat.** All condition targets are
  `ObjectDB`. The polymorphic-FK proposal that came up during brainstorming
  is **dropped** because `CombatOpponent` now owns an `ObjectDB`.
- **`CombatNPC` typeclass lives in `world/combat/typeclasses/combat_npc.py`**
  inheriting from `typeclasses/npcs.NonPlayerCharacter` (or whichever Evennia
  base is closest — verified during plan-writing).

### Module map

```
world/combat/
├── models.py
│   ├── CombatEncounter            ← add room FK if not present
│   ├── CombatOpponent             ← add objectdb OneToOne (SET_NULL, nullable),
│   │                                 add objectdb_is_ephemeral bool,
│   │                                 add CheckConstraint, clean() validation
│   └── CombatRoundAction          ← rename focused_target → focused_opponent_target,
│                                     add focused_ally_target FK CombatParticipant,
│                                     XOR validation in clean()
├── services.py
│   ├── add_opponent(...)          ← creates ObjectDB + sets ephemeral flag correctly
│   ├── cleanup_completed_encounter ← NEW: deletes ephemeral ObjectDBs only
│   ├── has_persistent_identity_references(objectdb) ← NEW helper
│   ├── is_combat_npc_typeclass(objectdb) ← NEW helper
│   ├── CombatTechniqueResolver    ← renamed from CombatAttackResolver
│   │   ├── _roll_check()          ← unchanged from predecessor
│   │   ├── _apply_damage()        ← renamed from _apply, no-ops if base_power None
│   │   └── _apply_conditions()    ← NEW: reads TechniqueAppliedCondition,
│   │                                 resolves target_kind, computes formulas,
│   │                                 calls bulk_apply_conditions
│   ├── compute_effective_intensity ← NEW: aggregates intensity + INTENSITY_BUMP
│   ├── resolve_combat_technique   ← updated: passes meaningful targets
│   ├── _build_affected_targets    ← NEW helper: target_kind → ObjectDB list
│   └── _resolve_pc_action         ← updated: removes "base_power None" no-op
├── types.py
│   ├── AppliedConditionResult     ← NEW
│   └── CombatTechniqueResolution  ← extend with applied_conditions list
├── typeclasses/
│   └── combat_npc.py              ← NEW: CombatNPC typeclass
└── declare_action validators      ← XOR target validation, target_kind
                                      alignment validation

world/magic/
└── models/techniques.py
    ├── Technique                   ← M2M applied_conditions through-model link
    └── TechniqueAppliedCondition   ← NEW through model with formula fields

world/conditions/
├── models.py
│   └── ConditionInstance           ← UNCHANGED (target stays single ObjectDB FK)
└── services.py                     ← bulk_apply_conditions signature widens to
                                      accept per-entry severity/duration via
                                      a BulkConditionApplication dataclass.
                                      Round-tick functions (process_round_start /
                                      process_round_end) already exist; combat
                                      now calls them.
```

## Data flow

### Action declaration

```
declare_action(participant, *, focused_action, focused_category, effort_level,
               focused_opponent_target=None, focused_ally_target=None,
               physical_passive, social_passive, mental_passive)
  │
  ├─ vitals/encounter status validation (existing)
  ├─ XOR: focused_opponent_target vs focused_ally_target
  │     (raise ValidationError if both set)
  ├─ target_kind alignment validation:
  │     - if technique has TechniqueAppliedCondition rows:
  │           supplied target's kind (opponent vs ally vs self) must match
  │           at least one row's target_kind, else ValidationError
  │     - if technique has base_power and no condition rows:
  │           focused_opponent_target required
  ├─ existing passive-slot validation
  └─ persists CombatRoundAction
```

### Round resolution

```
resolve_round(encounter)
  │
  ├─ select_for_update encounter; status DECLARING → RESOLVING
  ├─ build action lookups (existing)
  ├─ resolution_order = speed-rank sorted (existing)
  │
  └─ for each (entity_type, entity) in resolution_order:
        │
        ├─ if PC: _resolve_pc_action(participant, action)
        │     │
        │     ├─ if technique is None: return outcome (passives only)
        │     ├─ if combo_upgrade: existing combo path (unchanged)
        │     │
        │     └─ else: route through magic pipeline (always now —
        │              no more "base_power is None → no-op" branch)
        │           ▼
        │     resolve_combat_technique(participant, action, ...)
        │           │
        │           ├─ pull_flat_bonus = _sum_active_flat_bonuses(...)  (existing)
        │           ├─ resolver = CombatTechniqueResolver(...)
        │           ├─ targets = _build_affected_targets(participant, action)
        │           │     # Resolves to ObjectDBs (uniformly):
        │           │     # - opponent target → opp.objectdb (always present)
        │           │     # - ally target → ally.character_sheet.character
        │           │     # - self target → caster.character
        │           │
        │           └─ use_technique(
        │                 character=caster_obj,
        │                 technique=action.focused_action,
        │                 resolve_fn=resolver,
        │                 confirm_soulfray_risk=True,
        │                 targets=targets,
        │              )
        │                 │
        │                 ├─ runtime stats → effective anima cost → soulfray ckpt
        │                 ├─ TECHNIQUE_PRE_CAST emit (cancellable)
        │                 │     └─ on cancel: TechniqueUseResult(confirmed=False)
        │                 ├─ deduct_anima
        │                 │
        │                 ├─ resolver()  ─────────────────────────────────────┐
        │                 │     ├─ check_result = _roll_check()               │
        │                 │     ├─ damage_results = _apply_damage(check_result)│
        │                 │     │     # no-op if base_power None,             │
        │                 │     │     # no opponent target, or DEFEATED       │
        │                 │     └─ applied_conditions = _apply_conditions(...) │
        │                 │           ├─ effective_intensity =                │
        │                 │           │   compute_effective_intensity(...)    │
        │                 │           ├─ for each TechniqueAppliedCondition:  │
        │                 │           │     skip if SL < min_sl               │
        │                 │           │     resolve target_kind to ObjectDB   │
        │                 │           │     severity = compute_severity(...)  │
        │                 │           │     duration = compute_duration(...)  │
        │                 │           │     build BulkConditionApplication    │
        │                 │           └─ bulk_apply_conditions(applications,  │
        │                 │               source_character=caster.character,  │
        │                 │               source_technique=technique)         │
        │                 │                 ├─ CONDITION_PRE_APPLY (per cond) │
        │                 │                 ├─ stacking / interaction         │
        │                 │                 ├─ ConditionInstance create       │
        │                 │                 └─ CONDITION_APPLIED              │
        │                 │ ◄───────────────────────────────────────────────────┘
        │                 ├─ soulfray accrual
        │                 ├─ mishap rider
        │                 ├─ corruption accrual
        │                 ├─ TECHNIQUE_CAST emit
        │                 └─ for each target in targets:
        │                       TECHNIQUE_AFFECTED emit (target's room)
        │                       # Fires uniformly — every target is ObjectDB.
        │                       # Lifesteal / on-affected reactive triggers fire.
        │                 ▼
        │     adapter unpacks TechniqueUseResult into ActionOutcome,
        │     runs apply_fatigue (always — preserves existing contract)
        │
        └─ if NPC: _resolve_npc_action(...)  (unchanged)

  ▼
After all actions resolved:
  ├─ dying final round consumption (existing)
  ├─ boss phase transitions (existing)
  ├─ NEW: process_round_end for each active participant + active opponent
  │     # decrements rounds_remaining on conditions, ticks DoT, fires expiry
  └─ encounter completion check
       ├─ if completed: status → COMPLETED
       │     └─ run cleanup_completed_encounter(encounter)
       │           # deletes ephemeral CombatNPC ObjectDBs (only ephemeral!)
       │           # CombatOpponent rows preserved (historical record)
       └─ else: status → BETWEEN_ROUNDS

begin_declaration_phase(encounter)  # next round
  ├─ status BETWEEN_ROUNDS → DECLARING; round_number += 1
  ├─ NEW: process_round_start for each active participant + active opponent
  │     # start-of-round DoT (Burning, etc.)
  └─ expire_pulls_for_round (existing)
```

## Component shapes

### `CombatEncounter` change

`CombatEncounter` currently has a `scene` FK but no room linkage. Adding:

```python
room = models.ForeignKey(
    "objects.ObjectDB",
    on_delete=models.PROTECT,
    related_name="combat_encounters",
    help_text="Room where the encounter takes place. Ephemeral CombatNPC "
              "ObjectDBs are placed here at creation.",
)
```

Existing test factories and any encounter-creation paths must supply `room`.
Verified: `room` is not currently a field on `CombatEncounter` — this is a
definite new field, not conditional.

### `CombatOpponent` changes

```python
class CombatOpponent(SharedMemoryModel):
    # existing fields ...
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_opponent",
        help_text="The in-world ObjectDB representation. Set at creation; "
                  "nulled if the ObjectDB is destroyed externally.",
    )
    objectdb_is_ephemeral = models.BooleanField(
        default=False,
        help_text="If True, the ObjectDB was created for this encounter only "
                  "and will be cleaned up at encounter completion. "
                  "Persona-bearing or pre-existing ObjectDBs MUST NOT be "
                  "flagged ephemeral.",
    )

    class Meta:
        constraints = [
            *existing_constraints,
            models.CheckConstraint(
                check=Q(persona__isnull=True) | Q(objectdb_is_ephemeral=False),
                name="persona_bearing_opponent_not_ephemeral",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.objectdb_is_ephemeral:
            return
        if self.objectdb is None:
            raise ValidationError({"objectdb":
                "Ephemeral CombatOpponent must have an ObjectDB."})
        if self.persona is not None:
            raise ValidationError({"objectdb_is_ephemeral":
                "Persona-bearing CombatOpponent cannot be ephemeral."})
        if not is_combat_npc_typeclass(self.objectdb):
            raise ValidationError({"objectdb_is_ephemeral":
                "Only CombatNPC-typeclass ObjectDBs can be marked ephemeral."})
        if has_persistent_identity_references(self.objectdb):
            raise ValidationError({"objectdb_is_ephemeral":
                "ObjectDB has persistent identity references; cannot be marked "
                "ephemeral."})
```

### `CombatRoundAction` changes

```python
class CombatRoundAction(SharedMemoryModel):
    # rename:
    focused_opponent_target = models.ForeignKey(  # was: focused_target
        CombatOpponent,
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # NEW:
    focused_ally_target = models.ForeignKey(
        CombatParticipant,
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # ... existing fields unchanged ...

    def clean(self) -> None:
        super().clean()
        if self.focused_opponent_target_id and self.focused_ally_target_id:
            raise ValidationError(
                "Action cannot target both an opponent and an ally simultaneously."
            )
```

### `add_opponent` rewrite

```python
def add_opponent(
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    max_health: int,
    threat_pool: ThreatPool,
    description: str = "",
    soak_value: int = 0,
    probing_threshold: int | None = None,
    persona: Persona | None = None,
    existing_objectdb: ObjectDB | None = None,
) -> CombatOpponent:
    """Create a CombatOpponent. Three sources for the ObjectDB:
    - existing_objectdb: pre-existing OD (PvP, named NPC w/o persona). Never ephemeral.
    - persona: reuses persona's character ObjectDB. Never ephemeral.
    - neither: creates a new CombatNPC OD scoped to this encounter. Ephemeral.
    """
    if existing_objectdb is not None:
        objectdb = existing_objectdb
        is_ephemeral = False
    elif persona is not None:
        # Persona FK is character_sheet; CharacterSheet.character is OneToOne
        # to ObjectDB (primary_key=True), so .character already IS the ObjectDB.
        objectdb = persona.character_sheet.character
        is_ephemeral = False
    else:
        if encounter.room is None:
            raise ValueError("Cannot create ephemeral CombatNPC: encounter has no room.")
        objectdb = create_combat_npc_objectdb(name=name, location=encounter.room)
        is_ephemeral = True

    opp = CombatOpponent(
        encounter=encounter,
        name=name, tier=tier, max_health=max_health, health=max_health,
        threat_pool=threat_pool, description=description,
        soak_value=soak_value, probing_threshold=probing_threshold,
        persona=persona,
        objectdb=objectdb,
        objectdb_is_ephemeral=is_ephemeral,
    )
    opp.full_clean()  # runs all clean() validations including ephemeral guards
    opp.save()
    return opp
```

### `cleanup_completed_encounter`

```python
def cleanup_completed_encounter(encounter: CombatEncounter) -> None:
    """Delete encounter-ephemeral CombatNPC ObjectDBs. Persistent NPCs and PCs
    are never touched. Layer 5 of the multi-layer guard: defensive re-check
    before each delete in case a corrupt row escaped Layers 1–4.

    CombatOpponent rows are preserved (historical record). Only the ephemeral
    ObjectDB is destroyed; the SET_NULL FK behavior nulls
    CombatOpponent.objectdb after deletion.
    """
    qs = encounter.opponents.filter(
        objectdb_is_ephemeral=True,
    ).select_related("objectdb")
    for opp in qs:
        objectdb = opp.objectdb
        if objectdb is None:
            continue
        if not is_combat_npc_typeclass(objectdb):
            logger.error(
                "Refusing to delete: %s is not a CombatNPC typeclass", objectdb,
            )
            continue
        if has_persistent_identity_references(objectdb):
            logger.error(
                "Refusing to delete: %s has persistent identity references",
                objectdb,
            )
            continue
        objectdb.delete()
```

### Helpers

```python
def has_persistent_identity_references(objectdb: ObjectDB) -> bool:
    """Return True if this ObjectDB is referenced by any model that signals
    persistent identity (Persona, RosterEntry, CharacterSheet, etc.).

    Single source of truth for "is this an ObjectDB any persistent system
    cares about?" — when a new persistent-identity model is added, this
    function adds the corresponding check.

    Traversal paths reflect the actual schema:
    - CharacterSheet.character is a OneToOne to ObjectDB (primary_key=True),
      so the direct filter is `CharacterSheet.objects.filter(character=objectdb)`.
    - Persona.character_sheet FK; walks through CharacterSheet to ObjectDB.
    - RosterEntry.character_sheet FK; same walk.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if CharacterSheet.objects.filter(character=objectdb).exists():
        return True
    if Persona.objects.filter(character_sheet__character=objectdb).exists():
        return True
    if RosterEntry.objects.filter(character_sheet__character=objectdb).exists():
        return True
    return False


def is_combat_npc_typeclass(objectdb: ObjectDB) -> bool:
    """Return True iff the ObjectDB's typeclass is the CombatNPC class."""
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415
    return isinstance(objectdb, CombatNPC)
```

### `CombatNPC` typeclass

```python
# world/combat/typeclasses/combat_npc.py

from typeclasses.npcs import NonPlayerCharacter  # actual base verified during plan-writing

class CombatNPC(NonPlayerCharacter):
    """Encounter-scoped NPC ObjectDB.

    Owned by a CombatOpponent with `objectdb_is_ephemeral=True`. Created at
    `add_opponent` time, destroyed at `cleanup_completed_encounter` time.
    Never used for persistent NPCs — those use their existing ObjectDB
    (typically via Persona).
    """
```

### `TechniqueAppliedCondition`

```python
# world/magic/models/techniques.py

class TargetKind(models.TextChoices):
    SELF = "self", "Self"
    ALLY = "ally", "Ally"
    ENEMY = "enemy", "Enemy"


class TechniqueAppliedCondition(SharedMemoryModel):
    """Authored row binding a Technique to a ConditionTemplate with
    formula-based severity / duration scaling. One Technique may have many
    of these.
    """

    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE,
        related_name="condition_applications",
    )
    condition = models.ForeignKey(
        "conditions.ConditionTemplate", on_delete=models.PROTECT,
        related_name="applied_by_techniques",
    )
    target_kind = models.CharField(
        max_length=16, choices=TargetKind.choices, default=TargetKind.ENEMY,
    )
    minimum_success_level = models.PositiveIntegerField(default=1)

    # Severity formula
    base_severity = models.PositiveIntegerField(default=1)
    severity_intensity_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
    )
    severity_per_extra_sl = models.PositiveIntegerField(default=0)

    # Duration formula (null base → use ConditionTemplate.default_duration_value)
    base_duration_rounds = models.PositiveIntegerField(null=True, blank=True)
    duration_intensity_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
    )
    duration_per_extra_sl = models.PositiveIntegerField(default=0)

    stack_count = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "condition", "target_kind"],
                name="unique_applied_condition_per_technique",
            ),
        ]

    def compute_severity(
        self, *, effective_intensity: int, success_level: int,
    ) -> int:
        intensity_contribution = int(
            self.severity_intensity_multiplier * effective_intensity,
        )
        sl_above = max(0, success_level - self.minimum_success_level)
        sl_contribution = self.severity_per_extra_sl * sl_above
        return self.base_severity + intensity_contribution + sl_contribution

    def compute_duration_rounds(
        self, *, effective_intensity: int, success_level: int,
    ) -> int | None:
        base = self.base_duration_rounds
        if base is None:
            base = self.condition.default_duration_value
        intensity_contribution = int(
            self.duration_intensity_multiplier * effective_intensity,
        )
        sl_above = max(0, success_level - self.minimum_success_level)
        sl_contribution = self.duration_per_extra_sl * sl_above
        return base + intensity_contribution + sl_contribution
```

### `compute_effective_intensity`

```python
def compute_effective_intensity(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> int:
    """Aggregate the caster's effective scaling input for this cast.

    Sources today:
    - technique.intensity (caster's invested power baseline)
    - sum of INTENSITY_BUMP scaled_values from active CombatPulls

    Future hooks (additive, no signature change required):
    - Condition-derived intensity bumps
    - Item-derived intensity bumps
    - Environmental modifiers
    """
    technique = action.focused_action
    if technique is None:
        return 0
    base = technique.intensity
    encounter = participant.encounter
    pull_bonus = 0
    character = participant.character_sheet.character
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                pull_bonus += eff.scaled_value
    return base + pull_bonus
```

### `CombatTechniqueResolver` (renamed from `CombatAttackResolver`)

```python
@dataclass(frozen=True)
class CombatTechniqueResolver:
    """Resolves the inner step of a combat-cast technique. Single class
    handles both damage and condition application; behavior differences
    live in technique-authored data (base_power, TechniqueAppliedCondition rows).
    """

    participant: CombatParticipant
    action: CombatRoundAction
    pull_flat_bonus: int
    fatigue_category: str
    offense_check_type: CheckType
    offense_check_fn: PerformCheckFn | None

    def __call__(self) -> CombatTechniqueResolution:
        check_result = self._roll_check()
        damage_results = self._apply_damage(check_result)
        applied_conditions = self._apply_conditions(check_result)
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            applied_conditions=applied_conditions,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=sum(r.damage_dealt for r in damage_results),
        )

    def _roll_check(self) -> CheckResult: ...  # ~unchanged from predecessor PR

    def _apply_damage(
        self, check_result: CheckResult,
    ) -> list[OpponentDamageResult]:
        """Damage path. No-op when base_power is None, no
        focused_opponent_target, or target DEFEATED."""
        ...

    def _apply_conditions(
        self, check_result: CheckResult,
    ) -> list[AppliedConditionResult]:
        """Condition path. Iterates technique.condition_applications,
        resolves target_kind to ObjectDB, computes severity/duration via
        TechniqueAppliedCondition formulas, calls bulk_apply_conditions
        in one batched call."""
        ...
```

### Types

```python
# world/combat/types.py

@dataclass(frozen=True)
class AppliedConditionResult:
    """Per-condition apply outcome from CombatTechniqueResolver._apply_conditions."""
    target: ObjectDB
    condition: ConditionTemplate
    severity_applied: int
    duration_rounds: int | None
    success: bool


@dataclass(frozen=True)
class CombatTechniqueResolution:
    check_result: CheckResult
    damage_results: list[OpponentDamageResult]
    applied_conditions: list[AppliedConditionResult]   # NEW
    pull_flat_bonus: int
    scaled_damage: int
```

### `bulk_apply_conditions` interface change

The existing `bulk_apply_conditions(applications, *, severity, duration_rounds, ...)`
takes a single `severity` and `duration_rounds` applied uniformly to every
entry in the batch. That doesn't fit our use case: a single technique cast can
apply Empowered (sev=3, dur=4) to self AND Slowed (sev=1, dur=2) to an enemy
in the same batch. Per-entry values are required.

Replace the signature (no backward-compatible dual-format, per project rule):

```python
# world/conditions/types.py — NEW

@dataclass(frozen=True)
class BulkConditionApplication:
    """One target/template/per-entry-knobs binding for bulk_apply_conditions."""
    target: ObjectDB
    template: ConditionTemplate
    severity: int = 1
    duration_rounds: int | None = None
    stack_count: int = 1


# world/conditions/services.py — replaced signature

def bulk_apply_conditions(
    applications: list[BulkConditionApplication],
    *,
    source_character: ObjectDB | None = None,
    source_technique: Technique | None = None,
    source_description: str = "",
) -> list[ApplyConditionResult]:
    """Apply multiple conditions in one transaction with batched queries.

    Each BulkConditionApplication carries its own severity, duration_rounds,
    and stack_count. Source attribution (caster, technique, description) is
    shared across the batch — a single cast is the source of all entries.
    """
    if not applications:
        return []
    targets = list({a.target for a in applications})
    templates = list({a.template for a in applications})
    ctx = _build_bulk_context(targets, templates)
    results: list[ApplyConditionResult] = []
    for app in applications:
        # ... existing CONDITION_PRE_APPLY / _apply_single / CONDITION_APPLIED logic,
        #     reading severity/duration_rounds/stack_count from app instead of
        #     shared kwargs ...
        ...
    return results
```

**Caller migration** within this PR:
- `_resolve_npc_action` in `world/combat/services.py` constructs
  `BulkConditionApplication` rows from `(target_obj, ct)` tuples with
  `severity=1, duration_rounds=None` (preserving today's behavior).
- `CombatTechniqueResolver._apply_conditions` constructs them with the
  per-row formula outputs from `TechniqueAppliedCondition.compute_severity`
  and `compute_duration_rounds`.
- Any other call sites (verified during plan-writing) get the same
  one-line conversion.

The `apply_condition` single-application function keeps its existing keyword
arguments (severity, duration_rounds) — it's a thin wrapper over the same
logic and changing it is not load-bearing.

### Round-tick wiring

In `begin_declaration_phase`, after `round_number` advances and before
`expire_pulls_for_round`:

```python
from world.conditions.services import process_round_start
for p in active_participants:
    process_round_start(p.character_sheet.character)
for opp in active_opponents:
    if opp.objectdb is not None:
        process_round_start(opp.objectdb)
```

In `resolve_round`, after dying-final-round consumption and before
boss-phase transitions:

```python
from world.conditions.services import process_round_end
for p in active_participants:
    process_round_end(p.character_sheet.character)
for opp in active_opponents:
    if opp.objectdb is not None:
        process_round_end(opp.objectdb)
```

The `if opp.objectdb is not None` guard handles the post-cleanup state
where an ephemeral ObjectDB has been deleted (FK is now null).

## Cancel and error handling

| Failure mode | Behavior |
|---|---|
| **PRE_CAST cancelled by reactive scar** | `confirmed=False`. Resolver never called. No damage, no conditions, no anima. Fatigue still applied (existing contract). |
| **CONDITION_PRE_APPLY cancelled** (per-condition reactive) | That single condition skipped; other conditions in the same `bulk_apply_conditions` batch still apply. `AppliedConditionResult.success=False` for cancelled ones. Damage path unaffected. |
| **`focused_ally_target = self_participant`** (self-cast) | `target_kind=SELF` rows resolve to caster.character. `target_kind=ALLY` rows also accept self. Targets list dedup'd so AFFECTED fires once on caster. |
| **Mixed-target technique** (shield self + burn enemy) | Rows differ by `target_kind`. `_apply_conditions` resolves each separately. `targets` list to `use_technique` is the dedup'd union. One PRE_CAST, one CAST, multiple AFFECTED. |
| **No condition rows AND `base_power is None`** | Resolver runs check, applies nothing. Anima still deducted; PRE_CAST/CAST still emit. Useful for "narrative-only" techniques whose effect IS the events. |
| **Target opponent DEFEATED mid-resolution** | Damage skips (existing). Conditions for `target_kind=ENEMY` skip. |
| **Action has `focused_ally_target` but technique only ENEMY-kind rows** | Caught at `declare_action` time. If somehow slipped through, `_apply_conditions` no-ops because no rows resolve to a target. |
| **`compute_effective_intensity` yields 0** | Severity/duration formulas still produce sensible values via `base_*` constants. |
| **Persistent ObjectDB externally deleted** | SET_NULL nulls `CombatOpponent.objectdb`. Round-tick wiring handles `None` defensively. CombatOpponent row preserved. |
| **Caller tries to mark a real PC ephemeral** | Layer 1 (DB constraint) blocks if persona is set. Layer 2 (clean()) catches all four invalid combos. Layer 4 (`add_opponent`) only sets `is_ephemeral=True` when no persona and no existing OD. Layer 5 (cleanup) re-checks before deletion. |
| **Encounter has no room when adding ephemeral mook** | `add_opponent` raises `ValueError("Cannot create ephemeral CombatNPC: encounter has no room.")` |

## Tests

### Combat — schema & lifecycle (`world/combat/tests/test_opponent_lifecycle.py`)

- `test_add_opponent_creates_ephemeral_objectdb` — mook path: ObjectDB created with CombatNPC typeclass, location is encounter.room, `is_ephemeral=True`.
- `test_add_opponent_with_persona_uses_persona_objectdb` — reuses persona's character ObjectDB, `is_ephemeral=False`.
- `test_add_opponent_with_existing_objectdb_marks_non_ephemeral` — pre-existing OD: `is_ephemeral=False`.
- `test_persona_bearing_opponent_cannot_be_ephemeral_db_layer` — DB CheckConstraint raises IntegrityError.
- `test_clean_rejects_ephemeral_with_no_objectdb` — Layer 2.
- `test_clean_rejects_ephemeral_with_persona` — Layer 2.
- `test_clean_rejects_ephemeral_with_non_combat_npc_typeclass` — Layer 2.
- `test_clean_rejects_ephemeral_with_persistent_references` — Layer 2.
- `test_has_persistent_identity_references_detects_persona` — Layer 3.
- `test_has_persistent_identity_references_detects_roster_entry` — Layer 3.
- `test_has_persistent_identity_references_detects_character_sheet` — Layer 3.
- `test_cleanup_deletes_ephemeral_only` — happy path.
- `test_cleanup_recheck_refuses_non_combat_npc_typeclass` — Layer 5.
- `test_cleanup_recheck_refuses_persistent_references` — Layer 5.
- `test_objectdb_externally_deleted_nulls_combat_opponent_fk` — SET_NULL.
- `test_combat_opponent_row_survives_cleanup` — historical-record invariant.

### Combat — declaration & target validation (`world/combat/tests/test_declare_action.py`)

- `test_declare_action_xor_targets` — both fields set raises.
- `test_declare_action_self_target_via_ally_field` — accepted.
- `test_declare_action_target_kind_alignment_enemy_only_technique` — ally target with enemy-only technique raises.
- `test_declare_action_damage_only_requires_opponent_target` — base_power technique without conditions requires opponent target.
- `test_declare_action_buff_accepts_self_or_ally` — buff technique authored with target_kind=ALLY/SELF accepts both.

### Resolver (`world/combat/tests/test_combat_technique_resolver.py`)

- `test_resolver_attack_damage_unchanged` — regression.
- `test_resolver_non_attack_no_damage` — base_power None → empty damage.
- `test_resolver_applies_self_targeted_buff` — condition lands on caster.character.
- `test_resolver_applies_ally_targeted_buff` — condition lands on ally.character_sheet.character.
- `test_resolver_applies_enemy_targeted_debuff_on_persona_opponent` — lands on persona's character.
- `test_resolver_applies_enemy_targeted_debuff_on_mook` — lands on opp.objectdb (CombatNPC).
- `test_resolver_applies_attack_plus_condition` — damage AND condition both fire.
- `test_resolver_skips_condition_below_minimum_sl` — below threshold skipped, others apply.
- `test_resolver_severity_uses_effective_intensity_formula` — formula correctness.
- `test_resolver_duration_uses_effective_intensity_formula` — same.
- `test_resolver_duration_falls_back_to_template_default` — `base_duration_rounds=None` → template default.
- `test_resolver_skips_defeated_enemy_for_conditions` — defeated mid-resolution.
- `test_resolver_mixed_target_dedups_affected_targets` — self+ally+enemy: dedup'd targets list.

### Effective intensity (`world/combat/tests/test_effective_intensity.py`)

- `test_effective_intensity_uses_technique_intensity_baseline`.
- `test_effective_intensity_aggregates_intensity_bump_pulls`.
- `test_effective_intensity_ignores_other_pull_kinds`.
- `test_intensity_bump_pull_increases_buff_severity` — end-to-end.

### Magic envelope integration (`world/combat/tests/test_combat_magic_non_attack_integration.py`)

- `test_pre_cast_emitted_for_buff`.
- `test_cast_emitted_for_buff`.
- `test_affected_emitted_per_resolved_target`.
- `test_affected_fires_for_ephemeral_mook` — gap closed by this PR's refactor.
- `test_reactive_scar_cancels_buff_cast`.
- `test_anima_deducted_on_buff_cast`.
- `test_mishap_fires_on_buff_intensity_overflow`.
- `test_condition_pre_apply_cancel_skips_only_that_condition`.

### Round-tick integration (`world/combat/tests/test_round_tick_integration.py`)

- `test_end_of_round_decrements_condition_rounds`.
- `test_end_of_round_expires_zero_round_conditions`.
- `test_start_of_round_dot_ticks`.
- `test_round_tick_runs_for_active_opponents`.
- `test_round_tick_skips_completed_encounter`.

### Conditions — `bulk_apply_conditions` signature change

- `test_bulk_apply_conditions_per_entry_severity` — applications with different
  severities applied correctly per row.
- `test_bulk_apply_conditions_per_entry_duration` — same for duration.
- `test_bulk_apply_conditions_per_entry_stack_count` — same for stack_count.
- `test_bulk_apply_conditions_shared_source_attribution` — source_character and
  source_technique apply to all rows in batch.
- `test_bulk_apply_conditions_empty_list_no_op` — regression.
- `test_bulk_apply_conditions_one_pre_apply_cancel_does_not_skip_others` —
  per-entry CONDITION_PRE_APPLY cancel only skips that one entry.

### Factories

- `CombatNPCObjectDBFactory` — minimal CombatNPC instance.
- `CombatOpponentFactory` (updated) — defaults to ephemeral mook with linked CombatNPC; `with_persona=` and `with_existing_objectdb=` traits.
- `TechniqueAppliedConditionFactory` — sensible defaults: enemy-target, min_sl=1, base_severity=1, no scaling multipliers.
- `BuffTechniqueFactory`, `DebuffTechniqueFactory`, `DefenseTechniqueFactory` — pre-wire condition rows for tests.

### Test discipline

- All test data via FactoryBoy (project rule). No fixtures.
- `setUpTestData` for shared content per class.
- Run `arx test world.combat world.magic world.conditions` per pass during development.
- Final pass before merge: full suite without `--keepdb` to match CI fresh-DB.

## Migration plan

Schema-only. No data migrations; local DB is disposable, CI starts fresh, factories handle test data.

### Migration order (dependency-driven)

1. **`combat`** — add `CombatOpponent.objectdb` (OneToOne SET_NULL nullable),
   `CombatOpponent.objectdb_is_ephemeral` (bool default False), CheckConstraint,
   `CombatEncounter.room` (definite new field, not conditional).
2. **`combat`** — rename `CombatRoundAction.focused_target` → `focused_opponent_target`;
   add `CombatRoundAction.focused_ally_target`.
3. **`magic`** — add `TechniqueAppliedCondition` model and
   `Technique.applied_conditions` M2M.

No `conditions` schema migration — `ConditionInstance` model unchanged. The
`bulk_apply_conditions` signature change is code-only (caller migration).

### Code update sequencing

Single branch with commits in this order so reviewers can step through:

1. Combat schema (migrations 1+2) and factory updates — no behavioral change yet.
2. Magic schema (migration 3) and factory updates.
3. `BulkConditionApplication` dataclass + `bulk_apply_conditions` signature
   change + caller migration (`_resolve_npc_action`, any other callers).
4. CombatNPC typeclass + `add_opponent` rewrite + `cleanup_completed_encounter`.
5. Resolver rename + `_apply_conditions` method.
6. `compute_effective_intensity` helper + INTENSITY_BUMP wiring.
7. `_resolve_pc_action` removes the `base_power is None` no-op branch.
8. Round-tick wiring in `begin_declaration_phase` + `resolve_round`.
9. Tests added per step (not bulk-at-the-end).

## Anti-patterns avoided

- **Inverting dependencies.** Magic does not import combat. Conditions does not import combat.
- **Polymorphic FK on `ConditionInstance`.** Initial brainstorming proposal dropped because the CombatOpponent → ObjectDB refactor in this PR makes it unnecessary.
- **Subclass-per-effect-type resolver tree.** Predecessor PR anticipated this; Q3's "any technique can apply conditions" decision made it data-driven instead. Single resolver class with explicit step methods.
- **Closure-captured state.** Resolver is a frozen dataclass with explicit attributes — inspectable, testable.
- **Scaling damage by intensity in this PR.** Tempting given `effective_intensity` exists, but stays out of scope for predictability of review.
- **Combat-specific failure modes for anima.** Inherits use_technique semantics; no combat-only rejection path.
- **Auto-cleanup of persistent ObjectDBs.** `objectdb_is_ephemeral` defaults to False; only `add_opponent` sets True; multi-layer guard makes accidentally flipping it on a real character take four independent failures.

## Known limitations the spec explicitly calls out

1. **`add_opponent` is the canonical creation path.** Direct ORM creation that bypasses it is technically possible but discouraged; tests assert `add_opponent` is the path used.
2. **`CombatOpponent` rows persist after encounter cleanup, but their ephemeral ObjectDB is gone.** Code reading `opp.objectdb` post-cleanup must handle `None`.
3. **No condition-application reactive abilities authoring path yet.** `CONDITION_APPLIED` fires via `bulk_apply_conditions`; high-level "when X happens to me, do Y" authoring is a separate scar/reactive system PR.
4. **`CombatEncounter.room` becomes load-bearing.** Ephemeral CombatNPC ObjectDBs are placed there at creation; null room → loud error rather than homeless ObjectDB.

## Open questions intentionally left to authoring

These are tuning decisions, not architecture:
- Default values for `severity_intensity_multiplier` per condition category.
- Whether common buffs use `severity_per_extra_sl` vs `duration_per_extra_sl` as primary "crit reward" axis.
- EffectType seed cleanup (Defense currently has `base_power=8`; author decision whether to remove and rely entirely on TechniqueAppliedCondition rows for shielding mechanics, or keep as hybrid).

## References

- `docs/superpowers/specs/2026-04-30-combat-magic-pipeline-integration-design.md` — predecessor.
- `src/world/combat/services.py` — existing `CombatAttackResolver`, `_resolve_pc_action`.
- `src/world/conditions/services.py` — `bulk_apply_conditions`, `process_round_start`, `process_round_end`.
- `src/world/magic/services/techniques.py` — `use_technique`, event emission.
- `src/world/magic/models/techniques.py` — `Technique`, `TechniqueCapabilityGrant` (pattern for formula-based scaling).

# Prerequisite System Design

## Purpose

Make prerequisites functional so the system can gate capability availability based on
game state. Currently `Prerequisite` (formerly `PrerequisiteType`) exists as a registry
with FKs from `CapabilityType` and `TechniqueCapabilityGrant`, but nothing evaluates them.

## Design Approach

Prerequisites are **data-driven property checks**, not code-dispatched callables. Most
prerequisites answer the same question: "Does [entity] have [property] at [minimum value]?"

The entity varies — it might be the character (SELF), the challenge's physical object
(TARGET), or the room (LOCATION). The property and threshold are configured on the
Prerequisite record. No Python functions, no registry, no import paths.

This covers the vast majority of cases. A `service_function_path` escape hatch for
truly bespoke prerequisites (e.g., "must have a Thread with target") can be added later
if needed. YAGNI for MVP.

## Model Changes

### Rename: PrerequisiteType -> Prerequisite

The model is currently named `PrerequisiteType` but there is no corresponding
`Prerequisite` instance model. The "Type" suffix implies a template/instance pattern
that doesn't exist. Rename to `Prerequisite`.

Affected FKs (field names stay the same, target model changes):
- `CapabilityType.prerequisite` -> points to `Prerequisite` (was `PrerequisiteType`)
- `TechniqueCapabilityGrant.prerequisite` -> points to `Prerequisite` (was `PrerequisiteType`)

Affected types:
- `CapabilitySource.prerequisite_id` -> `prerequisite: Prerequisite | None = None`
  Store the model instance instead of a bare PK. The prefetch in
  `_get_technique_sources()` already joins the grant's prerequisite — pass the
  object through instead of its PK. Eliminates the need for a separate batch-fetch
  step during evaluation.

Affected factories:
- `PrerequisiteTypeFactory` -> `PrerequisiteFactory`

### New Fields on Prerequisite

```
property: FK to Property (required)
    The property to check for on the target entity.

property_holder: CharField with PropertyHolder choices (required)
    Which entity to check: SELF (character), TARGET (challenge object),
    or LOCATION (room).

minimum_value: PositiveIntegerField (default=1)
    Threshold for graduated checks. A minimum_value of 1 means "property
    must be present." Higher values gate on intensity (e.g., "flammable >= 3"
    for a particularly resistant material).
```

### New Field on ChallengeInstance

```
target_object: FK to ObjectDB (required)
    The object embodying this challenge in the world. Every challenge is a
    physical (or intangible) thing — a boulder, door, magic ward, gas cloud.
    This object carries ObjectProperty records at runtime and serves as the
    TARGET for prerequisite evaluation.
```

This is non-nullable. Every challenge has a world object. The target_object may be
the same ObjectDB as the location (e.g., a room-wide magical ward) or a separate
object within the room (e.g., a boulder blocking a path). Both are valid.

Future work may introduce typeclasses for different challenge object types (obstacles,
hazards, wards) with class-level properties and special methods.

**Breakage scope**: 6 test files create ChallengeInstance directly and will need the
new `target_object` kwarg:
- `world/mechanics/tests/test_pipeline_integration.py`
- `world/mechanics/tests/test_challenge_resolution.py`
- `world/checks/tests/test_consequence_resolution.py`
- `world/mechanics/tests/test_challenge_models.py`
- `actions/tests/test_actions.py`
- `world/mechanics/tests/test_action_generation.py`

Each needs an ObjectDB created and passed as `target_object`. In most cases,
reusing the existing `location` ObjectDB is fine for test purposes.

### PropertyHolder TextChoices

New constant in `world/mechanics/constants.py`:

```python
class PropertyHolder(models.TextChoices):
    SELF = "self", "Character (self)"
    TARGET = "target", "Target object"
    LOCATION = "location", "Location (room)"
```

### PrerequisiteEvaluation Dataclass

New in `world/mechanics/types.py`:

```python
@dataclass
class PrerequisiteEvaluation:
    met: bool
    reason: str = ""
```

### AvailableAction Changes

Two new fields:

```python
prerequisite_met: bool = True
prerequisite_reasons: list[str] = field(default_factory=list)
```

Actions that fail prerequisites are still returned (for frontend display as disabled
with reasons) but skip difficulty calculation.

## Evaluation Logic

### Prerequisite.evaluate() Method

The `Prerequisite` model gets an `evaluate` method:

```python
def evaluate(
    self,
    character: ObjectDB,
    target_object: ObjectDB,
    location: ObjectDB,
) -> PrerequisiteEvaluation:
```

Logic:
1. Resolve entity from `self.property_holder` (SELF -> character, TARGET -> target_object,
   LOCATION -> location)
2. Query `ObjectProperty.objects.filter(object=entity, property=self.property)`
   (Note: the field is `object`, not `target_object` — that's the existing ObjectProperty
   field name)
3. If no ObjectProperty found: return `PrerequisiteEvaluation(met=False, reason=...)`
4. If found but `value < self.minimum_value`: return not met with reason
5. Otherwise: return `PrerequisiteEvaluation(met=True)`

The reason string is auto-generated from the model fields:
`"Requires {property.name} on {property_holder label} (minimum {minimum_value})"`

### Two-Level Evaluation in get_available_actions()

Prerequisites are checked at two levels in `_match_approaches()`:

1. **Capability-level**: `approach.application.capability.prerequisite` — if set, evaluate
   once per capability. Result cached per `capability_id` since multiple sources share
   the same capability.

2. **Source-level**: Look up `Prerequisite` from `source.prerequisite_id` — if set,
   evaluate per-source. This is the grant-specific prerequisite from
   `TechniqueCapabilityGrant.prerequisite`.

Both levels receive the same arguments: `(character, challenge_instance.target_object, location)`.

If either level fails:
- `AvailableAction.prerequisite_met = False`
- Failed reasons appended to `prerequisite_reasons`
- Difficulty calculation is skipped (no point computing difficulty for an unavailable action)

### Interaction with IMPOSSIBLE Difficulty

Currently `_match_approaches()` skips actions with `DifficultyIndicator.IMPOSSIBLE`.
With prerequisites, the ordering is:

1. Effect property check (existing)
2. **Prerequisite check (new)**
3. Difficulty calculation (existing, skipped if prerequisite fails)
4. IMPOSSIBLE filter (existing, skipped if prerequisite fails)

If a prerequisite fails, the action is included with `prerequisite_met=False` and
difficulty calculation is skipped entirely. This means `difficulty_indicator` needs a
default for prerequisite-failed actions. Make the field optional:
`difficulty_indicator: DifficultyIndicator | None = None`.

### Caching and Prefetch

**Capability-level cache**: Build a `dict[int, PrerequisiteEvaluation]` keyed by
`capability_id` inside `_match_approaches()`. Before evaluating, check the cache.
This avoids re-evaluating the same capability prerequisite for each source.

**Prefetch additions**:
- Add `application__capability__prerequisite` and
  `application__capability__prerequisite__property` to the existing select_related
  chain on approaches. This avoids lazy-loading the capability's prerequisite and its
  property FK during evaluation.

**Source-level**: No batch fetch needed. `CapabilitySource.prerequisite` carries the
`Prerequisite` instance directly (populated from the grant's FK during
`_get_technique_sources()`). The prefetch in `_get_technique_sources()` should add
`prerequisite` and `prerequisite__property` to the select_related chain so the
instance is fully loaded with no lazy queries.

## Integration Test Updates

The pipeline integration tests already have a `PrerequisiteType` (now `Prerequisite`)
on the control capability grant. Update `ChallengePathTests`:

- Create an `ObjectProperty` on the character (or target_object/location as appropriate)
  that satisfies the prerequisite
- Assert that `AvailableAction.prerequisite_met` is True when the property is present
- Assert that `prerequisite_met` is False with a reason when the property is absent
- `ChallengeInstance` creation needs the new `target_object` FK

## Migration Notes

Fixtures are not in version control. The dev database may have PrerequisiteType rows
from testing. The implementer should check and document what they find.

**Strategy**: Use `RenameModel` for the PrerequisiteType -> Prerequisite rename.
New fields on Prerequisite (`property`, `property_holder`) should be added as nullable
first, then backfilled and made required in a second migration if existing rows need it.
`minimum_value` has a default of 1 so it's safe as non-nullable from the start.

`ChallengeInstance.target_object` should be added as nullable first, then existing
instances backfilled (set `target_object = location` as a reasonable default), then
made non-nullable.

If the tables are empty (no fixture data), skip the nullable dance and make everything
required from the start.

## Scope Boundaries

**In scope:**
- Rename PrerequisiteType -> Prerequisite
- New fields on Prerequisite (property, property_holder, minimum_value)
- evaluate() method on Prerequisite
- PrerequisiteEvaluation dataclass
- PropertyHolder TextChoices
- target_object FK on ChallengeInstance
- Prerequisite evaluation in get_available_actions()
- AvailableAction prerequisite_met + prerequisite_reasons fields
- Factory updates
- Integration test updates

**Out of scope (future work):**
- service_function_path escape hatch for bespoke prerequisites
- Challenge object typeclasses
- Frontend display of disabled actions with reasons
- Prerequisite evaluation in scene action path (only challenge path for now)
- Admin UI improvements for prerequisite authoring

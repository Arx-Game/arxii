# Post-Effect System Design

## Summary

Replace the JSONField-based effect vocabulary on `ActionEnhancement` with proper
Django models that have real foreign keys. Each effect type is a concrete model
inheriting from an abstract `BaseEffectConfig`. Handlers are plain functions
dispatched by config model type. The first complex handler, `apply_condition_on_check`,
demonstrates the generic "attempt to apply an effect gated by a check" pattern that
covers charm, poison, intimidate, and any similar mechanic.

## Motivation

The current `effect_parameters` JSONField stores string references to other models
(`"condition": "charmed"`, `"check_type": "social"`). This discards referential
integrity — nothing prevents referencing a condition that doesn't exist or was renamed.
Proper FK-backed config models give us database-enforced integrity, admin discoverability,
and clear schema documentation.

## Architecture

### Effect Config Models

An abstract base provides shared fields. Each effect type is a concrete model with
typed FKs to the entities it references:

```python
class BaseEffectConfig(Model):
    class Meta:
        abstract = True
    enhancement = FK(ActionEnhancement, related_name="%(class)s_configs")
    execution_order = IntField(default=0)

class ModifyKwargsConfig(BaseEffectConfig):
    kwarg_name = CharField(max_length=50)
    transform = CharField(max_length=50, choices=TransformChoices)

class AddModifierConfig(BaseEffectConfig):
    modifier_key = CharField(max_length=50)
    modifier_value = IntField()

class ConditionOnCheckConfig(BaseEffectConfig):
    check_type = FK(CheckType)                        # attacker's weighted traits
    resistance_check_type = FK(CheckType, null=True)  # defender's weighted traits
    target_difficulty = IntField(null=True)            # fixed fallback for NPCs/missions
    condition = FK(ConditionTemplate)                  # applied on success
    severity = IntField(default=1)
    duration_rounds = IntField(null=True)
    immunity_condition = FK(ConditionTemplate, null=True)  # applied on failure
    immunity_duration = IntField(null=True)
    source_description = CharField(max_length=200)
```

An `ActionEnhancement` can have multiple config rows across different tables,
ordered by `execution_order`. The `effect_parameters` JSONField is removed.

### Effects Package Structure

`effects.py` becomes a package:

```
src/actions/effects/
    __init__.py      # public API: apply_effects(enhancement, context)
    base.py          # shared reusable steps
    kwargs.py        # ModifyKwargsConfig handler
    modifiers.py     # AddModifierConfig handler
    conditions.py    # ConditionOnCheckConfig handler
    registry.py      # maps config model classes -> handler functions
```

### Handler Registry and Dispatch

The registry maps concrete config model classes to typed handler functions:

```python
HANDLER_REGISTRY: dict[type[BaseEffectConfig], Callable[[ActionContext, BaseEffectConfig], None]] = {
    ModifyKwargsConfig: handle_modify_kwargs,
    AddModifierConfig: handle_add_modifier,
    ConditionOnCheckConfig: handle_condition_on_check,
}
```

`apply_effects` queries all config tables for a given enhancement, sorts by
`execution_order`, and calls each handler:

```python
def apply_effects(enhancement: ActionEnhancement, context: ActionContext) -> None:
    configs = get_all_configs(enhancement)
    for config in configs:
        handler = HANDLER_REGISTRY[type(config)]
        handler(context, config)
```

`ActionEnhancement.apply()` calls `apply_effects(self, context)`.

### Adding a New Effect Type

1. Create a concrete model inheriting `BaseEffectConfig` with proper FKs
2. Write the handler function in an appropriate module under `effects/`
3. Register it in `HANDLER_REGISTRY`
4. Migration for the new table

No changes to `ActionEnhancement`, `base.py`, or the dispatch mechanism.

## ConditionOnCheckConfig Handler

### Reusable Steps (effects/base.py)

Discrete functions that other handlers can also call:

- `check_immunity(target, immunity_condition) -> bool`
- `resolve_target_difficulty(target, resistance_check_type, fallback_difficulty) -> int`
- `roll_effect_check(actor, check_type, target_difficulty, extra_modifiers) -> CheckResult`
- `apply_effect_condition(target, condition, severity, duration, source_info) -> ApplyConditionResult`
- `apply_immunity_on_fail(target, immunity_condition, immunity_duration) -> None`

### Handler Flow

1. **Check immunity** — `has_condition(target, config.immunity_condition)`. If immune, skip.
2. **Resolve difficulty** — compute target's resistance points from `config.resistance_check_type`
   via the standard trait → point conversion pipeline, or use `config.target_difficulty` as
   fallback for synthetic NPCs / mission contexts.
3. **Roll** — `perform_check(actor, config.check_type, target_difficulty=resolved)`.
4. **On success** — `apply_condition(target, config.condition, config.severity, config.duration_rounds, source_character=actor)`.
5. **On failure** — if `config.immunity_condition` is set, apply it with `config.immunity_duration`.

Each step calls existing service functions (`perform_check`, `apply_condition`,
`has_condition`). The handler is purely orchestration.

### Difficulty Resolution

Either `resistance_check_type` or `target_difficulty` provides the difficulty:

- If `resistance_check_type` is set and the target has traits, compute points through
  the standard weighted trait → point conversion pipeline.
- If `target_difficulty` is set (synthetic NPCs, mission difficulty), use it directly.
- If both are set, `resistance_check_type` takes precedence for real characters;
  `target_difficulty` serves as fallback for targets without traits.

## Testing Strategy (TDD)

Tests written first, verified red, then implementation makes them green.

### Unit tests for shared steps
Each reusable step function tested in isolation with factories and real DB objects.
Patch `perform_check` to control roll outcomes.

### Handler tests
Each handler tested with its config model. Create config with real FKs, call handler
directly with a manually-built ActionContext, verify outcomes (condition applied,
immunity granted, kwargs modified).

### Scenario integration tests
Full `action.run()` path with real DB records. The existing Loud and Alluring Voice
tests updated to use config models. Prove the whole chain: build context → query
configs → dispatch handlers → execute → post-effects.

### What we don't test
Django FK integrity (DB enforces), config CRUD (Django built-in), registry lookup (trivial).

### Definition of done per handler
A scenario test creates real DB records for source model, ActionEnhancement, and effect
config, calls `action.run()`, and verifies the game-world outcome — not internal
implementation details.

## Upstream Dependencies (Out of Scope)

### OOC Consent System
When a player targets another player with an action, the target sees the actor's
intent and can accept, accept with a modifier to the roll, or decline. This gates
the action before any post-effect fires. NPCs are always valid targets.

Player preferences control automation: auto-accept from friends, whitelist, per-category
rules. Players who accept are flagged for weekly Kudos awards as good sport recognition.

This is a prerequisite concern at the action level, not a post-effect concern. If a
post-effect fires, consent was already established upstream.

See `memory/consent-and-targeting.md` for full notes.

## Design Principles

- **Data-driven over code-driven** — new effects are DB rows, not new handler code
  (when using existing handler types)
- **Real FKs over string references** — database integrity, not hope
- **Abstract base, concrete models** — DRY shared fields, no polymorphic models
- **Reusable steps, composed handlers** — shared functions, flat registry
- **Types over dicts** — typed config models, typed handler signatures, no `Any`
- **Existing systems do the work** — `perform_check()`, `apply_condition()`,
  `has_condition()` already exist. Handlers orchestrate, not reinvent.

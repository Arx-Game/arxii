# Behaviors - Reusable Behavior System

Database-driven behavior attachment for game objects: attach a hooks module to
any object, with per-instance configuration, so behavior changes without code
changes.

## Models (`models.py`)

- **`BehaviorPackageDefinition`** - the reusable template. `name` (unique),
  `description`, and `service_function_path` (a dotted path, imported and cached
  via the `service_function` cached_property).
- **`BehaviorPackageInstance`** - attaches a definition to one object.
  Fields: `definition` FK, `obj` FK to ObjectDB, `hook` (the hook name this
  package answers), and `data` (a JSONField - see the warning below).
  `get_hook(name)` returns the service function **only** when `name` matches
  this instance's `hook`; `get_from_data(key)` reads a key out of `data`.

There is no `BehaviorState` model. (This file previously documented one, along
with `object=` / `package_definition=` / `configuration=` kwargs that do not
exist. Corrected 2026-08-28 during #3416.)

## How hooks are dispatched

`SceneDataManager.initialize_state_for_object` loads every
`BehaviorPackageInstance` for an object onto `BaseState.packages`.
`BaseState._run_package_hook(name, *args)` then walks them, calls the first
package whose `hook` matches, and **the first non-None result wins**.
`apply_attribute_modifiers` uses the sibling `modify_<attr>` convention and
chains every package instead of stopping at the first.

Hooks currently consulted: `initialize_state`, `can_move`, `can_traverse`
(`ExitState`), `can_take` / `can_drop` / `can_give` / `can_equip`
(`ItemState`), `can_apply` (`OutfitState`), and `modify_<attr>`.

**There is no `resolve_destination` hook.** Movement redirection is authored
through flows and conditions instead - see ADR-0242 and #3416.

## Shipped packages

- **`matching_value_package.require_matching_value`** - gates an action on the
  actor (or something they carry) having an attribute equal to a required
  value. The canonical example is a locked exit keyed to an item.
- **`state_values_package.initialize_state`** - copies values out of `data`
  onto the state.

## Attaching a package

From a flow, via `flows.service_functions.packages`:
`register_behavior_package(obj, package_id, hook, data)` /
`remove_behavior_package(obj, package_id)`.

Directly:

```python
BehaviorPackageInstance.objects.create(
    definition=lock_def,          # NOT package_definition
    obj=exit_obj,                 # NOT object
    hook="can_traverse",          # required - get_hook matches on this
    data={"attribute": "key_id", "value": "silver"},   # NOT configuration
)
```

## Status and caveats

- **No production consumers.** Verified 2026-08-28: every non-test reference is
  infrastructure (the loader, the registrar, type annotations). The only
  `objects.create` calls are in tests and docstrings. The system was added in
  #42 and has never been adopted, so treat it as unfinished rather than
  battle-tested - and see ADR-0242 for why #3416 deliberately did not build on
  it.
- **`data` is a JSONField, against ADR-0007.** Do not extend its use for
  relational or queryable state. If a package needs structured configuration,
  give it typed columns rather than growing the blob.

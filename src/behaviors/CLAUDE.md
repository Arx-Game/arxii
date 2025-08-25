# Behaviors - Reusable Behavior System

Database-driven behavior attachment system for game objects. Allows dynamic object behavior modification without code changes.

## Key Files

### `models.py`
- **`BehaviorPackageDefinition`**: Defines available behavior packages
- **`BehaviorPackageInstance`**: Links behaviors to specific objects
- **`BehaviorState`**: Runtime state for behavior instances

### `matching_value_package.py`
- Behavior package for value matching and comparison logic

### `state_values_package.py`
- Behavior package for state value management and tracking

## Key Classes

- **`BehaviorPackageDefinition`**: Database-defined behavior templates
- **`BehaviorPackageInstance`**: Attaches behaviors to objects with configuration
- **`BehaviorState`**: Runtime behavior state management

## Usage Pattern

```python
# Attach behavior to object
behavior = BehaviorPackageInstance.objects.create(
    object=some_object,
    package_definition=package_def,
    configuration={"key": "value"}
)

# Behavior automatically affects object functionality
```

Enables dynamic object customization through database configuration rather than code changes.

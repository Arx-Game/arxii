# Cached Property Usage Standard

## Current State
The codebase currently has inconsistent usage of `cached_property`:

- **8 files** use Django's `cached_property` (`django.utils.functional`)
- **3 files** use functools `cached_property`

## Recommendation: Standardize on `functools.cached_property`

### Rationale:
1. **Standard Library**: `functools.cached_property` is part of Python's standard library (3.8+)
2. **Performance**: Slightly better performance as it's implemented in C
3. **Future-proof**: Less dependency on Django internals
4. **ArxII Target**: We're using Python 3.13+, so standard library version is available

### Migration Strategy:
1. **New Code**: Always use `from functools import cached_property`
2. **Existing Code**: Can remain with Django version for now - both are supported
3. **Gradual Migration**: Update Django imports to functools when touching files

### Mixin Compatibility:
The `CachedPropertiesMixin` and `RelatedCacheClearingMixin` support both implementations automatically, so migration can be gradual without breaking cache clearing functionality.

### Standard Import:
```python
# Preferred (new code)
from functools import cached_property

# Legacy (existing code, still supported)
from django.utils.functional import cached_property
```

### Files to Eventually Migrate:
- `behaviors/models.py`
- `typeclasses/tests/test_trigger_registry.py`
- `typeclasses/rooms.py`
- `flows/managers.py`
- `flows/models/triggers.py`
- `typeclasses/characters.py`
- `typeclasses/accounts.py`
- `flows/object_states/base_state.py`

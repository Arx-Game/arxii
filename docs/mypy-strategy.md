# MyPy Type Checking Strategy

## Philosophy

MyPy is used **strategically** in this project to catch bugs in complex business logic, not to satisfy ceremonial typing requirements. We focus on areas where type errors cause real debugging pain, while avoiding the overhead of typing Django boilerplate.

## What Gets Type Checked

### Currently Included Systems
- **`src/flows`** - Flow system with complex execution logic and state machines
- **`src/world/traits`** - Trait calculations, dice resolution, and complex math
- **`src/commands/handlers`** - Command processing business logic
- **`src/behaviors`** - Dynamic behavior attachment system

### Inclusion Criteria
Add new modules/apps to mypy when they contain:
- **Complex business logic** - Multi-step calculations, state machines, algorithms
- **External integrations** - API calls where wrong types fail silently
- **Error-prone patterns** - Functions with 4+ parameters, complex data transformations
- **Critical path logic** - Code where runtime errors are expensive to debug

## What We Don't Type Check

### Excluded by Default
- **Django CRUD apps** - Simple models, views, serializers with minimal business logic
- **Migration files** - Auto-generated, no business logic
- **Test files** - Focus testing effort on functionality, not types
- **Admin interfaces** - Django boilerplate with minimal custom logic

### Django Pain Points We Avoid
- Model field access (returns `Any`)
- QuerySet operations (untyped)
- Foreign key traversal (returns `Any`)
- Simple Django forms and views

## Implementation Guidelines

### For New Django Apps

When creating a new Django app, ask:
1. **Does it contain complex business logic?** If yes, add to mypy
2. **Is it mainly CRUD operations?** If yes, skip mypy
3. **Does it integrate with external APIs?** If yes, consider adding to mypy

### For Existing Code

If mypy becomes painful on existing code:
1. **First option**: Add `# type: ignore` and move on (if <5 minutes to fix)
2. **Second option**: Extract business logic to service modules
3. **Last resort**: Exclude problematic files individually

### Type Annotation Standards

When adding type annotations:
- **Avoid `Any` - use specific types instead** - `AccountDB | None` instead of `Any`, proper model types instead of `Any`
- **Use `cast()` strategically** for Django integration points where we know more than mypy can infer
- **Use `TYPE_CHECKING` imports** to avoid circular imports while maintaining precise typing
- **Be strict with pure business logic** - proper types for calculations, transformations
- **Document complex types** - Use type aliases for readability
- **Don't over-engineer** - Prefer simple types over complex generics

#### Preferred Patterns

```python
# ✅ Good - specific types with TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

def process_user(account: AccountDB | None) -> bool:
    return account is not None and account.is_active

# ✅ Good - cast() for Django magic we can't avoid  
character = cast(Character, ObjectDB.objects.get(id=char_id))
level_value = cast(int, enum_choice.value)

# ❌ Avoid - Any abandons all type safety
def process_user(account: Any) -> bool:  # Too vague!
    return hasattr(account, 'is_active') and account.is_active
```

## Configuration

### Current MyPy Settings
```toml
[tool.mypy]
files = [
    "src/flows",                       # Flow system - core game logic
    "src/world/traits",                # Trait system - calculations and dice
    "src/commands/handlers",           # Command processing logic
    "src/behaviors",                   # Dynamic behavior system
]
exclude = [
    "^.*/tests",
    "^.*/migrations",
]
ignore_missing_imports = true
warn_return_any = true
check_untyped_defs = true
```

### Adding New Systems

To add a new system to type checking:
1. Add the module path to `files` array in `pyproject.toml`
2. Run `mypy` to see what breaks
3. Fix genuine type issues, add `# type: ignore` for Django pain points
4. If it becomes too painful, exclude specific files and/or refactor

## Success Metrics

MyPy is successful in this project if it:
- **Catches actual bugs** during development (not just style issues)
- **Improves developer experience** (better IDE support, clearer interfaces)
- **Doesn't slow down development** (quick to fix issues, minimal ceremony)

If mypy becomes a development burden rather than a development aid, we should reduce its scope rather than fight with it.

## Examples

### ✅ Good MyPy Candidates
```python
# Complex business logic - worth typing
def calculate_trait_total(base_value: int, modifiers: List[int]) -> int:
    return base_value + sum(modifiers)

# External API integration - silent failures are bad
def upload_to_cloudinary(image_data: bytes) -> CloudinaryResponse:
    return cloudinary.uploader.upload(image_data)
```

### ❌ Poor MyPy Candidates  
```python
# Simple Django CRUD - not worth the typing overhead
class CharacterListView(ListView):
    model = Character
    template_name = 'characters/list.html'

# Basic model with no complex logic
class SimpleLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
```

## References

This strategy is referenced by:
- `CLAUDE.md` - Project guidelines for Claude Code
- Development onboarding documentation
- Code review checklists for new Django apps

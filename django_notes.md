# Django Development Guidelines

This document contains Django-specific development guidelines for Arx II. These rules should be followed when working with Django models, views, serializers, and other Django components.

## Model Field Choices

### Use Django TextChoices and IntegerChoices
**Always use Django's built-in choice classes instead of Enums with manual choice generation.**

```python
# CORRECT - Use Django TextChoices
class StoryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"

# In models
status = models.CharField(choices=StoryStatus.choices, default=StoryStatus.INACTIVE)

# WRONG - Don't use Enums with manual choice generation
class StoryStatus(Enum):
    ACTIVE = "active"
```

**Benefits:**
- Cleaner, more readable code
- Better admin interface labels
- Native Django integration
- Better IDE support and type checking

## Migration Management for New Apps

**When developing a new app, avoid creating multiple migrations. Use the clean-slate approach:**

```bash
# 1. Fake-migrate app to zero (marks migrations as unapplied, preserves data)
arx manage migrate app_name zero --fake

# 2. Move any data migrations to temporary storage
mkdir temp_migrations
mv world/app_name/migrations/0*_data_*.py temp_migrations/

# 3. Delete all remaining migration files (keep __init__.py)
rm world/app_name/migrations/0*.py

# 4. Regenerate clean initial migration
arx manage makemigrations app_name

# 5. Move data migrations back and fix dependencies
mv temp_migrations/0*_data_*.py world/app_name/migrations/
# Edit data migration dependencies to point to new 0001_initial.py

# 6. Fake-apply the initial migration (tables already exist)
arx manage migrate app_name --fake-initial

# 7. Apply any remaining migrations normally
arx manage migrate app_name
```

This prevents migration dependency issues and maintains clean history.

**IMPORTANT: Do NOT drop or flush the database.** The dev database contains fixture data
and test state that is time-consuming to reconstruct. Use `--fake` and `--fake-initial`
to reset migration state without destroying data. Only drop the database in dire
circumstances where the schema is irrecoverably broken.

## ViewSets and API Design

### Required Components for All ViewSets

**Every ViewSet must include:**

1. **Filters**: Use django-filter for flexible query capabilities
2. **Pagination**: Custom pagination classes for consistent API responses
3. **Permissions**: Proper permission classes for security
4. **Serializers**: Separate serializers for different operations when needed

### Permission Classes

**All ViewSets must have permission classes that:**

- **Create/Update/Delete**: Restricted to staff or entity 'owner'
- **Read Operations**:
  - Public entities: Open to authenticated users
  - Private/Hidden entities: Restricted to staff, owner, or explicitly allowed parties

```python
class StoryPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_staff or self.is_owner(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return self.can_read_story(request.user, obj)
        return self.is_owner_or_staff(request.user, obj)
```

### Filters

**Use django-filter for all ViewSets:**

```python
class StoryFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=StoryStatus.choices)
    privacy = django_filters.ChoiceFilter(choices=StoryPrivacy.choices)
    owner = django_filters.ModelChoiceFilter(queryset=Account.objects.all())

    class Meta:
        model = Story
        fields = ['status', 'privacy', 'owner', 'is_personal_story']
```

### Pagination

**Create custom pagination classes for consistent API responses:**

```python
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
```

### ViewSet Example

```python
class StoryViewSet(viewsets.ModelViewSet):
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [StoryPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StoryFilter
    pagination_class = StandardResultsSetPagination
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'updated_at', 'title']
    ordering = ['-updated_at']
```

### ViewSet Anti-Patterns to Avoid

**Never use custom `get()` methods when filters or queryset can handle the logic:**

```python
# WRONG - Custom get method with manual query param handling
class SpeciesListView(APIView):
    def get(self, request):
        heritage_id = request.query_params.get("heritage_id")
        queryset = Species.objects.filter(allowed_in_chargen=True)
        if heritage_id:
            pass  # full list
        else:
            queryset = queryset.filter(name__iexact="Human")
        serializer = SpeciesSerializer(queryset, many=True)
        return Response(serializer.data)

# CORRECT - Use ViewSet with FilterSet
class SpeciesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Species.objects.filter(allowed_in_chargen=True)
    serializer_class = SpeciesSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SpeciesFilter
```

**Never convert model instances to dicts before passing to serializers:**

```python
# WRONG - Manual dict conversion defeats the purpose of serializers
species_data = [
    {"id": s.id, "name": s.name, "description": s.description} for s in queryset
]
serializer = SpeciesSerializer(species_data, many=True)

# CORRECT - Pass queryset/instances directly to serializer
serializer = SpeciesSerializer(queryset, many=True)
```

**Use `@action` decorators for custom endpoints on ViewSets:**

```python
# WRONG - Separate APIView for related action
class SubmitDraftView(APIView):
    def post(self, request):
        draft = CharacterDraft.objects.filter(account=request.user).first()
        # ... process draft

# CORRECT - Action on the ViewSet
class CharacterDraftViewSet(viewsets.ModelViewSet):
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        draft = self.get_object()
        # ... process draft
```

## Testing Guidelines

### Test Coverage Philosophy

**Focus on application logic, not Django functionality:**

- ✅ **Test**: Custom methods, API behavior, serializers, business logic
- ❌ **Don't Test**: Django's built-in functionality (save(), delete(), etc.)

### Use FactoryBoy for All Test Data

**Always use FactoryBoy factories instead of creating models directly:**

```python
# CORRECT - Use FactoryBoy
class StoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Story

    title = factory.Faker('sentence', nb_words=4)
    description = factory.Faker('paragraph')
    status = StoryStatus.ACTIVE
    privacy = StoryPrivacy.PUBLIC

# In tests
story = StoryFactory()
stories = StoryFactory.create_batch(5)

# WRONG - Don't create models directly
story = Story.objects.create(title="Test Story", description="Test")
```

### Performance Optimization

**Use `setUpTestData` for reusable test data:**

```python
class StoryViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Create data once for the entire test class"""
        cls.user = AccountFactory()
        cls.staff_user = AccountFactory(is_staff=True)
        cls.story = StoryFactory()
        cls.private_story = StoryFactory(privacy=StoryPrivacy.PRIVATE)

    def test_story_list_authenticated(self):
        """Test that authenticated users can list public stories"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/stories/')
        self.assertEqual(response.status_code, 200)
```

**Benefits of `setUpTestData`:**
- Data created once per test class, not per test method
- Significant performance improvement for test suites
- Wrapped in database transactions for isolation

### Test Structure

**Organize tests by functionality:**

```python
class StoryModelTestCase(TestCase):
    """Test Story model methods and properties"""

class StorySerializerTestCase(TestCase):
    """Test Story serialization and deserialization"""

class StoryViewSetTestCase(TestCase):
    """Test Story API endpoints and permissions"""

class StoryPermissionTestCase(TestCase):
    """Test Story permission classes"""
```

### Test Naming Convention

**Use descriptive test method names:**

```python
def test_authenticated_user_can_list_public_stories(self):
def test_staff_user_can_create_story(self):
def test_story_owner_can_update_story(self):
def test_private_story_not_visible_to_non_owners(self):
```

## API Response Standards

### Consistent Error Responses

**Use DRF's standard error format:**

```python
{
    "detail": "Error message",
    "field_errors": {
        "field_name": ["Specific field error"]
    }
}
```

### Pagination Response Format

**Consistent pagination wrapper:**

```python
{
    "count": 123,
    "next": "http://api.example.org/accounts/?page=4",
    "previous": "http://api.example.org/accounts/?page=2",
    "results": [...]
}
```

### Serializer Guidelines

**Use separate serializers for different operations:**

```python
class StoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""

class StoryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail views"""

class StoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for create operations with validation"""
```

## Security Best Practices

### Permission Checking

**Always implement proper permission checking:**

1. **Authentication**: All API endpoints require authentication unless explicitly public
2. **Authorization**: Check user permissions for each operation
3. **Object-Level Permissions**: Use `has_object_permission` for instance-level checks
4. **Field-Level Security**: Hide sensitive fields from unauthorized users

### Input Validation

**Validate all input at the serializer level:**

```python
class StorySerializer(serializers.ModelSerializer):
    def validate_title(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Title must be at least 3 characters")
        return value.strip()

    def validate(self, data):
        # Cross-field validation
        if data.get('privacy') == StoryPrivacy.PRIVATE and not data.get('owners'):
            raise serializers.ValidationError("Private stories must have owners")
        return data
```

## Import Guidelines

### Use Global Imports by Default

**Always use global imports at the top of the file unless there's a specific reason not to:**

```python
# CORRECT - Use global imports
from django.contrib.auth import get_user_model
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from world.stories.models import Story

class MyView(APIView):
    def get(self, request):
        user = get_user_model().objects.get(id=1)
        return Response({'user': user.username})
```

### When to Use Local Imports

**Only use local imports in these specific situations:**

1. **Circular Import Prevention**: When two modules would import each other
2. **Avoid Premature Model Loading**: When importing before Django has fully loaded
3. **Dynamic/Conditional Imports**: When the import depends on runtime conditions

```python
# CORRECT - Local import to avoid circular dependency
def my_function():
    from world.stories.models import Story  # Avoids circular import
    return Story.objects.all()

# WRONG - Unnecessary local import
def my_function():
    from django.contrib.auth import get_user_model  # No reason for local import
    return get_user_model().objects.all()
```

### Evennia Model Imports

**Evennia models are nearly always safe to import globally:**

```python
# CORRECT - Evennia models are safe to import
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.scripts.models import ScriptDB

# Evennia models will never import from our apps, so no circular import risk
```

**Exception**: Only use local imports for Evennia models if you're in a module that runs during Django startup before Evennia is fully loaded.

### Django-Filter Best Practices

**Follow the established pattern used in existing apps like `world.roster.filters`:**

```python
# CORRECT - Simple filters using field names and method-based custom filtering
import django_filters
from world.stories.models import Story

class StoryFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=StoryStatus.choices)
    owner = django_filters.CharFilter(method='filter_owner', label="Owner Username")
    search = django_filters.CharFilter(method='filter_search', label="Search")

    class Meta:
        model = Story
        fields = ['status', 'privacy', 'is_personal_story']

    def filter_owner(self, queryset, name, value):
        """Filter by owner username"""
        return queryset.filter(owners__username__icontains=value)

    def filter_search(self, queryset, name, value):
        """Search in title and description"""
        return queryset.filter(
            models.Q(title__icontains=value) |
            models.Q(description__icontains=value)
        )

# AVOID - Complex ModelChoiceFilter setups that can cause version compatibility issues
class StoryFilter(django_filters.FilterSet):
    owner = django_filters.ModelChoiceFilter(queryset=AccountDB.objects.all())  # Can cause issues
```

**Key Principles:**
- Use simple field filters (`NumberFilter`, `CharFilter`, `ChoiceFilter`) where possible
- Use method-based custom filtering for complex queries
- Avoid `ModelChoiceFilter` unless absolutely necessary - use `CharFilter` with methods instead
- Focus on functionality over perfect form field types - usability matters more
- Test filters through API endpoint tests, not isolated filter tests

## Code Quality Standards

These standards apply across all Django (and broader Python) work in this repo.

- **Type Annotations Required in Typed Apps**: All functions in apps listed under `[tool.ty.src].include` in `pyproject.toml` **must** have type annotations for all arguments and return types. A pre-commit hook (`check-type-annotations`) enforces this via ruff ANN rules on staged files. If a function truly cannot be annotated, add an inline `# noqa: ANN` with a comment explaining why. The typed apps list is maintained in both `pyproject.toml` and `tools/check_type_annotations.py` — keep them in sync when adding new apps
- **ty Type Checking**: Strategic type checking via `ty` covers complex business logic apps (see `[tool.ty.src].include`). Skip Django CRUD boilerplate
- **No Relative Imports**: Always use absolute imports (e.g., `from world.roster.models import Roster` not `from .models import Roster`) - relative imports are a flake8 violation for this project
- **Environment Variables**: Use `.env` file for all configurable settings, provide sensible defaults in settings.py
- **No Django Signals**: Never use Django signals (post_save, pre_save, etc.) - they create difficult-to-trace bugs. Always use explicit service function calls that can be tested and debugged easily
- **Migrations**: When model changes require migrations, use `arx manage makemigrations <app>` to generate them. Always use the `arx manage` commands for migrations to ensure correct Django settings are loaded. After generating, apply with `arx manage migrate`
- **No data migrations pre-production**: We have no production data and the dev DB is recreated periodically. Write **schema** migrations only; do NOT add `RunPython` **data** migrations to backfill/transform existing rows — there are no meaningful rows to migrate. (Revisit once shipped to production.)
- **Line Length**: Respect 100-character line limit even with indentation - break long lines appropriately
- **Model Instance Preference**: Always work with model instances rather than dictionary representations. Only serialize models to dictionaries when absolutely necessary (API responses, Celery tasks, etc.) using Django REST Framework serializers. This preserves access to model methods, relationships, and SharedMemoryModel caching benefits
- **Avoid Dict Returns**: Never return untyped dictionaries from functions. Use dataclasses, named tuples, or proper model instances for structured data. Dictionaries should only be used for wire serialization or when truly dynamic key-value storage is needed. Always prefer explicit typing over generic Dict[str, Any]
- **Separate Types Files**: Place dataclasses, TypedDicts, and other type declarations in dedicated `types.py` files within each app/module. This prevents circular import issues when the types need to be referenced across multiple modules. Import types using `from app.types import TypeName`
- **Don't add `Meta.ordering` to models unless necessary**: Default model ordering is not free — it adds an `ORDER BY` to every query against that model, including ones that don't need it. Only set `Meta.ordering` for sequential data with a meaningful natural order, like Chapters or Episodes. ViewSets that paginate querysets **must** add `.order_by(...)` to their queryset (otherwise pagination is unstable across requests and DRF emits `UnorderedObjectListWarning`) — that is the right place to put ordering, not on the model.
- **Prefer Inheritance Over Protocols**: Use concrete base classes with abstract methods instead of Protocol classes for type safety. All objects in our codebase inherit from shared base classes (BaseState, BaseHandler, etc.). When mypy compliance requires type annotations, prefer adding abstract methods to base classes rather than creating Protocol classes. This maintains clear inheritance hierarchies and ensures methods are actually implemented. Use Protocol only for true duck typing scenarios with external libraries.
- **Service Functions Use Model Instances**: Service functions should never accept slug strings for lookups. Always pass model instances or primary keys. Slugs are only for user-facing search APIs where users search by text and receive objects with IDs for subsequent operations. This applies to all internal service layer code.
- **Avoid Denormalization**: Don't copy data from related models into a local field to save joins. If a value is derivable via a relationship (e.g., a scene's story is derivable from scene → episode → story), don't store it redundantly. Denormalized copies create data integrity risks — if the source changes, the copy is stale, and adding verification infrastructure to keep them in sync negates any join savings. Only denormalize when the value is genuinely different per-instance (e.g., a per-encounter risk level) rather than a cached copy of a related field.
- **Avoid Denormalized Foreign Keys**: When a model has a FK to a parent and optionally a FK to a child of that parent (e.g., `condition` + `stage` where stage implies condition), either make one FK derivable from the other or add `clean()` validation to ensure consistency. Don't create situations where FKs can contradict each other. If the child FK is nullable (null = applies to all), keep the parent FK for direct queries but validate the relationship.
- **TextChoices in constants.py**: Place Django TextChoices/IntegerChoices in a separate `constants.py` file rather than as nested classes inside models. This avoids circular import issues when serializers or other modules need to reference the choices, and makes it clearer these are shared constants.
- **No Queries in Loops**: Never execute database queries inside loops, serializer methods that recurse, or while loops that traverse relationships. Use annotations, prefetch_related with bounded depth, or restructure to batch queries. Recursive serializers are acceptable only when paired with bounded prefetch_related in the view (e.g., `prefetch_related("children__children__children")` limits depth to 4 levels).
- **No Management Commands**: Do not create Django management commands unless explicitly requested. Use existing tools: fixtures for seed data, the Django admin for data management, service functions for business logic, and the `arx` CLI for development tasks.
- **No Backwards Compatibility in Dev**: Never add legacy format support, backwards-compatibility shims, or dual-format handling. Accept only the current format. This avoids unnecessary code complexity and maintenance burden.
- **Preserve the Dev Database**: The dev database contains fixture data and test state that is time-consuming to reconstruct. Do NOT drop, flush, or destroy the database except in dire circumstances. For migration work: use `arx manage migrate app_name zero` to fake-migrate down, then regenerate — this preserves the database while resetting an app's migration state. Never delete the database as a shortcut to fix migration issues.
- **PostgreSQL Only (production)**: This project uses PostgreSQL exclusively in production. Freely use PG-specific features: recursive CTEs, materialized views, JSONB operators, window functions, `DISTINCT ON`, etc. Don't write database-agnostic workarounds in production code; use the Postgres feature directly.

  **For tests, see the two-tier model in the `running-tests` skill.** The SQLite inner-loop tier is a developer convenience that exposes PG-specific features as `@tag("postgres")` skips; the Postgres parity tier (every CI run, `just test-parity` locally) always runs the full chain. New tests should pass on both tiers unless they exercise PG-specific code, in which case `@tag("postgres")` is the correct decoration.
- **`# noqa` Suppression Policy**: `# noqa` comments for our custom linters should be rare exceptions, not a convenient escape hatch. Only suppress when fixing the violation would cause more harm than good — for example, necessitating a massive and inelegant refactor. Every suppression MUST include a brief justification comment explaining why (e.g., `# noqa: SHARED_MEMORY — abstract mixin used by multiple apps`). Custom linter tokens: `PREFETCH_STRING`, `STRING_LITERAL`, `SHARED_MEMORY`, `USE_FILTERSET`, `GETATTR_LITERAL`, `CACHED_PROPERTY_IMPORT`, `OBJECTDB_PARAM`
- **SharedMemoryModel Default**: All concrete Django models should use `SharedMemoryModel`. Both lookup tables and per-instance data benefit from the identity-map cache. Only suppress with `# noqa: SHARED_MEMORY` and a justification
- **Prefetch with to_attr**: Always use `Prefetch()` objects with `to_attr=` in `prefetch_related()`. Never use bare strings. The `to_attr` should point to a `cached_property` on the model for cache-safe access
- **cached_property must come from Django**: Use `from django.utils.functional import cached_property` exclusively. `functools.cached_property` silently breaks `Prefetch(to_attr=...)` because Django's prefetch machinery checks `isinstance` against its own class. Enforced by `lint_cached_property_import.py`. See `src/evennia_extensions/CACHED_PROPERTY_STANDARD.md` for full rationale.
- **Constants over String Literals**: Never return spaceless string literals or compare against them. Use `TextChoices`, `IntegerChoices`, or module-level constants. This prevents typo bugs and makes refactoring safe
- **FilterSets in Views**: Always use `django-filter` FilterSet classes for query parameter handling in ViewSets and Views. Never access `request.query_params` or `request.GET` directly

## FactoryBoy `django_get_or_create` Gotcha

This expands the FactoryBoy guidance in "Use FactoryBoy for All Test Data" above with a sharp edge worth calling out explicitly.

**FactoryBoy gotcha: `django_get_or_create` silently drops non-lookup
kwargs.** When a `DjangoModelFactory` declares
`Meta.django_get_or_create = ("lookup_field",)` AND the row already
exists at create time, factory_boy returns the existing row and
**never applies any non-lookup kwargs you passed**. Example: if
something upstream (Evennia signal, `at_object_creation` hook,
fixture) already created the row, `FooFactory(name="X", color="red")`
returns the existing row with the existing color, not `red`. The bug
is invisible unless a test asserts on the dropped field.

When the underlying row may pre-exist via signals/hooks, override
`_create` to apply non-lookup kwargs after the lookup:

```python
@classmethod
def _create(cls, model_class, *args, **kwargs):
    lookup_field = "objectdb"  # or whichever lookup field the factory uses
    lookup_value = kwargs.pop(lookup_field)
    instance, created = model_class.objects.get_or_create(
        **{lookup_field: lookup_value}, defaults=kwargs,
    )
    if not created and kwargs:
        for field, value in kwargs.items():
            setattr(instance, field, value)
        instance.save()
    return instance
```

## ViewSet & API Design (Standards)

These standards complement the "ViewSets and API Design" section above, which covers the required components (filters, pagination, permissions, serializers) and concrete patterns. The bullets below capture the higher-level design rules.

- **Separate ViewSet for related model CRUD**: Custom actions on a ViewSet should operate on that ViewSet's own model (e.g., lifecycle transitions). If an action does create/read/update/delete on a *different* model, extract it into its own ViewSet with proper serializers and filters. Example: invitation CRUD belongs in an `EventInvitationViewSet`, not as custom actions on `EventViewSet`
- **No implicit first-item selection**: Never silently select the first item from a queryset or list when the choice should be user-specified. If there are multiple valid options (e.g., which persona to act as), require explicit selection via request data. Picking `items[0]` hides a decision that should be the caller's
- **Prefer Django/DRF helpers over manual boilerplate**: Use `get_object_or_404` over manual `try/except DoesNotExist`. Use FilterSets over `request.query_params` access. Use DRF's destroy/create mixins over manual `.delete()` and `.create()` with hand-rolled error handling
- **Never use `str(exc)` in API responses**: Always use typed exception classes with a `user_message` property and an allowlist of safe messages (see `EventError`, `JournalError`, `ProgressionError` for the pattern). Raw `str(exc)` risks exposing internal details and triggers CodeQL warnings. Service functions should raise these typed exceptions, and views should use `exc.user_message`
- **Validation belongs in serializers, not views or services**: Views should be thin — accept request, delegate to serializer, return response. Do NOT wrap service calls in `try/except ValidationError` inside views; that indicates validation that belongs in a serializer's `validate()` / `validate_<field>()` methods, which DRF surfaces as 400 responses natively. If a view has `try/except DjangoValidationError as exc: raise serializers.ValidationError(...)`, that's a code smell — move the check into the serializer. Services do not duplicate serializer validation. There is exactly one path to an operation: serializer validates, serializer calls service, service performs the atomic work. Services may raise `ValidationError` only for defensive assertions against programmer errors (e.g., passing the wrong type) — not for user-input validation that belongs in a serializer.
- **Permissions belong in permission classes, not inline checks**: Inline `try/except GMProfile.DoesNotExist → raise PermissionDenied` (or similar) inside a view method is a code smell. Extract to a `BasePermission` subclass (e.g., `IsGM`, `IsGMOrStaff`). That way DRF's permission pipeline handles the 403 uniformly, auth logging/metrics work, and views can safely access `request.user.gm_profile` (or similar) without defensive checks.

These guidelines ensure consistent, secure, and maintainable Django applications within the Arx II codebase.

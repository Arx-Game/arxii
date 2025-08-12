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
# 1. Migrate app to zero (removes all tables)
arx manage migrate app_name zero

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

# 6. Apply all migrations
arx manage migrate app_name
```

This prevents migration dependency issues and maintains clean history.

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

These guidelines ensure consistent, secure, and maintainable Django applications within the Arx II codebase.

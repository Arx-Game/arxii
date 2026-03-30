# Phase 6 REST API: Available Actions & Mechanics Browsing

## Purpose

Expose the proven technique → capability → application → resolution pipeline to
the frontend. The backend logic is complete and integration-tested; this spec
covers the REST API layer that makes it accessible.

## Scope

1. **Available Actions view** — the primary gameplay endpoint: "what can my
   character do here?"
2. **Read-only model ViewSets** — browsing endpoints for ChallengeTemplate,
   ChallengeInstance, SituationTemplate, SituationInstance
3. **`IsCharacterOwner` permission** — reusable permission for any endpoint that
   takes a character ID in the URL
4. **`djangorestframework-dataclasses` adoption** — DRY serialization for
   dataclass return types, including cleanup of existing hand-written serializers
5. **Mechanics URL registration** — add `api/mechanics/` to `web/urls.py`

Out of scope: challenge resolution (POST/mutation), cooperative actions, GM
situation builder.

## Endpoint Layout

### Available Actions (standalone view)

```
GET /api/mechanics/characters/{character_id}/available-actions/
GET /api/mechanics/characters/{character_id}/available-actions/?location_id=123
```

A `ListAPIView` registered via explicit URL pattern (not through the router).
Returns a paginated list of challenge groups. Character ID in the URL, location
defaults to `character.location` with optional query param override for GM use.

### Read-Only Model ViewSets (on the router)

```
GET /api/mechanics/challenge-templates/
GET /api/mechanics/challenge-templates/{id}/
GET /api/mechanics/challenge-instances/
GET /api/mechanics/challenge-instances/{id}/
GET /api/mechanics/situation-templates/
GET /api/mechanics/situation-templates/{id}/
GET /api/mechanics/situation-instances/
GET /api/mechanics/situation-instances/{id}/
```

Registered on the existing `DefaultRouter` in `world/mechanics/urls.py` alongside
the current modifier endpoints.

## Available Actions View

### View Class

`AvailableActionsView(ListAPIView)` in `world/mechanics/views.py`.

- **Permission classes**: `[IsAuthenticated, IsCharacterOwner]`
- **Serializer**: `ChallengeGroupSerializer`
- **Pagination**: `MechanicsPagination` (shared with the model ViewSets)
- **Character resolution**: `get_object_or_404(ObjectDB, pk=kwargs["character_id"])`
- **Location resolution**: optional `location_id` query parameter →
  `get_object_or_404(ObjectDB, pk=location_id)` if provided, else
  `character.location`. The `location_id` query param access requires
  `# noqa: USE_FILTERSET` — this is a standalone computed view, not a
  queryset-filtering scenario, so a FilterSet does not apply

### Grouping Logic

The service function `get_available_actions(character, location)` returns a flat
`list[AvailableAction]`. The view's `get_queryset()` (or `list()` override)
groups these by `challenge_instance_id` into `ChallengeGroup` objects before
passing to the serializer.

`ChallengeGroup` is a small dataclass in `world/mechanics/types.py`:

```python
@dataclass
class ChallengeGroup:
    challenge_instance_id: int
    challenge_name: str
    actions: list[AvailableAction]
```

The view builds these with a simple dict accumulation — no dict comprehensions
returned to the serializer, no ad-hoc dict construction. The serializer receives
typed dataclass instances.

### Response Shape

```json
[
  {
    "challenge_instance_id": 1,
    "challenge_name": "Locked Iron Door",
    "actions": [
      {
        "application_id": 3,
        "application_name": "Pick Lock",
        "capability_source": {
          "capability_name": "lockpicking",
          "capability_id": 5,
          "value": 12,
          "source_type": "TECHNIQUE",
          "source_name": "Skeleton Key",
          "source_id": 7,
          "effect_property_ids": [2, 4]
        },
        "approach_id": 8,
        "check_type_name": "dexterity",
        "display_name": "Pick the Lock",
        "custom_description": "Work the tumblers with magical precision",
        "difficulty_indicator": "moderate",
        "prerequisite_met": true,
        "prerequisite_reasons": []
      }
    ]
  }
]
```

## Serializers

### Dataclass Serializers (new dependency)

Add `djangorestframework-dataclasses` to project dependencies. This provides
`DataclassSerializer` which introspects dataclass fields automatically, just as
`ModelSerializer` introspects model `_meta`.

All dataclass serializers use `DataclassSerializer` with a `Meta.dataclass`
attribute. Fields are derived from the dataclass definition — explicit field
declarations are only needed when excluding fields whose types
`DataclassSerializer` cannot introspect (e.g., Django model instances).

```python
from rest_framework_dataclasses.serializers import DataclassSerializer

class CapabilitySourceSerializer(DataclassSerializer):
    class Meta:
        dataclass = CapabilitySource
        exclude = ["prerequisite"]  # Django model instance, not serializable

class AvailableActionSerializer(DataclassSerializer):
    class Meta:
        dataclass = AvailableAction

class ChallengeGroupSerializer(DataclassSerializer):
    class Meta:
        dataclass = ChallengeGroup
```

`DataclassSerializer` handles nesting automatically — `CapabilitySource` inside
`AvailableAction` and `list[AvailableAction]` inside `ChallengeGroup` are
resolved from the type annotations.

Note: `CapabilitySource.prerequisite` is a `Prerequisite | None` (Django model
instance). This cannot be auto-serialized by `DataclassSerializer`, so it is
excluded. The `prerequisite_met` and `prerequisite_reasons` fields on
`AvailableAction` already carry the evaluation result for the frontend.

`TextChoices` fields (`source_type`, `difficulty_indicator`) serialize as their
string values since `TextChoices` values are plain strings.

### Model Serializers

Standard `ModelSerializer` classes for the read-only ViewSets. Each resource has
a list serializer (lightweight) and a detail serializer (full).

**ChallengeTemplateListSerializer**: `id`, `name`, `category` (name via source),
`severity`, `challenge_type`, `discovery_type`

**ChallengeTemplateDetailSerializer**: adds `description_template`, `goal`,
`properties` (nested), `approaches` (nested with application name, check type
name), `consequences` (nested)

**ChallengeInstanceSerializer**: `id`, `template` (nested list-level template
serializer), `location` (id + name), `target_object` (id + name), `is_active`,
`is_revealed`, `situation_instance` (id, nullable), `created_at`

**SituationTemplateListSerializer**: `id`, `name`, `category` (name via source)

**SituationTemplateDetailSerializer**: adds `description_template`, challenge
links (nested with challenge template name, display_order, depends_on)

**SituationInstanceSerializer**: `id`, `template` (nested list-level serializer),
`location` (id + name), `is_active`, `created_by` (id, nullable), `scene` (id,
nullable), `created_at`

Nested related objects use `source=` for denormalized read-only fields (e.g.,
`category_name = serializers.CharField(source="category.name", read_only=True)`)
following the existing `ModifierTargetSerializer` pattern.

## Read-Only Model ViewSets

All ViewSets follow the existing mechanics app pattern:
`ReadOnlyModelViewSet` + `DjangoFilterBackend` + `IsAuthenticated` + FilterSet.

A shared pagination class avoids repetition across ViewSets:

```python
class MechanicsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
```

### Existing cleanup

The existing `CharacterModifierViewSet` uses bare `filterset_fields` instead of
a `FilterSet` class. Since we're adding `filters.py` and modifying `views.py`,
migrate `CharacterModifierViewSet` to use a proper `FilterSet` class in the
same change. Also move the existing inline `ModifierTargetFilter` class from
`views.py` into `filters.py`.

### ChallengeTemplateViewSet

- **Queryset**: `ChallengeTemplate.objects.select_related("category")`
- **List prefetch**: none needed (flat fields only)
- **Detail prefetch**: `Prefetch` for properties (via through model),
  approaches (with `select_related("application", "check_type")`),
  consequences (via through model with `select_related("consequence")`)
- **FilterSet fields**: `category` (name, iexact), `challenge_type`, `severity`,
  `discovery_type`
- **Pagination**: `PageNumberPagination(page_size=20, max_page_size=100)`
- **List/detail split**: `get_serializer_class()` switching on `self.action`

### ChallengeInstanceViewSet

- **Queryset**: `ChallengeInstance.objects.select_related("template", "location",
  "target_object")`
- **FilterSet fields**: `location` (id), `is_active`, `is_revealed`,
  `template` (id), `situation_instance` (id)
- **Pagination**: `PageNumberPagination(page_size=20, max_page_size=100)`

### SituationTemplateViewSet

- **Queryset**: `SituationTemplate.objects.select_related("category")`
- **Detail prefetch**: challenge links with
  `select_related("challenge_template")`
- **FilterSet fields**: `category` (name, iexact)
- **Pagination**: `PageNumberPagination(page_size=20, max_page_size=100)`
- **List/detail split**: `get_serializer_class()` switching on `self.action`

### SituationInstanceViewSet

- **Queryset**: `SituationInstance.objects.select_related("template", "location")`
- **FilterSet fields**: `location` (id), `is_active`, `created_by` (id)
- **Pagination**: `PageNumberPagination(page_size=20, max_page_size=100)`

## IsCharacterOwner Permission

A reusable permission class in `src/web/api/permissions.py`.

```python
class IsCharacterOwner(permissions.BasePermission):
    """
    Validates that the requesting account has an active RosterTenure
    for the character identified by 'character_id' in the URL kwargs.
    Staff bypass.
    """
```

**Logic:**
1. Extract `character_id` from `view.kwargs["character_id"]`
2. If `request.user.is_staff`, return `True`
3. Query `RosterTenure.objects.filter(roster_entry__character_id=character_id,
   player_data__account=request.user, start_date__isnull=False,
   end_date__isnull=True).exists()`
4. Return the query result

The `start_date__isnull=False` filter matches the existing `IsPlayerOrStaff`
pattern — tenures without a start date are pending/unapproved and should not
grant access.

This follows the same pattern as `IsPlayerOrStaff` in `world/roster/permissions.py`
but resolves through `character_id` in the URL rather than requiring a
`RosterEntry` object.

## URL Registration

### mechanics/urls.py changes

Add the new ViewSets to the existing router and add a manual path for the
available-actions view:

```python
router.register(r"challenge-templates", ChallengeTemplateViewSet, ...)
router.register(r"challenge-instances", ChallengeInstanceViewSet, ...)
router.register(r"situation-templates", SituationTemplateViewSet, ...)
router.register(r"situation-instances", SituationInstanceViewSet, ...)

urlpatterns = [
    path(
        "characters/<int:character_id>/available-actions/",
        AvailableActionsView.as_view(),
        name="available-actions",
    ),
    path("", include(router.urls)),
]
```

### web/urls.py changes

Add the mechanics app URL registration (currently missing):

```python
path("api/mechanics/", include("world.mechanics.urls", namespace="mechanics")),
```

## Existing Serializer Cleanup

Two existing hand-written serializers should be converted to `DataclassSerializer`:

- `DispatcherDescriptorSerializer` in
  `src/flows/service_functions/serializers/commands.py` — serializes
  `@dataclass DispatcherDescriptor`
- `CommandDescriptorSerializer` in the same file — serializes
  `@dataclass CommandDescriptor`

These currently list every field explicitly and have custom `to_representation`
methods that accept both dataclass instances and raw dicts. Converting to
`DataclassSerializer` with `Meta.dataclass` drops the dict-input handling, which
is intentional — per the project's "No Backwards Compatibility in Dev" rule,
callers should pass typed dataclass instances, not dicts.

## Files Changed

### New files
- `src/world/mechanics/filters.py` — FilterSet classes for all ViewSets
- `src/web/api/permissions.py` — `IsCharacterOwner` permission class

### Modified files
- `pyproject.toml` — add `djangorestframework-dataclasses` dependency
- `src/web/urls.py` — register `api/mechanics/` path
- `src/world/mechanics/views.py` — add `AvailableActionsView` and 4 ViewSets
- `src/world/mechanics/serializers.py` — add model serializers and dataclass
  serializers
- `src/world/mechanics/urls.py` — register new ViewSets and available-actions path
- `src/world/mechanics/types.py` — add `ChallengeGroup` dataclass
- `src/flows/service_functions/serializers/commands.py` — convert 2 serializers
  to `DataclassSerializer`

### Test files
- `src/world/mechanics/tests/test_api.py` — ViewSet and view tests following
  `django_notes.md` patterns (FactoryBoy, `setUpTestData`, descriptive names)

## Testing Strategy

Tests follow `django_notes.md` guidelines: FactoryBoy factories, `setUpTestData`,
focus on application logic not Django builtins.

### AvailableActionsView tests
- Authenticated user with owned character gets actions
- Unauthenticated request returns 401
- Non-owned character returns 403
- Staff can access any character
- Optional `location_id` override works
- Empty location (no challenges) returns empty list
- Response shape matches grouped format

### Model ViewSet tests
- List endpoint returns paginated results
- Detail endpoint returns full serializer
- Filter parameters narrow results correctly
- Unauthenticated returns 401

### Permission tests
- `IsCharacterOwner` grants access for active tenure
- `IsCharacterOwner` denies for expired tenure
- `IsCharacterOwner` denies for no tenure
- Staff bypass works

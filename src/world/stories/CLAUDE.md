# Stories System - Narrative Campaign Management

Structured narrative campaign management with hierarchical storytelling and trust-based participation system.

## Action Endpoint Pattern (Canonical — Strictly Enforced)

Every action endpoint in this app follows a strict three-layer architecture. Deviating from this
pattern is a bug. When in doubt, follow this template exactly.

### Layer 1: Permission classes — who can call this

Use `BasePermission` subclasses in `permissions.py`. Never write inline `if not request.user...`
checks or `try/except GMProfile.DoesNotExist → raise PermissionDenied` inside view methods.

```python
# CORRECT
permission_classes = [IsAuthenticated, IsGMProfile, IsLeadGMOnClaimStoryOrStaff]

# WRONG — inline permission check inside view body
try:
    gm_profile = request.user.gm_profile
except GMProfile.DoesNotExist:
    return Response({"detail": "..."}, status=403)
```

### Layer 2: Input serializers — is this input valid?

All business-rule validation belongs in serializer `validate()` / `validate_<field>()` methods.
Use `PrimaryKeyRelatedField(queryset=...)` for FK existence checks. Pass view-resolved objects via
`context={"beat": beat, "claim": claim, ...}` so the serializer can validate cross-field rules.

```python
# CORRECT — FK existence via PrimaryKeyRelatedField
beat = serializers.PrimaryKeyRelatedField(queryset=Beat.objects.all())

def validate_beat(self, beat: Beat) -> Beat:
    if not beat.agm_eligible:
        msg = "This beat is not flagged as available for Assistant GM claims."
        raise serializers.ValidationError(msg)  # assign msg first (TRY003/EM101)
    return beat

# CORRECT — state validation in validate()
def validate(self, attrs: dict) -> dict:
    claim = self.context["claim"]
    if claim.status != AssistantClaimStatus.REQUESTED:
        raise serializers.ValidationError(
            {"non_field_errors": "Only REQUESTED claims can be approved."}
        )
    return attrs
```

Views call `ser.is_valid(raise_exception=True)` and access `ser.validated_data` only.
No `try/except ValidationError` in view bodies — DRF surfaces serializer errors as 400 natively.

### Layer 3: Service functions — the atomic work

Services receive only pre-validated data. They contain only **defensive programmer-error guards**
(not user-input validation). Use `if ... raise ValueError(msg)` — never `assert` (ruff S101).

```python
# CORRECT
if claim.status != AssistantClaimStatus.REQUESTED:
    msg = (
        f"Claim {claim.pk} is not REQUESTED (status={claim.status!r}); "
        "ApproveClaimInputSerializer should have rejected this."
    )
    raise ValueError(msg)

# WRONG — assert triggers ruff S101
assert claim.status == AssistantClaimStatus.REQUESTED, "..."

# WRONG — duplicating user-input validation in service
if not beat.agm_eligible:
    raise serializers.ValidationError("...")
```

### Anti-patterns to never introduce

| Anti-pattern | Correct replacement |
|---|---|
| `try: gm = request.user.gm_profile except DoesNotExist: raise PermissionDenied` in view | `IsGMProfile` permission class |
| `obj = Model.objects.get(pk=...); except DoesNotExist: return 404` in view body | `PrimaryKeyRelatedField` in serializer |
| `try: service() except StoryError: return 400` in view | Validate in serializer `validate()` |
| `assert condition, "..."` in service | `if not condition: raise ValueError(msg)` |
| String literal directly in `raise ValidationError(...)` | Assign `msg = ...` first |

### Exceptions: permitted race-condition `try/except` blocks in view bodies

The following view bodies retain narrow `try/except` blocks for race-condition errors that cannot
be pre-validated by serializers without duplicating service-level atomic state checks. These are
the **only** permitted `try/except` blocks in views; all other validation belongs in serializers.

**`EpisodeViewSet.resolve`** — catches `NoEligibleTransitionError` and `AmbiguousTransitionError`
from `resolve_episode()`. These cannot be pre-validated without duplicating
`get_eligible_transitions()`.

**`StoryGMOfferViewSet.accept`** — catches `StoryGMOfferError("The receiving GM has no active
table…")`. Between serializer validation and service execution, the GM may have lost their active
table (e.g., table archived concurrently). Pre-validating this in the serializer would duplicate
the service's atomic table-existence check without preventing the race condition.

**`EraViewSet.advance`** and **`EraViewSet.archive`** — catch `EraAdvanceError`. The era status
can change between serializer validation and the atomic `advance_era()`/`archive_era()` call.
Pre-validating in the serializer would duplicate the service's idempotency checks without
eliminating the window.

## Key Files

### `models/`
- **`stories.py`**: `Story`, `Chapter`, `Episode` - hierarchical story structure
- **`participation.py`**: `StoryParticipation` - character involvement tracking
- **`trust.py`**: `PlayerTrust`, `TrustCategory` - trust system foundation

### `views.py`
- **`StoryViewSet`**: Story CRUD operations and management
- **`ChapterViewSet`**: Chapter management within stories
- **`EpisodeViewSet`**: Episode management and scheduling
- **`TrustViewSet`**: Trust level administration

### `serializers.py`
- Story hierarchy serialization for API responses
- Trust level and participation data serialization

### `permissions.py`
- Trust-based story access control
- GM permissions for story management
- Visibility controls for public/private stories

### `filters.py`
- Filter stories by status, trust requirements, participation
- Search by GM, participants, story content
- Date-based filtering for archival

## Key Classes

- **`Story`**: Top-level campaign container with trust-based access
- **`Chapter`**: Major narrative arcs within stories  
- **`Episode`**: Individual sessions linking to scene recordings
- **`StoryParticipation`**: Character involvement with role management
- **`PlayerTrust`**: Trust levels across different categories (GM, approval, moderation)

## Hierarchical Structure

```
Story (Campaign)
└── Chapter (Major Arc)
    └── Episode (Individual Session)
        └── Scene (Roleplay Recording)
```

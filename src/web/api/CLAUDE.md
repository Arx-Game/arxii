# Web API — Reviewer Guidance

Specific patterns that reviewers (human or agent) should flag in `src/web/api/` work. These supplement, not replace, the project-wide rules in `C:\Users\apost\PycharmProjects\arxii\CLAUDE.md`.

## Serializer anti-patterns

### `.filter()` / `.objects.filter()` inside `get_*` methods

A serializer method that calls `.filter()` on a related manager fires a fresh query per row being serialized. It bypasses any upstream `prefetch_related`. Symptoms: `assertNumQueries` blows up under load, query-count regression tests catch it.

**Wrong:**
```python
def get_personas(self, obj):
    primary = obj.character_sheet.personas.filter(persona_type=PersonaType.PRIMARY)
    established = obj.character_sheet.personas.filter(
        persona_type=PersonaType.ESTABLISHED
    ).order_by("created_at")
    return PersonaPayloadSerializer(list(primary) + list(established), many=True).data
```

**Right:** add a `cached_property` on the model that returns the filtered list, and use `Prefetch(..., to_attr="<that name>")` upstream:

```python
# On the model
@cached_property
def cached_payload_personas(self) -> list[Persona]:
    """Serves as the to_attr target for Prefetch+to_attr.
    Falls back to a query when not prefetched."""
    return list(self.personas.filter(...).order_by(...))

# In the serializer
def get_personas(self, obj):
    return PersonaPayloadSerializer(obj.cached_payload_personas, many=True).data

# In the view (or context-builder helper)
RosterEntry.objects.filter(...).prefetch_related(
    Prefetch(
        "character_sheet__personas",
        queryset=Persona.objects.filter(...).order_by(...),
        to_attr="cached_payload_personas",
    )
)
```

**The cached_property must come from `django.utils.functional`** — `functools.cached_property` silently breaks `Prefetch(to_attr=...)`. Enforced by `tools/lint_cached_property_import.py`. See `src/evennia_extensions/CACHED_PROPERTY_STANDARD.md`.

### Queryset construction inside serializer methods

```python
def get_available_characters(self, obj):
    entries = RosterEntry.objects.filter(...).select_related(...)
    return AvailableCharacterSerializer(entries, many=True).data
```

This is the same anti-pattern at a coarser grain. The view (or a helper called by the view) should build the queryset and pass it via `context=`. The serializer reads from context, walks attributes, never queries.

**The pattern in this app:** `web/api/payload_helpers.build_account_payload_context(account)` is the canonical example. It returns a dict with the prefetched lists and any derived sets (e.g., `puppeted_character_ids`). `CurrentUserAPIView` calls it; `AccountPlayerSerializer` reads from `self.context`. Tests construct context the same way.

### `select_related` / `prefetch_related` inside serializer methods

Same root cause. These belong on the upstream queryset.

## Permission and validation patterns

These are documented project-wide in `CLAUDE.md`'s "ViewSet & API Design" section. Reviewers should check:

- Inline `try/except <Model>.DoesNotExist → raise PermissionDenied`: should be a `BasePermission` subclass
- `try/except DjangoValidationError as exc: raise serializers.ValidationError(...)` in views: validation belongs in the serializer's `validate()` / `validate_<field>()` methods
- `str(exc)` in API responses: use typed exceptions with `.user_message`
- `request.query_params` / `request.GET` direct access: use a `FilterSet`

## Reference: things that triggered these rules

- Phase 5 senior dev review: inline permission checks in `StoryViewSet.send_ooc` and `TransitionViewSet.save_with_outcomes` (fixed by extracting permission classes).
- Phase 6a senior dev review: `.filter()` inside `AvailableCharacterSerializer.get_personas`; queryset construction inside `AccountPlayerSerializer.get_available_characters`. Fixed in commit `dd6a5ca1` (refactor) and `e5ed0381` (project-wide cached_property sweep that surfaced the silent Prefetch+to_attr bug).

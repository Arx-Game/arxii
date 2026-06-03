# Missions Create UI + Slug Removal — Design

**Date:** 2026-05-27
**Status:** Approved design, awaiting implementation plan
**Branch:** `feature/missions-create-ui`

## Problem

The Mission Studio at `/staff/missions/` has no create-from-scratch affordance. The backend `MissionTemplateViewSet` is a full `ModelViewSet` (POST is supported), but the frontend exposes only the `copy` action — which is useless if nothing exists to copy from. Staff land on a viewer that reads "No missions match these filters" with no path forward.

Two related gaps surface alongside this:

1. `MissionTemplate.categories` is declared `SlugRelatedField(read_only=True)` on the serializer — categories display in the detail panel but cannot be set or changed via the API at all. The model has no `MissionCategoryViewSet` to list available categories either.
2. The missions API uses slug-based URL lookup (`MissionTemplateViewSet.lookup_field = "slug"`, `MissionGiver.slug`, all related custom actions, all frontend routes), where DRF's default `PrimaryKeyRelatedField` / `pk` lookup would work for free. Since no production missions exist, this is a good moment to delete the slug fields entirely and standardize on PK before authoring tools see real use.

## Goal

Ship the create-from-scratch flow end-to-end, fix categories so they're writable, and remove slug fields from the missions surface in one bundled PR. Staff can create a new mission from `/staff/missions/`, fill in all template-level fields including categories on a dedicated form page, and land on the canvas to start authoring nodes.

## Non-Goals

- Authoring the entry node as part of create. A `MissionTemplate` with zero nodes is legal in the DB; it is mechanically non-functional, but visibility/access control is staff's responsibility via `access_tier=STAFF_ONLY` (the model default for new templates) and giver attachment. The author opens the canvas after create to add nodes.
- Authoring `availability_rule` (predicate tree) on the create page. Defaults to `{}`; the existing `PredicateBuilder` component handles editing in the detail/edit surface.
- Inline category creation. Categories are seeded via fixture/admin; the create page picks from existing ones only.
- Changing `MissionNode.key` — this is a graph-internal symbolic identifier (`route.target_node = "boss_room"`), not a URL slug. Authors deliberately name nodes for readability. Different concern, out of scope.
- Backwards compatibility for the slug-based API URLs. There is no production data and no external consumer; the sweep is complete and atomic.

## Architecture

**Single bundled PR**, three internal logical chunks (commit-wise or just review-wise):

1. **Slug → PK sweep** — foundation for everything that follows.
2. **MissionCategory CRUD plumbing** — makes categories writable end-to-end.
3. **Create page + button + route** — the user-visible feature.

## Backend Changes

### Migration

`world/missions/migrations/0XXX_drop_slug_fields.py` (number assigned by `arx manage makemigrations missions`):

- Drops `MissionTemplate.slug` (`SlugField(unique=True)`) and the implicit unique index.
- Drops `MissionGiver.slug` and its unique index.
- Forward operation removes both columns. Reverse re-adds them as `null=True` (no data to backfill — no production missions exist).

### Serializer changes

`MissionTemplateSerializer` (`src/world/missions/serializers.py`):

- **Delete** the explicit `categories = SlugRelatedField(many=True, slug_field="name", read_only=True)` field declaration. DRF's default for an M2M in `ModelSerializer` is `PrimaryKeyRelatedField(many=True, queryset=MissionCategory.objects.all())`, which accepts and returns a list of category PKs on both read and write. Free, no override needed.
- **Remove** `"slug"` from the `Meta.fields` list.
- **Override** `create()` to apply auto-suffix on name collision:
  ```python
  def create(self, validated_data):
      validated_data["name"] = next_available_name(
          validated_data["name"], MissionTemplate.objects.all()
      )
      return super().create(validated_data)
  ```
- Existing `validate_access_tier` stays unchanged — still guards OPEN-flip on instances. No slug involvement.

`MissionTemplateDetailSerializer` — verify `Meta.fields` no longer references `"slug"` after parent class change.

`MissionGiverSerializer` — same treatment: remove `"slug"` from `Meta.fields`; add `create()` override using `next_available_name(..., MissionGiver.objects.all())`.

### ViewSet changes

`MissionTemplateViewSet` (`src/world/missions/views.py`):

- **Remove** `lookup_field = "slug"`. Defaults to `pk`.
- Custom actions: `def copy(self, request, pk=None)` (was `slug=None`); `def assign(self, request, pk=None)`.
- URLs become `/api/missions/templates/<pk>/copy/`, `/api/missions/templates/<pk>/assign/`.
- `copy` action body simplifies: `new_slug` removed (no more slugs); `new_name` becomes optional (auto-suffix from source name if absent). The `copy_template` service uses `next_available_name(source.name + " (copy)", MissionTemplate.objects.all())` internally if no `new_name` is provided.

`MissionGiverViewSet` — same pattern: drop `lookup_field`, custom action sigs become `(request, pk=None)`.

### New ViewSet

`MissionCategoryViewSet` in `src/world/missions/views.py`:

```python
class MissionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MissionCategory.objects.all().order_by("display_order", "name")
    serializer_class = MissionCategorySerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = MissionStudioPagination
```

Register at `/api/missions/categories/` in `src/world/missions/urls.py`. Add `MissionCategorySerializer` to `serializers.py` (id / name / description / display_order).

### Naming service

`src/world/missions/services/naming.py` (new):

```python
def next_available_name(base_name: str, queryset, max_length: int = 200) -> str:
    """Return base_name, or base_name + ' N' for the smallest N >= 2 that is free.

    Truncates base_name when base + suffix would exceed max_length.
    Lookup is on the queryset's model's `name` field.
    """
```

Used by both `MissionTemplateSerializer.create()` and `MissionGiverSerializer.create()` and the `copy_template` / `copy_giver` services. Pure logic + one queryset lookup per attempt.

### Internal call-site sweep

`grep` for slug references in `world/missions/` services and any other internal code: `.get(slug=)`, `.filter(slug=)`, fixture references. Switch to `pk=` or rework the helper to take an instance. The `copy_template` service signature (`copy_template(source: MissionTemplate, ...)`) stays the same — it already accepts an instance — only the view's slug→pk handoff changes.

## Frontend Changes

### New files

**`frontend/src/missions/pages/CreateMissionPage.tsx`** — full-page form at `/staff/missions/new`. Plain `useState` for form state, matching existing missions pages (the codebase does not use `react-hook-form` in this surface). Lazy-loaded in `App.tsx` consistent with the other mission pages. Fields:

- `name` (text, required)
- `summary` (textarea, required)
- `epilogue` (textarea, optional)
- `level_band_min` / `level_band_max` (number inputs, required)
- `risk_tier` (number input, required)
- `base_weight` (number, default 1)
- `arc_scope` (select: `global` / `org` / `giver`, required)
- `percent_replace` (number, default 0)
- `created_in_era` (select from `useEras()`, optional)
- `cooldown` — number input + unit `<Select>` (`hours / days / weeks`); serialized to ISO 8601 duration (`PT24H`, `P7D`) before POST. Required.
- `reward_group_rule` (select, default `ALL_EQUAL`)
- `categories` (`CategoryMultiSelect` — multi-select, optional)
- `access_tier` (select, default `STAFF_ONLY`)

`availability_rule` is not exposed; uses backend default `{}`.

**`frontend/src/missions/components/CategoryMultiSelect.tsx`** — reusable picker. Consumes `useMissionCategories()`, renders a popover with checkboxes (shadcn pattern). Value is `number[]` (array of category PKs). Used by `CreateMissionPage` and `EditCategoriesDialog`.

**`frontend/src/missions/components/EditCategoriesDialog.tsx`** — small dialog opened from `MissionDetailPanel`. Wraps `CategoryMultiSelect` + a save button. PATCHes `{categories: [...pkArray]}` to `/api/missions/templates/<id>/`.

### API + queries additions

`src/missions/api.ts`:

- `createMissionTemplate(body: Partial<MissionTemplate>): Promise<MissionTemplate>` — POST `/api/missions/templates/`.
- `listMissionCategories(): Promise<PaginatedResponse<MissionCategory>>` — GET `/api/missions/categories/`.

`src/missions/queries.ts`:

- `useCreateMissionTemplate()` — `useMutation`; `onSuccess` invalidates `missionKeys.templates()`.
- `useMissionCategories()` — `useQuery` with a long `staleTime` (categories rarely change); cached globally for both the picker and the detail panel name-lookup.

`src/missions/types.ts`:

- Add `MissionCategory` type: `{id: number, name: string, description: string, display_order: number}`.
- Update `MissionTemplate.categories` type from `readonly string[]` to `readonly number[]`.

### Slug → ID sweep (frontend)

| Surface | Change |
|---|---|
| All `api.ts` function signatures | `slug: string` → `id: number`; URL templates updated |
| All `queries.ts` hooks | parameter rename; query keys `["templates","detail",slug]` → `["templates","detail",id]` |
| `App.tsx` routes | `/staff/missions/:slug/canvas` → `/staff/missions/:id/canvas`; same for `/nodes/:nodeId`, `/options/:optionId`, `/givers/:slug` |
| `useParams()` callers | read `id`, parse as number |
| `MissionBrowserPage.tsx` | URL search param `?slug=` → `?id=`; `handleSelectSlug` → `handleSelectId`; `MissionRow data-slug` → `data-id`; add `+ New Mission` button in header |
| `MissionDetailPanel.tsx` | id-keyed queries; `CategoriesRow` takes `readonly number[]`, looks up names via cached `useMissionCategories()`; add edit-pencil opening `EditCategoriesDialog` |
| `StaffActionsCard.tsx` | `template.slug` → `template.id` in all mutate calls; copy dialog simplified (no more `new_slug` field; `new_name` optional, server auto-suffixes) |
| `MissionCanvasPage.tsx`, `NodePage.tsx`, `OptionPage.tsx`, `GiverLibraryPage.tsx`, `GiverEditorPage.tsx` | `useParams` reads `id` |

### Create flow data path

1. User clicks `+ New Mission` on `/staff/missions/` → `navigate('/staff/missions/new')`.
2. `CreateMissionPage` mounts → fires `useMissionCategories()` + `useEras()` (cached on subsequent mounts).
3. User fills form. Cooldown number + unit → ISO 8601 conversion on submit.
4. Submit → `createTemplate.mutateAsync({name, summary, ..., categories: [1,2,3], cooldown: "P7D"})`.
5. Backend `MissionTemplateSerializer.create()` calls `next_available_name(...)`, saves, returns the full serialized template (including the possibly-suffixed name and new `id`).
6. `onSuccess`: if `response.name !== submittedName`, `toast.success(\`Saved as "${response.name}" — "${submittedName}" was taken.\`)`. Then `navigate(\`/staff/missions/${response.id}/canvas\`)`. The templates list query is invalidated by the mutation hook.

### Validation

- **Client-side**: only truly local checks block submit — required fields present, `level_band_min <= level_band_max`, cooldown > 0.
- **Server-side**: everything else trusts the server. On 400, parse DRF field-error shape (`{field: [msg]}`), display inline under each input. No client mirroring of `validate_access_tier` (cannot trigger at create — no givers attached yet).

## Testing

### Backend (pytest)

- **`tests/test_naming.py`** (new) — `next_available_name` unit tests: base returns when no collision; `"Foo"` exists → `"Foo 2"`; `"Foo"` + `"Foo 2"` exist → `"Foo 3"`; long base truncated to fit suffix; empty queryset returns base.
- **`tests/test_template_create.py`** (new) — `MissionTemplateViewSet.create` API tests: 201 with required fields; 400 on missing required field; 400 on `level_band_min > level_band_max`; categories `[id, id]` persisted and returned; 400 on nonexistent category PK; name collision returns `"Heist 2"`; triple collision returns `"Heist 3"`; defaults verified (`access_tier=STAFF_ONLY`, `is_active=True`, `base_weight=1`).
- **`tests/test_categories_endpoint.py`** (new) — `MissionCategoryViewSet`: GET list paginated with id/name/description/display_order; GET detail; POST/PATCH/DELETE return 405; 403 for non-staff.
- **Update existing tests** (`test_template_views.py`, `test_giver_views.py`, copy-service tests, etc.): all `/api/missions/templates/<slug>/` URLs → `<pk>/`; `copy`/`assign` kwarg becomes `pk`; factories drop `slug=`; `copy_template` tests assert auto-suffix instead of caller-provided name.
- **Migration test**: `arx manage migrate missions zero && arx manage migrate missions` runs clean against a populated dev DB. Reverse migration also runs without error.

### Frontend (Vitest)

- **`__tests__/CreateMissionPage.test.tsx`** (new): renders all fields; submit blocked when required fields empty or `level_band_min > level_band_max`; valid submit calls `createMissionTemplate` with correct payload including ISO 8601 cooldown; `useNavigate` called with `/staff/missions/<id>/canvas` on success; field errors rendered inline on 400; `toast.success` invoked when response name differs from submitted name.
- **`__tests__/CategoryMultiSelect.test.tsx`** (new): renders categories from query; checkbox toggling updates value; empty-categories state.
- **`__tests__/MissionBrowserPage.test.tsx`** (update or new): `+ New Mission` button navigates to `/staff/missions/new`; URL param uses `?id=`.
- **Update existing tests**: `__tests__/queries.test.tsx`, `__tests__/StaffActions.test.tsx`, and any detail-panel tests — switch mocks and assertions from slug to id.
- **Type-check sweep**: `pnpm typecheck` after the slug→id sweep surfaces anything missed.

### Test tier

Missions app is in the SQLite-clean set per CLAUDE.md. Inner-loop with `just test-fast missions`; full PG parity via `just test-parity missions` before pushing. Nothing here uses PG-specific features, so no `@tag("postgres")` decorations.

### Manual verification (UI changes per CLAUDE.md)

1. `arx start` + `pnpm dev`; log in as staff.
2. Visit `/staff/missions/` — confirm `+ New Mission` button in header.
3. Click → lands on `/staff/missions/new` with empty form.
4. Submit with one required field empty → inline error.
5. Submit valid form → redirect to `/staff/missions/<id>/canvas`.
6. Hit `+ New Mission` again, submit with same name → toast `Saved as "X 2" — "X" was taken.`; lands on new canvas.
7. Back to `/staff/missions/` — both rows present.
8. Open detail panel on one → confirm category pills render with names (not PKs).
9. Click edit-categories → dialog opens, toggle, save → panel updates.
10. Regression: copy an existing template, assign to a character, edit a node — all still work post-slug-removal.

## Files Changed (rough scale)

### Backend

| File | Change |
|---|---|
| `world/missions/migrations/0XXX_drop_slug_fields.py` | new |
| `world/missions/models.py` | remove `slug` fields from `MissionTemplate`, `MissionGiver` |
| `world/missions/serializers.py` | drop categories override, remove `slug` from Meta.fields on `MissionTemplateSerializer` + `MissionGiverSerializer`, add `create()` overrides on both, add `MissionCategorySerializer` |
| `world/missions/views.py` | drop `lookup_field` on two viewsets, custom action sigs slug→pk, add `MissionCategoryViewSet` |
| `world/missions/urls.py` | register category router |
| `world/missions/services/naming.py` | new |
| `world/missions/services/copy.py` | update to use `next_available_name` |
| `world/missions/tests/test_naming.py` | new |
| `world/missions/tests/test_template_create.py` | new |
| `world/missions/tests/test_categories_endpoint.py` | new |
| `world/missions/tests/test_api_template_detail.py` | update slug→pk URLs |
| `world/missions/tests/test_api_editor_crud.py` | update slug→pk URLs |
| `world/missions/tests/test_api_staff_power.py` | update assign action kwarg slug→pk |
| `world/missions/tests/test_api_giver_library.py` | update slug→pk URLs |
| `world/missions/tests/test_api_copy_actions.py` | update auto-suffix assertions; drop `new_slug` |
| `world/missions/factories.py` | drop `slug=` from `MissionTemplateFactory`, `MissionGiverFactory` |

### Frontend

| File | Change |
|---|---|
| `missions/pages/CreateMissionPage.tsx` | new (~250 LOC) |
| `missions/components/CategoryMultiSelect.tsx` | new (~80 LOC) |
| `missions/components/EditCategoriesDialog.tsx` | new (~60 LOC) |
| `missions/api.ts` | sweep slug→id + 2 new functions |
| `missions/queries.ts` | sweep slug→id + 2 new hooks |
| `missions/types.ts` | new `MissionCategory`; update `categories` type |
| `App.tsx` | new route + 5 route param renames |
| `missions/pages/MissionBrowserPage.tsx` | + button, slug→id |
| `missions/components/MissionDetailPanel.tsx` | slug→id, categories name lookup from cache, edit affordance |
| `missions/components/StaffActionsCard.tsx` | slug→id, simplify copy dialog |
| `missions/pages/MissionCanvasPage.tsx` | useParams slug→id |
| `missions/pages/NodePage.tsx` | useParams slug→id |
| `missions/pages/OptionPage.tsx` | useParams slug→id |
| `missions/pages/GiverLibraryPage.tsx` | slug→id |
| `missions/pages/GiverEditorPage.tsx` | slug→id |
| `missions/__tests__/CreateMissionPage.test.tsx` | new |
| `missions/__tests__/CategoryMultiSelect.test.tsx` | new |
| `missions/__tests__/MissionBrowserPage.test.tsx` | new or updated |
| `missions/__tests__/queries.test.tsx` | update slug→id |
| `missions/__tests__/StaffActions.test.tsx` | update slug→id |

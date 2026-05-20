# drf-spectacular schema coverage: DraftDistinctionViewSet + ClockViewSet

> Executed directly (overnight, unattended) on `feature/drf-spectacular-distinctions-clock`.

**Goal:** Two `viewsets.ViewSet` subclasses ship with no `@extend_schema`, so drf-spectacular can't introspect them and their endpoints are missing/wrong in `src/schema.json` → `frontend/src/generated/api.d.ts`. Apply the documented recipe (memory `drf-spectacular pattern for viewsets.ViewSet`; reference `src/world/items/views.py`) so the schema + generated FE types are correct. **Schema-only / behavior-neutral**: add `@extend_schema` decorators + descriptor serializers; do NOT rewire view bodies' existing ad-hoc validation.

**Tech stack:** DRF + drf-spectacular; `ty`-checked (`src/world/game_clock`, `src/world/distinctions` — check pyproject; `serializers.py` ty-excluded); ruff; React + generated `api.d.ts`. FE gate = `pnpm -C frontend build` (tsc -b + vite), NOT just typecheck.

**Command-shape discipline:** Write/Edit tools only (no heredoc/`$()`); `git -C`; `pnpm -C frontend`; forward-slash `/c/...`; tests via `echo "yes" | uv run arx test <mod>` in background (real exit code, no `tail` pipe); never `> file` redirection.

---

## Recipe (from memory + items reference)

Per `viewsets.ViewSet`: class `@extend_schema(tags=["<app>"])` + `serializer_class = <ReadSerializer>`; per action `@extend_schema(request=..., responses=...)`; `destroy` → `responses={204: None}`; non-paginated list → `responses=<S>(many=True)` (bare array) — these viewsets do NOT use DRF pagination wrapper, so NO `_paginated_response`. Path params (`draft_id`, `pk`) are auto-detected from the URL conf. Imports: `from drf_spectacular.utils import extend_schema, inline_serializer` (+ `OpenApiParameter, OpenApiTypes` only if a query param is needed — none here).

---

### Task 1: game_clock descriptor serializer

**Files:** Modify `src/world/game_clock/serializers.py`

Add a reusable detail-response serializer (the staff actions + error paths return `{"detail": str}`):

```python
class ClockDetailSerializer(serializers.Serializer):
    """Generic ``{"detail": "..."}`` response (staff actions + errors)."""

    detail = serializers.CharField()
```

**Verify:** `uv run ruff check src/world/game_clock/serializers.py`

**Commit:** `feat(game_clock): add ClockDetailSerializer schema descriptor`

---

### Task 2: decorate ClockViewSet

**Files:** Modify `src/world/game_clock/views.py`

Add import: `from drf_spectacular.utils import extend_schema`. Import `ClockDetailSerializer`, `ClockConvertResponseSerializer`, `ClockStateSerializer` (already imported) from serializers.

- Class: `@extend_schema(tags=["game-clock"])` above `class ClockViewSet`; add `serializer_class = ClockStateSerializer` class attr (schema default; harmless at runtime per recipe gotcha).
- `list`: `@extend_schema(responses=ClockStateSerializer)`
- `convert` (`@action(detail=False, methods=["get"])`): keep the `@action`, add **above it** `@extend_schema(parameters=[ClockConvertSerializer], responses=ClockConvertResponseSerializer)` — `parameters=[<serializer>]` lets spectacular expand the query fields (ic_date/real_date). (If spectacular rejects a serializer in `parameters`, fall back to two explicit `OpenApiParameter(name="ic_date"/"real_date", type=OpenApiTypes.DATETIME, location=QUERY, required=False)` and import `OpenApiParameter, OpenApiTypes`.)
- `adjust`: `@extend_schema(request=ClockAdjustSerializer, responses=ClockDetailSerializer)`
- `ratio`: `@extend_schema(request=ClockRatioSerializer, responses=ClockDetailSerializer)`
- `pause`: `@extend_schema(request=None, responses=ClockDetailSerializer)`
- `unpause`: `@extend_schema(request=None, responses=ClockDetailSerializer)`

Decorator order: `@extend_schema(...)` ABOVE `@action(...)` for the action methods.

**Verify:** `uv run ruff check src/world/game_clock/views.py`; `uv run ty check src/world/game_clock/views.py`

**Commit:** `feat(game_clock): @extend_schema coverage for ClockViewSet`

---

### Task 3: distinctions descriptor serializers

**Files:** Modify `src/world/distinctions/serializers.py`

The DraftDistinction endpoints traffic in `draft_data` JSON via `build_distinction_entry` (`world.distinctions.types.DraftDistinctionEntry` TypedDict: `distinction_id:int, distinction_name:str, distinction_slug:str, category_slug:str, rank:int, cost:int, notes:str`). Add **schema-only descriptor serializers** (NOT wired into view validation — purely for `@extend_schema`):

```python
class DraftDistinctionEntrySerializer(serializers.Serializer):
    """Read shape of one distinction entry in draft_data (mirrors
    world.distinctions.types.DraftDistinctionEntry). Schema descriptor
    only — the view reads/writes the draft_data JSON directly."""

    distinction_id = serializers.IntegerField()
    distinction_name = serializers.CharField()
    distinction_slug = serializers.CharField()
    category_slug = serializers.CharField()
    rank = serializers.IntegerField()
    cost = serializers.IntegerField()
    notes = serializers.CharField(allow_blank=True)


class DraftDistinctionCreateSerializer(serializers.Serializer):
    """Request body for add (create)."""

    distinction_id = serializers.IntegerField()
    rank = serializers.IntegerField(required=False, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class DraftDistinctionSwapSerializer(serializers.Serializer):
    """Request body for swap."""

    remove_id = serializers.IntegerField()
    add_id = serializers.IntegerField()
    rank = serializers.IntegerField(required=False, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class DraftDistinctionSyncItemSerializer(serializers.Serializer):
    """One {id, rank} pair in the sync request list."""

    id = serializers.IntegerField()
    rank = serializers.IntegerField(required=False, default=1)


class DraftDistinctionSyncSerializer(serializers.Serializer):
    """Request body for sync (full replace)."""

    distinctions = DraftDistinctionSyncItemSerializer(many=True)
```

(swap/sync response wrappers — `{"removed": int, "added": <entry>}` and `{"distinctions": [<entry>]}` — declared inline at the view via `inline_serializer` in Task 4.)

**Verify:** `uv run ruff check src/world/distinctions/serializers.py`

**Commit:** `feat(distinctions): add DraftDistinction schema descriptor serializers`

---

### Task 4: decorate DraftDistinctionViewSet

**Files:** Modify `src/world/distinctions/views.py`

Add imports: `from drf_spectacular.utils import extend_schema, inline_serializer`; `from rest_framework import serializers` (if not present); import the five new serializers.

- Class: `@extend_schema(tags=["distinctions"])` above `class DraftDistinctionViewSet`; `serializer_class = DraftDistinctionEntrySerializer` class attr.
- `list`: `@extend_schema(responses=DraftDistinctionEntrySerializer(many=True))` (bare array — matches `Response(distinctions)`).
- `create`: `@extend_schema(request=DraftDistinctionCreateSerializer, responses=DraftDistinctionEntrySerializer)`.
- `destroy`: `@extend_schema(responses={204: None})`.
- `swap` (keep `@action(detail=False, methods=["post"])`): above it,
  `@extend_schema(request=DraftDistinctionSwapSerializer, responses=inline_serializer(name="DraftDistinctionSwapResult", fields={"removed": serializers.IntegerField(), "added": DraftDistinctionEntrySerializer()}))`.
- `sync` (keep `@action(detail=False, methods=["put"])`): above it,
  `@extend_schema(request=DraftDistinctionSyncSerializer, responses=inline_serializer(name="DraftDistinctionSyncResult", fields={"distinctions": DraftDistinctionEntrySerializer(many=True)}))`.

Do NOT change any view body logic. `__future__ annotations` is already imported in this file — fine.

**Verify:** `uv run ruff check src/world/distinctions/views.py`; `uv run ty check src/world/distinctions/views.py`

**Commit:** `feat(distinctions): @extend_schema coverage for DraftDistinctionViewSet`

---

### Task 5: regenerate schema + FE types (handle Prettier drift)

Per memory `feedback_gen_api_types_prettier_drift`: bare `just gen-api-types` always dirties `api.d.ts` with a non-semantic reflow; the real invariant is `committed api.d.ts == prettier(openapi-typescript(schema))`.

1. `just gen-api-types` (regens `src/schema.json` + `frontend/src/generated/api.d.ts`).
2. `pnpm -C frontend exec prettier --write src/generated/api.d.ts`
3. `git -C <repo> diff --stat src/schema.json frontend/src/generated/api.d.ts` — expect **real additions** for the now-covered endpoints (clock state/convert/adjust/ratio/pause/unpause, draft distinctions list/create/destroy/swap/sync). Sanity-check the new component names exist (`ClockState`, `ClockDetail`, `DraftDistinctionEntry`, etc.).
4. If `just gen-api-types` errors (spectacular warnings-as-errors), read the error, fix the offending decorator (most likely the `convert` `parameters=[serializer]` form — switch to explicit `OpenApiParameter`), re-run.

**Commit:** `chore(api): regenerate schema + api.d.ts for clock/distinction coverage`

---

### Task 6: reconcile FE consumers + gates

FE consumers: `frontend/src/character-creation/components/DistinctionsStage.tsx`, `ReviewStage.tsx`, `frontend/src/hooks/useDistinctions.ts`, `frontend/src/types/distinctions.ts`, `frontend/src/character-creation/types.ts`. Clock: grep for a consumer.

1. `pnpm -C frontend build` — the real gate. If `tsc -b` fails because a consumer referenced a generated name that changed/now-exists, reconcile (prefer using the now-correct generated type; do not weaken types). Hand-written `frontend/src/types/distinctions.ts` may now duplicate a generated type — leave it unless tsc demands a change; no behavior edits.
2. `pnpm -C frontend lint` on changed FE files (if any changed).
3. Backend: `echo "yes" | uv run arx test world.distinctions world.game_clock` (fresh DB, background, real exit code) — must stay green (behavior unchanged).
4. `uv run ruff check src/world/distinctions/ src/world/game_clock/`; `uv run ty check src/world/distinctions/views.py src/world/game_clock/views.py`.

**Commit (if FE reconciled):** `fix(fe): reconcile consumers with regenerated api types`

---

### Task 7: full gate, push, PR

1. Full affected backend suites on fresh DB (no `--keepdb`): `echo "yes" | uv run arx test world.distinctions world.game_clock world.character_creation` (character_creation consumes draft distinctions) — `OK`.
2. `pnpm -C frontend build` clean; `pnpm -C frontend exec vitest run src/character-creation` (distinctions UI) green.
3. Adversarial review (superpowers:requesting-code-review) over `origin/main..HEAD`: focus = schema fidelity (does each `@extend_schema` response shape EXACTLY match what the view returns? especially `list` bare-array vs wrapper, the `{detail}` shapes, the swap/sync wrappers), behavior-neutrality (no view-body logic changed), no `dict[str,Any]`/Any, query discipline. Fix Critical/Important.
4. Commit plan + any ledger note with `-f` (docs/plans gitignored).
5. `git -C <repo> push -u origin feature/drf-spectacular-distinctions-clock`; report PR URL + summary for manual PR (no `gh`).
6. superpowers:finishing-a-development-branch.

---

## Out of scope / risks

- Do NOT rewire view-body validation to the new serializers (behavior change/risk). Schema descriptors only.
- The `ReadOnlyModelViewSet` classes (DistinctionCategory/DistinctionViewSet, game_clock has none) auto-introspect — leave them.
- If spectacular cannot represent the `convert` query-serializer cleanly, the explicit-`OpenApiParameter` fallback is the bound; do not invent new request shapes.
- Stop and leave a written status if a gate hard-fails in a way that needs a design call (don't hack the schema to pass).

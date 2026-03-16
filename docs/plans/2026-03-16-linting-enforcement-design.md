# Linting Enforcement Design

**Goal:** Enforce project code quality conventions via pre-commit hooks that catch violations at commit time, with rare `# noqa` suppression for justified exceptions.

**Architecture:** AST-based Python scripts in `tools/`, wired into `.pre-commit-config.yaml` as local hooks. All linters are pure-AST (no Django setup) for speed. MODEL_MAP.md is auto-regenerated asynchronously by the custom `makemigrations` command.

## Linters

### 1. String Literal Linter (`lint_string_literal.py`)

**Rule:** Spaceless string literals in returns, comparisons, and match/case patterns should be constants (TextChoices, module-level constants, etc.).

**Catches:**
- `return "easy"` → use `DifficultyIndicator.EASY`
- `if x == "easy"` / `if "easy" != x` → compare against constant
- `case "easy":` → use constant in match pattern

**Skip list** (strings that are NOT identifiers):
- Contains spaces
- Empty string
- Single character
- Starts with underscore
- Contains `/`, `.`, `\`, or regex metacharacters (`^$*+?{}[]|()`)

**Suppression:** `# noqa: STRING_LITERAL`

### 2. SharedMemoryModel Linter (`lint_shared_memory.py`)

**Rule:** All concrete Django models should inherit from `SharedMemoryModel` unless justified. SharedMemoryModel's identity-map cache benefits both lookup tables and per-instance data (modified instances stay current in cache without re-querying).

**Catches:**
- Classes inheriting from `models.Model` or `Model` directly
- Only concrete classes (skips `abstract = True` in Meta)

**Skips:**
- Abstract models
- Migration files
- Test files

**Suppression:** `# noqa: SHARED_MEMORY` with justification comment

### 3. Filterset Linter (`lint_use_filterset.py`)

**Rule:** ViewSet/View classes must use django-filter FilterSets instead of parsing query params manually.

**Catches (inside classes with ViewSet/View/APIView in base name):**
- `request.query_params.get(...)`
- `request.query_params[...]`
- `request.GET.get(...)`
- `request.GET[...]`
- All of the above with `self.request` prefix

**Skips:**
- Code outside ViewSet/View classes
- Test files

**Suppression:** `# noqa: USE_FILTERSET`

### 4. Prefetch Linter Update (`lint_prefetch_string.py`)

**Existing rule:** No bare strings in `prefetch_related()`.

**New addition:** `Prefetch()` calls must include a `to_attr` keyword argument. Bare `Prefetch("foo", queryset=...)` without `to_attr` is flagged.

**Suppression:** `# noqa: PREFETCH_STRING` (existing token)

### 5. MODEL_MAP.md Auto-Regeneration

**Mechanism:** The custom `makemigrations` command (`core_management`) spawns a daemon thread to regenerate `docs/systems/MODEL_MAP.md` after writing migrations.

- Only triggers when migrations are actually written
- Non-blocking: developer sees migration output immediately
- Uses existing `introspect_models.py` logic
- If the process exits before completion, the file updates next time

## Suppression Policy

`# noqa` comments should be **rare exceptions**, not a convenient escape hatch. Only suppress when fixing the violation would cause more harm than good — for example, necessitating a massive and inelegant refactor. Every suppression should include a brief justification comment explaining why.

## Pre-commit Configuration

All four linters run as `pre-commit` stage hooks (same as existing `getattr-literal` and `prefetch-string` hooks). No new hook stages needed.

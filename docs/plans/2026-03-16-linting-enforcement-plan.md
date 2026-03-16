# Linting Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add four pre-commit linters and auto-regenerate MODEL_MAP.md on makemigrations, enforcing project code conventions at commit time.

**Architecture:** AST-based Python scripts in `tools/` following the existing `lint_getattr_literal.py` pattern. Each linter has a `check_file()` function, a visitor class, suppression via `# noqa: TOKEN`, and tests in `src/core_management/tests/`. MODEL_MAP.md regeneration is triggered asynchronously from the custom `makemigrations` command.

**Tech Stack:** Python `ast` module, `pre-commit` hooks, Django management commands, `threading`

**Design doc:** `docs/plans/2026-03-16-linting-enforcement-design.md`

---

### Task 1: Update prefetch linter to require `to_attr`

The existing `tools/lint_prefetch_string.py` catches bare strings in `prefetch_related()` but does not check that `Prefetch()` calls include `to_attr=`. Add this check.

**Files:**
- Modify: `tools/lint_prefetch_string.py`
- Modify: `src/core_management/tests/test_lint_prefetch_string.py` (create — no tests exist yet)

**Step 1: Write failing tests**

Create `src/core_management/tests/test_lint_prefetch_string.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestPrefetchStringLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_prefetch_string.py"
        spec = importlib.util.spec_from_file_location("lint_prefetch_string", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_prefetch_string module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def test_flags_bare_string(self) -> None:
        code = textwrap.dedent('''\
            qs.prefetch_related("tags")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_allows_prefetch_with_to_attr(self) -> None:
        code = textwrap.dedent('''\
            from django.db.models import Prefetch
            qs.prefetch_related(Prefetch("tags", queryset=Tag.objects.all(), to_attr="cached_tags"))
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_flags_prefetch_without_to_attr(self) -> None:
        code = textwrap.dedent('''\
            from django.db.models import Prefetch
            qs.prefetch_related(Prefetch("tags", queryset=Tag.objects.all()))
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_suppression_token(self) -> None:
        code = textwrap.dedent('''\
            qs.prefetch_related("tags")  # noqa: PREFETCH_STRING
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_suppression_on_prefetch_without_to_attr(self) -> None:
        code = textwrap.dedent('''\
            from django.db.models import Prefetch
            qs.prefetch_related(Prefetch("tags", queryset=Tag.objects.all()))  # noqa: PREFETCH_STRING
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])
```

**Step 2: Run tests to verify the new ones fail**

Run: `uv run arx test core_management.tests.test_lint_prefetch_string`
Expected: `test_flags_prefetch_without_to_attr` FAILS (not yet implemented)

**Step 3: Implement the `Prefetch()` without `to_attr` check**

In `tools/lint_prefetch_string.py`, add to the `PrefetchStringVisitor.visit_Call` method:

```python
def _is_prefetch_constructor(self, node: ast.Call) -> bool:
    """Return whether a call node is a Prefetch() constructor."""
    if isinstance(node.func, ast.Name) and node.func.id == "Prefetch":
        return True
    if isinstance(node.func, ast.Attribute) and node.func.attr == "Prefetch":
        return True
    return False

def _has_to_attr(self, node: ast.Call) -> bool:
    """Return whether a Prefetch() call has a to_attr keyword argument."""
    return any(kw.arg == "to_attr" for kw in node.keywords)
```

Update `visit_Call` to also check `Prefetch()` args inside `prefetch_related()`:

```python
def visit_Call(self, node: ast.Call) -> None:
    if is_prefetch_related_call(node):
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                line_index = max(arg.lineno - 1, 0)
                if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                    continue
                self.errors.append((arg.lineno, arg.col_offset, arg.value))
            elif isinstance(arg, ast.Call) and self._is_prefetch_constructor(arg):
                if not self._has_to_attr(arg):
                    line_index = max(arg.lineno - 1, 0)
                    if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                        continue
                    self.errors.append((arg.lineno, arg.col_offset, "Prefetch(missing to_attr)"))
    self.generic_visit(node)
```

**Step 4: Run tests to verify they pass**

Run: `uv run arx test core_management.tests.test_lint_prefetch_string`
Expected: All PASS

**Step 5: Commit**

```bash
git add tools/lint_prefetch_string.py src/core_management/tests/test_lint_prefetch_string.py
git commit -m "feat(lint): require to_attr in Prefetch() calls"
```

---

### Task 2: Create string literal linter

Catches spaceless string literals in returns, comparisons, and match/case patterns.

**Files:**
- Create: `tools/lint_string_literal.py`
- Create: `src/core_management/tests/test_lint_string_literal.py`
- Modify: `.pre-commit-config.yaml` (add hook entry)

**Step 1: Write failing tests**

Create `src/core_management/tests/test_lint_string_literal.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestStringLiteralLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_string_literal.py"
        spec = importlib.util.spec_from_file_location("lint_string_literal", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_string_literal module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    # --- Returns ---

    def test_flags_return_bare_string(self) -> None:
        code = textwrap.dedent('''\
            def get_status():
                return "active"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_allows_return_string_with_spaces(self) -> None:
        code = textwrap.dedent('''\
            def get_message():
                return "hello world"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_empty_string(self) -> None:
        code = textwrap.dedent('''\
            def get_default():
                return ""
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_single_char(self) -> None:
        code = textwrap.dedent('''\
            def get_sep():
                return ","
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_underscore_prefix(self) -> None:
        code = textwrap.dedent('''\
            def get_private():
                return "_internal"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_path_like(self) -> None:
        code = textwrap.dedent('''\
            def get_path():
                return "foo/bar"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_dotted_name(self) -> None:
        code = textwrap.dedent('''\
            def get_module():
                return "world.magic.models"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_with_regex_chars(self) -> None:
        code = textwrap.dedent('''\
            def get_pattern():
                return "foo.*bar"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_return_with_backslash(self) -> None:
        code = textwrap.dedent('''\
            def get_escape():
                return "foo\\nbar"
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    # --- Comparisons ---

    def test_flags_comparison_bare_string(self) -> None:
        code = textwrap.dedent('''\
            def check(x):
                if x == "active":
                    pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_comparison_left_side(self) -> None:
        code = textwrap.dedent('''\
            def check(x):
                if "active" == x:
                    pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_not_equal_comparison(self) -> None:
        code = textwrap.dedent('''\
            def check(x):
                if x != "inactive":
                    pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    # --- Match/case ---

    def test_flags_match_case_string(self) -> None:
        code = textwrap.dedent('''\
            def process(status):
                match status:
                    case "active":
                        pass
                    case "inactive":
                        pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 2)

    # --- Suppression ---

    def test_suppression_token(self) -> None:
        code = textwrap.dedent('''\
            def get_status():
                return "active"  # noqa: STRING_LITERAL
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    # --- Non-string returns should be ignored ---

    def test_allows_return_integer(self) -> None:
        code = textwrap.dedent('''\
            def get_count():
                return 42
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])
```

**Step 2: Run tests to verify they fail**

Run: `uv run arx test core_management.tests.test_lint_string_literal`
Expected: FAIL — module not found

**Step 3: Create the linter**

Create `tools/lint_string_literal.py`:

```python
"""Reject spaceless string literals in returns, comparisons, and match/case.

Use constants (TextChoices, module-level variables) instead of bare strings
for identifiers and enum values.

Use "# noqa: STRING_LITERAL" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

SUPPRESSION_TOKEN = "noqa: string_literal"  # noqa: S105

# Strings matching any of these patterns are not identifiers
_SKIP_RE = re.compile(r"[/\\.^$*+?{}\[\]|()\s]")


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the string literal check."""
    return SUPPRESSION_TOKEN in line.lower()


def is_identifier_string(value: str) -> bool:
    """Return whether a string looks like an identifier that should be a constant.

    Strings that are empty, single-character, start with underscore, contain
    spaces, paths, dotted names, regex metacharacters, or backslashes are
    considered non-identifiers and skipped.
    """
    if not value or len(value) <= 1:
        return False
    if value.startswith("_"):
        return False
    if _SKIP_RE.search(value):
        return False
    return True


class StringLiteralVisitor(ast.NodeVisitor):
    """Visitor that collects identifier-like string literals in returns/comparisons/match."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def _check_constant(self, node: ast.Constant) -> None:
        """Flag a string constant if it looks like an identifier."""
        if not isinstance(node.value, str):
            return
        if not is_identifier_string(node.value):
            return
        line_index = max(node.lineno - 1, 0)
        if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
            return
        self.errors.append((node.lineno, node.col_offset, node.value))

    def visit_Return(self, node: ast.Return) -> None:
        if isinstance(node.value, ast.Constant):
            self._check_constant(node.value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if isinstance(node.left, ast.Constant):
            self._check_constant(node.left)
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant):
                self._check_constant(comparator)
        self.generic_visit(node)

    def visit_MatchValue(self, node: ast.MatchValue) -> None:
        if isinstance(node.value, ast.Constant):
            self._check_constant(node.value)
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return errors for identifier-like string literals in a file."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: STRING_LITERAL could not read file: {exc}")
        return [(0, 0, "")]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: STRING_LITERAL syntax error: {exc.msg}")
        return [(lineno, offset, "")]

    lines = contents.splitlines()
    visitor = StringLiteralVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the string literal check."""
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        errors = check_file(path)
        for line, col, value in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: STRING_LITERAL "
                f'Use a constant instead of "{value}". '
                f"Add # noqa: STRING_LITERAL to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

**Step 4: Run tests to verify they pass**

Run: `uv run arx test core_management.tests.test_lint_string_literal`
Expected: All PASS

**Step 5: Add pre-commit hook entry**

Add to `.pre-commit-config.yaml` after the `prefetch-string` hook:

```yaml
      - id: string-literal
        name: Block bare string literals as identifiers
        entry: uv run python tools/lint_string_literal.py
        language: system
        pass_filenames: true
        types: [python]
```

**Step 6: Commit**

```bash
git add tools/lint_string_literal.py src/core_management/tests/test_lint_string_literal.py .pre-commit-config.yaml
git commit -m "feat(lint): add string literal linter for returns, comparisons, match/case"
```

---

### Task 3: Create SharedMemoryModel linter

Catches concrete Django models inheriting from `models.Model` instead of `SharedMemoryModel`.

**Files:**
- Create: `tools/lint_shared_memory.py`
- Create: `src/core_management/tests/test_lint_shared_memory.py`
- Modify: `.pre-commit-config.yaml`

**Step 1: Write failing tests**

Create `src/core_management/tests/test_lint_shared_memory.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestSharedMemoryLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_shared_memory.py"
        spec = importlib.util.spec_from_file_location("lint_shared_memory", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_shared_memory module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def test_flags_models_model(self) -> None:
        code = textwrap.dedent('''\
            from django.db import models
            class MyModel(models.Model):
                name = models.CharField(max_length=100)
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_bare_model(self) -> None:
        code = textwrap.dedent('''\
            from django.db.models import Model
            class MyModel(Model):
                pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_allows_shared_memory_model(self) -> None:
        code = textwrap.dedent('''\
            from evennia.utils.idmapper.models import SharedMemoryModel
            class MyModel(SharedMemoryModel):
                name = models.CharField(max_length=100)
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_abstract_model(self) -> None:
        code = textwrap.dedent('''\
            from django.db import models
            class MyAbstract(models.Model):
                class Meta:
                    abstract = True
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_suppression_token(self) -> None:
        code = textwrap.dedent('''\
            from django.db import models
            class MyModel(models.Model):  # noqa: SHARED_MEMORY
                name = models.CharField(max_length=100)
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_skips_migration_files(self) -> None:
        code = textwrap.dedent('''\
            from django.db import models
            class Migration(models.Model):
                pass
        ''')
        with TemporaryDirectory() as td:
            migrations_dir = Path(td) / "migrations"
            migrations_dir.mkdir()
            p = migrations_dir / "0001_initial.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_skips_test_files(self) -> None:
        code = textwrap.dedent('''\
            from django.db import models
            class FakeModel(models.Model):
                pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "test_something.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_allows_other_base_class(self) -> None:
        """Classes with non-Model bases are not flagged (can't resolve inheritance chain)."""
        code = textwrap.dedent('''\
            class MyModel(SomeOtherBase):
                pass
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])
```

**Step 2: Run tests to verify they fail**

Run: `uv run arx test core_management.tests.test_lint_shared_memory`
Expected: FAIL — module not found

**Step 3: Create the linter**

Create `tools/lint_shared_memory.py`:

```python
"""Reject concrete Django models that don't use SharedMemoryModel.

All concrete models should use SharedMemoryModel for identity-map caching.
Both lookup tables and per-instance data benefit: modified instances stay
current in cache without re-querying.

Use "# noqa: SHARED_MEMORY" to suppress a specific instance (with justification).
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: shared_memory"  # noqa: S105

# Base class patterns that indicate models.Model usage
_MODEL_BASES = {"models.Model", "Model"}


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the shared memory check."""
    return SUPPRESSION_TOKEN in line.lower()


def _get_base_name(node: ast.expr) -> str:
    """Extract a dotted name string from an AST base class node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""


def _is_abstract(class_node: ast.ClassDef) -> bool:
    """Return whether a class has abstract = True in its Meta class."""
    for item in class_node.body:
        if isinstance(item, ast.ClassDef) and item.name == "Meta":
            for meta_item in item.body:
                if isinstance(meta_item, ast.Assign):
                    for target in meta_item.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "abstract"
                            and isinstance(meta_item.value, ast.Constant)
                            and meta_item.value.value is True
                        ):
                            return True
    return False


def _should_skip_file(path: Path) -> bool:
    """Return whether this file should be skipped entirely."""
    name = path.name
    # Skip migration files
    if "migrations" in path.parts:
        return True
    # Skip test files
    if name.startswith("test_") or name.startswith("tests"):
        return True
    return False


class SharedMemoryVisitor(ast.NodeVisitor):
    """Visitor that flags concrete model classes not using SharedMemoryModel."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = [_get_base_name(b) for b in node.bases]

        # Only flag classes that directly inherit from models.Model or Model
        has_model_base = any(name in _MODEL_BASES for name in base_names)

        if has_model_base and not _is_abstract(node):
            line_index = max(node.lineno - 1, 0)
            if not (line_index < len(self.lines) and has_suppression(self.lines[line_index])):
                self.errors.append((node.lineno, node.col_offset, node.name))

        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return errors for concrete models not using SharedMemoryModel."""
    if _should_skip_file(path):
        return []

    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: SHARED_MEMORY could not read file: {exc}")
        return [(0, 0, "")]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: SHARED_MEMORY syntax error: {exc.msg}")
        return [(lineno, offset, "")]

    lines = contents.splitlines()
    visitor = SharedMemoryVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the SharedMemoryModel check."""
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        errors = check_file(path)
        for line, col, class_name in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: SHARED_MEMORY "
                f"class {class_name} should use SharedMemoryModel instead of models.Model. "
                f"Add # noqa: SHARED_MEMORY with justification to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

**Step 4: Run tests to verify they pass**

Run: `uv run arx test core_management.tests.test_lint_shared_memory`
Expected: All PASS

**Step 5: Add pre-commit hook entry**

Add to `.pre-commit-config.yaml` after the `string-literal` hook:

```yaml
      - id: shared-memory
        name: Enforce SharedMemoryModel for concrete models
        entry: uv run python tools/lint_shared_memory.py
        language: system
        pass_filenames: true
        types: [python]
```

**Step 6: Commit**

```bash
git add tools/lint_shared_memory.py src/core_management/tests/test_lint_shared_memory.py .pre-commit-config.yaml
git commit -m "feat(lint): add SharedMemoryModel enforcement linter"
```

---

### Task 4: Create filterset linter

Catches `query_params` and `request.GET` access inside ViewSet/View classes.

**Files:**
- Create: `tools/lint_use_filterset.py`
- Create: `src/core_management/tests/test_lint_use_filterset.py`
- Modify: `.pre-commit-config.yaml`

**Step 1: Write failing tests**

Create `src/core_management/tests/test_lint_use_filterset.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestUseFiltersetLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_use_filterset.py"
        spec = importlib.util.spec_from_file_location("lint_use_filterset", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_use_filterset module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def test_flags_query_params_get_in_viewset(self) -> None:
        code = textwrap.dedent('''\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    val = request.query_params.get("status")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_query_params_bracket_in_viewset(self) -> None:
        code = textwrap.dedent('''\
            class MyViewSet(ViewSet):
                def list(self, request):
                    val = request.query_params["status"]
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_request_get_in_view(self) -> None:
        code = textwrap.dedent('''\
            class MyView(APIView):
                def get(self, request):
                    val = request.GET.get("page")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_request_get_bracket_in_view(self) -> None:
        code = textwrap.dedent('''\
            class MyView(APIView):
                def get(self, request):
                    val = request.GET["page"]
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_flags_self_request_query_params(self) -> None:
        code = textwrap.dedent('''\
            class MyViewSet(ModelViewSet):
                def get_queryset(self):
                    val = self.request.query_params.get("status")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(len(errors), 1)

    def test_allows_query_params_outside_view(self) -> None:
        code = textwrap.dedent('''\
            class MyService:
                def process(self, request):
                    val = request.query_params.get("status")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_suppression_token(self) -> None:
        code = textwrap.dedent('''\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    val = request.query_params.get("status")  # noqa: USE_FILTERSET
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "sample.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])

    def test_skips_test_files(self) -> None:
        code = textwrap.dedent('''\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    val = request.query_params.get("status")
        ''')
        with TemporaryDirectory() as td:
            p = Path(td) / "test_views.py"
            p.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(p)
        self.assertEqual(errors, [])
```

**Step 2: Run tests to verify they fail**

Run: `uv run arx test core_management.tests.test_lint_use_filterset`
Expected: FAIL — module not found

**Step 3: Create the linter**

Create `tools/lint_use_filterset.py`:

```python
"""Reject query_params/GET access inside ViewSet and View classes.

Use django-filter FilterSet classes instead of parsing query parameters
manually in views.

Use "# noqa: USE_FILTERSET" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: use_filterset"  # noqa: S105

# Base class name fragments that indicate a ViewSet or View
_VIEW_BASES = {"ViewSet", "View", "APIView"}


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the filterset check."""
    return SUPPRESSION_TOKEN in line.lower()


def _get_base_name(node: ast.expr) -> str:
    """Extract a simple name from a base class node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_view_class(class_node: ast.ClassDef) -> bool:
    """Return whether a class appears to be a DRF ViewSet or Django View."""
    for base in class_node.bases:
        name = _get_base_name(base)
        if any(view_base in name for view_base in _VIEW_BASES):
            return True
    return False


def _should_skip_file(path: Path) -> bool:
    """Return whether this file should be skipped entirely."""
    name = path.name
    if name.startswith("test_") or name.startswith("tests"):
        return True
    return False


def _is_query_params_access(node: ast.AST) -> bool:
    """Return whether the node accesses query_params or GET on a request.

    Matches patterns:
    - request.query_params.get(...)
    - request.query_params[...]
    - self.request.query_params.get(...)
    - self.request.query_params[...]
    - request.GET.get(...)
    - request.GET[...]
    - self.request.GET.get(...)
    - self.request.GET[...]
    """
    # .get() calls: request.query_params.get(...) or request.GET.get(...)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "get":
            obj = node.func.value
            if isinstance(obj, ast.Attribute) and obj.attr in ("query_params", "GET"):
                return True

    # Subscript access: request.query_params["key"] or request.GET["key"]
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
        if node.value.attr in ("query_params", "GET"):
            return True

    return False


class FiltersetVisitor(ast.NodeVisitor):
    """Visitor that flags query_params/GET access inside ViewSet/View classes."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int]] = []
        self._in_view_class = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        was_in_view = self._in_view_class
        if _is_view_class(node):
            self._in_view_class = True
        self.generic_visit(node)
        self._in_view_class = was_in_view

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_view_class and _is_query_params_access(node):
            line_index = max(node.lineno - 1, 0)
            if not (line_index < len(self.lines) and has_suppression(self.lines[line_index])):
                self.errors.append((node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self._in_view_class and _is_query_params_access(node):
            line_index = max(node.lineno - 1, 0)
            if not (line_index < len(self.lines) and has_suppression(self.lines[line_index])):
                self.errors.append((node.lineno, node.col_offset))
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return errors for query param access inside view classes."""
    if _should_skip_file(path):
        return []

    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: USE_FILTERSET could not read file: {exc}")
        return [(0, 0)]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: USE_FILTERSET syntax error: {exc.msg}")
        return [(lineno, offset)]

    lines = contents.splitlines()
    visitor = FiltersetVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the filterset usage check."""
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        errors = check_file(path)
        for line, col in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: USE_FILTERSET "
                "Use a FilterSet class instead of accessing query_params/GET directly. "
                "Add # noqa: USE_FILTERSET to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

**Step 4: Run tests to verify they pass**

Run: `uv run arx test core_management.tests.test_lint_use_filterset`
Expected: All PASS

**Step 5: Add pre-commit hook entry**

Add to `.pre-commit-config.yaml` after the `shared-memory` hook:

```yaml
      - id: use-filterset
        name: Enforce FilterSet over query_params in views
        entry: uv run python tools/lint_use_filterset.py
        language: system
        pass_filenames: true
        types: [python]
```

**Step 6: Commit**

```bash
git add tools/lint_use_filterset.py src/core_management/tests/test_lint_use_filterset.py .pre-commit-config.yaml
git commit -m "feat(lint): add filterset enforcement linter for ViewSets"
```

---

### Task 5: Auto-regenerate MODEL_MAP.md from makemigrations

Modify the custom `makemigrations` command to spawn a daemon thread that regenerates `docs/systems/MODEL_MAP.md` after writing migrations.

**Files:**
- Modify: `src/core_management/management/commands/makemigrations.py`
- Modify: `tools/introspect_models.py` (extract a callable function from the script-level code)

**Step 1: Refactor `introspect_models.py` to expose a callable**

The current script runs its logic at module level. Extract the main loop into a `generate_model_map()` function that returns the content as a string, and a `write_model_map()` function that writes to the file. Keep the `if __name__ == "__main__"` block for standalone usage.

At the bottom of `tools/introspect_models.py`, replace the module-level `print` calls:

```python
def generate_model_map() -> str:
    """Generate the full MODEL_MAP.md content as a string."""
    parts = ["# Arx II Model Introspection Report", "# Generated for CLAUDE.md enrichment\n"]
    for app_label in sorted(TARGET_APPS):
        data = introspect_app(app_label)
        if data and (data["models"] or data["service_functions"]):
            parts.append(format_output(data))
    return "\n".join(parts)


def write_model_map() -> None:
    """Regenerate docs/systems/MODEL_MAP.md."""
    project_root = Path(__file__).resolve().parent.parent
    output_path = project_root / "docs" / "systems" / "MODEL_MAP.md"
    content = generate_model_map()
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    print(generate_model_map())
```

**Step 2: Add async regeneration to makemigrations**

In `src/core_management/management/commands/makemigrations.py`, at the end of `write_migration_files()`, after calling `super()`:

```python
import threading

# ... inside write_migration_files(), after the super() call:

        result = super().write_migration_files(
            filtered_changes,
            update_previous_migration_paths,
        )

        if filtered_changes:
            threading.Thread(target=self._regenerate_model_map, daemon=True).start()

        return result

    @staticmethod
    def _regenerate_model_map() -> None:
        """Regenerate MODEL_MAP.md in a background thread."""
        try:
            from tools.introspect_models import write_model_map
            write_model_map()
        except Exception:
            # Silent failure — non-critical background task
            pass
```

Note: Since `tools/` is not on `sys.path` by default inside Django, the import needs the path resolved. Update the static method to handle this:

```python
    @staticmethod
    def _regenerate_model_map() -> None:
        """Regenerate MODEL_MAP.md in a background thread."""
        try:
            import importlib.util
            from pathlib import Path

            tools_dir = Path(__file__).resolve().parents[4] / "tools"
            spec = importlib.util.spec_from_file_location(
                "introspect_models", tools_dir / "introspect_models.py"
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.write_model_map()
        except Exception:
            pass  # Silent failure — non-critical background task
```

**Step 3: Run tests to verify nothing broke**

Run: `uv run arx test core_management`
Expected: All PASS

**Step 4: Commit**

```bash
git add tools/introspect_models.py src/core_management/management/commands/makemigrations.py
git commit -m "feat: auto-regenerate MODEL_MAP.md asynchronously from makemigrations"
```

---

### Task 6: Annotate existing violations with `# noqa` comments

The new linters will flag existing code. Before they can be enforced, annotate justified existing violations. Run each linter against the full codebase and add suppression comments where the fix would cause more harm than good.

**Files:**
- Various existing files across `src/`

**Step 1: Run the SharedMemoryModel linter and annotate**

Run: `uv run python tools/lint_shared_memory.py $(find src -name "*.py" -not -path "*/migrations/*" -not -path "*/test*")`

For each flagged class, decide:
- Can it be changed to SharedMemoryModel? → Change it (preferred)
- Would changing it require a massive refactor? → Add `# noqa: SHARED_MEMORY — <reason>`

Known cases that need `# noqa`:
- Models in `core/natural_keys.py` — these are docstring examples, not real models
- Through-table models created by Django may need suppression

**Step 2: Run the string literal linter and annotate**

Run: `uv run python tools/lint_string_literal.py $(find src -name "*.py")`

For each flagged literal, decide:
- Can it be replaced with a constant? → Replace it
- Is it a legitimate use? → Add `# noqa: STRING_LITERAL`

**Step 3: Run the filterset linter and annotate**

Run: `uv run python tools/lint_use_filterset.py $(find src -name "*.py" -not -path "*/test*")`

For each flagged view:
- Can it use a FilterSet? → Convert it (preferred, but may be a separate PR)
- Is suppression needed for now? → Add `# noqa: USE_FILTERSET — will convert to FilterSet`

**Step 4: Run the prefetch linter and annotate**

Run: `uv run python tools/lint_prefetch_string.py $(find src -name "*.py")`

For each flagged prefetch, add `# noqa: PREFETCH_STRING` or convert to `Prefetch()` with `to_attr`.

**Step 5: Run pre-commit to verify everything passes**

Run: `pre-commit run --all-files`
Expected: All hooks pass

**Step 6: Commit**

```bash
git add -u
git commit -m "chore: annotate existing lint violations with noqa comments"
```

---

### Task 7: Update CLAUDE.md with suppression policy

Add guidance about `# noqa` comments and the new linting rules to `CLAUDE.md`.

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add to the Code Quality Standards section**

Add after the existing code quality bullet points:

```markdown
- **`# noqa` Suppression Policy**: `# noqa` comments for our custom linters should be rare exceptions, not a convenient escape hatch. Only suppress when fixing the violation would cause more harm than good — for example, necessitating a massive and inelegant refactor. Every suppression MUST include a brief justification comment explaining why (e.g., `# noqa: SHARED_MEMORY — abstract mixin used by multiple apps`). Custom linter tokens: `PREFETCH_STRING`, `STRING_LITERAL`, `SHARED_MEMORY`, `USE_FILTERSET`, `GETATTR_LITERAL`
- **SharedMemoryModel Default**: All concrete Django models should use `SharedMemoryModel`. Both lookup tables and per-instance data benefit from the identity-map cache. Only suppress with `# noqa: SHARED_MEMORY` and a justification
- **Prefetch with to_attr**: Always use `Prefetch()` objects with `to_attr=` in `prefetch_related()`. Never use bare strings. The `to_attr` should point to a `cached_property` on the model for cache-safe access
- **Constants over String Literals**: Never return spaceless string literals or compare against them. Use `TextChoices`, `IntegerChoices`, or module-level constants. This prevents typo bugs and makes refactoring safe
- **FilterSets in Views**: Always use `django-filter` FilterSet classes for query parameter handling in ViewSets and Views. Never access `request.query_params` or `request.GET` directly
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add noqa suppression policy and new lint rules to CLAUDE.md"
```

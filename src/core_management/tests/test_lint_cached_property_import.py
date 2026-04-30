from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestCachedPropertyImportLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_cached_property_import.py"
        spec = importlib.util.spec_from_file_location("lint_cached_property_import", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_cached_property_import module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def _check(self, code: str) -> list[tuple[int, str]]:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            return self.lint_module.check_file(path)

    def test_flags_bare_functools_import(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import cached_property
            """
        )
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_aliased_functools_import(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import cached_property as cp
            """
        )
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_multi_name_import(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import cached_property, lru_cache
            """
        )
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_allows_django_import(self) -> None:
        code = textwrap.dedent(
            """\
            from django.utils.functional import cached_property
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_allows_aliased_django_import(self) -> None:
        code = textwrap.dedent(
            """\
            from django.utils.functional import cached_property as cp
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_allows_unrelated_functools_import(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import lru_cache
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_suppression_token(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import cached_property  # noqa: CACHED_PROPERTY_IMPORT
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_suppression_token_case_insensitive(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import cached_property as cp  # noqa: cached_property_import
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_empty_file(self) -> None:
        errors = self._check("")
        self.assertEqual(errors, [])

    def test_suppression_on_multiline_import(self) -> None:
        code = textwrap.dedent(
            """\
            from functools import (
                cached_property as functools_cached_property,  # noqa: CACHED_PROPERTY_IMPORT
            )
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_attribute_access_violation(self) -> None:
        """Catch `functools.cached_property` used via `import functools`."""
        code = textwrap.dedent(
            """\
            import functools


            class Foo:
                @functools.cached_property
                def x(self):
                    return 1
            """
        )
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_attribute_access_suppression(self) -> None:
        """Suppression token on the attribute-access line is honored."""
        code = textwrap.dedent(
            """\
            import functools


            class Foo:
                @functools.cached_property  # noqa: CACHED_PROPERTY_IMPORT
                def x(self):
                    return 1
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_unrelated_functools_attribute_access(self) -> None:
        """Other functools attributes (e.g., lru_cache) are not flagged."""
        code = textwrap.dedent(
            """\
            import functools


            @functools.lru_cache
            def x():
                return 1
            """
        )
        errors = self._check(code)
        self.assertEqual(errors, [])

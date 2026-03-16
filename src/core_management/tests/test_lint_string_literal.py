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

    def _check(self, code: str) -> list[tuple[int, int]]:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(textwrap.dedent(code), encoding="utf-8")
            return self.lint_module.check_file(path)

    # --- Returns ---

    def test_flags_return_bare_string(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "active"
            """
        )
        self.assertEqual(len(errors), 1)

    def test_allows_return_string_with_spaces(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "hello world"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_empty_string(self) -> None:
        errors = self._check(
            """\
            def demo():
                return ""
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_single_char(self) -> None:
        errors = self._check(
            """\
            def demo():
                return ","
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_underscore_prefix(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "_internal"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_path_like(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "foo/bar"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_dotted_name(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "world.magic.models"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_with_regex_chars(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "foo.*bar"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_with_backslash(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "foo\\nbar"
            """
        )
        self.assertEqual(errors, [])

    def test_allows_return_integer(self) -> None:
        errors = self._check(
            """\
            def demo():
                return 42
            """
        )
        self.assertEqual(errors, [])

    # --- Comparisons ---

    def test_flags_comparison_bare_string(self) -> None:
        errors = self._check(
            """\
            def demo(x):
                if x == "active":
                    pass
            """
        )
        self.assertEqual(len(errors), 1)

    def test_flags_comparison_left_side(self) -> None:
        errors = self._check(
            """\
            def demo(x):
                if "active" == x:
                    pass
            """
        )
        self.assertEqual(len(errors), 1)

    def test_flags_not_equal_comparison(self) -> None:
        errors = self._check(
            """\
            def demo(x):
                if x != "inactive":
                    pass
            """
        )
        self.assertEqual(len(errors), 1)

    # --- Match/case ---

    def test_flags_match_case_string(self) -> None:
        errors = self._check(
            """\
            def demo(x):
                match x:
                    case "active":
                        pass
                    case "inactive":
                        pass
            """
        )
        self.assertEqual(len(errors), 2)

    # --- Suppression ---

    def test_suppression_token(self) -> None:
        errors = self._check(
            """\
            def demo():
                return "active"  # noqa: STRING_LITERAL
            """
        )
        self.assertEqual(errors, [])

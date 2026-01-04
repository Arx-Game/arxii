from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestGetattrLiteralLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_getattr_literal.py"
        spec = importlib.util.spec_from_file_location("lint_getattr_literal", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_getattr_literal module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def test_flags_literal_getattr_with_default(self) -> None:
        code = textwrap.dedent(
            """\
            def demo(obj):
                return getattr(obj, "is_staff", False)
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(len(errors), 1)

    def test_allows_non_literal_getattr(self) -> None:
        code = textwrap.dedent(
            """\
            def demo(obj, attr_name):
                return getattr(obj, attr_name, None)
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_suppression_token_ignores_literal(self) -> None:
        code = textwrap.dedent(
            """\
            def demo(obj):
                return getattr(obj, "is_staff", False)  # noqa: GETATTR_LITERAL
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

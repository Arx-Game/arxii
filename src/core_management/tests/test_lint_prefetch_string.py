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
        code = textwrap.dedent(
            """\
            qs.prefetch_related("tags")
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(len(errors), 1)

    def test_allows_prefetch_with_to_attr(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db.models import Prefetch
            qs.prefetch_related(Prefetch("tags", queryset=Tag.objects.all(), to_attr="cached_tags"))
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_flags_prefetch_without_to_attr(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db.models import Prefetch
            qs.prefetch_related(Prefetch("tags", queryset=Tag.objects.all()))
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(len(errors), 1)

    def test_suppression_token(self) -> None:
        code = textwrap.dedent(
            """\
            qs.prefetch_related("tags")  # noqa: PREFETCH_STRING
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_suppression_on_prefetch_without_to_attr(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db.models import Prefetch
            qs.prefetch_related(
                Prefetch("tags", queryset=Tag.objects.all())  # noqa: PREFETCH_STRING
            )
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

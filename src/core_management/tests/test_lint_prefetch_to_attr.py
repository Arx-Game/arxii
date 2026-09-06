"""The to_attr prefetch linter (#3673, ADR-0263)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import textwrap

from django.test import SimpleTestCase


class TestPrefetchToAttrLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_prefetch_to_attr.py"
        spec = importlib.util.spec_from_file_location("lint_prefetch_to_attr", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_prefetch_to_attr module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint = module

    def test_flags_a_to_attr_prefetch(self) -> None:
        code = textwrap.dedent(
            """\
            qs.prefetch_related(Prefetch("slots", queryset=S.objects.all(), to_attr="cached"))
            """
        )
        assert self.lint.check_source(code) == [(1, 72)]

    def test_flags_a_dotted_prefetch_import(self) -> None:
        code = textwrap.dedent(
            """\
            qs.prefetch_related(models.Prefetch("slots", to_attr="cached"))
            """
        )
        assert len(self.lint.check_source(code)) == 1

    def test_suppression_on_the_keyword_line(self) -> None:
        code = textwrap.dedent(
            """\
            qs.prefetch_related(
                Prefetch(
                    "slots",
                    to_attr="cached",  # noqa: PREFETCH_TO_ATTR - handler lands in #9999
                )
            )
            """
        )
        assert self.lint.check_source(code) == []

    def test_suppression_on_the_line_opening_the_call(self) -> None:
        """Where a reader looks first when the keyword is several lines down."""
        code = textwrap.dedent(
            """\
            qs.prefetch_related(
                Prefetch(  # noqa: PREFETCH_TO_ATTR - handler lands in #9999
                    "slots",
                    queryset=S.objects.all(),
                    to_attr="cached",
                )
            )
            """
        )
        assert self.lint.check_source(code) == []

    def test_a_prefetch_without_to_attr_is_fine(self) -> None:
        """This linter has one job; bare strings are PREFETCH_STRING's."""
        code = textwrap.dedent(
            """\
            qs.prefetch_related(Prefetch("slots", queryset=S.objects.all()))
            """
        )
        assert self.lint.check_source(code) == []

    def test_an_unrelated_to_attr_keyword_is_not_flagged(self) -> None:
        code = textwrap.dedent(
            """\
            render(to_attr="cached")
            """
        )
        assert self.lint.check_source(code) == []

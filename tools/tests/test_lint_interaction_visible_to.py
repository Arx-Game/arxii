"""Tests for tools/lint_interaction_visible_to.py (#3751).

These stay as unit tests: a linter's branches are not reachable from a journey.
"""

from __future__ import annotations

from pathlib import Path

from lint_interaction_visible_to import check_file, check_source


def test_a_bare_visible_to_call_is_flagged() -> None:
    source = "rows = Interaction.objects.visible_to(user).filter(pk=1)\n"
    assert check_source(source) == [(1, 7)]


def test_readable_by_is_clean() -> None:
    assert check_source("rows = Interaction.objects.readable_by(user)\n") == []


def test_a_noqa_on_the_call_line_suppresses_it() -> None:
    source = "rows = Interaction.objects.visible_to(user)  # noqa: VISIBLE_TO staff tool\n"
    assert check_source(source) == []


def test_the_queryset_module_is_exempt(tmp_path: Path) -> None:
    owner = tmp_path / "world" / "scenes" / "managers.py"
    owner.parent.mkdir(parents=True)
    owner.write_text("q = self.visible_to(account)\n")
    assert check_file(owner) == []

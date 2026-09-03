"""The view-memo linter flags None-defaulted private class attributes on views and
serializers, and honours its suppression."""

from lint_view_memo import check_source


def test_optional_none_default_on_a_class_is_flagged():
    source = (
        "class CovenantViewSet(viewsets.ReadOnlyModelViewSet):\n"
        "    _page_aggregates: dict[int, int] | None = None\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(2, "_page_aggregates")]


def test_typing_optional_spelling_is_flagged():
    source = "class Mixin:\n    _knowledge_map: Optional[dict] = None\n"
    assert [(line, name) for line, _, name in check_source(source)] == [(2, "_knowledge_map")]


def test_unannotated_none_default_is_flagged():
    source = "class Mixin:\n    _selected = None\n"
    assert [(line, name) for line, _, name in check_source(source)] == [(2, "_selected")]


def test_public_attribute_is_not_flagged():
    assert check_source("class V:\n    pagination_class = None\n") == []


def test_non_none_default_is_not_flagged():
    assert check_source("class V:\n    _fields: tuple[str, ...] = ()\n") == []


def test_module_level_none_is_not_flagged():
    assert check_source("_registry: dict | None = None\n") == []


def test_suppressed_line_passes():
    source = "class V:\n    _memo: int | None = None  # noqa: VIEW_MEMO - reason\n"
    assert check_source(source) == []


def test_nested_function_assignment_is_not_flagged():
    source = "class V:\n    def f(self):\n        _x: int | None = None\n        return _x\n"
    assert check_source(source) == []

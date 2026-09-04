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


def test_lazy_self_attribute_on_a_viewset_is_flagged():
    source = (
        "class OptionViewSet(viewsets.ReadOnlyModelViewSet):\n"
        "    def _resolve(self):\n"
        "        if hasattr(self, '_options'):\n"
        "            return self._options\n"
        "        self._options = compute()\n"
        "        return self._options\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [
        (3, "hasattr(self, ...)"),
        (5, "_options"),
    ]


def test_lazy_self_attribute_on_a_serializer_is_flagged():
    source = (
        "class ThingSerializer(serializers.ModelSerializer):\n"
        "    def get_flag(self, obj):\n"
        "        self._cache = resolve()\n"
        "        return self._cache\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(3, "_cache")]


def test_setattr_on_self_is_flagged():
    source = (
        "class ThingSerializer(serializers.Serializer):\n"
        "    def get_flag(self, obj):\n"
        "        setattr(self, '_cache', {})\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(3, "setattr(self, ...)")]


def test_assignment_in_init_is_not_flagged():
    source = (
        "class ThingSerializer(serializers.Serializer):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        self._configured = kwargs.pop('configured')\n"
        "        super().__init__(*args, **kwargs)\n"
    )
    assert check_source(source) == []


def test_public_self_attribute_is_not_flagged():
    source = (
        "class ThingViewSet(viewsets.GenericViewSet):\n"
        "    def list(self, request):\n"
        "        self.paginator.page = 1\n"
    )
    assert check_source(source) == []


def test_lazy_self_attribute_outside_a_view_or_serializer_is_not_flagged():
    source = (
        "class SummaryTests(TestCase):\n"
        "    def setUp(self):\n"
        "        self._factory = APIRequestFactory()\n"
    )
    assert check_source(source) == []


def test_suppressed_lazy_attribute_passes():
    source = (
        "class ThingSerializer(serializers.Serializer):\n"
        "    def get_flag(self, obj):\n"
        "        self._cache = resolve()  # noqa: VIEW_MEMO - reason\n"
    )
    assert check_source(source) == []

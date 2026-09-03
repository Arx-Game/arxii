"""The ``.only``/``.defer`` linter flags narrowing querysets and honours its suppression."""

from lint_only_defer import check_source


def test_only_is_flagged():
    errors = check_source('rows = Grant.objects.only("beginnings_id", "entry_id")\n')
    assert [(line, method) for line, _, method in errors] == [(1, "only")]


def test_defer_is_flagged_inside_a_prefetch():
    source = (
        "Prefetch(\n"
        '    "codex_grants",\n'
        '    queryset=Grant.objects.filter(active=True).defer("notes"),\n'
        ")\n"
    )
    errors = check_source(source)
    assert [(line, method) for line, _, method in errors] == [(3, "defer")]


def test_suppressed_line_passes():
    source = (
        'rows = ThirdParty.objects.only("pk")  # noqa: IDMAPPER_ONLY - not a SharedMemoryModel\n'
    )
    assert check_source(source) == []


def test_values_list_passes():
    assert check_source('ids = Grant.objects.values_list("pk", flat=True)\n') == []


def test_attribute_named_only_without_a_call_passes():
    assert check_source("flag = settings.only\n") == []

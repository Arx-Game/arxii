"""The shadow linter flags a ``Prefetch`` whose ``to_attr`` repeats its own relation (#4418)."""

from lint_prefetch_to_attr_shadow import check_source


def test_to_attr_equal_to_relation_fails():
    source = 'Prefetch("trait_lines", queryset=Q, to_attr="trait_lines")\n'
    assert len(check_source(source)) == 1


def test_to_attr_equal_to_last_path_segment_fails():
    source = 'Prefetch("preset__trait_lines", to_attr="trait_lines")\n'
    assert len(check_source(source)) == 1


def test_distinct_to_attr_passes():
    source = 'Prefetch("trait_lines", queryset=Q, to_attr="cached_trait_lines")\n'
    assert check_source(source) == []


def test_to_attr_equal_to_earlier_segment_passes():
    source = 'Prefetch("trait_lines__trait", to_attr="trait_lines")\n'
    assert check_source(source) == []


def test_suppression_on_the_call_line_passes():
    source = 'Prefetch("x", to_attr="x")  # noqa: PREFETCH_SHADOW rename lands in the next PR\n'
    assert check_source(source) == []

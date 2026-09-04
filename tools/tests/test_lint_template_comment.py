"""The template-comment linter flags multi-line ``{# ... #}``, which Django renders
as literal page text, and honours its suppression."""

from lint_template_comment import check_source


def test_multi_line_comment_is_flagged():
    source = "<h2>\n  {# A real button rather than role=button:\n     the heading. #}\n</h2>\n"
    assert [line for line, _ in check_source(source)] == [2]


def test_single_line_comment_is_not_flagged():
    assert check_source("{# a fine comment #}\n") == []


def test_two_single_line_comments_on_one_line_are_not_flagged():
    assert check_source("{# one #} <p>x</p> {# two #}\n") == []


def test_second_comment_on_a_line_can_be_unterminated():
    assert [line for line, _ in check_source("{# one #} {# two\n   three #}\n")] == [1]


def test_comment_tag_block_is_not_flagged():
    source = "{% comment %}\n  Spanning several\n  lines is fine here.\n{% endcomment %}\n"
    assert check_source(source) == []


def test_suppressed_line_passes():
    source = "{# spans lines  noqa: TEMPLATE_COMMENT - reason\n   still going #}\n"
    assert check_source(source) == []


def test_plain_template_is_not_flagged():
    assert check_source("<div>{{ group.grouper }}</div>\n{% if x %}y{% endif %}\n") == []

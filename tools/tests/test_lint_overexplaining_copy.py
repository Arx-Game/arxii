"""The over-explaining copy linter flags visibility captions in user-visible text and
leaves comments, imports and suppressed lines alone."""

from lint_overexplaining_copy import check_source


def test_a_caption_in_jsx_text_is_flagged():
    source = "<p>\n  Staff view: every entry is shown to staff.\n</p>\n"
    assert list(check_source(source)) == [(2, "shown to")]


def test_a_caption_in_a_prop_string_is_flagged():
    source = '<Band title="Abilities" note="Only you and staff read these." />\n'
    assert list(check_source(source)) == [(1, "Only you")]


def test_a_teaching_empty_state_is_flagged():
    source = "<p>No messages yet. Messages from your GM will appear here.</p>\n"
    assert list(check_source(source)) == [(1, "will appear here")]


def test_a_line_comment_is_not_flagged():
    source = "const x = 1; // only you see this in dev\n"
    assert list(check_source(source)) == []


def test_a_block_comment_keeps_line_numbers_and_is_not_flagged():
    source = "/* visible to\n   nobody else */\n<p>Only you may read it.</p>\n"
    assert list(check_source(source)) == [(3, "Only you")]


def test_a_jsx_comment_is_not_flagged():
    source = "<div>\n  {/* shown to the owner only */}\n</div>\n"
    assert list(check_source(source)) == []


def test_a_presence_fact_is_not_flagged():
    assert list(check_source("<p>Nobody else here.</p>\n")) == []
    assert list(check_source("<p>No one else is present to overhear.</p>\n")) == []


def test_a_presence_caption_is_flagged():
    assert list(check_source("<p>Nobody else can read this.</p>\n")) == [(1, "Nobody else can")]


def test_an_identifier_with_underscores_is_not_flagged():
    source = "const visible_to_tenures = form.visible_to_tenures;\n"
    assert list(check_source(source)) == []


def test_an_import_line_is_not_flagged():
    source = "import { visibleTo } from './not shown to';\n"
    assert list(check_source(source)) == []


def test_a_suppressed_line_passes():
    source = (
        "<p>\n"
        "  {/* noqa: OVEREXPLAIN - a security disclosure the account page owes */}\n"
        "  Your email is never shown to other players.\n"
        "</p>\n"
    )
    assert list(check_source(source)) == []

"""Unit tests for the MUSH %r/%t telnet-input converter."""

from django.test import SimpleTestCase

from server.conf.mush_markup import normalize_mush_markup


class NormalizeMushMarkupTests(SimpleTestCase):
    def test_percent_r_becomes_newline(self) -> None:
        self.assertEqual(normalize_mush_markup("a%rb"), "a\nb")

    def test_capital_r_becomes_newline(self) -> None:
        self.assertEqual(normalize_mush_markup("a%Rb"), "a\nb")

    def test_percent_t_becomes_tab(self) -> None:
        self.assertEqual(normalize_mush_markup("a%tb"), "a\tb")

    def test_capital_t_becomes_tab(self) -> None:
        self.assertEqual(normalize_mush_markup("a%Tb"), "a\tb")

    def test_percent_b_becomes_non_breaking_space(self) -> None:
        self.assertEqual(normalize_mush_markup("a%bb"), "a\u00a0b")

    def test_capital_b_becomes_non_breaking_space(self) -> None:
        self.assertEqual(normalize_mush_markup("a%Bb"), "a\u00a0b")

    def test_double_percent_escapes_to_literal_percent(self) -> None:
        self.assertEqual(normalize_mush_markup("100%%ready"), "100%ready")

    def test_escaped_r_is_literal_not_newline(self) -> None:
        self.assertEqual(normalize_mush_markup("%%r"), "%r")

    def test_unknown_percent_sequence_passes_through(self) -> None:
        self.assertEqual(normalize_mush_markup("a %s b %d c"), "a %s b %d c")

    def test_trailing_lone_percent_preserved(self) -> None:
        self.assertEqual(normalize_mush_markup("50%"), "50%")

    def test_mixed_line(self) -> None:
        self.assertEqual(
            normalize_mush_markup("A man.%rHe wears a hat.%tCrisp."),
            "A man.\nHe wears a hat.\tCrisp.",
        )

    def test_no_percent_is_unchanged(self) -> None:
        self.assertEqual(normalize_mush_markup("plain text"), "plain text")

    def test_empty_string(self) -> None:
        self.assertEqual(normalize_mush_markup(""), "")

"""These replace regexes, so the equivalence has to be shown, not assumed."""

from django.test import SimpleTestCase

from commands.utils.argsplit import (
    split_bracketed_prefix,
    split_on_keyword,
    split_possessive,
    strip_leading_word,
)


class SplitOnKeywordTests(SimpleTestCase):
    def test_splits_at_the_first_occurrence(self) -> None:
        assert split_on_keyword("a coin from the pouch from hell", "from") == (
            "a coin",
            "the pouch from hell",
        )

    def test_is_case_insensitive(self) -> None:
        assert split_on_keyword("coin FROM pouch", "from") == ("coin", "pouch")

    def test_requires_surrounding_whitespace(self) -> None:
        assert split_on_keyword("comfrompouch", "from") is None
        assert split_on_keyword("fromage cheese", "from") is None

    def test_absent_keyword_is_no_match(self) -> None:
        assert split_on_keyword("just an item", "from") is None

    def test_empty_side_is_no_match(self) -> None:
        assert split_on_keyword("from pouch", "from") is None
        assert split_on_keyword("coin from ", "from") is None

    def test_trims_both_halves(self) -> None:
        assert split_on_keyword("  coin   from   pouch  ", "from") == ("coin", "pouch")


class StripLeadingWordTests(SimpleTestCase):
    def test_returns_the_remainder(self) -> None:
        assert strip_leading_word("outfit my finery", "outfit") == "my finery"

    def test_is_case_insensitive(self) -> None:
        assert strip_leading_word("OUTFIT my finery", "outfit") == "my finery"

    def test_rejects_a_longer_word_with_the_same_prefix(self) -> None:
        assert strip_leading_word("outfitter shop", "outfit") is None

    def test_rejects_a_bare_word_with_no_remainder(self) -> None:
        assert strip_leading_word("outfit", "outfit") is None
        assert strip_leading_word("outfit   ", "outfit") is None


class SplitPossessiveTests(SimpleTestCase):
    """``split_possessive`` isolates an owner from the item drilled into."""

    def test_splits_a_plain_possessive(self):
        self.assertEqual(split_possessive("alice's sword"), ("alice", "sword"))

    def test_is_case_insensitive_on_the_s(self):
        self.assertEqual(split_possessive("ALICE'S SWORD"), ("ALICE", "SWORD"))

    def test_splits_on_the_first_apostrophe(self):
        self.assertEqual(split_possessive("alice's friend's sword"), ("alice", "friend's sword"))

    def test_rejects_a_contraction_without_a_following_space(self):
        self.assertIsNone(split_possessive("alice'sword"))

    def test_rejects_a_possessive_with_no_item(self):
        self.assertIsNone(split_possessive("alice's   "))

    def test_rejects_a_leading_apostrophe(self):
        self.assertIsNone(split_possessive("'s sword"))

    def test_rejects_a_string_with_no_apostrophe(self):
        self.assertIsNone(split_possessive("alice sword"))

    def test_rejects_a_non_possessive_apostrophe(self):
        self.assertIsNone(split_possessive("rock'n roll"))


class SplitBracketedPrefixTests(SimpleTestCase):
    """``split_bracketed_prefix`` peels a leading "(tag) rest" off a line."""

    def test_splits_a_leading_tag(self):
        self.assertEqual(
            split_bracketed_prefix("(elvish) hello there", "(", ")"), ("elvish", "hello there")
        )

    def test_strips_whitespace_inside_the_tag(self):
        self.assertEqual(split_bracketed_prefix("(  elvish ) hi", "(", ")"), ("elvish", "hi"))

    def test_rejects_a_line_that_does_not_open_with_the_tag(self):
        self.assertIsNone(split_bracketed_prefix("hello (elvish)", "(", ")"))

    def test_rejects_an_unclosed_tag(self):
        self.assertIsNone(split_bracketed_prefix("(elvish hello", "(", ")"))

    def test_rejects_an_empty_tag(self):
        self.assertIsNone(split_bracketed_prefix("() hello", "(", ")"))

    def test_rejects_a_tag_with_no_speech_after_it(self):
        self.assertIsNone(split_bracketed_prefix("(elvish)   ", "(", ")"))

    def test_rejects_a_closer_not_followed_by_whitespace(self):
        self.assertIsNone(split_bracketed_prefix("(elvish)hello", "(", ")"))

    def test_rejects_a_tag_longer_than_the_cap(self):
        self.assertIsNone(split_bracketed_prefix(f"({'x' * 51}) hi", "(", ")"))

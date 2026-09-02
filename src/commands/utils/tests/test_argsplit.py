"""These replace regexes, so the equivalence has to be shown, not assumed."""

from django.test import SimpleTestCase

from commands.utils.argsplit import split_on_keyword, strip_leading_word


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

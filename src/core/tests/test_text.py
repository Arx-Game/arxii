"""The shared indefinite-article helper (#4858)."""

from django.test import SimpleTestCase

from core.text import with_indefinite_article


class WithIndefiniteArticleTests(SimpleTestCase):
    def test_a_consonant_takes_a(self) -> None:
        self.assertEqual(with_indefinite_article("rapier"), "a rapier")

    def test_a_vowel_takes_an_whatever_its_case(self) -> None:
        self.assertEqual(with_indefinite_article("axe"), "an axe")
        self.assertEqual(with_indefinite_article("Iron Maul"), "an Iron Maul")

    def test_blank_stays_blank(self) -> None:
        self.assertEqual(with_indefinite_article(""), "")

"""Tests for parse_coppers (#1909): telnet/UI-edge amount parsing to coppers."""

from django.test import TestCase

from world.currency.constants import parse_coppers


class ParseCoppersTests(TestCase):
    def test_parses_silver_and_copper(self):
        assert parse_coppers("3s 5c") == 35

    def test_parses_gold_only(self):
        assert parse_coppers("2g") == 200

    def test_parses_copper_only(self):
        assert parse_coppers("35c") == 35

    def test_parses_all_three_denominations(self):
        assert parse_coppers("1g 2s 3c") == 123

    def test_tokens_in_any_order(self):
        assert parse_coppers("3c 1g 2s") == 123

    def test_case_insensitive(self):
        assert parse_coppers("1G 2S 3C") == 123

    def test_none_for_item_name(self):
        assert parse_coppers("sword") is None

    def test_none_for_empty_string(self):
        assert parse_coppers("") is None

    def test_none_for_item_with_count(self):
        assert parse_coppers("3 swords") is None

    def test_none_for_duplicated_unit(self):
        assert parse_coppers("1g 2g") is None

    def test_none_for_negative_amount(self):
        assert parse_coppers("-3c") is None

    def test_none_for_zero_total(self):
        assert parse_coppers("0c") is None

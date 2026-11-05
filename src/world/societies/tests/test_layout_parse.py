"""The layout grammar (#4983 slice 2, #4986): one line per rung, fields split on
``|``, children indented by two spaces; every error names its line."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.societies.houses.constants import TitleStation, TitleTier
from world.societies.houses.layout import LayoutError, Range, parse_layout

SPEC_EXAMPLE = """
realm | counties 2-6 | baronies 1-4 | capital x1.5
kingdom Umbros | seat Umbros | duchies 5 | capital x2
kingdom East Cinderus | titular | lore The Daeva remnant that once ruled the east.
  duchy Ashfall | counties 3
  duchy Embermarch | sworn Cinderus
kingdom | potential
"""


class ParseLayoutTests(SimpleTestCase):
    def test_parses_the_spec_example(self) -> None:
        layout = parse_layout(SPEC_EXAMPLE)
        assert layout.defaults.counties == Range(2, 6)
        assert layout.defaults.baronies == Range(1, 4)
        assert layout.defaults.capital == 1.5
        assert layout.defaults.duchies is None
        assert [k.name for k in layout.kingdoms] == ["Umbros", "East Cinderus", ""]
        umbros, east, slot = layout.kingdoms
        assert umbros.seat == "Umbros"
        assert umbros.duchies == Range(5, 5)
        assert umbros.capital == 2.0
        assert umbros.station == TitleStation.SEATED
        assert east.station == TitleStation.TITULAR
        assert east.lore == "The Daeva remnant that once ruled the east."
        assert [c.name for c in east.children] == ["Ashfall", "Embermarch"]
        assert east.children[0].tier == TitleTier.DUCHY
        assert east.children[0].counties == Range(3, 3)
        assert east.children[1].sworn == "Cinderus"
        assert slot.station == TitleStation.POTENTIAL
        assert slot.line_no == 7

    def test_charters_claims_and_claimability_words(self) -> None:
        layout = parse_layout(
            "kingdom Old Luxen | titular | chartered Brittany, Anjou"
            " | claimed by Sharlotte | basis The exiled queen\n"
            "  duchy Brittany | held\n"
            "  duchy Anjou | claimable | baronies 2\n"
        )
        crown = layout.kingdoms[0]
        assert crown.chartered == ["Brittany", "Anjou"]
        assert crown.claims == [("Sharlotte", "The exiled queen")]
        assert crown.children[0].claimable is False
        assert crown.children[1].claimable is True
        assert crown.children[1].baronies == Range(2, 2)
        assert crown.children[0].claimable is not None

    def test_held_on_a_kingdom_line_is_the_seated_no_op(self) -> None:
        layout = parse_layout("kingdom Republic of Luxen | held | duchies 8\n")
        assert layout.kingdoms[0].station == TitleStation.SEATED
        assert layout.kingdoms[0].duchies == Range(8, 8)

    def test_comments_and_blank_lines_are_skipped(self) -> None:
        layout = parse_layout("# the north\n\nkingdom Umbros\n")
        assert [k.name for k in layout.kingdoms] == ["Umbros"]
        assert layout.kingdoms[0].line_no == 3

    def test_errors_name_the_line(self) -> None:
        cases = {
            "  duchy Orphan\n": "line 1: ",
            "kingdom Umbros | mystery word\n": "line 1: ",
            "kingdom Umbros | duchies 5-2\n": "line 1: ",
            "kingdom Umbros | counties 0\n": "line 1: ",
            "realm | capital x1\nrealm | capital x2\n": "line 2: ",
            "kingdom | duchies 2\n": "line 1: ",
            "kingdom Umbros\n  duchy Ash | titular\n": "line 2: ",
            "kingdom Umbros | capital two\n": "line 1: ",
        }
        for text, prefix in cases.items():
            with self.assertRaises(LayoutError, msg=text) as caught:
                parse_layout(text)
            assert str(caught.exception).startswith(prefix), (text, str(caught.exception))
            assert caught.exception.line_no == int(prefix.split()[1].rstrip(":"))

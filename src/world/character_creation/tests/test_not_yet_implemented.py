"""A choice with no content behind it is marked, never hidden (#5197).

On production's content four of the five Paths had no gift a new character could take
and two Beginnings had no route, and character creation offered them all the same; a
player found out several stages later. The owner's ruling (2026-11-18): do not remove
them, mark them "Not Yet Implemented", and let the mark go by itself when the content is
written. These tests read the three lists as the page does and then author the missing
content the way staff would, to see the mark go with no code in between.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from web.admin.tuning import required_content as rc
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    OriginTemplateFactory,
)
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.cg_catalog import cg_gift_offerings, get_gift_options

PATHS = "/api/character-creation/paths/"
TRADITIONS = "/api/character-creation/traditions/"
BEGINNINGS = "/api/character-creation/beginnings/"


def _marks(rows: list[dict]) -> dict[str, bool]:
    return {row["name"]: row["not_yet_implemented"] for row in rows}


class NotYetImplementedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.template = get_standalone_cast_template()
        cls.wardens = TraditionFactory(name="Wardens of the Ford")
        cls.keepers = TraditionFactory(name="Keepers of the Weir")
        cls.reeds = PathFactory(name="Path of Reeds", stage=PathStage.PROSPECT, is_active=True)
        cls.stones = PathFactory(name="Path of Stones", stage=PathStage.PROSPECT, is_active=True)
        cls.gift = GiftFactory(name="River Tongue")
        # Path of Reeds holds a technique every Tradition may take.
        cls.reeds_grant = PathGiftGrantFactory(path=cls.reeds, gift=cls.gift)
        cls.reeds_grant.starter_techniques.add(
            TechniqueFactory(gift=cls.gift, action_template=cls.template)
        )
        # Path of Stones has a list for the gift and nothing on it yet.
        cls.stones_grant = PathGiftGrantFactory(path=cls.stones, gift=cls.gift)
        cls.ford = BeginningsFactory(name="Ford-born")
        BeginningTraditionFactory(beginning=cls.ford, tradition=cls.wardens)
        BeginningTraditionFactory(beginning=cls.ford, tradition=cls.keepers)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _paths(self, **params) -> dict[str, bool]:
        return _marks(self.client.get(PATHS, params).json())

    def _traditions(self, **params) -> dict[str, bool]:
        params.setdefault("beginning_id", self.ford.id)
        return _marks(self.client.get(TRADITIONS, params).json())

    def test_a_path_with_no_gift_is_marked_and_still_listed(self) -> None:
        marks = self._paths()

        self.assertEqual(marks, {"Path of Reeds": False, "Path of Stones": True})

    def test_the_mark_goes_when_a_technique_is_put_on_the_paths_list(self) -> None:
        self.assertTrue(self._paths()["Path of Stones"])

        self.stones_grant.starter_techniques.add(
            TechniqueFactory(gift=self.gift, action_template=self.template)
        )

        self.assertFalse(self._paths()["Path of Stones"])

    def test_a_path_is_marked_for_a_beginning_whose_traditions_are_shut_out(self) -> None:
        # The only technique on Path of Stones is one the Keepers keep to themselves.
        kept = TechniqueFactory(gift=self.gift, action_template=self.template)
        self.stones_grant.starter_techniques.add(kept)
        TraditionGiftGrantFactory(tradition=self.keepers, gift=self.gift).special_techniques.add(
            kept
        )
        wardens_only = BeginningsFactory(name="Warden-raised")
        BeginningTraditionFactory(beginning=wardens_only, tradition=self.wardens)

        # Some Tradition has a gift there, so the bare list does not mark it.
        self.assertFalse(self._paths()["Path of Stones"])
        # The Ford-born may be Keepers; the Warden-raised may not.
        self.assertFalse(self._paths(beginning_id=self.ford.id)["Path of Stones"])
        self.assertTrue(self._paths(beginning_id=wardens_only.id)["Path of Stones"])

    def test_a_tradition_is_marked_on_the_path_it_has_no_gift_for(self) -> None:
        kept = TechniqueFactory(gift=self.gift, action_template=self.template)
        self.stones_grant.starter_techniques.add(kept)
        TraditionGiftGrantFactory(tradition=self.keepers, gift=self.gift).special_techniques.add(
            kept
        )

        on_stones = self._traditions(path_id=self.stones.id)
        on_reeds = self._traditions(path_id=self.reeds.id)

        self.assertEqual(on_stones, {"Wardens of the Ford": True, "Keepers of the Weir": False})
        self.assertEqual(on_reeds, {"Wardens of the Ford": False, "Keepers of the Weir": False})

    def test_with_no_path_named_a_tradition_is_marked_only_when_no_path_has_a_gift(self) -> None:
        self.assertEqual(
            self._traditions(), {"Wardens of the Ford": False, "Keepers of the Weir": False}
        )

        self.reeds_grant.starter_techniques.clear()

        self.assertEqual(
            self._traditions(), {"Wardens of the Ford": True, "Keepers of the Weir": True}
        )

    def test_the_marks_agree_with_the_gift_list_the_stage_shows(self) -> None:
        """An unmarked pairing has a gift to pick and a marked one has none."""
        for path in (self.reeds, self.stones):
            marks = self._traditions(path_id=path.id)
            for tradition in (self.wardens, self.keepers):
                with self.subTest(path=path.name, tradition=tradition.name):
                    self.assertEqual(marks[tradition.name], not get_gift_options(tradition, path))

    def test_a_beginning_with_no_active_route_is_marked_and_still_listed(self) -> None:
        routed = BeginningsFactory(name="Hold-born", starting_area=self.ford.starting_area)
        OriginTemplateFactory(beginning=routed, is_active=True)
        retired = BeginningsFactory(name="Road-born", starting_area=self.ford.starting_area)
        OriginTemplateFactory(beginning=retired, is_active=False)

        marks = _marks(
            self.client.get(BEGINNINGS, {"starting_area": self.ford.starting_area_id}).json()
        )

        self.assertEqual(marks, {"Ford-born": True, "Hold-born": False, "Road-born": True})

    def test_the_mark_goes_when_a_route_is_written_for_the_beginning(self) -> None:
        params = {"starting_area": self.ford.starting_area_id}
        self.assertTrue(_marks(self.client.get(BEGINNINGS, params).json())["Ford-born"])

        OriginTemplateFactory(beginning=self.ford, is_active=True)

        self.assertFalse(_marks(self.client.get(BEGINNINGS, params).json())["Ford-born"])

    def test_reading_the_catalog_costs_the_same_queries_whatever_its_size(self) -> None:
        """The read behind the marks is one fixed set of queries, not one per path or gift."""
        cg_gift_offerings()  # the first read of a process fills its own caches
        with CaptureQueriesContext(connection) as before:
            small = cg_gift_offerings()
        for index in range(4):
            path = PathFactory(
                name=f"Path of Fords {index}", stage=PathStage.PROSPECT, is_active=True
            )
            gift = GiftFactory(name=f"Ford Gift {index}")
            PathGiftGrantFactory(path=path, gift=gift).starter_techniques.add(
                TechniqueFactory(gift=gift, action_template=self.template)
            )
            TraditionFactory(name=f"Fordwrights {index}")

        with CaptureQueriesContext(connection) as after:
            large = cg_gift_offerings()

        self.assertEqual(len(small.paths), 2)
        self.assertEqual(len(large.paths), 6)
        self.assertGreater(len(large.pairs), len(small.pairs))
        self.assertEqual(len(after), len(before))


class BeginningsRouteDashboardRowTests(TestCase):
    """The Required content dashboard lists the Beginnings the page marks (#5197)."""

    def _row(self) -> rc.ProbeResult:
        dependency = next(d for d in rc._declarations() if d.key == "beginnings-have-a-route")
        return dependency.probe.resolve(None)

    def test_the_row_names_each_beginning_with_no_active_route_and_clears(self) -> None:
        ford = BeginningsFactory(name="Ford-born")
        hold = BeginningsFactory(name="Hold-born", starting_area=ford.starting_area)
        OriginTemplateFactory(beginning=hold, is_active=True)

        result = self._row()

        self.assertFalse(result.present)
        self.assertEqual(result.missing, (f"{ford.starting_area.name} / Ford-born",))

        OriginTemplateFactory(beginning=ford, is_active=True)

        self.assertTrue(self._row().present)

    def test_the_row_links_to_the_upbringing_admin(self) -> None:
        dependency = next(d for d in rc._declarations() if d.key == "beginnings-have-a-route")

        self.assertEqual(dependency.tier, rc.DependencyTier.REQUIRED)
        self.assertEqual(dependency.admin_model, "OriginTemplate")

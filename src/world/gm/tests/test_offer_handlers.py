"""Unit tests for GMSummonPendingHandler, the telnet accept/decline face (#3071).

Complements ``actions.tests.test_gm_summon_actions`` (the action-level journey);
these tests cover the offer-registry handler shape itself: ``pending_for``,
``describe``, and that ``accept``/``decline`` reach the same target-side actions
the web dispatch endpoint uses.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.models import GMSummonOffer
from world.gm.offer_handlers import GMSummonPendingHandler
from world.gm.services import offer_gm_summon
from world.scenes.factories import SceneFactory


def _room(*, db_key: str) -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


class GMSummonPendingHandlerTests(TestCase):
    def setUp(self) -> None:
        self.gm_room = _room(db_key="HandlerGMRoom")
        self.other_room = _room(db_key="HandlerElsewhere")
        self.scene = SceneFactory(location=self.gm_room, name="A Quiet Word")

        self.target = CharacterFactory(db_key="HandlerTarget", location=self.other_room)
        self.target_sheet = CharacterSheetFactory(character=self.target)

        from world.areas.services import get_room_profile

        self.room_profile = get_room_profile(self.gm_room)
        self.handler = GMSummonPendingHandler()

    def test_pending_for_returns_none_without_an_offer(self) -> None:
        self.assertIsNone(self.handler.pending_for(self.target_sheet))

    def test_pending_for_returns_the_offer(self) -> None:
        offer_gm_summon(
            None,
            self.target_sheet,
            room=self.room_profile,
            scene=self.scene,
            gm_display_name="Story Weaver",
        )
        pending = self.handler.pending_for(self.target_sheet)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.target_sheet_id, self.target_sheet.pk)

    def test_describe_names_the_gm_and_scene_only(self) -> None:
        offer_gm_summon(
            None,
            self.target_sheet,
            room=self.room_profile,
            scene=self.scene,
            gm_display_name="Story Weaver",
        )
        pending = self.handler.pending_for(self.target_sheet)
        description = self.handler.describe(pending)
        self.assertIn("Story Weaver", description)
        self.assertIn("A Quiet Word", description)

    def test_accept_moves_the_target_and_clears_the_offer(self) -> None:
        offer_gm_summon(
            None,
            self.target_sheet,
            room=self.room_profile,
            scene=self.scene,
            gm_display_name="Story Weaver",
        )
        pending = self.handler.pending_for(self.target_sheet)

        self.handler.accept(pending, self.target, "")

        self.target.refresh_from_db()
        self.assertEqual(self.target.db_location_id, self.gm_room.pk)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target_sheet).exists())

    def test_decline_clears_the_offer_without_moving(self) -> None:
        offer_gm_summon(
            None,
            self.target_sheet,
            room=self.room_profile,
            scene=self.scene,
            gm_display_name="Story Weaver",
        )
        pending = self.handler.pending_for(self.target_sheet)

        self.handler.decline(pending, self.target)

        self.target.refresh_from_db()
        self.assertEqual(self.target.db_location_id, self.other_room.pk)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target_sheet).exists())

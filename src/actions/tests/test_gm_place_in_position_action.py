"""Tests for GMPlaceInPositionAction — GM/staff unchecked placement (#2005).

Covers the gate precedent shared with ``_actor_may_gm_battle``
(``actions/definitions/battles.py``): staff always passes; otherwise the
actor's account must be the GM of the active scene in the actor's room.
No active scene means only staff may place. ``place_in_position`` is the
unchecked primitive (bypasses entry-kind + mobility), so staff/GM placement
succeeds even at an ELEVATED position.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.positioning import GMPlaceInPositionAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import position_of
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _make_room(label: str) -> object:
    from evennia import create_object

    return create_object("typeclasses.rooms.Room", key=label, nohome=True)


def _make_actor_with_account(db_key: str, room: object, account: object) -> object:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char


class GMPlaceInPositionActionTests(TestCase):
    """Gate + execution behavior for gm_place_in_position."""

    def setUp(self) -> None:
        self.room = _make_room("GMPlaceRoom")
        self.throne = PositionFactory(room=self.room, name="throne", kind=PositionKind.PRIMARY)
        self.sky = PositionFactory(room=self.room, name="sky", kind=PositionKind.ELEVATED)

        self.staff_account = AccountFactory(username="gmplace_staff", is_staff=True)
        self.staff_actor = _make_actor_with_account(
            "gmplace_staff_actor", self.room, self.staff_account
        )

        self.gm_account = AccountFactory(username="gmplace_gm")
        self.gm_actor = _make_actor_with_account("gmplace_gm_actor", self.room, self.gm_account)

        self.player_account = AccountFactory(username="gmplace_player")
        self.player_actor = _make_actor_with_account(
            "gmplace_player_actor", self.room, self.player_account
        )

        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

        self.npc = CharacterFactory(db_key="gmplace_npc", location=self.room)

    def test_staff_can_place_at_any_kind_including_elevated(self) -> None:
        result = GMPlaceInPositionAction().run(
            self.staff_actor,
            position_id=self.sky.pk,
            target_object_id=self.npc.pk,
        )
        self.assertTrue(result.success, result.message)
        current = position_of(self.npc)
        self.assertIsNotNone(current)
        self.assertEqual(current.pk, self.sky.pk)

    def test_scene_gm_can_place(self) -> None:
        result = GMPlaceInPositionAction().run(
            self.gm_actor,
            position_id=self.throne.pk,
            target_object_id=self.npc.pk,
        )
        self.assertTrue(result.success, result.message)
        current = position_of(self.npc)
        self.assertIsNotNone(current)
        self.assertEqual(current.pk, self.throne.pk)

    def test_plain_player_denied(self) -> None:
        result = GMPlaceInPositionAction().run(
            self.player_actor,
            position_id=self.throne.pk,
            target_object_id=self.npc.pk,
        )
        self.assertFalse(result.success)
        self.assertIsNone(position_of(self.npc))

    def test_non_co_located_target_denied(self) -> None:
        other_room = _make_room("GMPlaceOtherRoom")
        elsewhere_npc = CharacterFactory(db_key="gmplace_elsewhere_npc", location=other_room)

        result = GMPlaceInPositionAction().run(
            self.staff_actor,
            position_id=self.throne.pk,
            target_object_id=elsewhere_npc.pk,
        )
        self.assertFalse(result.success)
        self.assertIsNone(position_of(elsewhere_npc))

    def test_no_active_scene_staff_only(self) -> None:
        bare_room = _make_room("GMPlaceBareRoom")
        bare_position = PositionFactory(room=bare_room, name="bare", kind=PositionKind.PRIMARY)

        bare_staff_account = AccountFactory(username="gmplace_bare_staff_acct", is_staff=True)
        staff_actor = _make_actor_with_account("gmplace_bare_staff", bare_room, bare_staff_account)
        gm_account = AccountFactory(username="gmplace_bare_gm_acct")
        gm_actor = _make_actor_with_account("gmplace_bare_gm_actor", bare_room, gm_account)
        bare_npc = CharacterFactory(db_key="gmplace_bare_npc", location=bare_room)

        # No active Scene exists in bare_room, so even a would-be GM is denied.
        denied = GMPlaceInPositionAction().run(
            gm_actor,
            position_id=bare_position.pk,
            target_object_id=bare_npc.pk,
        )
        self.assertFalse(denied.success)
        self.assertIsNone(position_of(bare_npc))

        allowed = GMPlaceInPositionAction().run(
            staff_actor,
            position_id=bare_position.pk,
            target_object_id=bare_npc.pk,
        )
        self.assertTrue(allowed.success, allowed.message)
        current = position_of(bare_npc)
        self.assertIsNotNone(current)
        self.assertEqual(current.pk, bare_position.pk)

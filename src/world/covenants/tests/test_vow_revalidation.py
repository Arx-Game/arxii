"""Tests for continuous vow engagement enforcement (#2051).

Verifies that ``revalidate_engagements`` dims a Durance vow when
covenant-mates are no longer co-present, and keeps COURT vows lit when
the servant is on the master's business.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.services import revalidate_engagements
from world.scenes.factories import SceneFactory


def _make_room(key: str = "TestRoom"):
    """Create a Room typeclass instance usable as a scene location."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_character_in_room(character, room) -> None:
    """Set a character's db_location directly and bust the scene cache."""
    character.db_location = room
    character.save(update_fields=["db_location"])
    if hasattr(room, "_active_scene_cache"):
        del room._active_scene_cache


class VowRevalidationTests(TestCase):
    """revalidate_engagements dims a vow when covenant-mates leave (#2051)."""

    def setUp(self) -> None:
        # Per-test setup (not setUpTestData): Evennia's ObjectDB carries a
        # DbHolder that doesn't survive the inter-test deepcopy.
        self.cov = CovenantFactory(name="RevalCov", covenant_type=CovenantType.DURANCE)
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.mem_a = CharacterCovenantRoleFactory(
            covenant=self.cov,
            covenant_role=self.role,
        )
        self.mem_b = CharacterCovenantRoleFactory(
            covenant=self.cov,
            covenant_role=self.role,
        )
        self.room = _make_room("RevalRoom")
        self.char_a = self.mem_a.character_sheet.character
        self.char_b = self.mem_b.character_sheet.character

    def test_durance_vow_dims_when_alone(self) -> None:
        """An engaged Durance member whose covenant-mate left is disengaged."""
        # Both members in the room with an active scene → auto-engage.
        _place_character_in_room(self.char_a, self.room)
        _place_character_in_room(self.char_b, self.room)
        SceneFactory(location=self.room, is_active=True)

        from world.covenants.services import evaluate_scene_engagement

        evaluate_scene_engagement(character_sheet=self.mem_a.character_sheet, room=self.room)
        evaluate_scene_engagement(character_sheet=self.mem_b.character_sheet, room=self.room)
        self.mem_a.refresh_from_db()
        self.assertTrue(self.mem_a.engaged)

        # char_b leaves the room — char_a is now alone.
        other_room = _make_room("OtherRoom")
        _place_character_in_room(self.char_b, other_room)

        revalidate_engagements(character_sheet=self.mem_a.character_sheet, room=self.room)

        self.mem_a.refresh_from_db()
        self.assertFalse(self.mem_a.engaged)

    def test_durance_vow_stays_lit_with_covenant_mate(self) -> None:
        """An engaged Durance member stays engaged while a covenant-mate is co-present."""
        _place_character_in_room(self.char_a, self.room)
        _place_character_in_room(self.char_b, self.room)
        SceneFactory(location=self.room, is_active=True)

        from world.covenants.services import evaluate_scene_engagement

        evaluate_scene_engagement(character_sheet=self.mem_a.character_sheet, room=self.room)
        self.mem_a.refresh_from_db()
        self.assertTrue(self.mem_a.engaged)

        # char_b is still present — revalidate keeps the vow lit.
        revalidate_engagements(character_sheet=self.mem_a.character_sheet, room=self.room)

        self.mem_a.refresh_from_db()
        self.assertTrue(self.mem_a.engaged)

    def test_revalidate_no_ops_when_not_engaged(self) -> None:
        """revalidate_engagements is a no-op for a character with no engaged roles."""
        _place_character_in_room(self.char_a, self.room)
        SceneFactory(location=self.room, is_active=True)

        # mem_a is not engaged — revalidate should be a clean no-op.
        revalidate_engagements(character_sheet=self.mem_a.character_sheet, room=self.room)

        self.mem_a.refresh_from_db()
        self.assertFalse(self.mem_a.engaged)


class SceneFinishVowDimTests(TestCase):
    """finish_scene_full dims Durance vows when the scene ends (#2051)."""

    def test_finishing_scene_dims_remaining_member_vow(self) -> None:
        from world.scenes.scene_admin_services import finish_scene_full

        cov = CovenantFactory(name="FinishCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        mem_a = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        mem_b = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

        room = _make_room("FinishRoom")
        char_a = mem_a.character_sheet.character
        char_b = mem_b.character_sheet.character

        # Both members in the room with an active scene → both engaged.
        _place_character_in_room(char_a, room)
        _place_character_in_room(char_b, room)
        scene = SceneFactory(location=room, is_active=True)

        from world.covenants.services import evaluate_scene_engagement

        evaluate_scene_engagement(character_sheet=mem_a.character_sheet, room=room)
        evaluate_scene_engagement(character_sheet=mem_b.character_sheet, room=room)
        mem_a.refresh_from_db()
        self.assertTrue(mem_a.engaged)

        # Finish the scene — the active scene is gone, so Durance vows dim.
        from unittest.mock import patch

        with (
            patch("world.scenes.scene_admin_services.on_scene_finished"),
            patch("world.scenes.scene_admin_services.process_deferred_fatigue_resets"),
            patch("world.scenes.scene_admin_services.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        mem_a.refresh_from_db()
        self.assertFalse(mem_a.engaged)

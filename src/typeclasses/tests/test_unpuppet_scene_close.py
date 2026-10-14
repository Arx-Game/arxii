"""Tests for Character.at_post_unpuppet's scene auto-close wiring (#1361)."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory


class UnpuppetFinishesEmptySceneTests(TestCase):
    _PATCH_BASE = "world.scenes.scene_admin_services"

    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(room=self.room, is_active=True)
        self.character = CharacterFactory(db_key="Solo", location=self.room)
        CharacterSheetFactory(character=self.character)

    def test_another_open_window_does_not_close_scene(self):
        """A character still played in another window stays on the grid (#3812),
        so the scene-close check must not run at all."""
        self.character.sessions.all = mock.Mock(return_value=[mock.Mock()])

        with mock.patch(
            "world.scenes.round_services.maybe_finish_empty_scene"
        ) as mock_maybe_finish:
            self.character.at_post_unpuppet(session=mock.Mock())

        mock_maybe_finish.assert_not_called()
        assert self.character.location == self.room
        self.scene.refresh_from_db()
        assert self.scene.is_finished is False

    def test_real_relocation_finishes_the_scene_end_to_end(self):
        """No mocking of the hook at all: a freshly-created CharacterFactory has
        zero attached sessions, so the last-session-out step (``_leave_the_grid``,
        #4336) relocates for real."""
        with (
            mock.patch(f"{self._PATCH_BASE}.on_scene_finished"),
            mock.patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            mock.patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            self.character.at_post_unpuppet()

        assert self.character.location is None
        assert self.character.db.prelogout_location.pk == self.room.pk
        self.scene.refresh_from_db()
        assert self.scene.is_finished is True

    def test_real_relocation_with_another_pc_present_keeps_scene_active(self):
        """Disconnect, not alone: real relocation still happens (this PC leaves
        the room), but another PC remains — the scene must stay active."""
        other_pc = CharacterFactory(db_key="Staying", location=self.room)
        CharacterSheetFactory(character=other_pc)

        with (
            mock.patch(f"{self._PATCH_BASE}.on_scene_finished"),
            mock.patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            mock.patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            self.character.at_post_unpuppet()

        assert self.character.location is None  # this character still relocated
        self.scene.refresh_from_db()
        assert self.scene.is_finished is False  # but the scene stays open


class UnpuppetPausesCombatBattleMissionTests(TestCase):
    """Character.at_post_unpuppet also pauses live CombatEncounter/Battle/
    MissionInstance participation on disconnect (#1899)."""

    def setUp(self) -> None:
        # A location is required: at_post_unpuppet captures `origin = self.location`
        # before leaving the grid, and only runs the guarded block (scene-close +
        # pause calls) `if origin is not None and self.location is None` — i.e. only
        # when the "last session out" relocation (_leave_the_grid) actually fires. A
        # character created with no location at all (origin already None) never
        # takes that branch, so the pause calls would never run regardless of
        # wiring. Mirrors the room setup `UnpuppetFinishesEmptySceneTests` uses above.
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.character = CharacterFactory(db_key="PauseTester", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_disconnect_pauses_combat_encounter(self) -> None:
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory

        encounter = CombatEncounterFactory()
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )

        self.character.at_post_unpuppet()

        encounter.refresh_from_db()
        assert encounter.is_paused is True

    def test_disconnect_pauses_small_battle(self) -> None:
        from world.battles.constants import BattleParticipantStatus
        from world.battles.factories import (
            BattleFactory,
            BattleParticipantFactory,
            BattleSideFactory,
        )

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=self.sheet,
            status=BattleParticipantStatus.ACTIVE,
        )

        self.character.at_post_unpuppet()

        battle.refresh_from_db()
        assert battle.is_paused is True

    def test_disconnect_pauses_mission_instance(self) -> None:
        from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory

        instance = MissionInstanceFactory()
        MissionParticipantFactory(instance=instance, character=self.character.sheet_data)

        self.character.at_post_unpuppet()

        instance.refresh_from_db()
        assert instance.is_paused is True

    def test_disconnect_with_no_combat_battle_mission_does_not_raise(self) -> None:
        """No active combat/battle/mission participation (but sheet_data exists)
        — the three maybe_pause_* calls are each individually a no-op; must not
        raise. Does NOT exercise the `sheet_data is None` guard branch — see
        `test_disconnect_with_no_character_sheet_does_not_raise` for that."""
        self.character.at_post_unpuppet()  # No participation rows anywhere — must not raise.

    def test_disconnect_with_no_character_sheet_does_not_raise(self) -> None:
        """Regression (#1899 whole-branch review): a sheet-less character (no
        CharacterSheet at all) must short-circuit at the
        `getattr(self, "sheet_data", None) is None` guard in
        Character.at_post_unpuppet before any maybe_pause_* call — must not raise."""
        sheetless = CharacterFactory(db_key="NoSheet", location=self.room)

        sheetless.at_post_unpuppet()
